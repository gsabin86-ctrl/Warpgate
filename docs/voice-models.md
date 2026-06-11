# Warpgate Voice Models Manifest

Last updated: 2026-06-11

This manifest records Phase 2 voice-layer assets for Giga-Brain. Voice support is intentionally CLI-first before any Warpgate UI integration.

## Install root

Recommended local install/cache root:

```text
/home/greg/voice-arsenal
```

Proposed layout:

```text
/home/greg/voice-arsenal/
  whisper.cpp/
  whisper-models/
  piper/
  piper-voices/
  samples/
```

## Speech-to-text: Whisper via whisper.cpp

- Capability: speech-to-text / transcription
- Project source: https://github.com/ggerganov/whisper.cpp
- Model repository source: https://huggingface.co/ggerganov/whisper.cpp
- Exact first model file: `ggml-base.en.bin`
- Direct model URL: https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-base.en.bin
- Source verification: HF page and direct model URL returned HTTP 200.
- Target path: `/home/greg/voice-arsenal/whisper-models/ggml-base.en.bin`
- Reason for adding: fast CPU-friendly English transcription for voice memos, audio files, and future voice-command experiments.
- Validation command after install:

```bash
/home/greg/voice-arsenal/whisper.cpp/build/bin/whisper-cli \
  -m /home/greg/voice-arsenal/whisper-models/ggml-base.en.bin \
  -f /home/greg/voice-arsenal/samples/test.wav
```

- Rollback/removal command:

```bash
rm -rf /home/greg/voice-arsenal/whisper.cpp /home/greg/voice-arsenal/whisper-models
```

## Text-to-speech: Piper

- Capability: lightweight CPU-friendly local TTS
- Project source: https://github.com/rhasspy/piper
- Voice model source: https://huggingface.co/rhasspy/piper-voices
- Exact first voice model: `en_US-amy-medium.onnx`
- Exact first voice config: `en_US-amy-medium.onnx.json`
- Direct model URL: https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/amy/medium/en_US-amy-medium.onnx
- Direct config URL: https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/amy/medium/en_US-amy-medium.onnx.json
- Source verification: HF page and direct model/config URLs returned HTTP 200.
- Target path: `/home/greg/voice-arsenal/piper-voices/en_US-amy-medium.onnx`
- Reason for adding: fast local voice output for future spoken summaries/statuses.
- Validation command after install:

```bash
printf 'Warpgate voice test. Power overwhelming.' | \
  /home/greg/voice-arsenal/piper/piper/piper \
  --model /home/greg/voice-arsenal/piper-voices/en_US-amy-medium.onnx \
  --output_file /home/greg/voice-arsenal/samples/piper-test.wav
```

- Rollback/removal command:

```bash
rm -rf /home/greg/voice-arsenal/piper /home/greg/voice-arsenal/piper-voices
```

## Deferred voice candidate

### XTTS-v2

- Source: https://huggingface.co/coqui/XTTS-v2
- Status: deferred.
- Reason: heavier dependency footprint and possible GPU/VRAM concerns. Piper should prove the TTS path first.

## Integration rule

Do not integrate voice into Warpgate until CLI validation is reliable. The first useful integration target is likely a separate voice-service endpoint or Hermes-side helper, not a large Warpgate UI change.
