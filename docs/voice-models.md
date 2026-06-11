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

## Installation result — 2026-06-11

Installed under:

```text
/home/greg/voice-arsenal
```

### Whisper.cpp

- Repo path: `/home/greg/voice-arsenal/whisper.cpp`
- Checked-out commit: `df7638d`
- Build command used:

```bash
cd /home/greg/voice-arsenal/whisper.cpp
cmake -B build -S . -DWHISPER_BUILD_TESTS=OFF
cmake --build build --config Release -j "$(nproc)"
```

- Binary: `/home/greg/voice-arsenal/whisper.cpp/build/bin/whisper-cli`
- Model: `/home/greg/voice-arsenal/whisper-models/ggml-base.en.bin`
- Model SHA256:

```text
a03779c86df3323075f5e796cb2ce5029f00ec8869eee3fdfb897afe36c6d002
```

### Piper

- Release: `2023.11.14-2`
- Binary archive: `piper_linux_x86_64.tar.gz`
- Binary: `/home/greg/voice-arsenal/piper/piper/piper`
- Voice model: `/home/greg/voice-arsenal/piper-voices/en_US-amy-medium.onnx`
- Voice config: `/home/greg/voice-arsenal/piper-voices/en_US-amy-medium.onnx.json`
- Voice SHA256:

```text
b3a6e47b57b8c7fbe6a0ce2518161a50f59a9cdd8a50835c02cb02bdd6206c18
```

- Voice config SHA256:

```text
95a23eb4d42909d38df73bb9ac7f45f597dbfcde2d1bf9526fdeaf5466977d77
```

### Validation

Piper generated:

```text
/home/greg/voice-arsenal/samples/piper-test.wav
```

Audio properties:

```text
mono 22050 Hz, 16-bit PCM, about 3.71 seconds
```

Whisper transcribed the Piper sample as:

```text
War paint voice test. Power overwhelming.
```

The phrase was originally `Warpgate voice test. Power overwhelming.` The transcription missed `Warpgate`, but the STT/TTS loop is functional and recognizable. Whisper timing for the sample was about 14.2 seconds total with `ggml-base.en.bin` on CPU.

### System dependency installed

`cmake` was installed with apt because the current `whisper.cpp` build system requires it.
