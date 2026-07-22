# Warpgate Voice Models Manifest

Last updated: 2026-07-21

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

## Additional installed Piper voice — Norman Medium

Installed 2026-07-21 as an optional voice; Amy remains the default.

- Voice ID: `en_US-norman-medium`
- Language: U.S. English
- Speaker: male, single speaker
- Quality: medium
- Sample rate: 22,050 Hz
- Dataset: approximately 15.5 hours of LibriVox recordings
- Dataset license: public domain
- Training: trained from scratch, avoiding dependency on the separately licensed Lessac training set
- Model card: `/home/greg/voice-arsenal/piper-voices/en_US-norman-medium.MODEL_CARD`
- Model: `/home/greg/voice-arsenal/piper-voices/en_US-norman-medium.onnx`
- Config: `/home/greg/voice-arsenal/piper-voices/en_US-norman-medium.onnx.json`
- Verified sample: `/home/greg/voice-arsenal/samples/norman-warpgate-test.wav`

SHA256:

```text
b9739443232a80a59c7d18810dd856899bf16a7964725f5ab81ea49b1351cb71  en_US-norman-medium.onnx
6c2db7f558a4a8deb9fe822583c1c5105f6c4e834dd0f9de8ad17a888ee9fe1d  en_US-norman-medium.onnx.json
```

Live Warpgate verification:

```text
The Warpgate is online. -> The warp gate is online.
Power overwhelming. -> Power overwhelming.
```

Rollback removes only the optional Norman assets and leaves Amy untouched:

```bash
rm /home/greg/voice-arsenal/piper-voices/en_US-norman-medium.onnx \
   /home/greg/voice-arsenal/piper-voices/en_US-norman-medium.onnx.json \
   /home/greg/voice-arsenal/piper-voices/en_US-norman-medium.onnx.sha256 \
   /home/greg/voice-arsenal/piper-voices/en_US-norman-medium.onnx.json.sha256 \
   /home/greg/voice-arsenal/piper-voices/en_US-norman-medium.MODEL_CARD
```

## Deferred voice candidate

### XTTS-v2

- Source: https://huggingface.co/coqui/XTTS-v2
- Status: deferred.
- Reason: heavier dependency footprint and possible GPU/VRAM concerns. Piper should prove the TTS path first.

## Integration rule

Do not expand voice beyond the current CLI-backed Warpgate Voice Console until the first integration remains stable. See `docs/voice-integration.md` for the API/UI integration details.

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
