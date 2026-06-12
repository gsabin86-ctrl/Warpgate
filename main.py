from __future__ import annotations

import asyncio
import os
import re
import signal
import socket
import subprocess
import time
import wave
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

import httpx
from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

OLLAMA_BIN = "/usr/local/bin/ollama"
SHARED_MODELS_DIR = "/usr/share/ollama/.ollama/models"
INSTANCES_DIR = Path("/tmp/ollama-instances")
DISCOVERY_RANGE = range(11434, 11500)

VOICE_ROOT = Path(os.environ.get("WARPGATE_VOICE_ROOT", "/home/greg/voice-arsenal"))
WHISPER_BIN = Path(os.environ.get("WARPGATE_WHISPER_BIN", str(VOICE_ROOT / "whisper.cpp/build/bin/whisper-cli")))
WHISPER_MODEL = Path(os.environ.get("WARPGATE_WHISPER_MODEL", str(VOICE_ROOT / "whisper-models/ggml-base.en.bin")))
PIPER_BIN = Path(os.environ.get("WARPGATE_PIPER_BIN", str(VOICE_ROOT / "piper/piper/piper")))
PIPER_VOICE = Path(os.environ.get("WARPGATE_PIPER_VOICE", str(VOICE_ROOT / "piper-voices/en_US-amy-medium.onnx")))
PIPER_VOICE_DIR = VOICE_ROOT / "piper-voices"
WHISPER_MODEL_DIR = VOICE_ROOT / "whisper-models"
VOICE_RUNTIME_DIR = Path(os.environ.get("WARPGATE_VOICE_RUNTIME_DIR", "/tmp/warpgate-voice"))
VOICE_TTS_DIR = VOICE_RUNTIME_DIR / "tts"
VOICE_STT_DIR = VOICE_RUNTIME_DIR / "stt"
MAX_TTS_CHARS = 2000
MAX_AUDIO_UPLOAD_BYTES = 25 * 1024 * 1024
VOICE_AUDIO_RE = re.compile(r"^[A-Za-z0-9_.-]+\.wav$")
AUDIO_UPLOAD_RE = re.compile(r"^[A-Za-z0-9_.-]+\.(wav|mp3|ogg|flac|webm)$", re.IGNORECASE)

instances: dict[int, dict] = {}
instance_loading: set[int] = set()
instance_pulling: set[int] = set()
port_targets: dict[int, str | None] = {}
port_errors: dict[int, str | None] = {}
voice_job_semaphore = asyncio.Semaphore(2)

CURATED_PULL_MODELS = [
    "llama3.2:3b",
    "llama3:8b",
    "mistral:7b",
    "qwen2.5:7b",
    "qwen2.5:32b",
    "qwen3.5:9b-q4_K_M",
    "gemma4:e4b",
    "llama2-uncensored:latest",
    "fredrezones55/Qwen3.5-Uncensored-HauhauCS-Aggressive:4b",
    "nomic-embed-text:latest",
]

MODEL_NAME_RE = re.compile(r"^[A-Za-z0-9_.:/-]+$")
VOICE_ASSET_ID_RE = re.compile(r"^[A-Za-z0-9_.-]+$")


