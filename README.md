# Analyze video

Version 2.0.

Local video review for coding agents. One command turns a recording into timestamped contact sheets and a transcript. ffmpeg picks the frames. whisper.cpp transcribes the audio on the same machine, unless the meeting tool already saved a transcript. The video and the audio are not uploaded.

The folder is an [Agent Skill](https://agentskills.io/): `SKILL.md` plus `scripts/analyze_video.py`. Cursor, Claude Code, Codex, and other apps that load that layout can use it.

## Install on a Mac (Cursor and Claude Code)

One copy in `~/.claude/skills/analyze-video/` serves both apps: Claude Code reads that folder, and Cursor reads it too. Run these in Terminal, not in an agent chat:

```bash
git clone https://github.com/richardjahnke-eng/ai-video-skill.git ~/.claude/skills/analyze-video
~/.claude/skills/analyze-video/scripts/install
```

`install` runs `scripts/setup`, which:

1. Installs `ffmpeg`, `whisper.cpp`, and Python with Homebrew if they are missing (it asks first; `--yes` skips the question).
2. Creates the skill's own Python environment in `.venv/` and installs Pillow there. Homebrew's Python refuses `pip install` into itself, and this keeps the skill independent of whichever `python3` is on PATH.
3. Records the programs it found in `~/.cache/analyze-video/preflight.json`.
4. Downloads the Whisper model (`ggml-large-v3-turbo.bin`, about 1.6 GB) into `~/.cache/whisper/`.
5. Runs a self-test on a short generated clip.

Setup runs outside the agent sandbox because it needs the network and writes outside any project. After it passes, a normal run only reads those files and writes into the open project, so Cursor's sandbox lets it run without asking.

From a zip instead of git: unzip it anywhere and run `scripts/install --from /path/to/ai-video-skill-main.zip`.

To have an agent do the install or update, paste the prompt in [`INSTALL-PROMPT.md`](INSTALL-PROMPT.md) into Cursor or Claude Code.

### Update

```bash
~/.claude/skills/analyze-video/scripts/install
```

A git checkout pulls. A copied folder is replaced from `--from`. Either way, `config.local.json` and `.venv/` are kept and setup runs again.

Install only one copy. Cursor also reads `~/.cursor/skills/`, `~/.agents/skills/`, and `~/.codex/skills/`, and lists the skill twice if it is in two of them. `install` warns when it finds another copy.

## What you get

Run from a project, the script writes into that project:

```text
_video/<meeting folder>--<recording name>/
  index.md
  transcript.md
  transcript.json
  manifest.json
  frames/f_0001.jpg
  sheets/sheet_001.jpg
```

The folder name includes the folder the recording is in, because meeting tools reuse names: every Zoom meeting folder holds a `zoom_0.mp4`. Names are reduced to ASCII letters, digits, `.`, `_`, and `-`. If two recordings still map to the same name, the second gets a short hash.

The first time `_video/` is created inside a git repository, the script adds `_video/` to that repository's `.git/info/exclude`. That file is not committed, so meeting transcripts stay out of git without changing the team's `.gitignore`.

`index.md` lists the duration, the interval, and every contact sheet. `transcript.md` has one line per spoken segment, `[start --> end] text`. A file with no audio track gets a one-line transcript and no Whisper run. A file with no video track, such as Zoom's audio-only `.m4a`, gets a transcript and no sheets. `manifest.json` stores the source size and modification time plus the settings. The same file with the same settings is skipped. Change the interval or the model and it runs again. A run that was killed (an agent timeout, a closed terminal) leaves a lock behind. The next run sees that its process is gone and takes over.

Some recordings store no duration, such as a `.webm` saved by a browser. The script then measures the file from its packet times. A recording in iCloud Drive that is not downloaded yet gets a warning: reading it downloads it first.

### Transcript

If the meeting tool saved a transcript next to the recording, it is used instead of Whisper:

- Zoom cloud recordings download as `GMT<date>-<time>_Recording_<size>.mp4` with `GMT<date>-<time>_Recording.transcript.vtt`. Its lines carry speaker names.
- Teams and others: `<recording name>.vtt` or `<recording name>.transcript.vtt`. `<v Name>` speaker tags become `Name: text`.

`--transcript /path/to/file.vtt` names another file. `--whisper`, or `"sidecar_transcript": false`, transcribes locally anyway.

Otherwise audio is extracted as 16 kHz mono WAV, passed to `whisper-cli`, then deleted. `transcript.json` stays. Set `"keep_audio": true` to leave `audio.wav` in the output folder. Whisper output has no speaker names.

### Frames

Frames are chosen two ways:

- A steady interval, every 30 seconds by default, including the first frame.
- A scene-change frame when the picture changes past the threshold (0.2) and at least 1 second has passed since the last frame. In a meeting that is mostly a new slide or a new shared window.

`max_frames` (default 96, which is 8 sheets) caps a long recording by widening the interval and the scene gap. An agent can read every sheet of a one-hour meeting that way. For a short recording, or for more detail, pass `--interval 5 --max-frames 0`.

Each frame is scaled to 1280 pixels wide, stamped with `HH:MM:SS`, then packed onto sheets of 4 columns by 3 rows. Cells are 480×270.

## Requirements

On a Mac, `scripts/setup` installs everything. Elsewhere, install these yourself:

- `python3` 3.9 or newer
- Pillow (`PIL`) 9.1 or newer for that interpreter (older Pillow works too)
- `ffmpeg` and `ffprobe` (5.1 or newer is best; older builds fall back to `-vsync`)
- `whisper-cli` (whisper.cpp)
- `curl`, for the first Whisper model download

macOS and Linux use `scripts/analyze_video`. Windows uses `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/analyze_video.ps1`. Without `-ExecutionPolicy Bypass`, Windows' default policy refuses to run the script, and so does any policy for a folder that came from a downloaded zip. Either one checks the programs once, then writes `~/.cache/analyze-video/preflight.json`. Later runs print nothing while the recorded programs still exist. A missing one is named, with the install command for that OS, and the command exits. Windows and Linux are less tested than macOS.

On first use of a model, the script downloads it into `~/.cache/whisper/` if setup has not. The default `large-v3-turbo` is multilingual, which `"language": "auto"` needs. An English-only model such as `medium.en` works only with `"language": "en"`.

## Settings

In Cursor, type `/configure` to open a settings page in the Cursor browser. It writes `config.local.json` in this folder. That file overrides `config.json`, is not in git, and survives updates. A command-line flag overrides both for one run. Unknown JSON keys are an error.

```json
{ "language": "en" }
```

| Key | Default | Meaning |
|---|---|---|
| `interval_sec` | `30` | Seconds between frames when the picture is quiet. Must be greater than 0. |
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
| `model` | `"large-v3-turbo"` | `tiny`, `tiny.en`, `base`, `base.en`, `small`, `small.en`, `medium`, `medium.en`, `large`, `large-v3-turbo`, or a path to a `.bin` file. |
| `language` | `"auto"` | A language code such as `en`, or `auto`. `auto` needs a multilingual model. |
| `threads` | `0` | Whisper threads. `0` uses half of the machine's CPU cores. |
| `keep_audio` | `false` | Leave the WAV in the output folder. |
| `font` | `""` | Optional `.ttf` path for timestamps. Empty uses Arial, DejaVu, Liberation, or a built-in bitmap font. |
| `model_dir` | `""` | Folder for downloaded models. Empty uses `~/.cache/whisper`. |
| `initial_prompt` | `""` | Words Whisper should expect. Empty passes no prompt. A prompt can make the model write those words into speech that did not include them. |
| `max_frames` | `96` | `0` means no cap. A positive number widens the interval and the scene gap so the frame count can stay under it. |
| `extract_frames` | `true` | `false` writes the transcript only. |
| `output_root` | `""` | Folder that gets `_video/`. Empty is the current directory (the open project). `"beside"` puts it next to the video, as before 2.0. |
| `sidecar_transcript` | `true` | Use a `.vtt` saved next to the recording instead of Whisper. |

```bash
scripts/analyze_video "/path/to/video.mp4"
scripts/analyze_video "/path/to/video.mp4" --interval 10
scripts/analyze_video "/path/to/video.mp4" --language en --model medium.en
scripts/analyze_video "/path/to/video.mp4" --no-scene
scripts/analyze_video "/path/to/video.mp4" --whisper
scripts/analyze_video "/path/to/video.mp4" --config /path/to/other.json
```

Also: `--scene-threshold`, `--min-scene-gap`, `--scene`, `--sheet-cols`, `--sheet-rows`, `--frame-width`, `--keep-audio`, `--no-keep-audio`, `--prompt`, `--max-frames`, `--skip-frames`, `--output-root`, `--transcript`, `--download-model`, `--self-test`.

The script refuses a file that is already inside a `_video` folder.

## Tests

From this folder:

```bash
python3 -m unittest discover -s tests -v
```

The tests build short videos with ffmpeg (they skip without it) and replace `whisper-cli` with a stand-in, so they need no model and no network. [`docs/TESTING-mac.md`](docs/TESTING-mac.md) is the hands-on checklist for a Mac with Cursor and Claude Code.

## Other installs

The Mac install above covers Cursor and Claude Code. For other layouts, copy this whole folder, or symlink it, so the host sees `SKILL.md` at the top of the skill directory. The script finds `config.json` by its own path. Keep `SKILL.md`, `scripts/`, and `config.json` together.

| App | User skill | Project skill |
|---|---|---|
| Claude Code | `~/.claude/skills/analyze-video/` | `<repo>/.claude/skills/analyze-video/` |
| Cursor | `~/.cursor/skills/analyze-video/` (or any folder above) | `<repo>/.cursor/skills/analyze-video/` |
| Codex | `~/.agents/skills/analyze-video/` | `<repo>/.agents/skills/analyze-video/` |

See [Cursor's skills docs](https://cursor.com/docs/skills) and [Codex's skills docs](https://developers.openai.com/codex/skills). Codex's sandbox, like Cursor's, blocks the network and writes outside the project, so run setup (or the first run) outside it.
