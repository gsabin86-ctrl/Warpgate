# Warpgate Voice Console

Warpgate Voice Console exposes the local voice tools installed under `/home/greg/voice-arsenal`.

## Components

- Speech-to-text: whisper.cpp
- STT binary: `/home/greg/voice-arsenal/whisper.cpp/build/bin/whisper-cli`
- STT model: `/home/greg/voice-arsenal/whisper-models/ggml-base.en.bin`
- Text-to-speech: Piper
- TTS binary: `/home/greg/voice-arsenal/piper/piper/piper`
- Piper voice: `/home/greg/voice-arsenal/piper-voices/en_US-amy-medium.onnx`

## Runtime directory

Generated speech files and temporary transcription uploads live under:

```text
/tmp/warpgate-voice
```

This directory is disposable and should not be committed.

## UI

Open the console from the sidebar:

```text
🎙 Voice Console
```

The first integration supports:

- generating WAV speech from text with Piper
- transcribing uploaded audio with whisper.cpp
- checking local voice tool availability

Deferred for later:

- browser microphone recording
- voice-to-chat pipeline
- speaking model responses
- multiple selectable voices
- streaming progress

## API

### `GET /api/voice/health`

Reports configured voice paths and availability.

### `POST /api/voice/tts`

Request:

```json
{"text":"Warpgate voice console test. Power overwhelming."}
```

Response:

```json
{
  "status": "ok",
  "audio_url": "/api/voice/audio/tts-<id>.wav",
  "path": "/tmp/warpgate-voice/tts/tts-<id>.wav",
  "bytes": 123456
}
```

### `GET /api/voice/audio/{filename}`

Serves generated WAV files from `/tmp/warpgate-voice/tts` only.

### `POST /api/voice/stt`

Multipart upload field:

```text
file
```

Response:

```json
{
  "status": "ok",
  "transcript": "War paint voice test. Power overwhelming.",
  "input_filename": "piper-test.wav"
}
```

## Validation

Run tests:

```bash
cd /home/greg/ollama-project
.venv/bin/python -m unittest discover -s tests -v
```

Check health:

```bash
curl -fsS http://127.0.0.1:8000/api/voice/health | python3 -m json.tool
```

Generate speech:

```bash
curl -fsS -X POST http://127.0.0.1:8000/api/voice/tts \
  -H 'Content-Type: application/json' \
  -d '{"text":"Warpgate voice console test. Power overwhelming."}'
```

Transcribe a known sample:

```bash
curl -fsS -X POST http://127.0.0.1:8000/api/voice/stt \
  -F 'file=@/home/greg/voice-arsenal/samples/piper-test.wav'
```

## Security and safety notes

- Backend subprocess calls use argv lists, not `shell=True`.
- TTS input is capped by `MAX_TTS_CHARS`.
- STT upload size is capped by `MAX_AUDIO_UPLOAD_BYTES`.
- Uploaded files receive generated server-side names.
- Original upload filenames are not used as filesystem paths.
- Served audio filenames are restricted to safe `.wav` names.

## Disable voice without rollback

Voice can be disabled by making the configured tool paths unavailable via service environment overrides:

```text
WARPGATE_PIPER_BIN
WARPGATE_PIPER_VOICE
WARPGATE_WHISPER_BIN
WARPGATE_WHISPER_MODEL
```

If a path is missing, `/api/voice/health` reports the feature unavailable and the UI disables the corresponding button.

## Rollback

Use git rollback if voice integration causes trouble:

```bash
cd /home/greg/ollama-project
git log --oneline
# choose the commit before voice integration
git reset --hard <known-good-commit>
sudo systemctl restart ollama-manager.service
systemctl is-active ollama-manager.service
curl -fsS http://127.0.0.1:8000/api/instances
```

If the full voice integration has been tagged, rollback can use the previous stable tag from `docs/rollback.md` or a newer post-voice stable tag if one has been verified.