def is_port_bound(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        return s.connect_ex(("127.0.0.1", port)) == 0


def get_next_port() -> int:
    used = set(instances.keys()) | {11434}
    port = 11435
    while port in used or is_port_bound(port):
        port += 1
    return port


def read_meminfo() -> dict[str, int]:
    values: dict[str, int] = {}
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            key, raw = line.split(":", 1)
            parts = raw.strip().split()
            if parts:
                values[key] = int(parts[0]) * 1024
    except OSError:
        pass
    return values


def count_ollama_processes() -> int:
    count = 0
    proc = Path("/proc")
    try:
        entries = list(proc.iterdir())
    except OSError:
        return 0
    for entry in entries:
        if not entry.name.isdigit():
            continue
        try:
            cmdline = (entry / "cmdline").read_bytes().replace(b"\x00", b" ").decode("utf-8", "ignore")
        except OSError:
            continue
        if "ollama" in cmdline:
            count += 1
    return count


def is_safe_voice_audio_name(name: str) -> bool:
    return bool(VOICE_AUDIO_RE.match(name))


def is_allowed_audio_upload(name: str) -> bool:
    return Path(name).name == name and bool(AUDIO_UPLOAD_RE.match(name))


def is_safe_voice_asset_id(value: str) -> bool:
    return bool(value and VOICE_ASSET_ID_RE.fullmatch(value))


def discover_piper_voices() -> list[dict]:
    voices: list[dict] = []
    if not PIPER_VOICE_DIR.exists():
        return voices
    for path in sorted(PIPER_VOICE_DIR.glob("*.onnx")):
        if path.is_symlink() or not path.is_file():
            continue
        voice_id = path.stem
        if not is_safe_voice_asset_id(voice_id):
            continue
        try:
            is_default = path.resolve() == PIPER_VOICE.resolve() if PIPER_VOICE.exists() else path == PIPER_VOICE
        except OSError:
            is_default = path == PIPER_VOICE
        voices.append({"id": voice_id, "label": voice_id, "path": str(path), "default": is_default})
    return voices


def discover_whisper_models() -> list[dict]:
    models: list[dict] = []
    if not WHISPER_MODEL_DIR.exists():
        return models
    for path in sorted(WHISPER_MODEL_DIR.glob("ggml-*.bin")):
        if path.is_symlink() or not path.is_file():
            continue
        model_id = path.stem.removeprefix("ggml-")
        if not is_safe_voice_asset_id(model_id):
            continue
        try:
            is_default = path.resolve() == WHISPER_MODEL.resolve() if WHISPER_MODEL.exists() else path == WHISPER_MODEL
        except OSError:
            is_default = path == WHISPER_MODEL
        models.append({"id": model_id, "label": model_id, "path": str(path), "default": is_default})
    return models


def resolve_piper_voice(voice_id: Optional[str]) -> Path:
    if not voice_id:
        return PIPER_VOICE
    if not is_safe_voice_asset_id(voice_id):
        raise HTTPException(status_code=400, detail="Invalid Piper voice")
    path = PIPER_VOICE_DIR / f"{voice_id}.onnx"
    try:
        if path.is_symlink() or not path.is_file() or path.parent.resolve() != PIPER_VOICE_DIR.resolve():
            raise HTTPException(status_code=400, detail="Unknown Piper voice")
    except OSError:
        raise HTTPException(status_code=400, detail="Unknown Piper voice")
    return path


def resolve_whisper_model(model_id: Optional[str]) -> Path:
    if not model_id:
        return WHISPER_MODEL
    if not is_safe_voice_asset_id(model_id):
        raise HTTPException(status_code=400, detail="Invalid Whisper model")
    path = WHISPER_MODEL_DIR / f"ggml-{model_id}.bin"
    try:
        if path.is_symlink() or not path.is_file() or path.parent.resolve() != WHISPER_MODEL_DIR.resolve():
            raise HTTPException(status_code=400, detail="Unknown Whisper model")
    except OSError:
        raise HTTPException(status_code=400, detail="Unknown Whisper model")
    return path


def ensure_private_voice_dir(path: Path) -> None:
    if path != VOICE_RUNTIME_DIR:
        try:
            if path.is_relative_to(VOICE_RUNTIME_DIR):
                ensure_private_voice_dir(VOICE_RUNTIME_DIR)
        except ValueError:
            pass
    if path.is_symlink():
        raise HTTPException(status_code=500, detail="Unsafe voice runtime directory")
    path.mkdir(parents=True, exist_ok=True)
    if path.is_symlink() or not path.is_dir():
        raise HTTPException(status_code=500, detail="Unsafe voice runtime directory")
    try:
        path.chmod(0o700)
    except OSError:
        pass


def get_safe_voice_audio_path(filename: str) -> Path:
    if not is_safe_voice_audio_name(filename):
        raise HTTPException(status_code=400, detail="Invalid audio filename")
    ensure_private_voice_dir(VOICE_TTS_DIR)
    path = VOICE_TTS_DIR / filename
    try:
        if path.is_symlink() or not path.is_file() or path.parent.resolve() != VOICE_TTS_DIR.resolve():
            raise HTTPException(status_code=404, detail="Audio file not found")
    except OSError:
        raise HTTPException(status_code=404, detail="Audio file not found")
    return path


def voice_health() -> dict:
    return {
        "piper": {
            "available": PIPER_BIN.exists() and os.access(PIPER_BIN, os.X_OK) and PIPER_VOICE.exists(),
            "binary": str(PIPER_BIN),
            "voice": str(PIPER_VOICE),
            "voice_exists": PIPER_VOICE.exists(),
        },
        "whisper": {
            "available": WHISPER_BIN.exists() and os.access(WHISPER_BIN, os.X_OK) and WHISPER_MODEL.exists(),
            "binary": str(WHISPER_BIN),
            "model": str(WHISPER_MODEL),
            "model_exists": WHISPER_MODEL.exists(),
        },
        "runtime_dir": str(VOICE_RUNTIME_DIR),
    }


def voice_options() -> dict:
    return {
        "tts": {
            "voices": discover_piper_voices(),
            "defaults": TTSOptions().model_dump(),
        },
        "stt": {
            "models": discover_whisper_models(),
            "defaults": STTOptions().model_dump(),
            "languages": ["en", "auto"],
        },
    }


def build_piper_command(output_path: Path, options: Optional[TTSOptions] = None) -> list[str]:
    options = options or TTSOptions()
    cmd = [
        str(PIPER_BIN),
        "--model", str(resolve_piper_voice(options.voice_id)),
        "--output_file", str(output_path),
        "--noise_scale", str(options.noise_scale),
        "--length_scale", str(options.length_scale),
        "--noise_w", str(options.noise_w),
        "--sentence_silence", str(options.sentence_silence),
    ]
    if options.speaker is not None:
        cmd += ["--speaker", str(options.speaker)]
    return cmd


def build_whisper_command(input_path: Path, output_base: Path, options: Optional[STTOptions] = None) -> list[str]:
    options = options or STTOptions()
    cmd = [
        str(WHISPER_BIN),
        "-m", str(resolve_whisper_model(options.model_id)),
        "-f", str(input_path),
        "-nt",
        "-otxt",
        "-of", str(output_base),
        "-l", options.language,
        "-t", str(options.threads),
        "-bs", str(options.beam_size),
        "-tp", str(options.temperature),
    ]
    if options.translate:
        cmd.append("-tr")
    return cmd


def prepend_wav_silence(path: Path, silence_ms: int) -> None:
    if silence_ms <= 0:
        return
    temp_path = path.with_suffix(".padded.wav")
    try:
        with wave.open(str(path), "rb") as src:
            params = src.getparams()
            frames = src.readframes(src.getnframes())
            silence_frames = int(src.getframerate() * silence_ms / 1000)
            silence = b"\x00" * silence_frames * src.getnchannels() * src.getsampwidth()
        with wave.open(str(temp_path), "wb") as dst:
            dst.setparams(params)
            dst.writeframes(silence + frames)
        temp_path.replace(path)
    finally:
        temp_path.unlink(missing_ok=True)


def cleanup_old_voice_files(max_age_seconds: int = 24 * 60 * 60) -> None:
    cutoff = time.time() - max_age_seconds
    for directory in (VOICE_TTS_DIR, VOICE_STT_DIR):
        if not directory.exists():
            continue
        ensure_private_voice_dir(directory)
        for path in directory.iterdir():
            try:
                if path.is_file() and path.stat().st_mtime < cutoff:
                    path.unlink(missing_ok=True)
            except OSError:
                continue


def run_piper_tts(text: str, options: Optional[TTSOptions] = None) -> dict:
    options = options or TTSOptions()
    health = voice_health()
    if not health["piper"]["available"]:
        raise HTTPException(status_code=503, detail="Piper voice is not available")

    ensure_private_voice_dir(VOICE_TTS_DIR)
    cleanup_old_voice_files()
    filename = f"tts-{os.urandom(8).hex()}.wav"
    output_path = VOICE_TTS_DIR / filename

    try:
        proc = subprocess.run(
            build_piper_command(output_path, options),
            input=text,
            text=True,
            capture_output=True,
            timeout=60,
            check=False,
        )
    except subprocess.TimeoutExpired:
        output_path.unlink(missing_ok=True)
        raise HTTPException(status_code=504, detail="Piper timed out")

    if proc.returncode != 0 or not output_path.exists():
        output_path.unlink(missing_ok=True)
        detail = (proc.stderr or proc.stdout or "Piper failed").strip()[-500:]
        raise HTTPException(status_code=500, detail=detail)

    try:
        prepend_wav_silence(output_path, options.leading_silence_ms)
    except wave.Error:
        output_path.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail="Piper generated invalid WAV audio")

    return {
        "status": "ok",
        "audio_url": f"/api/voice/audio/{filename}",
        "bytes": output_path.stat().st_size,
    }


