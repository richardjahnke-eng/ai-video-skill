---
name: analyze-video
description: >-
  Turns a local video or meeting recording into timestamped contact sheets and
  a transcript with ffmpeg and local whisper.cpp, or the transcript Zoom or
  Teams saved with it. Use when the user asks to review, watch, transcribe,
  summarize, or analyze a video or recording (.mp4, .mov, .webm, .mkv, .m4v,
  .m4a), including Zoom meetings and screen recordings. The recording stays on
  the machine.
---

# Analyze video

Process the file on this machine. Do not upload the video or its audio, and do not send either to a cloud transcription service.

## Run

Run the command from the root of the open project. The output goes into `_video/` there, which keeps it inside the agent sandbox and out of shared folders. Run this skill's entry script by its absolute path.

macOS and Linux:

```bash
/absolute/path/to/analyze-video/scripts/analyze_video "/absolute/path/to/video.mp4"
```

Windows:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File \absolute\path\to\analyze-video\scripts\analyze_video.ps1 "C:\path\to\video.mp4"
```

Take the video path from a directory listing and pass it exactly as listed. Recording names can hold characters that look like a plain space but are not one.

Zoom's local recordings are in `~/Documents/Zoom/<date time meeting name>/`, usually as `zoom_0.mp4`, with an audio-only `audio_only.m4a`. Use the `.mp4` unless the user asks for the audio file. An audio-only file gets a transcript and no sheets.

The command prints the path of `index.md`. The folder holds:

- `index.md`: duration, frame interval, and the sheet list
- `transcript.md`: the timestamped transcript, or a note that there is no audio
- `sheets/sheet_NNN.jpg`: contact sheets
- `frames/f_NNNN.jpg`: individual frames, already stamped with a timestamp
- `manifest.json`: source fingerprint and the settings used

If a `.vtt` transcript sits next to the recording (Zoom cloud recordings download with `…_Recording.transcript.vtt`, Teams with `<name>.vtt`), it is used instead of Whisper and keeps the speaker names. Pass `--whisper` to transcribe locally anyway, or `--transcript /path/to/file.vtt` to point at one with another name.

A second run with the same file and the same settings prints `already processed` and does not redo the work. A different interval, model, language, scene setting, prompt, frame cap, skip-frames choice, or transcript file processes it again.

If the command fails, stop and relay its output. Do not sample frames yourself as a substitute. If the output says setup is needed, or the Whisper model download is blocked, give the user the setup command it prints. They run it once in a Terminal. Run it yourself only if the user asks and approves running it outside the sandbox.

## Read the result

1. Read `index.md`.
2. Read `transcript.md` in full.
3. Read every contact sheet image.
4. Open one file under `frames/` only when a cell is unreadable.

If `index.md` says frames were skipped, read `transcript.md` and stop. There are no sheets.

## When the user wants different settings

Flags override `config.json` for that run. By default a frame is taken every 30 seconds and at every scene change (a new slide or window), and a long recording is capped at 96 frames (8 sheets). For more detail on a short recording:

```bash
/absolute/path/to/analyze-video/scripts/analyze_video "/absolute/path/to/video.mp4" --interval 5 --max-frames 0
```

On Windows, pass the same flags to `scripts/analyze_video.ps1`.

Pass `--prompt "terms already known for this video"` only when those names are already in the task. Do not invent a prompt. `--max-frames 0` removes the cap. Pass `--skip-frames` only when the user asks for a transcript or summary and does not ask to watch or review the picture.

Other flags: `--language en`, `--model medium`, `--no-scene`, `--scene-threshold 0.2`, `--min-scene-gap 1`, `--sheet-cols`, `--sheet-rows`, `--frame-width`, `--keep-audio`, `--output-root beside` (next to the video), `--config /path/to/config.json`.

Defaults and the full key list are in `config.json` and `README.md` in this skill folder. An English-only model (`medium.en` and the other `*.en` names) cannot use `"language": "auto"`.
