import unittest
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
