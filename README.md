# OPERATOR

An AI-powered terminal assistant for Windows with full system control and a tiered memory system. Speak naturally — it opens apps, manages files, controls your keyboard, searches the web, and remembers context across sessions.

## Features

- Natural language → system commands (launch apps, manage files, control windows, run scripts)
- Real-time web search via DuckDuckGo (no API key needed)
- Screenshot + vision analysis (`/img`)
- Tiered memory: facts it learns about you persist and get curated automatically
- Smart retry — when a command fails, it asks the AI for alternatives using past fixes as context
- Supports Mistral AI and Google Gemini as AI providers

## Quick Start

```bash
# 1. Clone the repo
git clone https://github.com/yourname/operator.git
cd operator

# 2. Create and activate a virtual environment
python -m venv .venv
.venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Set your API key
copy .env.example .env
# Edit .env and add your MISTRAL_API_KEY or GEMINI_API_KEY

# 5. Run
python operatorone/main.py
```

Or use `start.bat` if you already have a `.venv` set up.

## Configuration

Copy `.env.example` to `.env` and fill in your key:

```env
MISTRAL_API_KEY=your_key_here
# GEMINI_API_KEY=your_key_here
# OPERATOR_PROVIDER=mistral
```

Get API keys:
- Mistral: https://console.mistral.ai/
- Gemini: https://aistudio.google.com/app/apikey

## Usage

```
OPERATOR> open spotify
OPERATOR> search the web for latest Python news
OPERATOR> find all PDF files in my documents
OPERATOR> create a python script that prints hello world and run it
OPERATOR> /img what's on my screen?
OPERATOR> /help
OPERATOR> /exit
```

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
| `/curate` | Force memory curation now |
| `/forget <id>` | Remove a fact |
| `/cleanup` | Run data maintenance |
| `/paths` | Show data file locations |
| `/exit` | Quit |

## Command Syntax

The AI generates these commands automatically. You can also type them directly.

```
# Applications
start spotify
start https://youtube.com

# Files
file:create:script.py:print("hello")
file:run:script.py
file:create-run:page.html:<html><body>Hello</body></html>

# Keyboard
key:press:enter
key:combo:ctrl:c
key:type:hello world
key:seq:win:r

# Windows
window:focus:Chrome
window:minimize:PyCharm
window:list

# Clipboard
clipboard:get
clipboard:set:some text

# Processes
process:list
process:kill:chrome
process:top:5:cpu

# File Explorer
file_explorer:search:*.py:C:/Users/you/Documents
file_explorer:list:C:/Downloads
file_explorer:move:C:/src.txt:C:/dest.txt
file_explorer:delete:C:/file.txt

# Web Search
web:search:Python tutorials
web:news:technology:5
```

## Memory System

OPERATOR uses a 4-tier memory system stored in `%LOCALAPPDATA%\OPERATOR\operator_learnings.json`.

| Tier | Name | Size | How It Works |
|------|------|------|--------------|
| 1 | Core | ~30 facts | Always injected into every AI prompt |
| 2 | Active | ~500 facts | Retrieved per-query by relevance scoring |
| 3 | Episodic | Unlimited | Session summaries and long-term memories |
| 4 | Archive | ~2000 max | Stale facts auto-demoted here |

Memory is curated automatically in the background every 6 interactions — the AI decides what to promote, demote, or delete.

## Project Structure

```
operatorone/
├── main.py                  Entry point — CLI loop
├── orchestrator.py          Core coordinator — wires all components together
├── config.py                All configuration: API keys, models, system prompt
│
├── command_generator.py     AI engine — sends prompts, extracts <command> tags
├── llm_providers.py         Mistral and Gemini provider wrappers
│
├── executor.py              Detects command type and routes to the right handler
├── file_ops.py              file:create, file:run, file:create-run
├── key_ops.py               key:press, key:combo, key:type, key:seq
├── window_ops.py            window:focus, window:minimize, window:list, etc.
├── clipboard_ops.py         clipboard:get, clipboard:set, etc.
├── process_ops.py           process:list, process:kill, process:top, etc.
├── file_explorer_ops.py     file_explorer:search, move, delete, list, etc.
├── web_ops.py               web:search and web:news via DuckDuckGo
│
├── tools.py                 /commands: /img, /stats, /memory, /core, etc.
├── validator.py             Blocks destructive or dangerous commands
│
├── memory.py                High-level memory API used by orchestrator
├── learning_system.py       JSON persistence layer for all memory data
├── core_memory.py           Tier 1 CRUD — identity, preferences, projects
├── context_retrieval.py     Tier 2 retrieval — relevance scoring per query
├── memory_curator.py        Background AI curation every 6 interactions
├── implicit_learning.py     Auto-extracts facts from conversations
├── conversation_memory.py   Session tracking and long-term memory
├── user_profiler.py         Builds a profile from interaction patterns
├── data_management.py       Maintenance — auto-demotion, archive pruning, backups
│
├── paths.py                 Resolves data directory paths cross-platform
├── logger_config.py         Logging setup
├── utils.py                 Shared utility functions
├── async_utils.py           Async helpers
└── __init__.py
```

## Requirements

- Windows (window management uses win32 APIs)
- Python 3.10+
- A Mistral or Gemini API key

See `requirements.txt` for the full dependency list.
