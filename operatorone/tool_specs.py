"""Provider-neutral tool definitions for the AI.

Each spec is {"name", "description", "parameters"} where parameters is a
plain JSON Schema object. llm_providers converts these to each vendor's
native function-calling format; executor.py maps names to handlers.
"""

from typing import Dict

TOOL_SPECS = [
    {
        "name": "run_shell",
        "description": (
            "Run a Windows shell command. Use for launching apps ('start notepad', "
            "'start https://url.com'), quick system queries, or anything without a "
            "dedicated tool. Use shell='powershell' for PowerShell syntax."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "The command line to execute"},
                "shell": {
                    "type": "string",
                    "enum": ["cmd", "powershell"],
                    "description": "Which shell to use (default cmd)"
                }
            },
            "required": ["command"]
        }
    },
    {
        "name": "write_file",
        "description": (
            "Create or overwrite a file with the given content. A bare filename "
            "saves to the user's OperatorPrograms folder; use an absolute path "
            "to save elsewhere."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Filename or absolute path"},
                "content": {"type": "string", "description": "Full file content"}
            },
            "required": ["path", "content"]
        }
    },
    {
        "name": "read_file",
        "description": (
            "Read a text file's contents. A bare filename reads from the user's "
            "OperatorPrograms folder; use an absolute path to read anywhere else. "
            "Returns up to ~100k characters of UTF-8 text (not for binary files). "
            "Use this to inspect or answer questions about a file's contents."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Filename or absolute path"}
            },
            "required": ["path"]
        }
    },
    {
        "name": "run_file",
        "description": (
            "Run or open a file by extension: .py runs with Python, .html opens in "
            "the browser, .bat/.ps1 run in a new console, anything else opens with "
            "its default application."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Filename or absolute path"}
            },
            "required": ["path"]
        }
    },
    {
        "name": "keyboard",
        "description": (
            "Send keystrokes to the currently focused window. Actions: 'press' one "
            "key, 'combo' for chords like ctrl+c, 'type' to type text, 'sequence' "
            "to press keys one after another. Keys: ctrl, shift, alt, win, enter, "
            "space, tab, escape, backspace, delete, arrows, f1-f12, a-z, 0-9."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["press", "combo", "type", "sequence"]},
                "keys": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Key names for press/combo/sequence (press uses the first)"
                },
                "text": {"type": "string", "description": "Text to type (for action='type')"}
            },
            "required": ["action"]
        }
    },
    {
        "name": "manage_window",
        "description": (
            "Manage application windows. Title matching is partial and "
            "case-insensitive ('Chrome' matches 'Google Chrome - YouTube'). "
            "Use action='list' first if unsure of titles."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["list", "monitors", "focus", "close", "minimize",
                             "maximize", "resize", "move", "to_monitor"]
                },
                "title": {"type": "string", "description": "Window title to match"},
                "width": {"type": "integer"},
                "height": {"type": "integer"},
                "x": {"type": "integer"},
                "y": {"type": "integer"},
                "monitor": {"type": "integer", "description": "Monitor number (1-indexed), for to_monitor"}
            },
            "required": ["action"]
        }
    },
    {
        "name": "clipboard",
        "description": (
            "Access the clipboard: 'get' reads text, 'set' replaces it, 'append' adds "
            "to it, 'clear' empties it, 'copy'/'paste' press Ctrl+C/Ctrl+V in the "
            "focused window, 'save_image' saves a clipboard image to a file."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["get", "set", "append", "clear", "copy", "paste", "save_image"]
                },
                "text": {"type": "string", "description": "Text for set/append"},
                "path": {"type": "string", "description": "Output path for save_image"}
            },
            "required": ["action"]
        }
    },
    {
        "name": "manage_process",
        "description": (
            "Inspect or manage running processes: 'list' running apps, 'info' about "
            "one process, 'top' consumers by cpu/memory, 'stats' for system CPU/RAM, "
            "'exists' to check by name or PID, 'kill' to terminate."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["list", "info", "top", "stats", "exists", "kill"]},
                "name": {"type": "string", "description": "Process name or PID"},
                "count": {"type": "integer", "description": "How many for 'top' (default 5)"},
                "sort_by": {"type": "string", "enum": ["cpu", "memory"], "description": "Metric for 'top'"}
            },
            "required": ["action"]
        }
    },
    {
        "name": "file_explorer",
        "description": (
            "File management. 'search' finds files by glob pattern, 'list' shows a "
            "directory, 'info' stats one item, 'storage' reports disk usage, 'mkdir' "
            "creates a directory, 'move'/'rename'/'copy'/'delete' modify items. "
            "Before delete/move, verify the path exists with 'info' or 'list' first."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["search", "list", "info", "storage", "mkdir",
                             "move", "rename", "copy", "delete", "delete_force"]
                },
                "path": {"type": "string", "description": "Target path (source for move/copy/rename)"},
                "destination": {"type": "string", "description": "Destination for move/copy"},
                "new_name": {"type": "string", "description": "New name for rename"},
                "pattern": {"type": "string", "description": "Glob pattern for search, e.g. *.py"}
            },
            "required": ["action"]
        }
    },
    {
        "name": "web_search",
        "description": (
            "Search the live web (DuckDuckGo). Set news=true for news results. "
            "Summarise from the returned results only; never invent URLs — only "
            "open links that appear in the results."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "max_results": {"type": "integer", "description": "1-10, default 5"},
                "news": {"type": "boolean", "description": "Search news instead of web"}
            },
            "required": ["query"]
        }
    },
    {
        "name": "browser",
        "description": (
            "Control the user's own Chrome browser (their real profile and logins) "
            "through the OPERATOR extension. Actions: 'tabs' lists open tabs, "
            "'open' opens a url in a new tab, 'navigate' goes to a url in the "
            "current/given tab, 'read' returns the page's text plus a numbered "
            "list of clickable/fillable elements, 'click' clicks element number N "
            "from the last read, 'fill' types into element N (submit=true presses "
            "Enter/submits), 'close_tab' closes a tab. Workflow: read first, then "
            "act by element number; re-read after any navigation. Prefer this over "
            "web_search when the user wants things done in their browser."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["tabs", "open", "navigate", "read", "click", "fill", "close_tab"]
                },
                "url": {"type": "string", "description": "For open/navigate"},
                "tab_id": {"type": "integer", "description": "Target tab id (default: active tab)"},
                "element": {"type": "integer", "description": "Element number from the last read"},
                "selector": {"type": "string", "description": "CSS selector alternative to element"},
                "text": {"type": "string", "description": "Text for fill"},
                "submit": {"type": "boolean", "description": "After fill, press Enter / submit the form"}
            },
            "required": ["action"]
        }
    },
    {
        "name": "remember",
        "description": (
            "Store a fact about the user or their environment in long-term memory. "
            "Use when the user shares preferences, corrections, or says 'remember this'."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "content": {"type": "string", "description": "The fact to remember"},
                "category": {"type": "string", "enum": ["personal", "technical", "general"]},
                "tags": {"type": "array", "items": {"type": "string"}}
            },
            "required": ["content"]
        }
    },
    {
        "name": "forget",
        "description": "Remove a stored fact by its id (e.g. when the user corrects outdated info).",
        "parameters": {
            "type": "object",
            "properties": {
                "fact_id": {"type": "string", "description": "Fact id like fact_042"}
            },
            "required": ["fact_id"]
        }
    },
    {
        "name": "update_core_memory",
        "description": (
            "Update always-available core memory: the user's identity (name, "
            "profession, location), a preference, an active project, or a critical "
            "fact the assistant should always know."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "section": {
                    "type": "string",
                    "enum": ["identity", "preference", "project", "important_fact"]
                },
                "key": {
                    "type": "string",
                    "description": "identity field (name/profession/location) or preference key"
                },
                "value": {"type": "string", "description": "The value / project text / fact text"}
            },
            "required": ["section", "value"]
        }
    },
]