def get_system_telemetry() -> dict:
    mem = read_meminfo()
    total = mem.get("MemTotal", 0)
    available = mem.get("MemAvailable", 0)
    used = max(total - available, 0) if total else 0
    swap_total = mem.get("SwapTotal", 0)
    swap_free = mem.get("SwapFree", 0)
    swap_used = max(swap_total - swap_free, 0) if swap_total else 0
    load1, load5, load15 = os.getloadavg()
    cpu_count = os.cpu_count() or 1
    return {
        "cpu": {
            "load_1m": load1,
            "load_5m": load5,
            "load_15m": load15,
            "cores": cpu_count,
            "load_percent": min(round((load1 / cpu_count) * 100, 1), 999.0),
        },
        "memory": {
            "total": total,
            "available": available,
            "used": used,
            "used_percent": round((used / total) * 100, 1) if total else None,
        },
        "swap": {
            "total": swap_total,
            "used": swap_used,
            "used_percent": round((swap_used / swap_total) * 100, 1) if swap_total else 0,
        },
        "ollama_processes": count_ollama_processes(),
    }


def kill_orphaned_instances():
    if not INSTANCES_DIR.exists():
        return
    for instance_dir in INSTANCES_DIR.iterdir():
        if not instance_dir.is_dir():
            continue
        pid_file = instance_dir / "manager.pid"
        if not pid_file.exists():
            continue
        try:
            pid = int(pid_file.read_text().strip())
            try:
                os.kill(pid, 0)
                cmdline = Path(f"/proc/{pid}/cmdline").read_text()
                if "ollama" in cmdline:
                    try:
                        os.killpg(os.getpgid(pid), signal.SIGTERM)
                    except ProcessLookupError:
                        os.kill(pid, signal.SIGTERM)
            except (ProcessLookupError, PermissionError):
                pass
        except (ValueError, OSError):
            pass
        pid_file.unlink(missing_ok=True)


