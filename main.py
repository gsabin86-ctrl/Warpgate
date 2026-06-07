import asyncio
import os
import re
import signal
import socket
import subprocess
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

import httpx
from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

OLLAMA_BIN = "/usr/local/bin/ollama"
SHARED_MODELS_DIR = "/usr/share/ollama/.ollama/models"
INSTANCES_DIR = Path("/tmp/ollama-instances")
DISCOVERY_RANGE = range(11434, 11500)

instances: dict[int, dict] = {}
instance_loading: set[int] = set()
instance_pulling: set[int] = set()
port_targets: dict[int, str | None] = {}
port_errors: dict[int, str | None] = {}

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


async def do_load_model(port: int, model: str):
    instance_loading.add(port)
    port_targets[port] = model
    port_errors[port] = None
    try:
        async with httpx.AsyncClient(timeout=300.0) as client:
            r = await client.post(
                f"http://127.0.0.1:{port}/api/generate",
                json={"model": model, "prompt": "", "keep_alive": -1, "stream": False},
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


app = FastAPI(title="Ollama Manager", lifespan=lifespan)


class CreateInstanceRequest(BaseModel):
    port: Optional[int] = None
    model: Optional[str] = None


class LoadModelRequest(BaseModel):
    model: str


class PullModelRequest(BaseModel):
    model: str


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    model: str
    messages: list[ChatMessage]
    system: Optional[str] = None
    options: Optional[dict] = None


def is_safe_model_name(name: str) -> bool:
    return bool(name and MODEL_NAME_RE.fullmatch(name) and ".." not in name and "://" not in name)


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

    bg.add_task(do_load_model, port, req.model)
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
        "options": req.options or {},
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
