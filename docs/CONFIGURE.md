# Configure the skill from chat

`/configure` is a message you send in a Cursor chat. It is not an item in the Cursor menus or the command palette. Cursor loads this skill because the skill description says to use it when you type `/configure` or ask to change its settings. The agent then starts a small page on this computer and opens it in the Cursor browser.

The skill Cursor is using has to be this version. If chat does nothing with `/configure`, update the installed copy with `scripts/install` from this folder, then start a new chat.

## Open the page

1. Open a Cursor chat in a project where this skill is available.
2. Send:

   ```text
   /configure
   ```

   Any of these also work: “configure the AI Video skill”, “change the analyze-video settings”, “open the video skill settings”.

3. The agent runs `scripts/configure` and opens the printed address, which looks like `http://127.0.0.1:51022/`. That address stays on this machine. Nothing is uploaded.

Leave that server running while you use the page. Sending `/configure` again reuses the same address instead of starting a second page.

You can also start it yourself and open the printed address:

```bash
/absolute/path/to/analyze-video/scripts/configure
```

On Windows, run `python scripts/configure.py` with the skill’s Python.

## What the page does

The page lists every setting: pictures, contact sheets, the transcript, and where results are written. Each one has a short description and a control that fits it (a number, a choice, a menu, or a text field).

A valid change saves on its own. The page writes only the values that differ from the built-in `config.json`, into `config.local.json` beside the skill. That file is not in git and stays in place when the skill is updated. The next video uses it.

**Use built-in settings** deletes `config.local.json` and returns to the shipped defaults.

A value the skill would reject, such as a negative interval or an English-only Whisper model left on automatic language, stays unsaved and the page shows the reason.

A flag on one run still wins over the page. `/configure` changes the usual settings. Asking for a different interval or model on a single video does not change them.

## Stop the page

The page is a local server. Closing the browser tab does not stop it. Stop the terminal process that printed `configure: http://127.0.0.1:…/`, or end that command in the agent’s terminal. The next `/configure` starts a new address.
