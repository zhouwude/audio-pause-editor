# Audio Pause Editor

Audio pause interval analysis and adjustment desktop application.

## Features

- Upload audio files (MP3, WAV, OGG, FLAC, M4A, AAC, WMA)
- Automatic silence gap detection using ffmpeg
- Visual waveform display with overlaid pause bars
- Per-pause duration editing with millisecond precision
- Real-time diff comparison (original vs adjusted)
- Regenerate audio with modified pause durations
- Noise sensitivity and minimum pause duration tuning

## Architecture

- **Electron** — Desktop shell
- **Python/FastAPI** — Backend audio processing
- **Vanilla JS** — Frontend UI with Canvas waveform

## Getting Started

```bash
npm install
npm run dev
```

## Build

```bash
npm run build
```