async def check_health(port: int) -> bool:
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            r = await client.get(f"http://127.0.0.1:{port}/api/version")
            return r.status_code == 200
    except Exception:
        return False


async def get_loaded_models(port: int) -> list[dict]:
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            r = await client.get(f"http://127.0.0.1:{port}/api/ps")
            if r.status_code == 200:
                return r.json().get("models", [])
    except Exception:
        pass
    return []


async def wait_for_startup(port: int, max_wait: float = 45.0) -> bool:
    loop = asyncio.get_event_loop()
    deadline = loop.time() + max_wait
    while loop.time() < deadline:
        if port not in instances:
            return False
        if await check_health(port):
            return True
        await asyncio.sleep(0.5)
    return False


async def do_load_model(port: int, model: str, options: Optional[RuntimeOptions | dict] = None):
    instance_loading.add(port)
    port_targets[port] = model
    port_errors[port] = None
    try:
        async with httpx.AsyncClient(timeout=300.0) as client:
            r = await client.post(
                f"http://127.0.0.1:{port}/api/generate",
                json=build_load_payload(model, options),
            )
            if r.status_code >= 400:
                try:
                    detail = r.json().get("error") or r.text
                except Exception:
                    detail = r.text
                raise RuntimeError(detail or f"Load failed with HTTP {r.status_code}")
        if port in instances:
            instances[port]["last_error"] = None
        port_errors[port] = None
        port_targets[port] = None
    except Exception as e:
        port_errors[port] = str(e)
        if port in instances:
            instances[port]["last_error"] = str(e)
    finally:
        instance_loading.discard(port)


async def startup_sequence(port: int, model: Optional[str]):
    ok = await wait_for_startup(port)
    if ok and model and port in instances:
        await do_load_model(port, model)
    elif not ok and port in instances:
        log_path = instances[port].get("log_path", "")
        error_msg = "Failed to start"
        if log_path and Path(log_path).exists():
            try:
                lines = Path(log_path).read_text().strip().splitlines()
                last = next((l for l in reversed(lines) if l.strip()), "")
                if last:
                    error_msg = last.strip()
            except OSError:
                pass
        instances[port]["last_error"] = error_msg


def format_instance(port: int, info: dict, loaded: list[dict], loading: bool) -> dict:
    proc = info.get("process")
    alive = proc is not None and proc.poll() is None

    if not alive:
        status = "stopped"
    elif port in instance_pulling:
        status = "pulling"
    elif loading:
        status = "loading"
    elif loaded:
        status = "running"
    else:
        status = "ready"

    model_data = loaded[0] if loaded else None
    details = model_data.get("details", {}) if model_data else {}

    return {
        "port": port,
        "pid": info.get("pid"),
        "status": status,
        "loaded_model": model_data["name"] if model_data else None,
        "loaded_model_size": model_data.get("size") if model_data else None,
        "model_family": details.get("family"),
        "model_params": details.get("parameter_size"),
        "model_quant": details.get("quantization_level"),
        "context_length": model_data.get("context_length") if model_data else None,
        "target_model": info.get("target_model"),
        "last_error": info.get("last_error") or port_errors.get(port),
        "external": False,
        "pulling": port in instance_pulling,
    }


@asynccontextmanager
async def lifespan(app: FastAPI):
    kill_orphaned_instances()
    yield
    for info in list(instances.values()):
        proc = info.get("process")
        if proc and proc.poll() is None:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            except Exception:
                proc.terminate()
        lf = info.get("log_file")
        if lf:
            try:
                lf.close()
            except Exception:
                pass


app = FastAPI(title="Warpgate", lifespan=lifespan)


class CreateInstanceRequest(BaseModel):
    port: Optional[int] = None
    model: Optional[str] = None


