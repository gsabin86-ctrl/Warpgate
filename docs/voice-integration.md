# Warpgate Voice Console

Warpgate Voice Console exposes the local voice tools installed under `/home/greg/voice-arsenal`.

## Components

- Speech-to-text: whisper.cpp
- Browser-audio normalization: FFmpeg (`/usr/bin/ffmpeg` by default)
- STT binary: `/home/greg/voice-arsenal/whisper.cpp/build/bin/whisper-cli`
- STT model directory: `/home/greg/voice-arsenal/whisper-models/`
- Default STT model: `/home/greg/voice-arsenal/whisper-models/ggml-base.en.bin`
- Text-to-speech: Piper
- TTS binary: `/home/greg/voice-arsenal/piper/piper/piper`
- Piper voice directory: `/home/greg/voice-arsenal/piper-voices/`
- Default Piper voice: `/home/greg/voice-arsenal/piper-voices/en_US-amy-medium.onnx`

## Runtime directory

Generated speech files and temporary transcription uploads live under:

```text
/tmp/warpgate-voice
```

Generated TTS WAV files are kept temporarily for browser playback. Old voice files are cleaned up automatically. STT uploads and transcript files are removed after each transcription response.

## UI

Open the console from the sidebar:

```text
🎙 Voice Console
```

The console supports:

- generating WAV speech from text with Piper
- selecting discovered Piper voices
- tuning Piper speech speed, sentence silence, and leading silence
- transcribing uploaded audio with whisper.cpp
- selecting discovered Whisper models
- selecting English or automatic language detection
- permission-gated browser microphone push-to-talk transcription
- checking local voice tool availability

### Voice Settings

Use the `⚙ Settings` button inside Voice Console.

Settings are stored in browser `localStorage` under:

```text
warpgate_voice_settings_v2
```

They are browser-local preferences, not server secrets. Existing `warpgate_voice_settings_v1` preferences are migrated once to v2; unrelated voice/model choices are preserved, while the old `250ms` default is upgraded to `1000ms`.

TTS settings:

- Piper voice
- speech speed / Piper `length_scale`
- sentence silence
- leading silence in milliseconds

STT settings:

- Whisper model
- language (`en` or `auto`)

### First-word cutoff protection

Warpgate uses three protections for the first playback missing-first-word issue:

1. The Generate button immediately primes the browser audio output with a near-inaudible Web Audio signal while Piper generates the clip. This gives mobile Safari, Bluetooth, and sleeping audio routes time to wake under the original user gesture.
2. Backend TTS prepends configurable WAV silence, default `1000ms`, so the output remains warm before speech begins.
3. Frontend playback preloads the generated audio before calling `play()`.

If a browser or Bluetooth/speaker path still clips the beginning, increase `Leading Silence (ms)` in Voice Settings.

### Push-to-talk microphone behavior

The `🎙 Hold to Talk` button uses the browser microphone APIs:

```js
navigator.mediaDevices.getUserMedia({ audio: true })
MediaRecorder
```

Privacy and permission behavior:

- Warpgate cannot access a microphone until the browser grants permission.
- The permission prompt appears when push-to-talk starts.
- Recording only runs while the button is held.
- Warpgate stops microphone tracks immediately after recording.
- Recorded audio is sent to `/api/voice/stt` as a temporary upload.
- Warpgate normalizes browser WebM/Opus and other accepted formats to mono 16 kHz PCM WAV with FFmpeg before invoking whisper.cpp.
- Decoded audio is capped at five minutes and its normalized size is bounded before Whisper runs.
- The original upload, normalized WAV, transcript, and sidecar files are deleted after each request.

Browser requirements:

- `http://127.0.0.1:8000/` works for local testing.
- HTTPS access, such as Tailscale HTTPS, is recommended for access from another device.
- Plain HTTP from a different host may block microphone APIs because browsers require a secure context.

## API

### `GET /api/voice/health`

Reports configured voice paths and availability.

### `GET /api/voice/options`

Reports discovered voices, discovered Whisper models, and frontend defaults.

Response shape:

```json
{
  "tts": {
    "voices": [
      {
        "id": "en_US-amy-medium",
        "label": "en_US-amy-medium",
        "default": true
      }
    ],
    "defaults": {
      "voice_id": null,
      "speaker": null,
      "noise_scale": 0.667,
      "length_scale": 1.0,
      "noise_w": 0.8,
      "sentence_silence": 0.2,
      "leading_silence_ms": 1000
    }
  },
  "stt": {
    "models": [
      {
        "id": "base.en",
        "label": "base.en",
        "default": true
      }
    ],
    "defaults": {
      "model_id": null,
      "language": "en",
      "translate": false,
      "threads": 4,
      "beam_size": 5,
      "temperature": 0.0
    },
    "languages": ["en", "auto"]
  }
}
```

### `POST /api/voice/tts`

Request:

```json
{
  "text": "Warpgate voice console test. Power overwhelming.",
  "options": {
    "voice_id": "en_US-amy-medium",
    "length_scale": 1.0,
    "sentence_silence": 0.2,
    "leading_silence_ms": 250
  }
}
```

Response:

```json
{
  "status": "ok",
  "audio_url": "/api/voice/audio/tts-<id>.wav",
  "bytes": 123456
}
```

### `GET /api/voice/audio/{filename}`

Serves generated WAV files from `/tmp/warpgate-voice/tts` only.

### `POST /api/voice/stt`

Multipart upload fields:

```text
file
model_id
language
translate
threads
beam_size
temperature
```

Supported upload extensions:

```text
.wav .mp3 .ogg .flac .webm
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
python3 -m unittest discover -s tests -v
```

Check health:

```bash
curl -fsS http://127.0.0.1:8000/api/voice/health | python3 -m json.tool
```

Check discovered voice options:

```bash
curl -fsS http://127.0.0.1:8000/api/voice/options | python3 -m json.tool
```

Generate speech:

```bash
curl -fsS -X POST http://127.0.0.1:8000/api/voice/tts \
  -H 'Content-Type: application/json' \
  -d '{"text":"Warpgate voice console test. Power overwhelming.","options":{"leading_silence_ms":250}}'
```

Transcribe a known sample:

```bash
curl -fsS -X POST http://127.0.0.1:8000/api/voice/stt \
  -F 'file=@/home/greg/voice-arsenal/samples/piper-test.wav' \
  -F 'language=en'
```

Browser validation:

1. Open `http://127.0.0.1:8000/` or the HTTPS Tailscale URL.
2. Open `🎙 Voice Console`.
3. Open `⚙ Settings` and verify voice/model dropdowns populate.
4. Generate speech and confirm the first word is not clipped.
5. Hold `🎙 Hold to Talk`, grant microphone permission, speak, release, and verify transcription.
6. Check the browser console for JavaScript errors.

## Security and safety notes

- Backend subprocess calls use argv lists, not `shell=True`.
- TTS input is capped by `MAX_TTS_CHARS`.
- Voice jobs share a small semaphore so slow subprocesses do not stampede the server.
- Runtime voice directories are created with private permissions and symlink directories are rejected.
- Old generated voice files are cleaned up automatically.
- STT upload size is capped by `MAX_AUDIO_UPLOAD_BYTES`.
- Uploaded files receive generated server-side names and are removed after transcription.
- Original upload filenames are not used as filesystem paths.
- Served audio filenames are restricted to safe `.wav` names.
- Piper voice IDs and Whisper model IDs are constrained to safe filename-like IDs.
- Browser microphone access is permission-gated and microphone tracks are stopped after each recording.

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
