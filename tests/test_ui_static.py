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

        self.assertIn('await refreshSelectedModelMetadata(port, model)', submit_load)
        self.assertIn('const settings = validateContextBeforeLoad(port, model)', submit_load)
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

    def test_voice_settings_ui_hooks_are_present(self):
        ui = self.read_ui()

        self.assertIn('id="voiceSettingsBtn"', ui)
        self.assertIn('id="voiceSettingsPanel"', ui)
        self.assertIn('id="voicePiperVoice"', ui)
        self.assertIn('id="voiceLengthScale"', ui)
        self.assertIn('id="voiceLeadingSilenceMs"', ui)
        self.assertIn('id="voiceWhisperModel"', ui)
        self.assertIn('id="voiceLanguage"', ui)
        self.assertIn('function loadVoiceOptions()', ui)
        self.assertIn('function getVoiceSettings()', ui)
        self.assertIn('function saveVoiceSettings()', ui)
        self.assertIn('prepareVoicePlayerForPlayback', ui)

    def test_voice_requests_send_settings_and_preload_audio(self):
        ui = self.read_ui()

        self.assertIn('body: JSON.stringify({ text, options: settings.tts })', ui)
        self.assertIn('if (settings.stt.model_id) form.append', ui)
        self.assertIn("form.append('language', settings.stt.language)", ui)
        self.assertIn('async function prepareVoicePlayerForPlayback(player, audioUrl)', ui)
        self.assertIn("player.preload = 'auto'", ui)
        self.assertIn('await waitForAudioReady(player)', ui)

    def test_voice_push_to_talk_hooks_are_present(self):
        ui = self.read_ui()

        self.assertIn('id="voicePushToTalkBtn"', ui)
        self.assertIn('id="voiceMicStatus"', ui)
        self.assertIn('navigator.mediaDevices.getUserMedia', ui)
        self.assertIn('let voiceMediaRecorder = null', ui)
        self.assertIn('async function startVoicePushToTalk()', ui)
        self.assertIn('function stopVoicePushToTalk()', ui)
        self.assertIn('async function transcribeRecordedVoiceAudio(blob)', ui)
        self.assertIn('voiceMicStream.getTracks().forEach(track => track.stop())', ui)
        self.assertIn('const recordingStream = voiceMicStream', ui)
        self.assertIn('recordingStream?.getTracks().forEach(track => track.stop())', ui)

    def test_voice_modal_all_close_paths_stop_microphone(self):
        ui = self.read_ui()

        self.assertIn("if (id === 'voiceModal') stopVoicePushToTalk()", ui)
        self.assertIn("closeModal('voiceModal')", ui)
        self.assertIn("closeModal(el.id)", ui)

    def test_frontend_formats_object_shaped_errors(self):
        ui = self.read_ui()

        self.assertIn('function formatErrorMessage(value)', ui)
        self.assertIn('Array.isArray(value)', ui)
        self.assertIn('value.detail', ui)
        self.assertIn('JSON.stringify(value)', ui)
        self.assertIn("throw new Error(formatErrorMessage(d.detail || d || 'Failed'))", ui)

    def test_model_dropdown_options_have_dark_readable_theme(self):
        ui = self.read_ui()

        self.assertIn('.form-select option, .model-select option', ui)
        self.assertIn('background: var(--surface2)', ui)
        self.assertIn('color: var(--text)', ui)
        self.assertIn('.form-select option:checked, .model-select option:checked', ui)

    def test_context_length_uses_slider_controls(self):
        ui = self.read_ui()

        self.assertIn('id="s_num_ctx"', ui)
        self.assertIn("oninput=\"syncSlider('num_ctx')\"", ui)
        self.assertIn("oninput=\"syncSliderInput('num_ctx')\"", ui)
        self.assertIn('id="contextRangeHelp"', ui)
        self.assertIn("'num_ctx'", ui)

    def test_load_modal_fetches_model_metadata_before_loading(self):
        ui = self.read_ui()

        self.assertIn('let selectedModelMetadata = null', ui)
        self.assertIn('async function refreshSelectedModelMetadata(port, model)', ui)
        self.assertIn('/model-metadata?model=', ui)
        self.assertIn('selectedModelMetadata.context_length', ui)
        self.assertIn('validateContextBeforeLoad(port, model)', ui)

    def test_context_normalization_does_not_round_above_max(self):
        ui = self.read_ui()
        start = ui.index('function normalizeContextValue(value')
        end = ui.index('function contextBoundsForPort', start)
        normalize = ui[start:end]

        self.assertIn('Math.floor((clamped - min) / CONTEXT_STEP)', normalize)
        self.assertIn('Math.min(Math.max(stepped, min), max)', normalize)
        self.assertNotIn('Math.round(clamped / CONTEXT_STEP)', normalize)

    def test_cards_do_not_translate_or_animate_on_hover(self):
        ui = self.read_ui()
        start = ui.index('/* ── Cards ── */')
        end = ui.index('.card-header', start)
        card_css = ui[start:end]

        self.assertIn('transition: none;', card_css)
        self.assertIn('.card:hover { border-color:', card_css)
        self.assertNotIn('transition: border-color .2s, transform .2s, box-shadow .2s;', card_css)
        self.assertNotIn('.card:hover { transform:', card_css)


if __name__ == "__main__":
    unittest.main()
