import unittest
from pathlib import Path

HTML = Path(__file__).resolve().parents[1] / "static" / "index.html"


class UiStaticTests(unittest.TestCase):
    def read_ui(self) -> str:
        return HTML.read_text()

    def test_external_badge_rendered_only_in_card_header(self):
        ui = self.read_ui()

        self.assertIn('const headerBadge = external', ui)
        self.assertNotIn('style="font-size:10px;margin-left:2px">◆ EXTERNAL</span>', ui)

    def test_settings_include_persistent_ui_label_control(self):
        ui = self.read_ui()

        self.assertIn('id="sv_ui_label"', ui)
        self.assertIn('function getUiLabel(port)', ui)
        self.assertIn('function saveUiLabel(port, label)', ui)
        self.assertIn('localStorage.setItem(`ollama_ui_label_${port}`', ui)
        self.assertIn('UI Label', ui)


if __name__ == "__main__":
    unittest.main()
