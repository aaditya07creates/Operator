# OPERATOR Command Reference

As of v5.0 you **don't type command syntax** — you describe what you want in
plain language and the AI calls the right tool. This page documents the tools
the AI can call and the `/slash` commands you type directly.

> Historical note: earlier versions used a `<command>file:create:path:content</command>`
> tag/colon-DSL. That's gone — the AI now uses native function-calling, which
> removed a whole class of parsing bugs (Windows paths, colons in content, etc.).

## Just talk to it

```
OPERATOR> open spotify
OPERATOR> put the last thing I copied into a new note on my desktop
OPERATOR> find every PDF in Documents modified this year
OPERATOR> write a python script that lists prime numbers up to 100 and run it
OPERATOR> what's the weather in Tokyo right now
OPERATOR> remember that I use Firefox, not Chrome
```

For multi-step tasks the AI chains tools automatically: it runs one, reads the
result, and decides the next step until the job is done.

## Tools the AI can call

| Tool | What it does |
|------|--------------|
| `run_shell` | Run a cmd/PowerShell command (launch apps, query the system, etc.) |
| `read_file` | Read a text file's contents (bare name → your OperatorPrograms folder) |
| `write_file` | Create/overwrite a file (bare name → your OperatorPrograms folder) |
| `run_file` | Run/open a file by type (.py, .html, .bat, .ps1, …) |
| `keyboard` | Press keys, chords, type text, or key sequences |
| `manage_window` | List/focus/close/minimize/maximize/resize/move windows, list monitors |
| `clipboard` | Get/set/append/clear clipboard, copy/paste, save a clipboard image |
| `manage_process` | List processes, info, top CPU/mem, check existence, kill |
| `file_explorer` | Search/list/info/storage/mkdir/move/copy/rename/delete |
| `web_search` | Live DuckDuckGo web or news search |
| `browser` | Act in your own Chrome via the companion extension: list tabs, open/navigate, read a page (text + numbered elements), click, fill forms, close tabs. See [extension/README.md](extension/README.md) |
| `remember` | Store a fact about you in long-term memory |
| `forget` | Remove a stored fact by id |
| `update_core_memory` | Update always-known identity / preference / project / fact |

Full schemas: [`operatorone/tool_specs.py`](operatorone/tool_specs.py).

## Safety

Every tool call is classified before it runs:

- **Safe** — runs automatically (reads, launches, web search, memory writes).
- **Caution** — asks first (keystroke injection, killing a process, `pip install`, writing outside the sandbox).
- **Dangerous** — asks first, shown prominently (deleting files, running a script, registry edits).
- **Blocked** — never runs (recursive delete of system/profile roots, `format`, disabling Defender, download-and-execute, killing critical processes).

Details: [`operatorone/safety.py`](operatorone/safety.py).

## Slash commands (you type these)

| Command | Description |
|---------|-------------|
| `/help` | List all commands |
| `/img [question]` | Screenshot + AI vision analysis |
| `/stats` | Execution statistics |
| `/memory` | Learned patterns and fixes |
| `/profile` | Your user profile |
| `/knowledge [category]` | Knowledge base facts |
| `/sessions` | Conversation history |
| `/storage` | Memory storage stats |
| `/core` | Core memory (Tier 1) contents |
| `/tiers` | Memory tier breakdown |
| `/forget <id>` | Remove a fact |
| `/cleanup` | Run data maintenance |
| `/paths` | Show data file locations |
| `/exit` | Quit |

Type `/` in either the terminal or the overlay to get autocomplete.

## Overlay mode

Run `python operatorone/main.py --overlay` (or `start.bat --overlay`). Press the
hotkey (default `Ctrl+Alt+O`, set `OPERATOR_HOTKEY` to change) to summon a
bar over any app. Type a request or `/tool`, press Enter to run, `Esc` to
dismiss. Risky actions pop a confirmation dialog.

## Tips

- Be specific about paths when it matters ("in my Downloads folder"); the AI
  can also search first if unsure.
- Say "remember …" to teach it a durable preference; it also learns implicitly.
- If an action needs confirmation, that's the safety layer — approve or deny.
- `--debug` prints verbose logs to the console; full logs are always written to
  `%LOCALAPPDATA%\OPERATOR\logs`.
