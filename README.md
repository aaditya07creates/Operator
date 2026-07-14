# OPERATOR

An AI desktop assistant for Windows with full system control and a tiered memory system. Talk to it naturally — it opens apps, manages files, controls your keyboard, searches the web, and remembers context across sessions. It runs as a terminal REPL **or** as a global-hotkey overlay bar that pops up over whatever app you're in.

## Features

- **Native tool-calling** — the AI drives the system through structured function calls (Mistral / Gemini function-calling APIs), not brittle text parsing. Multi-step tasks loop automatically: run a tool, read the result, decide the next step.
- **Global-hotkey overlay** — press a hotkey anywhere to summon a Spotlight-style input bar; type a request or `/` for a tool.
- **Risk-tiered safety** — every action is classified safe / caution / dangerous / blocked. Safe actions run automatically, risky ones ask first, catastrophic ones are hard-blocked.
- **Tiered memory, self-managed** — OPERATOR decides what to remember, update, and forget in first person as you talk (no background curator). Facts persist and get retrieved by relevance. Crash-safe atomic saves with backup recovery.
- **Voice input** — talk to it. Push-to-talk in the overlay (a hotkey), or `/voice` in the terminal. Speech is transcribed locally by Whisper (offline, no API cost), then run like any typed request. Optional install.
- **Your browser, driven by AI** — a tiny companion extension (see `extension/`) lets OPERATOR read pages, click, fill forms, and manage tabs **in the Chrome you already use** — your logins, your tabs. DOM-level text, no screenshots, localhost only. Reads are automatic; clicks/fills ask first.
- **Real-time web search** via DuckDuckGo (no API key needed).
- **Screenshot + vision analysis** (`/img`).
- Supports **Mistral AI** and **Google Gemini**.

## Quick Start

```bash
git clone https://github.com/yourname/operator.git
cd operator

python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

copy .env.example .env
# Edit .env and add MISTRAL_API_KEY or GEMINI_API_KEY

python operatorone/main.py            # terminal REPL
python operatorone/main.py --overlay  # global-hotkey overlay bar
```

Or just run `start.bat` — it creates the venv and installs dependencies on first run. Add `--overlay` to launch the overlay.

## Configuration

Copy `.env.example` to `.env`:

```env
MISTRAL_API_KEY=your_key_here
# GEMINI_API_KEY=your_key_here
# OPERATOR_PROVIDER=mistral
# OPERATOR_HOTKEY=<ctrl>+<alt>+o
# OPERATOR_VOICE_HOTKEY=<ctrl>+<alt>+v
# OPERATOR_WHISPER_MODEL=base   # tiny | base | small | medium
```