TOOL_NAMES = {spec["name"] for spec in TOOL_SPECS}


def format_call(name: str, args: Dict) -> str:
    """Compact human-readable rendering of a tool call for logs and confirmations."""
    if name == "run_shell":
        shell = args.get("shell", "cmd")
        prefix = "PS> " if shell == "powershell" else "> "
        return f"{prefix}{args.get('command', '')}"
    if name == "write_file":
        return f"write_file: {args.get('path', '?')} ({len(args.get('content', ''))} chars)"
    if name == "read_file":
        return f"read_file: {args.get('path', '?')}"
    if name == "keyboard":
        action = args.get("action", "?")
        detail = args.get("text") if action == "type" else "+".join(args.get("keys") or [])
        return f"keyboard {action}: {detail}"
    if name == "web_search":
        return f"web_search: {args.get('query', '')}"
    if name == "browser":
        action = args.get("action", "?")
        detail = args.get("url") or args.get("selector") or (
            f"element {args['element']}" if args.get("element") is not None else "")
        if action == "fill" and args.get("text"):
            detail = f"{detail} ← '{str(args['text'])[:40]}'"
        return f"browser {action}: {detail}".rstrip(": ")
    if name == "remember":
        return f"remember: {args.get('content', '')[:60]}"

    parts = []
    for key in ("action", "path", "title", "name", "destination", "new_name",
                "pattern", "fact_id", "section", "key", "value", "monitor"):
        if args.get(key) not in (None, ""):
            parts.append(str(args[key]))
    return f"{name}: {' '.join(parts)}" if parts else name
