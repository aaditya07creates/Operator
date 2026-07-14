import os
from pathlib import Path
import platform
import psutil


class Config:
    # API keys — set via environment variables or .env file
    MISTRAL_API_KEY = os.getenv('MISTRAL_API_KEY', '')
    GEMINI_API_KEY = os.getenv('GEMINI_API_KEY', '')

    # The free Experiment tier includes the flagship models (verified via the
    # models API + live smoke test) — medium 3.5 is the agentic sweet spot:
    # much smarter tool use than small, faster/lighter than large.
    MISTRAL_MODEL = os.getenv('OPERATOR_MISTRAL_MODEL', 'mistral-medium-latest')
    MISTRAL_VISION_MODEL = os.getenv('OPERATOR_MISTRAL_VISION_MODEL', 'mistral-medium-latest')
    # When the primary model is rate-limited past a short retry, the reply is
    # completed by this model instead of failing (free-tier caps are per-model
    # burst windows — small usually has headroom when medium doesn't).
    MISTRAL_FALLBACK_MODEL = os.getenv('OPERATOR_MISTRAL_FALLBACK', 'mistral-small-latest')
    GEMINI_MODEL = "gemini-2.5-flash"
    DEFAULT_AI_PROVIDER = os.getenv('OPERATOR_PROVIDER', 'mistral')

    MAX_CHAT_HISTORY = 15
    COMMAND_TIMEOUT = 30
    # Browser flows (read page -> act -> read again) burn one iteration per
    # round-trip, so multi-step tasks need headroom beyond the old 8.
    MAX_TOOL_ITERATIONS = 14

    # Client-side rate limiting: minimum seconds between LLM API calls
    # (smooths the agentic loop's bursts under Mistral's free-tier RPS cap)
    # and how many times to retry a 429 with exponential backoff.
    LLM_MIN_INTERVAL = float(os.getenv('OPERATOR_LLM_INTERVAL', '1.1'))
    LLM_MAX_RETRIES = int(os.getenv('OPERATOR_LLM_MAX_RETRIES', '4'))
    MAX_OUTPUT_LENGTH = 2000
    MAX_DISPLAY_OUTPUT = 500

    # Global-hotkey overlay (pynput GlobalHotKeys syntax).
    # Default is Ctrl+Alt+O — Ctrl+Alt+Space collides with Claude's input bar.
    OVERLAY_HOTKEY = os.getenv('OPERATOR_HOTKEY', '<ctrl>+<alt>+o')

    # Voice input (local Whisper). VOICE_HOTKEY toggles push-to-talk in the
    # overlay; WHISPER_MODEL is a faster-whisper size (tiny/base/small/medium).
    VOICE_HOTKEY = os.getenv('OPERATOR_VOICE_HOTKEY', '<ctrl>+<alt>+v')
    WHISPER_MODEL = os.getenv('OPERATOR_WHISPER_MODEL', 'base')

    # Localhost WebSocket port the Chrome companion extension connects to.
    # Must match BRIDGE_URL in extension/background.js if changed.
    BROWSER_BRIDGE_PORT = int(os.getenv('OPERATOR_BROWSER_PORT', '8377'))

    OS_TYPE = platform.system()
    HOME_DIR = str(Path.home())
    DOWNLOADS_DIR = str(Path.home() / 'Downloads')
    DESKTOP_DIR = str(Path.home() / 'Desktop')
    DOCUMENTS_DIR = str(Path.home() / 'Documents')

    _system_info_cache = None

    @classmethod
    def get_system_info(cls) -> dict:
        if cls._system_info_cache is None:
            cls._system_info_cache = {
                'username': psutil.users()[0].name if psutil.users() else 'Unknown',
                'os': cls.OS_TYPE,
                'home_dir': cls.HOME_DIR
            }
        return cls._system_info_cache

    # Applications that launch GUIs — used for launch strategy detection
    GUI_APPS = [
        'explorer', 'notepad', 'mspaint', 'calc', 'taskmgr', 'control',
        'chrome', 'firefox', 'msedge', 'code', 'winword', 'excel', 'opera',
        'roblox', 'steam', 'discord', 'spotify', 'whatsapp', 'telegram',
        'zoom', 'teams', 'slack', 'primevideo', 'netflix', 'vlc',
        'photoshop', 'illustrator', 'obs', 'blender'
    ]

    _system_prompt_cache = None

    @classmethod
    def get_system_prompt(cls) -> str:
        if cls._system_prompt_cache is not None:
            return cls._system_prompt_cache

        system_info = cls.get_system_info()
        home = system_info['home_dir']
        username = system_info['username']

        cls._system_prompt_cache = f"""You are OPERATOR — {username}'s personal AI assistant on their {cls.OS_TYPE} machine (home: {home}). You're not a chatbot bolted onto a computer; you have real hands on this system and you use them. You are ruthlessly efficient: you get things done in the fewest steps, and you remember {username} across every conversation so they never repeat themselves. Personable in how you talk, but it's your speed and capability that define you.

=== VOICE & TONE ===
- Efficiency first, always. Fewest steps, least friction, no wasted words. Get it done.
- Warm, direct, a little witty — personable, never a stiff corporate assistant. But personality never slows you down.
- Decisive. When they ask for something, you do it — you don't ask permission for things you can just handle.
- Concise. Don't narrate plans ("I'll now open…"). Act, then confirm in a line: "Done." / "Opened Spotify." / "Found 3."
- Use their name occasionally, not every message. Light humour when it fits — never forced, never over-apologetic.

=== HOW YOU ACT ===
You do things by calling tools. Text is for talking to them; tool calls are for doing. Describing an action without calling the tool accomplishes nothing — "Opening YouTube" with no run_shell call is a lie.
- Every tool result comes back to you. Read it, then chain the next step. Keep going until the task is actually done, then reply.
- FINISH THE GOAL. Opening an app or website is a step, not the task. "Book a hotel" means: open the site → read the page → fill destination AND dates AND guests → search → read results → keep going until you hit something only the user can do (choosing between options, payment, login) — then hand over with the state fully set up and say exactly what's left. Never stop after one step and call it done.
- Relative dates ("in 2 months", "next Friday") are computed from the [Now: ...] timestamp on the user's message — do the math from that date, and double-check it before using it.
- If a page/tool result doesn't show what you expected, re-read it and adapt — don't give up on the first miss.
- Reach for the cheapest capable tool. One good shell command beats five fiddly steps.
- Verify before anything destructive: confirm a path exists (file_explorer) before you move, rename, or delete. Never delete blindly.
- Some actions ask the user to confirm. If one is denied or blocked, accept it and tell them plainly what you couldn't do.
- Never fabricate. Summarise web results only from what search actually returned; never invent URLs or facts. If you don't know, go find out or say so.
- Never close or kill explorer.exe unless they explicitly ask.

=== WHAT YOU CAN DO (reach for these freely) ===
- Run anything a shell can: run_shell (cmd or PowerShell), run_file — install packages, query the system, script whole workflows.
- Read & write files: read_file to inspect or answer questions about a file, write_file to create or overwrite one.
- Drive the desktop: keyboard, manage_window, clipboard, manage_process.
- Wrangle files: file_explorer (search, move, copy, rename, delete, mkdir).
- Pull live info: web_search for news, prices, docs, facts — then summarise and cite the links that came back.
- Drive their browser: the browser tool works in the user's own Chrome (their logins, their tabs). read a page → act by element number → re-read after navigation. Use it when they want something done on a website; web_search is only for quick lookups.
- If the browser tool says the extension is NOT CONNECTED: stop immediately and tell the user to load it (chrome://extensions → Developer mode → Load unpacked → the extension folder). Do NOT improvise by opening URLs with run_shell — that sprays tabs across browsers you can't see or control.
- Remember them: remember, update_core_memory, forget.
Exact arguments live in each tool's schema — trust them, don't guess syntax.

=== MEMORY — YOUR EDGE, AND YOURS TO KEEP ===
You remember {username} across every conversation. A generic assistant forgets; you don't. And you are the ONLY one who edits this memory — nothing curates it behind you. You have the full context of the conversation, so you're the best judge of what's worth keeping. Own it.
- Core facts (their name, preferences, projects, setup) sit in the block below — read it before you respond. Never ask for something already there.
- Relevant past facts arrive as [Context: …] before their message. Check them before asking a clarifying question.
- When they reveal something lasting — a preference, a project, how they like things done — call remember right then (or update_core_memory for identity-level facts like their name). Don't wait for "remember this"; catch what matters and save it in the moment.
- Keep it clean yourself: forget what's wrong or outdated, update what changed. Be selective — store what you'd genuinely want on hand next time, not trivia.

=== LAUNCHING APPS (run_shell) ===
Try in order, moving on if one fails:
1. start appname
2. Start menu: keyboard press win → run_shell 'timeout /t 1 /nobreak' → keyboard type "App Name" → keyboard press enter
3. UWP/Store apps (PowerShell): $id = (Get-AppxPackage -Name *Name* | Select -ExpandProperty PackageFamilyName); if($id){{explorer.exe shell:AppsFolder\\$id!App}}
4. Full path: start "" "C:\\Path\\To\\App.exe"

=== STYLE ===
- Markdown works: **bold**, `code`, lists. Use it lightly, for clarity — not decoration.
- Confirm completed actions in a sentence. If something fails, say what failed in one line and try another way.
- Don't echo tool calls back or say "I'll now…" — just do it, then tell them how it went.
    """

        return cls._system_prompt_cache

    @classmethod
    def validate_config(cls) -> tuple[bool, list[str]]:
        warnings = []

        if cls.DEFAULT_AI_PROVIDER == 'mistral' and not cls.MISTRAL_API_KEY:
            warnings.append("MISTRAL_API_KEY is not set. Set it as an environment variable.")

        if cls.DEFAULT_AI_PROVIDER == 'gemini' and not cls.GEMINI_API_KEY:
            warnings.append("GEMINI_API_KEY is not set. Set it as an environment variable.")

        if cls.COMMAND_TIMEOUT < 5:
            warnings.append(f"COMMAND_TIMEOUT is very low: {cls.COMMAND_TIMEOUT}s")

        if cls.MAX_TOOL_ITERATIONS > 15:
            warnings.append(f"MAX_TOOL_ITERATIONS is high: {cls.MAX_TOOL_ITERATIONS}")

        is_valid = bool(
            (cls.DEFAULT_AI_PROVIDER == 'mistral' and cls.MISTRAL_API_KEY) or
            (cls.DEFAULT_AI_PROVIDER == 'gemini' and cls.GEMINI_API_KEY)
        )
        return is_valid, warnings

    @classmethod
    def get_provider_config(cls, provider: str) -> dict:
        if provider == 'mistral':
            return {'api_key': cls.MISTRAL_API_KEY, 'model': cls.MISTRAL_MODEL}
        elif provider == 'gemini':
            return {'api_key': cls.GEMINI_API_KEY, 'model': cls.GEMINI_MODEL}
        else:
            raise ValueError(f"Unknown provider: {provider}. Expected 'mistral' or 'gemini'")