Get keys: [Mistral](https://console.mistral.ai/) · [Gemini](https://aistudio.google.com/app/apikey)

CLI flags: `--provider {mistral,gemini}`, `--overlay`, `--debug` (verbose console logging).

### Voice (optional)

```bash
pip install -r requirements-voice.txt
```

Then press the voice hotkey (default `Ctrl+Alt+V`) in the overlay to speak — it listens, transcribes locally, and runs what you said. In the terminal, type `/voice` and speak. Recording stops automatically when you pause. The model (~150 MB for `base`) downloads once on first use; everything runs offline after that. No mic or packages? Voice just stays off — nothing else changes.

## Usage

```
OPERATOR> open spotify
OPERATOR> search the web for the latest Python news
OPERATOR> find all PDF files in my documents
OPERATOR> create a python script that prints hello world and run it
OPERATOR> remember that I prefer Firefox
OPERATOR> /img what's on my screen?
OPERATOR> /voice        # speak your request instead of typing
OPERATOR> /help
OPERATOR> /exit
```

In **overlay mode**, press the hotkey (default `Ctrl+Alt+O`) to summon the bar over any app, type the same things, and press `Esc` to dismiss. Typing `/` shows tool autocomplete. Press the **voice hotkey** (default `Ctrl+Alt+V`) to speak instead of type.

## How it works

You describe intent in natural language. The AI decides which **tools** to call; each call is safety-checked, executed, and its result is fed back so the AI can chain further steps until the task is done. There's no command syntax to learn — the tool schemas live in [`tool_specs.py`](operatorone/tool_specs.py).

Tools available to the AI: `run_shell`, `read_file`, `write_file`, `run_file`, `keyboard`, `manage_window`, `clipboard`, `manage_process`, `file_explorer`, `web_search`, `browser`, `remember`, `forget`, `update_core_memory`.

### Browser control setup (optional, one time)

Load the companion extension into your everyday Chrome: `chrome://extensions` → enable **Developer mode** → **Load unpacked** → select the repo's `extension/` folder. It auto-connects to OPERATOR over `ws://127.0.0.1:8377` (localhost only) whenever OPERATOR runs — start order doesn't matter. Full details in [extension/README.md](extension/README.md).

### Safety tiers

| Tier | Behavior | Examples |
|------|----------|----------|
| **Safe** | Runs automatically | `dir`, `Get-Process`, launching apps, web search, reading files, memory writes |
| **Caution** | Asks for confirmation | keystroke injection, killing a process, writing outside the sandbox, `pip install` |
| **Dangerous** | Asks, shown prominently | deleting files, running a script, registry edits |
| **Blocked** | Never runs | recursive delete of system/profile roots, `format`, disabling Defender, download-and-execute, killing critical processes |

Classification lives in [`safety.py`](operatorone/safety.py).

## Slash Commands

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

## Memory System

A 4-tier store in `%LOCALAPPDATA%\OPERATOR\operator_learnings.json`, written atomically (temp file + rename) with a rotating `.bak` — a crash mid-write never corrupts your memory, and a corrupt file auto-recovers from backup.

| Tier | Name | Size | How It Works |
|------|------|------|--------------|
| 1 | Core | ~30 items | Always injected into every AI prompt |
| 2 | Active | ~500 facts | Retrieved per-query by relevance scoring |
| 3 | Episodic | Unlimited | Session summaries and long-term memories |
| 4 | Archive | ~2000 max | Stale facts auto-demoted here |

Retrieval bumps each returned fact's access stats, so frequently-used facts stay relevant and aren't wrongly archived. **OPERATOR manages its own memory in first person** — it decides what to `remember`, `update_core_memory`, or `forget` while the conversation is happening, because it has the context to judge what matters. There's no background LLM curator second-guessing it; only deterministic upkeep (dedup, size caps, access-based demotion) runs behind the scenes.

## Project Structure

```
operatorone/
├── main.py                  Entry point — CLI REPL (rich + prompt_toolkit); --overlay flag
├── overlay.py               Global-hotkey Spotlight-style overlay bar (Tkinter)
├── orchestrator.py          Core coordinator — the agentic tool loop
├── config.py                Configuration: API keys, models, system prompt, hotkey
│
├── command_generator.py     AI engine — builds prompt, exchanges tool-enabled turns
├── llm_providers.py         Mistral/Gemini providers with native tool-calling
├── tool_specs.py            JSON-schema definitions of every tool
│
├── executor.py              Registry dispatch: tool call → ops handler, with safety gating
├── safety.py                Risk-tier classification + hard denylist
├── file_ops.py · key_ops.py · window_ops.py · clipboard_ops.py
├── process_ops.py · file_explorer_ops.py · web_ops.py   The actual OS operations
│
├── tools.py                 /commands: /img, /stats, /core, etc.
├── voice_input.py           Local Whisper speech-to-text (optional, offline)
├── browser_bridge.py        Localhost WebSocket server for the Chrome extension
│
├── memory.py                High-level memory API
├── learning_system.py       Atomic, locked JSON persistence
├── memory_utils.py          Shared dedup / id-allocation / keyword helpers
├── core_memory.py           Tier 1 CRUD
├── context_retrieval.py     Tier 2 relevance scoring (+ access tracking)
├── conversation_memory.py · data_management.py
│
├── paths.py · logger_config.py · utils.py · __init__.py
extension/                   Chrome companion extension (manifest + background.js)
tests/                       pytest suite (safety, memory, executor, voice, browser, parsing)
```

## Development

```bash
pip install pytest
pytest
```

## Requirements

- Windows (window management uses win32 APIs)
- Python 3.10+
- A Mistral or Gemini API key

See `requirements.txt` for the full dependency list.
