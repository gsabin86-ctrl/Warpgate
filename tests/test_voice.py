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


if __name__ == "__main__":
    unittest.main()
