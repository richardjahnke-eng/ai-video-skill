# Install or update prompt

Paste the text below into Cursor or Claude Code on a Mac. It installs the skill the first time and updates it after that. The agent needs your approval once, to run the install outside its sandbox.

If you were given a zip instead of repository access, replace the clone step with: `<folder of the zip>/scripts/install --from <path to the zip> --yes`.

---

Install or update the analyze-video skill on this Mac.

1. If `~/.claude/skills/analyze-video/scripts/install` exists, run `~/.claude/skills/analyze-video/scripts/install --yes`.
   Otherwise run `git clone https://github.com/richardjahnke-eng/ai-video-skill.git ~/.claude/skills/analyze-video` and then `~/.claude/skills/analyze-video/scripts/install --yes`.
2. These commands use the network and write outside this project (Homebrew packages, `~/.claude/skills`, the Whisper model in `~/.cache/whisper`). Ask me once to approve running them outside the sandbox, then run them. Allow up to 30 minutes: the first run downloads a 1.6 GB model.
3. Do not edit any file in the skill folder. If a step fails, stop and show me its output.
4. When it finishes, tell me the `Version:` line and the `self-test passed` line it printed, and whether it warned about another copy of the skill.
