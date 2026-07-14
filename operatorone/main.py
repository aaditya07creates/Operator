"""OPERATOR CLI entry point.

A single persistent async REPL: rich renders AI replies as markdown, shows a
spinner while work runs, and prompts for confirmation on risky tool calls;
prompt_toolkit provides input history and slash-command autocomplete.
"""

import argparse
import asyncio
import sys
from pathlib import Path

# Force UTF-8 so rich/logging never hit the cp1252 console codec on Windows
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding='utf-8', errors='replace')
    except (AttributeError, ValueError):
        pass

# Load .env from project root before Config is imported
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / '.env')
except ImportError:
    pass

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.text import Text

from prompt_toolkit import PromptSession
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.history import FileHistory
from prompt_toolkit.patch_stdout import patch_stdout

from config import Config
from logger_config import op_logger, enable_debug
from paths import Paths
from safety import RiskTier
from voice_input import VoiceInput

console = Console()

_voice = VoiceInput(Config.WHISPER_MODEL)

EXIT_WORDS = {"/exit", "/quit", "exit", "quit"}
VOICE_WORDS = {"/voice", "/v", "/listen"}

TIER_STYLE = {
    RiskTier.CAUTION: ("yellow", "CAUTION"),
    RiskTier.DANGEROUS: ("bold red", "DANGEROUS"),
}


def _make_confirm_callback(session: PromptSession):
    """Async confirmation prompt for CAUTION/DANGEROUS tool calls."""
    async def confirm(display: str, tier: RiskTier, reason: str) -> bool:
        style, label = TIER_STYLE.get(tier, ("yellow", tier.value.upper()))
        console.print(Panel(
            Text.assemble((f"{display}\n\n", "bold"), (reason, "dim")),
            title=f"[{style}]Confirm {label} action[/{style}]",
            border_style=style,
        ))
        try:
            answer = await session.prompt_async("  Allow this action? [y/N]: ")
        except (EOFError, KeyboardInterrupt):
            return False
        return answer.strip().lower() in ("y", "yes")

    return confirm


def _on_tool_event(display: str, success):
    """Live per-tool-call status line."""
    if success is None:
        console.print(f"[dim]▶ {display}[/dim]")
    elif success:
        console.print(f"[green]✓[/green] [dim]{display}[/dim]")
    else:
        console.print(f"[red]✗[/red] [dim]{display}[/dim]")


def _print_banner():
    console.print(Panel.fit(
        Text.assemble(
            ("OPERATOR", "bold cyan"),
            ("  ·  AI Terminal Assistant\n", "cyan"),
            ("Type ", "dim"), ("/help", "bold"), (" for tools, ", "dim"),
            ("/exit", "bold"), (" to quit.", "dim"),
        ),
        border_style="cyan",
    ))


async def _voice_capture() -> str:
    """Capture speech from the mic and return the transcript (or '')."""
    if not _voice.is_available():
        console.print(f"[yellow]Voice unavailable:[/yellow] {_voice.unavailable_reason()}")
        return ""
    if not _voice.model_ready():
        with console.status("[cyan]Loading speech model…[/cyan]", spinner="dots"):
            await asyncio.to_thread(_voice.ensure_model)
    with console.status("[cyan]🎤 Listening… speak, then pause[/cyan]", spinner="dots"):
        return await asyncio.to_thread(_voice.listen)


def _render_result(result):
    """Render a task result: markdown body, dim error footer if it failed."""
    message = (result.message or "").strip()
    if message:
        console.print(Markdown(message))
    if not result.success:
        console.print("[dim red]Task completed with errors.[/dim red]")


async def main_async(provider_name: str) -> int:
    is_valid, warnings = Config.validate_config()
    for w in warnings:
        console.print(f"[yellow]Warning:[/yellow] {w}")
    if not is_valid:
        console.print("[red]Configuration invalid.[/red] Set MISTRAL_API_KEY or GEMINI_API_KEY.")
        return 1

    history_file = str(Paths.get_user_data_dir() / 'history.txt')
    completer = WordCompleter(
        [f"/{name}" for name in _slash_command_names()],
        sentence=True, ignore_case=True,
    )
    session = PromptSession(history=FileHistory(history_file), completer=completer)

    # Build the core; importing here keeps startup errors inside the try below
    from orchestrator import OperatorCore
    with console.status("[cyan]Starting OPERATOR...[/cyan]", spinner="dots"):
        operator = OperatorCore(
            provider_name=provider_name,
            confirm_callback=_make_confirm_callback(session),
            on_tool_event=_on_tool_event,
        )

    _print_banner()

    while True:
        try:
            with patch_stdout():
                user_input = (await session.prompt_async("\nOPERATOR> ")).strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\nGoodbye!")
            break

        if not user_input:
            continue
        if user_input.lower() in EXIT_WORDS:
            console.print("Goodbye!")
            break

        if user_input.lower() in VOICE_WORDS:
            user_input = await _voice_capture()
            if not user_input:
                continue
            console.print(f"[cyan]🎤[/cyan] [bold]{user_input}[/bold]")

        try:
            with console.status("[cyan]Working...[/cyan]", spinner="dots"):
                result = await operator.process_task(user_input)
            _render_result(result)
        except Exception as e:
            op_logger.logger.exception(f"Unhandled error: {e}")
            console.print(f"[red]Error:[/red] {e}")

    operator.conversation_memory.end_session()
    operator.memory.learning_system.flush()
    return 0


def _slash_command_names():
    from tools import ToolRegistry
    names = set(ToolRegistry.list_tools())
    names.update({"exit", "quit", "help", "voice"})
    return sorted(names)


def run() -> int:
    parser = argparse.ArgumentParser(description="OPERATOR - AI terminal assistant")
    parser.add_argument("--provider", choices=["mistral", "gemini"],
                        default=Config.DEFAULT_AI_PROVIDER, help="AI provider")
    parser.add_argument("--debug", action="store_true", help="Verbose console logging")
    parser.add_argument("--overlay", action="store_true",
                        help="Run the global-hotkey overlay bar instead of the terminal REPL")
    args = parser.parse_args()

    if args.debug:
        enable_debug()

    if args.overlay:
        from overlay import run as run_overlay
        try:
            return run_overlay(args.provider)
        except KeyboardInterrupt:
            return 0

    try:
        return asyncio.run(main_async(args.provider))
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(run())
