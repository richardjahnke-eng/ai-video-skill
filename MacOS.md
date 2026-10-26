# Set up Analyze Video on macOS

These steps install the tools on a Mac, then connect the skill to Cursor, Claude Code, or Codex. The video and its audio stay on the Mac. The only download is the speech model, the first time a recording has audio.

You need about 2 GB of free disk space for that model. A transcription can take several minutes.

Use Terminal for the commands below. On a Mac with Apple silicon, Homebrew lives in `/opt/homebrew`. On an Intel Mac, it lives in `/usr/local`. The `brew` command works the same once Homebrew is installed.

## 1. Install Homebrew

Skip this step if `brew --version` prints a version.

1. Open Terminal.
2. Install Homebrew:

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

3. When the installer finishes, run the two commands it prints to add `brew` to your shell. They look like this on Apple silicon:

```bash
echo >> ~/.zprofile
echo 'eval "$(/opt/homebrew/bin/brew shellenv)"' >> ~/.zprofile
eval "$(/opt/homebrew/bin/brew shellenv)"
```

On an Intel Mac, the folder in those lines is `/usr/local` instead of `/opt/homebrew`.

4. Close Terminal, open it again, and run:

```bash
brew --version
```

## 2. Install the programs

The skill needs Python 3.9 or newer, Pillow, ffmpeg, ffprobe, whisper-cli, and curl. macOS already includes curl.

1. Install the video tools and the local speech engine:

```bash
brew install ffmpeg whisper-cpp
```

`ffmpeg` includes `ffprobe`. `whisper-cpp` includes `whisper-cli`.

2. Check Python:

```bash
python3 --version
```

If this prints `Python 3.9` or a newer 3.x version, keep going. If the command is missing, or the version is older than 3.9, install Python:

```bash
brew install python
```

Close Terminal, open it again, and run `python3 --version` once more. It must be 3.9 or newer.

3. Install Pillow for that same Python:

```bash
python3 -m pip install --user Pillow
```

If pip says the environment is externally managed, install Pillow for Homebrew’s Python and use that Python:

```bash
brew install python
"$(brew --prefix)/bin/python3" -m pip install --user Pillow
```

Then make sure a new Terminal window finds Homebrew’s `python3` before any other one. `which python3` should point inside the Homebrew folder.

4. Confirm every program is visible:

```bash
which python3 ffmpeg ffprobe whisper-cli curl
python3 -c "import PIL; print('Pillow', PIL.__version__)"
```

Each `which` line should print a path. The last line should print a Pillow version.

## 3. Get the skill folder

The folder has to stay together. `SKILL.md`, `config.json`, and `scripts/` must remain side by side.

If you already have the project folder, use it. Otherwise clone it:

```bash
git clone https://github.com/richardjahnke-eng/ai-video-skill.git
```

The clone is named `ai-video-skill`. When you connect it to an app below, the destination folder must be named `analyze-video`.

Make the Mac entry script executable:

```bash
chmod +x "/path/to/ai-video-skill/scripts/analyze_video" "/path/to/ai-video-skill/scripts/preflight"
```

Replace `/path/to/ai-video-skill` with the real folder.

## 4. Check the Mac before you connect an app

From the skill folder, run:

```bash
cd /path/to/ai-video-skill
./scripts/preflight
echo $?
```

No text, and `0`, means this Mac is ready. You only need to see that once.

If the command prints `prerequisite missing`, run the install line under each missing item, then run `./scripts/preflight` again.

## 5. Connect the skill to one app

Do the section for the app you use. A project install is available only in that project. A personal install is available in every project on this Mac.

Copy the folder with the commands below. To keep a single copy that updates in place, use `ln -s` instead of `cp -R` and keep the same destination path ending in `analyze-video`.

### Cursor, one project

1. Open the project in Finder or Terminal.
2. Create the skill folder and copy the files:

```bash
mkdir -p "/path/to/your-project/.cursor/skills"
cp -R /path/to/ai-video-skill "/path/to/your-project/.cursor/skills/analyze-video"
```

3. The project should now contain:

```text
your-project/.cursor/skills/analyze-video/SKILL.md
your-project/.cursor/skills/analyze-video/config.json
your-project/.cursor/skills/analyze-video/scripts/analyze_video
```

4. Quit Cursor and open it again.

### Cursor, every project

Current Cursor reads personal skills from your user Agent Store.

1. Find the skills folder Cursor is already using:

```bash
find "$HOME/Library/Application Support/Cursor/AgentStores" -type d -name skills
```

2. Copy the skill into the folder that command prints:

```bash
cp -R /path/to/ai-video-skill "/printed/path/skills/analyze-video"
```

3. Quit Cursor and open it again.

If that `find` command prints nothing, use this folder instead:

```bash
mkdir -p "$HOME/.cursor/skills"
cp -R /path/to/ai-video-skill "$HOME/.cursor/skills/analyze-video"
```

### Claude Code, every project

```bash
mkdir -p "$HOME/.claude/skills"
cp -R /path/to/ai-video-skill "$HOME/.claude/skills/analyze-video"
```

Quit Claude Code and open it again.

### Claude Code, one project

```bash
mkdir -p "/path/to/your-project/.claude/skills"
cp -R /path/to/ai-video-skill "/path/to/your-project/.claude/skills/analyze-video"
```

Open that project in Claude Code.

### Codex, every project

```bash
mkdir -p "$HOME/.codex/skills"
cp -R /path/to/ai-video-skill "$HOME/.codex/skills/analyze-video"
```

Quit Codex and open it again.

### Codex, one project

```bash
mkdir -p "/path/to/your-project/.codex/skills"
cp -R /path/to/ai-video-skill "/path/to/your-project/.codex/skills/analyze-video"
```

Open that project in Codex.

## 6. Try it

Put a short recording somewhere easy to find, such as your Desktop. In the app you connected, ask:

```text
Analyze this video: /Users/your-name/Desktop/recording.mp4
```

Use the real file path. The first recording that has audio downloads `ggml-medium.bin` (about 1.5 GB) into `~/.cache/whisper/`. Later recordings reuse that file.

When it finishes, look next to the video:

```text
Desktop/_video/recording/
  index.md
  transcript.md
  transcript.json
  sheets/
  frames/
```

`index.md` lists the contact sheets. `transcript.md` is the spoken text with timestamps. A silent recording still gets contact sheets, and `transcript.md` says there is no audio track.

Ask for a transcript only when you do not need the pictures. The agent can run the same command with `--skip-frames`. Ask it to pass `--max-frames` when the recording is long. Ask it to pass `--prompt` only for names you already know were spoken.

## 7. If a later run says something is missing

Run `./scripts/preflight` inside the skill folder again. Install only what it names, then retry. A successful check is saved in `~/.cache/analyze-video/preflight.json`, so later runs stay quiet while those programs remain installed.
