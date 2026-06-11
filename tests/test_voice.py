import unittest
import subprocess
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

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

    def test_tts_response_does_not_expose_local_path(self):
        with patch.object(main, "VOICE_TTS_DIR", Path("/tmp/warpgate-test-tts")), \
             patch.object(main, "voice_health", return_value={"piper": {"available": True}}), \
             patch.object(main.subprocess, "run") as run:
            def fake_run(cmd, **kwargs):
                Path(cmd[-1]).parent.mkdir(parents=True, exist_ok=True)
                Path(cmd[-1]).write_bytes(b"RIFFfake")
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


if __name__ == "__main__":
    unittest.main()