class RuntimeOptions(BaseModel):
    temperature: Optional[float] = Field(None, ge=0.0, le=2.0)
    top_p: Optional[float] = Field(None, ge=0.0, le=1.0)
    top_k: Optional[int] = Field(None, ge=1, le=1000)
    repeat_penalty: Optional[float] = Field(None, ge=0.1, le=5.0)
    num_ctx: Optional[int] = Field(None, ge=512, le=131072)
    seed: Optional[int] = Field(None, ge=-1, le=2147483647)


class LoadModelRequest(BaseModel):
    model: str
    options: Optional[RuntimeOptions] = None


class TTSOptions(BaseModel):
    voice_id: Optional[str] = None
    speaker: Optional[int] = Field(None, ge=0, le=99)
    noise_scale: float = Field(0.667, ge=0.0, le=2.0)
    length_scale: float = Field(1.0, ge=0.5, le=2.0)
    noise_w: float = Field(0.8, ge=0.0, le=2.0)
    sentence_silence: float = Field(0.2, ge=0.0, le=2.0)
    leading_silence_ms: int = Field(250, ge=0, le=2000)


class STTOptions(BaseModel):
    model_id: Optional[str] = None
    language: str = Field("en", pattern=r"^(auto|[A-Za-z]{2})$")
    translate: bool = False
    threads: int = Field(4, ge=1, le=32)
    beam_size: int = Field(5, ge=1, le=16)
    temperature: float = Field(0.0, ge=0.0, le=1.0)


class TTSRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=MAX_TTS_CHARS)
    options: TTSOptions = Field(default_factory=lambda: TTSOptions())


class PullModelRequest(BaseModel):
    model: str


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    model: str
    messages: list[ChatMessage]
    system: Optional[str] = None
    options: Optional[RuntimeOptions] = None


def is_safe_model_name(name: str) -> bool:
    return bool(name and MODEL_NAME_RE.fullmatch(name) and ".." not in name and "://" not in name)


def extract_model_context_length(show_data: dict) -> dict:
    model_info = show_data.get("model_info") or {}
    candidates: list[tuple[str, int]] = []

    for key, value in model_info.items():
        if not key.endswith(".context_length") and key != "context_length":
            continue
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            continue
        if parsed >= 512:
            candidates.append((f"model_info.{key}", parsed))

    if candidates:
        source, context_length = max(candidates, key=lambda item: item[1])
        return {"context_length": context_length, "context_source": source}

    return {"context_length": None, "context_source": "unknown"}


def build_model_metadata_response(port: int, model: str, show_data: dict) -> dict:
    context = extract_model_context_length(show_data)
    return {
        "port": port,
        "model": model,
        "context_length": context["context_length"],
        "context_source": context["context_source"],
    }


def runtime_options_dict(options: Optional[RuntimeOptions | dict]) -> dict:
    if not options:
        return {}
    if isinstance(options, BaseModel):
        return options.model_dump(exclude_none=True)
    return {k: v for k, v in options.items() if v is not None}


def build_load_payload(model: str, options: Optional[RuntimeOptions | dict] = None) -> dict:
    payload: dict = {"model": model, "prompt": "", "keep_alive": -1, "stream": False}
    clean_options = runtime_options_dict(options)
    if clean_options:
        payload["options"] = clean_options
    return payload


def build_model_catalog(
    target_port: int,
    models_by_port: dict[int, list[dict]],
    curated: list[str] | None = None,
) -> dict:
    curated = curated or CURATED_PULL_MODELS
    merged: dict[str, dict] = {}

    for port, models in models_by_port.items():
        for model in models:
            name = model.get("name") or model.get("model")
            if not name:
                continue
            entry = merged.setdefault(
                name,
                {
                    "name": name,
                    "size": model.get("size"),
                    "digest": model.get("digest"),
                    "modified_at": model.get("modified_at"),
                    "available_ports": [],
                },
            )
            if port not in entry["available_ports"]:
                entry["available_ports"].append(port)
            if entry.get("size") is None and model.get("size") is not None:
                entry["size"] = model.get("size")

    for name in curated:
        merged.setdefault(
            name,
            {"name": name, "size": None, "digest": None, "modified_at": None, "available_ports": []},
        )

    models = []
    for entry in merged.values():
        ports = sorted(entry["available_ports"])
        installed_on_target = target_port in ports
        availability = "installed" if installed_on_target else "needs_pull"
        models.append({
            **entry,
            "available_ports": ports,
            "installed_on_target": installed_on_target,
            "availability": availability,
        })

    models.sort(key=lambda m: (m["availability"] != "installed", m["name"].lower()))
    return {"target_port": target_port, "models": models}


async def get_installed_models(port: int) -> list[dict]:
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(f"http://127.0.0.1:{port}/api/tags")
            if r.status_code == 200:
                return r.json().get("models", [])
    except Exception:
        pass
    return []


