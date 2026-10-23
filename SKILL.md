---
name: analyze-video
description: >-
  Turns a local video into timestamped contact sheets and a transcript with
  ffmpeg and local whisper.cpp. Use when the user asks to review, watch,
  transcribe, or analyze a video file (.mp4, .mov, .webm, .mkv, .m4v),
  including a screen recording. The video and audio stay on the machine.
---

# Analyze video

Process the file on this machine. Do not upload the video or its audio, and do not send either to a cloud transcription service.

## Run

Run this skill's entry script by its absolute path. The working directory does not matter.

macOS and Linux:

```bash
/absolute/path/to/analyze-video/scripts/analyze_video "/absolute/path/to/video.mp4"
```

Windows:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File \absolute\path\to\analyze-video\scripts\analyze_video.ps1 "C:\path\to\video.mp4"
```

Take the video path from a directory listing and pass it exactly as listed. Recording names can hold characters that look like a plain space but are not one.

An audio-only file (such as Zoom's `.m4a`) works too. It gets a transcript and no sheets.

The script writes `<video folder>/_video/<recording name>/`:

- `index.md` — duration, frame interval, and the sheet list
- `transcript.md` — timestamped local transcript, or a note that there is no audio
- `sheets/sheet_NNN.jpg` — contact sheets
- `frames/f_NNNN.jpg` — individual frames, already stamped with a timestamp
- `manifest.json` — source fingerprint and the settings used

A second run with the same file and the same settings prints `already processed` and does not redo the work. A different interval, model, language, scene setting, prompt, frame cap, or skip-frames choice processes the file again.

If the command fails, stop and relay its output. Do not sample frames yourself as a substitute.

## Read the result

1. Read `index.md`.
2. Read `transcript.md` in full.
3. Read every contact sheet image.
4. Open one file under `frames/` only when a cell is unreadable.

If `index.md` says frames were skipped, read `transcript.md` and stop. There are no sheets.

## When the user wants different settings

Flags override `config.json` for that run. The usual change is the frame interval (default 5 seconds):

```bash
/absolute/path/to/analyze-video/scripts/analyze_video "/absolute/path/to/video.mp4" --interval 10
```

On Windows, pass the same flags to `scripts/analyze_video.ps1`.

Pass `--prompt "terms already known for this video"` only when those names are already in the task. Do not invent a prompt. Pass `--max-frames N` for a long recording. `0` means no cap. Pass `--skip-frames` only when the user asks for a transcript or summary and does not ask to watch or review the picture.

Other flags: `--language en`, `--model medium.en`, `--no-scene`, `--scene-threshold 0.2`, `--min-scene-gap 1`, `--sheet-cols`, `--sheet-rows`, `--frame-width`, `--keep-audio`, `--config /path/to/config.json`.

Defaults and the full key list are in `config.json` and `README.md` in this skill folder. An English-only model (`medium.en` and the other `*.en` names) cannot use `"language": "auto"`.
