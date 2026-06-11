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

    def test_main_status_uses_manager_backend_not_browser_localhost(self):
        ui = self.read_ui()
        start = ui.index('async function checkMainStatus()')
        end = ui.index('// ── Model list', start)
        check_main_status = ui[start:end]

        self.assertIn("fetch('/api/main-status'", check_main_status)
        self.assertNotIn('127.0.0.1:11434', check_main_status)

    def test_load_model_sends_runtime_options_from_saved_settings(self):
        ui = self.read_ui()
        start = ui.index('async function submitLoadModel()')
        end = ui.index('async function waitForLoadComplete', start)
        submit_load = ui[start:end]

        self.assertIn('const settings = getSettings(port)', submit_load)
        self.assertIn('const runtimeOptions = buildRuntimeOptions(settings)', submit_load)
        self.assertIn('body: JSON.stringify({ model, options: runtimeOptions })', submit_load)

    def test_settings_surface_reload_required_when_context_mismatches(self):
        ui = self.read_ui()

        self.assertIn('function buildRuntimeOptions(settings)', ui)
        self.assertIn('function contextMismatch(inst)', ui)
        self.assertIn('function applySettingsReloadFromButton(button)', ui)
        self.assertIn('data-model="${escapeAttr(loaded_model || \'\')}"', ui)
        self.assertIn('onclick="applySettingsReloadFromButton(this)"', ui)
        self.assertIn('Configured Context', ui)
        self.assertIn('Reload required', ui)
        self.assertIn('Apply & Reload', ui)


    def test_voice_console_ui_hooks_are_present(self):
        ui = self.read_ui()
        self.assertIn('Voice Console', ui)
        self.assertIn('id="voiceText"', ui)
        self.assertIn('id="voiceAudioFile"', ui)
        self.assertIn('async function loadVoiceHealth()', ui)
        self.assertIn('async function generateVoiceSpeech()', ui)
        self.assertIn('async function transcribeVoiceAudio()', ui)
        self.assertIn('/api/voice/health', ui)
        self.assertIn('/api/voice/tts', ui)
        self.assertIn('/api/voice/stt', ui)


if __name__ == "__main__":
    unittest.main()