async def collect_models_by_port(target_port: int | None = None) -> dict[int, list[dict]]:
    ports = {11434}
    if target_port:
        ports.add(target_port)
    ports.update(instances.keys())
    for port in DISCOVERY_RANGE:
        if is_port_bound(port):
            ports.add(port)

    result: dict[int, list[dict]] = {}
    for port in sorted(ports):
        if is_port_bound(port):
            result[port] = await get_installed_models(port)
    return result


async def do_pull_model(port: int, model: str):
    instance_pulling.add(port)
    port_errors[port] = None
    try:
        async with httpx.AsyncClient(timeout=900.0) as client:
            r = await client.post(
                f"http://127.0.0.1:{port}/api/pull",
                json={"name": model, "stream": False},
            )
            if r.status_code >= 400:
                try:
                    detail = r.json().get("error") or r.text
                except Exception:
                    detail = r.text
                raise RuntimeError(detail or f"Pull failed with HTTP {r.status_code}")
        port_errors[port] = None
        if port in instances:
            instances[port]["last_error"] = None
    except Exception as e:
        port_errors[port] = str(e)
        if port in instances:
            instances[port]["last_error"] = str(e)
    finally:
        instance_pulling.discard(port)


async def discover_external_instances() -> list[dict]:
    managed_ports = set(instances.keys())
    external = []
    for port in DISCOVERY_RANGE:
        if port in managed_ports:
            continue
        if not is_port_bound(port):
            continue
        try:
            async with httpx.AsyncClient(timeout=1.5) as client:
                r = await client.get(f"http://127.0.0.1:{port}/api/version")
                if r.status_code != 200:
                    continue
                ps = await client.get(f"http://127.0.0.1:{port}/api/ps")
                loaded = ps.json().get("models", []) if ps.status_code == 200 else []
        except Exception:
            continue

        model_data = loaded[0] if loaded else None
        details = model_data.get("details", {}) if model_data else {}

        external.append({
            "port": port,
            "pid": None,
            "status": "pulling" if port in instance_pulling else ("loading" if port in instance_loading else ("running" if loaded else "ready")),
            "loaded_model": model_data["name"] if model_data else None,
            "loaded_model_size": model_data.get("size") if model_data else None,
            "model_family": details.get("family"),
            "model_params": details.get("parameter_size"),
            "model_quant": details.get("quantization_level"),
            "context_length": model_data.get("context_length") if model_data else None,
            "target_model": port_targets.get(port),
            "last_error": port_errors.get(port),
            "external": True,
            "pulling": port in instance_pulling,
        })
    return external


@app.get("/api/instances")
async def list_instances():
    result = []
    for port, info in instances.items():
        proc = info.get("process")
        alive = proc is not None and proc.poll() is None
        loaded = await get_loaded_models(port) if alive else []
        loading = port in instance_loading
        result.append(format_instance(port, info, loaded, loading))

    result += await discover_external_instances()
    return sorted(result, key=lambda x: x["port"])


@app.post("/api/instances")
async def create_instance(req: CreateInstanceRequest, bg: BackgroundTasks):
    port = req.port or get_next_port()

    if port == 11434:
        raise HTTPException(400, "Port 11434 is reserved for the main Ollama instance")
    if port in instances:
        raise HTTPException(400, f"Instance already exists on port {port}")
    if is_port_bound(port):
        raise HTTPException(409, f"Port {port} is already in use by another process")

    instance_dir = INSTANCES_DIR / str(port)
    instance_dir.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    env["OLLAMA_HOST"] = f"0.0.0.0:{port}"
    env["OLLAMA_HOME"] = str(instance_dir)
    env["OLLAMA_MODELS"] = SHARED_MODELS_DIR

    log_path = instance_dir / "ollama.log"
    log_file = open(log_path, "w")

    proc = subprocess.Popen(
        [OLLAMA_BIN, "serve"],
        env=env,
        stdout=log_file,
        stderr=subprocess.STDOUT,
        preexec_fn=os.setsid,
    )

    (instance_dir / "manager.pid").write_text(str(proc.pid))

    instances[port] = {
        "pid": proc.pid,
        "process": proc,
        "log_file": log_file,
        "log_path": str(log_path),
        "target_model": req.model,
        "last_error": None,
    }

    bg.add_task(startup_sequence, port, req.model)
    return {"port": port, "pid": proc.pid, "status": "starting"}


@app.delete("/api/instances/{port}")
async def stop_instance(port: int):
    if port not in instances:
        raise HTTPException(404, f"No instance on port {port}")

    info = instances.pop(port)
    instance_loading.discard(port)

    proc = info.get("process")
    if proc and proc.poll() is None:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except Exception:
                proc.kill()
        except Exception:
            proc.terminate()

    lf = info.get("log_file")
    if lf:
        try:
            lf.close()
        except Exception:
            pass

    return {"status": "stopped", "port": port}


