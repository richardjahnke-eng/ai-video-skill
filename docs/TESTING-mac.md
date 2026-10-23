# Mac test checklist

For version 2.0 on an Apple Silicon Mac with Cursor and Claude Code. The automated tests (`python3 -m unittest discover -s tests -v`) cover the script logic. This list covers what only a real Mac, Homebrew, iCloud, and the agent sandboxes can show. Write the result next to each item.

## Setup

1. **Unit tests.** In the cloned folder: `python3 -m unittest discover -s tests -v`. Expect all tests to pass. If Pillow is missing for that `python3`, run them after setup with `.venv/bin/python -m unittest discover -s tests -v`.
2. **Clean install.** Remove `~/.claude/skills/analyze-video`, `~/.cache/analyze-video`, and (to test the download) `~/.cache/whisper/ggml-large-v3-turbo.bin`. Run the two Terminal commands from the README. Expect: the Homebrew question if something is missing, `Python: …/.venv/bin/python`, `passed`, a curl progress bar, `self-test passed`, and `Version: 2.0`.
3. **Homebrew Python.** Note whether `python3 -m pip install Pillow` fails with `externally-managed-environment` on this Mac. Setup should not need it either way.
4. **Second run.** Run `scripts/install` again. Expect `Updating the git checkout`, no model download, and `self-test passed`.
5. **Duplicate warning.** Make an empty `~/.cursor/skills/analyze-video` folder, run install, and expect the "another copy" note. Remove the folder after.
6. **Install prompt.** In a fresh Claude Code or Cursor chat, paste the prompt from `INSTALL-PROMPT.md`. Expect one approval request and the version and self-test lines in the reply.

## Cursor, sandbox on (the default)

Open a git repository as the workspace. Each item is one chat message, such as "review this recording: <path>".

7. **No approval needed.** A short `.mov` from the Desktop. Expect the command to run inside the sandbox without asking, output in `<workspace>/_video/Desktop--<name>-mov/`, and the agent reading the sheets. Write down if Cursor asked for anything, and what.
8. **Git exclude.** In that workspace, `git status` shows no `_video/`, and `.git/info/exclude` has one `_video/` line.
9. **Zoom local recording.** `~/Documents/Zoom/<meeting>/zoom_0.mp4` (macOS may ask Cursor for access to Documents the first time). Expect the folder name to start with the meeting folder's name, and slide changes to show up as frames.
10. **Audio only.** The same meeting's `audio_only.m4a`. Expect `Frames: skipped (no video track)` in `index.md`.
11. **Zoom cloud recording.** A downloaded `GMT…_Recording_….mp4` with its `GMT…_Recording.transcript.vtt` in the same folder. Expect `transcript.md` to start `From GMT…_Recording.transcript.vtt` and to carry speaker names. Then ask for `--whisper` and expect a Whisper transcript.
12. **Screen recording name.** A file named like `Screen Recording 2026-10-22 at 10.15.32 AM.mov` (macOS puts a special space before AM). Expect it to be found. If the agent retyped the name, the log says `the name differs only in spacing`.
13. **Browser recording.** A `.webm` from a browser recorder (for example Loom download or a MediaRecorder demo). Expect `the file stores no duration; reading packet times instead` and a normal result.
14. **Long meeting.** A recording of 45 minutes or more. Expect at most 96 frames (8 sheets) and `widened from 30s for max_frames 96` in `index.md`. Note how long the whole run took and the recording length.
15. **Killed run.** Start a long recording, then stop the agent's command partway. Run it again. Expect `removing the lock left by a run that stopped` and a complete result.
16. **Missing setup.** Rename `~/.cache/whisper/ggml-large-v3-turbo.bin`, run from Cursor, and expect a message naming `scripts/setup` instead of a hang or a raw curl error. Rename it back.
17. **iCloud.** If Desktop & Documents sync with iCloud: right-click a recording, choose Remove Download, then run it. Expect the iCloud warning, and either a normal result or a failure that says to download it in Finder.

## Maintenance

18. **Python upgraded under the skill.** Simulate a Homebrew Python upgrade by renaming `.venv` to `.venv-old`, then run the skill from Cursor. Expect the message to name `scripts/setup`. Run setup, expect a rebuilt `.venv`, and delete `.venv-old`.

## Claude Code

19. **Same skill.** In Claude Code, ask to review a recording from item 7 in another project. Expect the skill to be used from `~/.claude/skills/analyze-video` and output in that project's `_video/`.

## Report back

For each failure: the item number, the command output, and `~/.cache/analyze-video/preflight.json`.
