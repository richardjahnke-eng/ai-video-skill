# Analyze video

Version 1.0.

Local video review for coding agents. One command turns a recording into timestamped contact sheets and a transcript. ffmpeg picks the frames. whisper.cpp transcribes the audio on the same machine. The video and the audio are not uploaded.

The folder is an [Agent Skill](https://agentskills.io/): `SKILL.md` plus `scripts/analyze_video.py`. Copy it into Cursor, Claude Code, Codex, or any other app that loads that layout.

## What you get

For `recording.mp4`, the script writes `recording.mp4`'s folder:

```text
_video/recording/
  index.md
  transcript.md
  transcript.json
  manifest.json
  frames/f_0001.jpg
  sheets/sheet_001.jpg
```

`index.md` lists the duration, the interval, and every contact sheet. `transcript.md` has one line per spoken segment, `[start --> end] text`. A file with no audio track gets a one-line transcript and no Whisper run. `manifest.json` stores the source size and modification time plus the settings. The same file with the same settings is skipped. Change the interval or the model and it runs again.

Frames are chosen two ways:

- A steady interval, every 5 seconds by default, including the first frame.
- A scene-change frame when the picture changes past the threshold (0.2) and at least 1 second has passed since the last frame.

Each frame is scaled to 1280 pixels wide, stamped with `HH:MM:SS`, then packed onto sheets of 4 columns by 3 rows. Cells are 480×270.

Audio is extracted as 16 kHz mono WAV, passed to `whisper-cli`, then deleted. `transcript.json` stays. Set `"keep_audio": true` to leave `audio.wav` in the output folder.

## Requirements

macOS and Linux use `scripts/analyze_video`. Windows uses `powershell -NoProfile -File scripts/analyze_video.ps1`. Either one checks these once, then writes `~/.cache/analyze-video/preflight.json`. Later runs print nothing while the recorded programs still exist. A missing one is named, with the install command for that OS, and the command exits. Nothing here is installed except the Whisper model file.

- `python3` 3.9 or newer
- Pillow (`PIL`) for that interpreter
- `ffmpeg` and `ffprobe`
- `whisper-cli` (whisper.cpp)
- `curl`, for the first Whisper model download

On first use of the default model, the script downloads `ggml-medium.bin` (multilingual Medium, about 1.5 GB) into `~/.cache/whisper/`. That model is required for `"language": "auto"`. An English-only model such as `ggml-medium.en.bin` works only with `"language": "en"`.

## Settings

Edit `config.json` in this folder. A command-line flag overrides the file for one run. Unknown JSON keys are an error.

| Key | Default | Meaning |
|---|---|---|
| `interval_sec` | `5` | Seconds between frames when the picture is quiet. Must be greater than 0. |
| `scene_threshold` | `0.2` | ffmpeg scene score that counts as a cut. `0` is sensitive, `1` is strict. |
| `min_scene_gap_sec` | `1` | Minimum time between a scene frame and the previous frame. |
| `scene_detection` | `true` | Set `false` to keep only the steady interval. |
| `frame_width` | `1280` | Width of each saved frame. Odd values are rounded down. |
| `sheet_cols` | `4` | Contact-sheet columns. |
| `sheet_rows` | `3` | Contact-sheet rows. |
| `cell_width` | `480` | Cell width in pixels. |
| `cell_height` | `270` | Cell height in pixels. |
| `label_height` | `36` | Caption strip under each cell. |
| `jpeg_quality` | `85` | JPEG quality for frames and sheets, 1–95. |
| `ffmpeg_q` | `3` | ffmpeg still-image quality (`-q:v`). Lower is higher quality. |
| `model` | `"medium"` | `tiny`, `tiny.en`, `base`, `base.en`, `small`, `small.en`, `medium`, `medium.en`, `large`, or a path to a `.bin` file. |
| `language` | `"auto"` | A language code such as `en`, or `auto`. `auto` needs a multilingual model. |
| `threads` | `0` | Whisper threads. `0` uses up to 8 cores. |
| `keep_audio` | `false` | Leave the WAV in the output folder. |
| `font` | `""` | Optional `.ttf` path for timestamps. Empty uses Arial, DejaVu, Liberation, or a built-in bitmap font. |
| `model_dir` | `""` | Folder for downloaded models. Empty uses `~/.cache/whisper`. |
| `initial_prompt` | `""` | Words Whisper should expect. Empty passes no prompt. A prompt can make the model write those words into speech that did not include them. |
| `max_frames` | `0` | `0` means no cap. A positive number widens the interval and the scene gap so the frame count can stay under it. |
| `extract_frames` | `true` | `false` writes the transcript only. |

```bash
scripts/analyze_video "/path/to/video.mp4"
scripts/analyze_video "/path/to/video.mp4" --interval 10
scripts/analyze_video "/path/to/video.mp4" --language en --model medium.en
scripts/analyze_video "/path/to/video.mp4" --no-scene
scripts/analyze_video "/path/to/video.mp4" --config /path/to/other.json
```

Also: `--scene-threshold`, `--min-scene-gap`, `--scene`, `--sheet-cols`, `--sheet-rows`, `--frame-width`, `--keep-audio`, `--no-keep-audio`, `--prompt`, `--max-frames`, `--skip-frames`.

Output always goes next to the video, in `_video/<recording name>/`. The script refuses a file that is already inside `_video`.

## Deploy

Copy this whole folder, or symlink it, so the host sees `SKILL.md` at the top of the skill directory. The script finds `config.json` by its own path, so the working directory does not matter. After it is in place, ask the agent to analyze a local video. The skill tells it to run the script and then read `index.md`, `transcript.md`, and every contact sheet.

### Cursor

Project skill, shared with that repository:

```text
<repo>/.cursor/skills/analyze-video/
```

Personal skill, available in every project on that machine: put the same folder in Cursor's user skills directory (`skills/analyze-video/` in the user Agent Store, or `~/.cursor/skills/analyze-video/` on builds that still read that path).

### Claude Code

User skill:

```text
~/.claude/skills/analyze-video/
```

Project skill:

```text
<repo>/.claude/skills/analyze-video/
```

### Codex

User skill:

```text
~/.codex/skills/analyze-video/
```

Project skill:

```text
<repo>/.codex/skills/analyze-video/
```

### Other agents

Any app that loads Agent Skills can use this folder unchanged. The agent instructions are `SKILL.md`. Human setup and the settings table are this file. Point the app at the folder; do not split `SKILL.md` away from `scripts/` and `config.json`.

## Optional case-review hook

A Cursor hook can call the script for every case video. On the machine where this folder was written, `~/.cursor/hooks/process-case-video.py` is a wrapper around `scripts/analyze_video.py`, so those reviews use the same `config.json` and flags. Other machines can skip that wrapper and rely on the skill alone.