@app.post("/api/instances/{port}/restart")
async def restart_instance(port: int, bg: BackgroundTasks):
    if port not in instances:
        raise HTTPException(404, f"No instance on port {port}")

    info = instances[port]
    model = info.get("target_model")

    # Stop current process
    proc = info.get("process")
    if proc and proc.poll() is None:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except Exception:
                proc.kill()
        except Exception:
            proc.terminate()

    lf = info.get("log_file")
    if lf:
        try:
            lf.close()
        except Exception:
            pass

    await asyncio.sleep(1.0)

    # Relaunch
    instance_dir = INSTANCES_DIR / str(port)
    instance_dir.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    env["OLLAMA_HOST"] = f"0.0.0.0:{port}"
    env["OLLAMA_HOME"] = str(instance_dir)
    env["OLLAMA_MODELS"] = SHARED_MODELS_DIR

    log_path = instance_dir / "ollama.log"
    log_file = open(log_path, "w")

    proc = subprocess.Popen(
        [OLLAMA_BIN, "serve"],
        env=env,
        stdout=log_file,
        stderr=subprocess.STDOUT,
        preexec_fn=os.setsid,
    )

    (instance_dir / "manager.pid").write_text(str(proc.pid))

    instances[port] = {
        "pid": proc.pid,
        "process": proc,
        "log_file": log_file,
        "log_path": str(log_path),
        "target_model": model,
        "last_error": None,
    }

    bg.add_task(startup_sequence, port, model)
    return {"port": port, "pid": proc.pid, "status": "restarting"}


@app.post("/api/instances/{port}/load")
async def load_model(port: int, req: LoadModelRequest, bg: BackgroundTasks):
    if not is_port_bound(port):
        raise HTTPException(404, f"No instance on port {port}")
    if port in instance_loading:
        raise HTTPException(409, "Already loading a model on this instance")
    if port in instance_pulling:
        raise HTTPException(409, "Already pulling a model on this instance")

    if port in instances:
        proc = instances[port].get("process")
        if not proc or proc.poll() is not None:
            raise HTTPException(400, "Instance is not running")

        instances[port]["target_model"] = req.model
        instances[port]["last_error"] = None

    bg.add_task(do_load_model, port, req.model, req.options)
    return {"status": "loading", "model": req.model, "port": port}


@app.post("/api/instances/{port}/pull")
async def pull_model(port: int, req: PullModelRequest, bg: BackgroundTasks):
    if not is_port_bound(port):
        raise HTTPException(404, f"No instance on port {port}")
    if port in instance_pulling:
        raise HTTPException(409, "Already pulling a model on this instance")
    if not is_safe_model_name(req.model):
        raise HTTPException(400, "Invalid model name")

    bg.add_task(do_pull_model, port, req.model)
    return {"status": "pulling", "model": req.model, "port": port}


@app.post("/api/instances/{port}/unload")
async def unload_model(port: int):
    if not is_port_bound(port):
        raise HTTPException(404, f"No instance on port {port}")

    loaded = await get_loaded_models(port)
    if not loaded:
        return {"status": "no_model_loaded"}

    model = loaded[0]["name"]
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            await client.post(
                f"http://127.0.0.1:{port}/api/generate",
                json={"model": model, "keep_alive": 0, "stream": False},
            )
        return {"status": "unloaded", "model": model, "port": port}
    except Exception as e:
        raise HTTPException(500, str(e))


@app.post("/api/instances/{port}/chat")
async def chat(port: int, req: ChatRequest):
    if not is_port_bound(port):
        raise HTTPException(404, f"No instance on port {port}")

    payload: dict = {
        "model": req.model,
        "messages": [m.model_dump() for m in req.messages],
        "stream": True,
        "options": runtime_options_dict(req.options),
    }
    if req.system:
        payload["system"] = req.system

    async def stream_response():
        try:
            async with httpx.AsyncClient(timeout=None) as client:
                async with client.stream(
                    "POST",
                    f"http://127.0.0.1:{port}/api/chat",
                    json=payload,
                ) as r:
                    async for chunk in r.aiter_bytes():
                        yield chunk
        except Exception as e:
            import json
            yield json.dumps({"error": str(e)}).encode()

    return StreamingResponse(stream_response(), media_type="application/x-ndjson")


@app.get("/api/models")
async def list_models(port: int = 11434):
    if not is_port_bound(port):
        return build_model_catalog(port, {11434: await get_installed_models(11434)})
    models_by_port = await collect_models_by_port(port)
    return build_model_catalog(port, models_by_port)


@app.get("/api/instances/{port}/models")
async def list_models_for_instance(port: int):
    if not is_port_bound(port):
        raise HTTPException(404, f"No instance on port {port}")
    models_by_port = await collect_models_by_port(port)
    return build_model_catalog(port, models_by_port)


