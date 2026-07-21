import unittest
import subprocess
import struct
import tempfile
import time
import wave
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

import main


class VoiceTests(unittest.TestCase):
    def test_voice_health_reports_piper_and_whisper(self):
        with patch.object(main, "PIPER_BIN", Path("/bin/echo")), \
             patch.object(main, "PIPER_VOICE", Path("/tmp/fake-voice.onnx")), \
             patch.object(main, "WHISPER_BIN", Path("/bin/echo")), \
             patch.object(main, "WHISPER_MODEL", Path("/tmp/fake-whisper.bin")):
            health = main.voice_health()

        self.assertIn("piper", health)
        self.assertIn("whisper", health)
        self.assertIn("binary", health["piper"])
        self.assertIn("model", health["whisper"])

    def test_generated_audio_filename_is_restricted(self):
        self.assertTrue(main.is_safe_voice_audio_name("abc-123.wav"))
        self.assertFalse(main.is_safe_voice_audio_name("../secret.wav"))
        self.assertFalse(main.is_safe_voice_audio_name("abc.mp3"))

    def test_safe_voice_audio_path_rejects_symlinks(self):
        with tempfile.TemporaryDirectory() as tmp:
            audio_dir = Path(tmp)
            target = audio_dir / "target.wav"
            target.write_bytes(b"RIFFfake")
            with patch.object(main, "VOICE_TTS_DIR", audio_dir):
                self.assertEqual(main.get_safe_voice_audio_path("target.wav"), target)
            link = audio_dir / "linked.wav"
            link.symlink_to(target)
            with patch.object(main, "VOICE_TTS_DIR", audio_dir):
                with self.assertRaises(Exception):
                    main.get_safe_voice_audio_path("linked.wav")

    def test_private_voice_dir_rejects_symlink_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            safe = Path(tmp) / "safe"
            main.ensure_private_voice_dir(safe)
            self.assertTrue(safe.is_dir())
            real = Path(tmp) / "real"
            real.mkdir()
            link = Path(tmp) / "link"
            link.symlink_to(real, target_is_directory=True)
            with self.assertRaises(Exception):
                main.ensure_private_voice_dir(link)

    def test_voice_asset_id_rejects_path_traversal(self):
        self.assertTrue(main.is_safe_voice_asset_id("en_US-amy-medium"))
        self.assertTrue(main.is_safe_voice_asset_id("ggml-base.en"))
        self.assertFalse(main.is_safe_voice_asset_id("../secret"))
        self.assertFalse(main.is_safe_voice_asset_id("/tmp/model"))
        self.assertFalse(main.is_safe_voice_asset_id("bad model"))

    def test_discover_piper_voices_returns_safe_ids(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            voices = root / "piper-voices"
            voices.mkdir()
            voice = voices / "en_US-amy-medium.onnx"
            voice.write_bytes(b"fake")
            (voices / "en_US-amy-medium.onnx.json").write_text("{}")

            with patch.object(main, "VOICE_ROOT", root), \
                 patch.object(main, "PIPER_VOICE_DIR", voices), \
                 patch.object(main, "PIPER_VOICE", voice):
                result = main.discover_piper_voices()

        self.assertEqual(result, [
            {
                "id": "en_US-amy-medium",
                "label": "en_US-amy-medium",
                "default": True,
            }
        ])

    def test_discover_whisper_models_uses_runtime_model_dir_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            models = root / "whisper-models"
            models.mkdir()
            model = models / "ggml-base.en.bin"
            model.write_bytes(b"fake")
            test_models = root / "whisper.cpp" / "models"
            test_models.mkdir(parents=True)
            (test_models / "for-tests-ggml-large.bin").write_bytes(b"fake")

            with patch.object(main, "VOICE_ROOT", root), \
                 patch.object(main, "WHISPER_MODEL_DIR", models), \
                 patch.object(main, "WHISPER_MODEL", model):
                result = main.discover_whisper_models()

        self.assertEqual(result, [
            {
                "id": "base.en",
                "label": "base.en",
                "default": True,
            }
        ])

    def test_voice_options_response_contains_catalogs_and_defaults(self):
        result = main.voice_options()

        self.assertIn("tts", result)
        self.assertIn("stt", result)
        self.assertIn("defaults", result["tts"])
        self.assertIn("voices", result["tts"])
        self.assertIn("models", result["stt"])


class VoiceTTSTests(unittest.TestCase):
    def test_tts_request_rejects_empty_text(self):
        self.assertEqual(main.TTSRequest(text="hello").text, "hello")
        with self.assertRaises(Exception):
            main.TTSRequest(text="")

    def test_piper_command_uses_argv_not_shell(self):
        out = Path("/tmp/example.wav")
        cmd = main.build_piper_command(out)
        self.assertEqual(cmd[0], str(main.PIPER_BIN))
        self.assertIn("--model", cmd)
        self.assertIn(str(main.PIPER_VOICE), cmd)
        self.assertIn("--output_file", cmd)
        self.assertIn(str(out), cmd)

    def test_tts_options_validate_ranges(self):
        opts = main.TTSOptions(
            voice_id="en_US-amy-medium",
            speaker=0,
            noise_scale=0.667,
            length_scale=1.0,
            noise_w=0.8,
            sentence_silence=0.2,
            leading_silence_ms=250,
        )
        self.assertEqual(opts.leading_silence_ms, 250)

        with self.assertRaises(Exception):
            main.TTSOptions(length_scale=0.01)
        with self.assertRaises(Exception):
            main.TTSOptions(leading_silence_ms=5000)

    def test_piper_command_includes_tuning_options(self):
        out = Path("/tmp/example.wav")
        opts = main.TTSOptions(noise_scale=0.5, length_scale=1.2, noise_w=0.7, sentence_silence=0.35, speaker=1)

        cmd = main.build_piper_command(out, opts)

        self.assertIn("--noise_scale", cmd)
        self.assertIn("0.5", cmd)
        self.assertIn("--length_scale", cmd)
        self.assertIn("1.2", cmd)
        self.assertIn("--noise_w", cmd)
        self.assertIn("0.7", cmd)
        self.assertIn("--sentence_silence", cmd)
        self.assertIn("0.35", cmd)
        self.assertIn("--speaker", cmd)
        self.assertIn("1", cmd)

    def test_prepend_wav_silence_increases_duration(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sample.wav"
            with wave.open(str(path), "wb") as wav:
                wav.setnchannels(1)
                wav.setsampwidth(2)
                wav.setframerate(16000)
                wav.writeframes(b"\x01\x00" * 1600)  # 100ms

            main.prepend_wav_silence(path, 250)

            with wave.open(str(path), "rb") as wav:
                self.assertEqual(wav.getnframes(), 1600 + 4000)

    def test_leading_preroll_contains_sub_audible_wake_signal(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sample.wav"
            with wave.open(str(path), "wb") as wav:
                wav.setnchannels(1)
                wav.setsampwidth(2)
                wav.setframerate(16000)
                wav.writeframes(b"\x01\x00" * 1600)

            main.prepend_wav_silence(path, 250)

            with wave.open(str(path), "rb") as wav:
                preroll = wav.readframes(4000)
            samples = struct.unpack("<" + "h" * (len(preroll) // 2), preroll)
            self.assertTrue(any(samples))
            self.assertLessEqual(max(abs(sample) for sample in samples), 128)

    def test_tts_default_leading_silence_wakes_slow_output_devices(self):
        self.assertEqual(main.TTSOptions().leading_silence_ms, 1000)

    def test_tts_response_does_not_expose_local_path(self):
        with patch.object(main, "VOICE_TTS_DIR", Path("/tmp/warpgate-test-tts")), \
             patch.object(main, "voice_health", return_value={"piper": {"available": True}}), \
             patch.object(main.subprocess, "run") as run:
            def fake_run(cmd, **kwargs):
                output_path = Path(cmd[cmd.index("--output_file") + 1])
                output_path.parent.mkdir(parents=True, exist_ok=True)
                with wave.open(str(output_path), "wb") as wav:
                    wav.setnchannels(1)
                    wav.setsampwidth(2)
                    wav.setframerate(16000)
                    wav.writeframes(b"\x01\x00" * 1600)
                return subprocess.CompletedProcess(cmd, 0, "", "")
            run.side_effect = fake_run

            result = main.run_piper_tts("hello")

        self.assertEqual(result["status"], "ok")
        self.assertIn("audio_url", result)
        self.assertIn("bytes", result)
        self.assertNotIn("path", result)

    def test_cleanup_old_voice_files_removes_expired_tts_files(self):
        test_dir = Path("/tmp/warpgate-test-cleanup")
        test_dir.mkdir(parents=True, exist_ok=True)
        old_file = test_dir / "old.wav"
        old_file.write_bytes(b"old")
        old_time = time.time() - 90000
        old_file.touch()
        import os
        os.utime(old_file, (old_time, old_time))
        with patch.object(main, "VOICE_TTS_DIR", test_dir):
            main.cleanup_old_voice_files(max_age_seconds=3600)
        self.assertFalse(old_file.exists())


class VoiceSTTTests(unittest.TestCase):
    def test_audio_extension_is_allowed(self):
        self.assertTrue(main.is_allowed_audio_upload("sample.wav"))
        self.assertTrue(main.is_allowed_audio_upload("sample.mp3"))
        self.assertTrue(main.is_allowed_audio_upload("sample.ogg"))
        self.assertTrue(main.is_allowed_audio_upload("sample.flac"))
        self.assertTrue(main.is_allowed_audio_upload("sample.webm"))
        self.assertFalse(main.is_allowed_audio_upload("sample.exe"))
        self.assertFalse(main.is_allowed_audio_upload("../sample.wav"))

    def test_whisper_command_uses_model_and_input_path(self):
        input_path = Path("/tmp/input.wav")
        output_base = Path("/tmp/output")
        cmd = main.build_whisper_command(input_path, output_base)
        self.assertEqual(cmd[0], str(main.WHISPER_BIN))
        self.assertIn("-m", cmd)
        self.assertIn(str(main.WHISPER_MODEL), cmd)
        self.assertIn("-f", cmd)
        self.assertIn(str(input_path), cmd)
        self.assertIn("-otxt", cmd)

    def test_ffmpeg_command_normalizes_browser_audio_for_whisper(self):
        source = Path("/tmp/push-to-talk.webm")
        output = Path("/tmp/push-to-talk.normalized.wav")

        cmd = main.build_ffmpeg_normalize_command(source, output)

        self.assertEqual(cmd[0], str(main.FFMPEG_BIN))
        self.assertIn(str(source), cmd)
        self.assertEqual(cmd[-1], str(output))
        self.assertIn("pcm_s16le", cmd)
        self.assertIn("16000", cmd)
        self.assertIn("1", cmd)
        self.assertIn("-t", cmd)
        self.assertIn(str(main.MAX_STT_DURATION_SECONDS), cmd)

    @unittest.skipUnless(main.FFMPEG_BIN.exists(), "FFmpeg is required for normalization integration")
    def test_real_ffmpeg_normalizes_webm_to_whisper_wav_format(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_wav = root / "source.wav"
            source_webm = root / "source.webm"
            normalized = root / "normalized.wav"
            with wave.open(str(source_wav), "wb") as wav:
                wav.setnchannels(1)
                wav.setsampwidth(2)
                wav.setframerate(22050)
                wav.writeframes(b"\x01\x00" * 22050)

            encoded = subprocess.run(
                [str(main.FFMPEG_BIN), "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
                 "-i", str(source_wav), "-c:a", "libopus", str(source_webm)],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            self.assertEqual(encoded.returncode, 0, encoded.stderr)

            main.normalize_audio_for_whisper(source_webm, normalized)

            with wave.open(str(normalized), "rb") as wav:
                self.assertEqual(wav.getnchannels(), 1)
                self.assertEqual(wav.getframerate(), 16000)
                self.assertEqual(wav.getsampwidth(), 2)
                self.assertGreater(wav.getnframes(), 0)

    def test_stt_route_normalizes_webm_before_whisper(self):
        with tempfile.TemporaryDirectory() as tmp:
            stt_dir = Path(tmp)
            whisper_inputs = []

            def fake_run(cmd, **kwargs):
                if cmd[0] == str(main.FFMPEG_BIN):
                    normalized = Path(cmd[-1])
                    with wave.open(str(normalized), "wb") as wav:
                        wav.setnchannels(1)
                        wav.setsampwidth(2)
                        wav.setframerate(16000)
                        wav.writeframes(b"\x01\x00" * 16000)
                    return subprocess.CompletedProcess(cmd, 0, "", "")

                whisper_input = Path(cmd[cmd.index("-f") + 1])
                whisper_inputs.append(whisper_input)
                output_base = Path(cmd[cmd.index("-of") + 1])
                output_base.with_suffix(".txt").write_text("normalized speech")
                return subprocess.CompletedProcess(cmd, 0, "", "")

            client = TestClient(main.app)
            with patch.object(main, "VOICE_STT_DIR", stt_dir), \
                 patch.object(main, "voice_health", return_value={"whisper": {"available": True}}), \
                 patch.object(main.subprocess, "run", side_effect=fake_run):
                response = client.post(
                    "/api/voice/stt",
                    files={"file": ("push-to-talk.webm", b"fake-webm", "audio/webm")},
                )
            self.assertEqual(list(stt_dir.iterdir()), [])

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["transcript"], "normalized speech")
        self.assertEqual(len(whisper_inputs), 1)
        self.assertTrue(whisper_inputs[0].name.endswith(".normalized.wav"))

    def test_audio_normalization_timeout_is_504(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "source.webm"
            output = Path(tmp) / "normalized.wav"
            source.write_bytes(b"webm")
            with patch.object(main.subprocess, "run", side_effect=subprocess.TimeoutExpired("ffmpeg", 60)):
                with self.assertRaises(main.HTTPException) as raised:
                    main.normalize_audio_for_whisper(source, output)
        self.assertEqual(raised.exception.status_code, 504)

    def test_stt_route_rejects_empty_upload_and_cleans_up(self):
        with tempfile.TemporaryDirectory() as tmp:
            stt_dir = Path(tmp)
            client = TestClient(main.app)
            with patch.object(main, "VOICE_STT_DIR", stt_dir), \
                 patch.object(main, "voice_health", return_value={"whisper": {"available": True}}):
                response = client.post(
                    "/api/voice/stt",
                    files={"file": ("empty.webm", b"", "audio/webm")},
                )
            self.assertEqual(list(stt_dir.iterdir()), [])
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "Audio recording is empty")

    @unittest.skipUnless(main.FFMPEG_BIN.exists(), "FFmpeg is required for malformed-audio validation")
    def test_stt_route_rejects_malformed_audio_and_cleans_up(self):
        with tempfile.TemporaryDirectory() as tmp:
            stt_dir = Path(tmp)
            client = TestClient(main.app)
            with patch.object(main, "VOICE_STT_DIR", stt_dir), \
                 patch.object(main, "voice_health", return_value={"whisper": {"available": True}}):
                response = client.post(
                    "/api/voice/stt",
                    files={"file": ("broken.webm", b"not-an-audio-file", "audio/webm")},
                )
            self.assertEqual(list(stt_dir.iterdir()), [])
        self.assertEqual(response.status_code, 400)

    def test_stt_options_validate_ranges(self):
        opts = main.STTOptions(model_id="base.en", language="en", translate=False, threads=4, beam_size=5, temperature=0.0)
        self.assertEqual(opts.model_id, "base.en")
        with self.assertRaises(Exception):
            main.STTOptions(language="english")
        with self.assertRaises(Exception):
            main.STTOptions(threads=128)

    def test_whisper_command_includes_stt_options(self):
        input_path = Path("/tmp/input.wav")
        output_base = Path("/tmp/output")
        opts = main.STTOptions(model_id=None, language="auto", translate=True, threads=8, beam_size=3, temperature=0.2)

        cmd = main.build_whisper_command(input_path, output_base, opts)

        self.assertIn("-l", cmd)
        self.assertIn("auto", cmd)
        self.assertIn("-tr", cmd)
        self.assertIn("-t", cmd)
        self.assertIn("8", cmd)
        self.assertIn("-bs", cmd)
        self.assertIn("3", cmd)
        self.assertIn("-tp", cmd)
        self.assertIn("0.2", cmd)

    def test_stt_route_rejects_invalid_form_options_as_422(self):
        client = TestClient(main.app)
        with patch.object(main, "voice_health", return_value={"whisper": {"available": True}}):
            response = client.post(
                "/api/voice/stt",
                files={"file": ("sample.wav", b"RIFFfake", "audio/wav")},
                data={"threads": "128"},
            )

        self.assertEqual(response.status_code, 422)


if __name__ == "__main__":
    unittest.main()