@app.get("/api/instances/{port}/model-metadata")
async def model_metadata(port: int, model: str):
    if not is_safe_model_name(model):
        raise HTTPException(400, "Invalid model name")
    if not is_port_bound(port):
        raise HTTPException(404, f"No Ollama instance is reachable on port {port}")

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.post(f"http://127.0.0.1:{port}/api/show", json={"model": model})
    except httpx.RequestError as exc:
        raise HTTPException(502, f"Failed to query model metadata on port {port}: {exc}")

    if r.status_code >= 400:
        try:
            detail = r.json().get("error") or r.text
        except Exception:
            detail = r.text
        raise HTTPException(r.status_code, detail or f"Ollama metadata lookup failed with HTTP {r.status_code}")

    return build_model_metadata_response(port, model, r.json())


@app.get("/api/instances/{port}/logs")
async def get_logs(port: int, lines: int = 100):
    if port not in instances:
        raise HTTPException(404, f"No instance on port {port}")
    log_path = instances[port].get("log_path")
    if not log_path or not Path(log_path).exists():
        return {"logs": ""}
    try:
        with open(log_path, "r") as f:
            content = f.readlines()
        return {"logs": "".join(content[-lines:])}
    except Exception as e:
        raise HTTPException(500, str(e))


@app.get("/api/telemetry")
async def telemetry():
    return get_system_telemetry()


@app.get("/api/voice/health")
async def api_voice_health():
    return voice_health()


@app.get("/api/voice/options")
async def api_voice_options():
    return voice_options()


@app.post("/api/voice/tts")
async def api_voice_tts(req: TTSRequest):
    async with voice_job_semaphore:
        return await asyncio.to_thread(run_piper_tts, req.text, req.options)


@app.get("/api/voice/audio/{filename}")
async def api_voice_audio(filename: str):
    path = get_safe_voice_audio_path(filename)
    return FileResponse(path, media_type="audio/wav", filename=filename)


@app.post("/api/voice/stt")
async def api_voice_stt(
    file: UploadFile = File(...),
    model_id: Optional[str] = Form(None),
    language: str = Form("en"),
    translate: bool = Form(False),
    threads: int = Form(4),
    beam_size: int = Form(5),
    temperature: float = Form(0.0),
):
    health = voice_health()
    if not health["whisper"]["available"]:
        raise HTTPException(status_code=503, detail="Whisper is not available")
    if not file.filename or not is_allowed_audio_upload(file.filename):
        raise HTTPException(status_code=400, detail="Unsupported audio file type")
    options = STTOptions(
        model_id=model_id,
        language=language,
        translate=translate,
        threads=threads,
        beam_size=beam_size,
        temperature=temperature,
    )

    async with voice_job_semaphore:
        ensure_private_voice_dir(VOICE_STT_DIR)
        cleanup_old_voice_files()
        suffix = Path(file.filename).suffix.lower()
        stem = f"stt-{os.urandom(8).hex()}"
        input_path = VOICE_STT_DIR / f"{stem}{suffix}"
        output_base = VOICE_STT_DIR / stem
        output_txt = VOICE_STT_DIR / f"{stem}.txt"

        try:
            size = 0
            with input_path.open("wb") as out:
                while chunk := await file.read(1024 * 1024):
                    size += len(chunk)
                    if size > MAX_AUDIO_UPLOAD_BYTES:
                        raise HTTPException(status_code=413, detail="Audio upload too large")
                    out.write(chunk)

            proc = await asyncio.to_thread(
                subprocess.run,
                build_whisper_command(input_path, output_base, options),
                capture_output=True,
                text=True,
                timeout=180,
                check=False,
            )

            if proc.returncode != 0 or not output_txt.exists():
                detail = (proc.stderr or proc.stdout or "Whisper failed").strip()[-500:]
                raise HTTPException(status_code=500, detail=detail)

            transcript = output_txt.read_text(encoding="utf-8", errors="replace").strip()
            return {"status": "ok", "transcript": transcript, "input_filename": Path(file.filename).name}
        except subprocess.TimeoutExpired:
            raise HTTPException(status_code=504, detail="Whisper timed out")
        finally:
            input_path.unlink(missing_ok=True)
            output_txt.unlink(missing_ok=True)
            for sidecar in VOICE_STT_DIR.glob(f"{stem}.*"):
                sidecar.unlink(missing_ok=True)


@app.get("/api/main-status")
async def main_status():
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            r = await client.get("http://127.0.0.1:11434/api/version")
            if r.status_code == 200:
                data = r.json()
                return {"online": True, "version": data.get("version"), "port": 11434}
    except Exception:
        pass
    return {"online": False, "version": None, "port": 11434}


app.mount("/", StaticFiles(directory="static", html=True), name="static")
