"""Tool-call executor.

Dispatches validated AI tool calls (name + typed args) to the ops modules
through a declarative registry — no string parsing. Every call is classified
by safety.assess(); CAUTION/DANGEROUS calls go through an injectable async
confirmation callback, BLOCKED calls never run. Blocking work runs in a
thread so the event loop stays responsive.
"""

import asyncio
import subprocess
import time
from dataclasses import dataclass
from typing import Awaitable, Callable, Dict, Optional, Tuple

import safety
import tool_specs
from config import Config
from logger_config import op_logger
from file_ops import FileOps
from key_ops import KeyOps
from window_ops import WindowOps
from clipboard_ops import ClipboardOps
from process_ops import ProcessOps
from file_explorer_ops import FileExplorerOps
from web_ops import WebOps


@dataclass
class ExecutionResult:
    """Result of one tool call."""
    command: str          # human-readable rendering of the call
    success: bool
    output: str
    error: str
    execution_time: float = 0.0

    def __bool__(self):
        return self.success


# Handler signature: (args: dict) -> (success, output, error)
OpResult = Tuple[bool, str, str]

# Type of the confirmation callback: (display, tier, reason) -> approved?
ConfirmCallback = Callable[[str, safety.RiskTier, str], Awaitable[bool]]


def _require(args: Dict, *names: str) -> Optional[str]:
    """Return an error message if any required argument is missing/empty."""
    missing = [n for n in names if args.get(n) in (None, "")]
    if missing:
        return f"Missing required argument(s): {', '.join(missing)}"
    return None


class CommandExecutor:
    def __init__(self, memory=None, core_memory=None,
                 confirm_callback: Optional[ConfirmCallback] = None):
        """
        Args:
            memory: MemoryManager (for remember/forget tools)
            core_memory: CoreMemory (for update_core_memory tool)
            confirm_callback: async callback approving CAUTION/DANGEROUS calls.
                              If absent, those calls are denied.
        """
        self.memory = memory
        self.core_memory = core_memory
        self.confirm_callback = confirm_callback
        self.execution_count = 0

        self._handlers: Dict[str, Callable[[Dict], OpResult]] = {
            "run_shell": self._run_shell,
            "write_file": self._write_file,
            "read_file": self._read_file,
            "run_file": self._run_file,
            "keyboard": self._keyboard,
            "manage_window": self._manage_window,
            "clipboard": self._clipboard,
            "manage_process": self._manage_process,
            "file_explorer": self._file_explorer,
            "web_search": self._web_search,
            "browser": self._browser,
            "remember": self._remember,
            "forget": self._forget,
            "update_core_memory": self._update_core_memory,
        }

    async def execute_tool_call(self, name: str, arguments: Dict) -> ExecutionResult:
        """Validate, confirm, and run one tool call."""
        start_time = time.time()
        self.execution_count += 1
        display = tool_specs.format_call(name, arguments or {})
        op_logger.command(display)

        handler = self._handlers.get(name)
        if handler is None:
            return self._finish(display, False, "", f"Unknown tool: {name}", start_time)

        verdict = safety.assess(name, arguments)

        if verdict.tier == safety.RiskTier.BLOCKED:
            op_logger.logger.warning(f"BLOCKED: {display} ({verdict.reason})")
            return self._finish(
                display, False, "",
                f"Blocked by safety policy: {verdict.reason}", start_time
            )

        if verdict.tier in (safety.RiskTier.CAUTION, safety.RiskTier.DANGEROUS):
            if self.confirm_callback is None:
                return self._finish(
                    display, False, "",
                    "This action requires user confirmation, but no confirmation "
                    "channel is available.", start_time
                )
            approved = await self.confirm_callback(display, verdict.tier, verdict.reason)
            if not approved:
                return self._finish(
                    display, False, "", "User declined this action.", start_time
                )

        try:
            success, output, error = await asyncio.to_thread(handler, arguments or {})
        except Exception as e:
            op_logger.logger.exception(f"Tool {name} crashed")
            success, output, error = False, "", f"{name} error: {e}"

        op_logger.command_result(display, success, len(output) + len(error))
        return self._finish(display, success, output, error, start_time)

    @staticmethod
    def _finish(display: str, success: bool, output: str, error: str,
                start_time: float) -> ExecutionResult:
        return ExecutionResult(
            command=display,
            success=success,
            output=output,
            error=error,
            execution_time=time.time() - start_time,
        )

    # ==================== Handlers ====================

    def _run_shell(self, args: Dict) -> OpResult:
        if err := _require(args, "command"):
            return False, "", err
        command = str(args["command"]).strip()
        shell = str(args.get("shell", "cmd")).lower()

        if shell == "powershell" and not command.lower().startswith("powershell"):
            command = f'powershell -NoProfile -NonInteractive -Command "{command}"'

        # App/URL launches return immediately; treat a quick timeout as success
        is_launch = command.lower().startswith(("start ", "explorer"))
        timeout = 5 if is_launch else Config.COMMAND_TIMEOUT

        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
                encoding='utf-8',
                errors='replace',
                cwd=Config.HOME_DIR,
            )
        except subprocess.TimeoutExpired:
            if is_launch:
                return True, "Application launched", ""
            return False, "", f"Command timeout ({timeout}s)"
        except Exception as e:
            return False, "", f"Execution error: {e}"

        output = (result.stdout or "").strip()
        error = (result.stderr or "").strip()
        success = result.returncode == 0

        if not success and not error:
            error = f"Command exited with code {result.returncode}"
        if success and is_launch and not output:
            output = "Application launched"

        # Cap huge outputs before they hit the model context
        if len(output) > Config.MAX_OUTPUT_LENGTH:
            output = output[:Config.MAX_OUTPUT_LENGTH] + "\n... (output truncated)"

        return success, output, error

    def _write_file(self, args: Dict) -> OpResult:
        if err := _require(args, "path", "content"):
            return False, "", err
        return FileOps.create_file(str(args["path"]), str(args["content"]))

    def _read_file(self, args: Dict) -> OpResult:
        if err := _require(args, "path"):
            return False, "", err
        return FileOps.read_file(str(args["path"]))

    def _run_file(self, args: Dict) -> OpResult:
        if err := _require(args, "path"):
            return False, "", err
        return FileOps.run_file(str(args["path"]))

    def _keyboard(self, args: Dict) -> OpResult:
        action = str(args.get("action", "")).lower()
        keys = [str(k) for k in (args.get("keys") or [])]
        text = str(args.get("text", ""))

        if action == "press":
            if not keys:
                return False, "", "keyboard press requires keys"
            return KeyOps.press_key(keys[0])
        if action == "combo":
            if not keys:
                return False, "", "keyboard combo requires keys"
            return KeyOps.key_combo(keys)
        if action == "type":
            if not text:
                return False, "", "keyboard type requires text"
            return KeyOps.type_text(text)
        if action == "sequence":
            if not keys:
                return False, "", "keyboard sequence requires keys"
            return KeyOps.key_sequence(keys)
        return False, "", f"Unknown keyboard action: {action}"

    def _manage_window(self, args: Dict) -> OpResult:
        action = str(args.get("action", "")).lower()
        title = str(args.get("title", ""))

        if action == "list":
            return WindowOps.list_windows()
        if action == "monitors":
            return WindowOps.get_monitor_info()

        if not title:
            return False, "", f"manage_window {action} requires a title"

        if action == "focus":
            return WindowOps.focus_window(title)
        if action == "close":
            return WindowOps.close_window(title)
        if action == "minimize":
            return WindowOps.minimize_window(title)
        if action == "maximize":
            return WindowOps.maximize_window(title)
        if action == "resize":
            if err := _require(args, "width", "height"):
                return False, "", err
            return WindowOps.resize_window(title, int(args["width"]), int(args["height"]))
        if action == "move":
            if args.get("x") is None or args.get("y") is None:
                return False, "", "manage_window move requires x and y"
            return WindowOps.move_window(title, int(args["x"]), int(args["y"]))
        if action == "to_monitor":
            if err := _require(args, "monitor"):
                return False, "", err
            return WindowOps.move_to_monitor(title, int(args["monitor"]))
        return False, "", f"Unknown window action: {action}"

    def _clipboard(self, args: Dict) -> OpResult:
        action = str(args.get("action", "")).lower()
        if action == "get":
            return ClipboardOps.get_text()
        if action == "set":
            if err := _require(args, "text"):
                return False, "", err
            return ClipboardOps.set_text(str(args["text"]))
        if action == "append":
            if err := _require(args, "text"):
                return False, "", err
            return ClipboardOps.append_text(str(args["text"]))
        if action == "clear":
            return ClipboardOps.clear()
        if action == "copy":
            return ClipboardOps.copy_current()
        if action == "paste":
            return ClipboardOps.paste_current()
        if action == "save_image":
            if err := _require(args, "path"):
                return False, "", err
            return ClipboardOps.save_image(str(args["path"]))
        return False, "", f"Unknown clipboard action: {action}"

    def _manage_process(self, args: Dict) -> OpResult:
        action = str(args.get("action", "")).lower()
        name = str(args.get("name", ""))

        if action == "list":
            return ProcessOps.list_processes()
        if action == "stats":
            return ProcessOps.system_stats()
        if action == "top":
            count = int(args.get("count") or 5)
            sort_by = str(args.get("sort_by") or "cpu")
            return ProcessOps.top_processes(count, sort_by)

        if not name:
            return False, "", f"manage_process {action} requires a name"

        if action == "kill":
            return ProcessOps.kill_process(name)
        if action == "info":
            return ProcessOps.process_info(name)
        if action == "exists":
            return ProcessOps.process_exists(name)
        return False, "", f"Unknown process action: {action}"

    def _file_explorer(self, args: Dict) -> OpResult:
        action = str(args.get("action", "")).lower()
        path = args.get("path")
        path_str = str(path) if path not in (None, "") else None

        if action == "search":
            if err := _require(args, "pattern"):
                return False, "", err
            return FileExplorerOps.search_files(str(args["pattern"]), path_str)
        if action == "list":
            return FileExplorerOps.list_directory(path_str)
        if action == "storage":
            return FileExplorerOps.get_storage_usage(path_str)

        if not path_str:
            return False, "", f"file_explorer {action} requires a path"

        if action == "info":
            return FileExplorerOps.get_item_info(path_str)
        if action == "mkdir":
            return FileExplorerOps.create_directory(path_str, nested=True)
        if action == "move":
            if err := _require(args, "destination"):
                return False, "", err
            return FileExplorerOps.move_item(path_str, str(args["destination"]))
        if action == "copy":
            if err := _require(args, "destination"):
                return False, "", err
            return FileExplorerOps.copy_item(path_str, str(args["destination"]))
        if action == "rename":
            if err := _require(args, "new_name"):
                return False, "", err
            return FileExplorerOps.rename_item(path_str, str(args["new_name"]))
        if action == "delete":
            return FileExplorerOps.delete_item(path_str, force=False)
        if action == "delete_force":
            return FileExplorerOps.delete_item(path_str, force=True)
        return False, "", f"Unknown file_explorer action: {action}"

    def _web_search(self, args: Dict) -> OpResult:
        if err := _require(args, "query"):
            return False, "", err
        query = str(args["query"])
        max_results = int(args.get("max_results") or 5)
        if args.get("news"):
            return WebOps.search_news(query, max_results)
        return WebOps.search(query, max_results)

    def _browser(self, args: Dict) -> OpResult:
        from browser_bridge import BrowserBridge

        action = str(args.get("action", "")).lower()
        if action not in ("tabs", "open", "navigate", "read", "click", "fill", "close_tab"):
            return False, "", f"Unknown browser action: {action}"
        if action in ("open", "navigate") and (err := _require(args, "url")):
            return False, "", err
        if action in ("click", "fill") and args.get("element") is None and not args.get("selector"):
            return False, "", f"browser {action} requires element (from read) or selector"
        if action == "fill" and (err := _require(args, "text")):
            return False, "", err

        params = {k: args[k] for k in
                  ("url", "tab_id", "element", "selector", "text", "submit")
                  if args.get(k) is not None}
        return BrowserBridge.get().request(action, params)

    def _remember(self, args: Dict) -> OpResult:
        if self.memory is None:
            return False, "", "Memory is not available"
        if err := _require(args, "content"):
            return False, "", err
        category = args.get("category", "general")
        if category not in ("personal", "technical", "general"):
            category = "general"
        tags = [str(t) for t in (args.get("tags") or [])]
        fact_id = self.memory.remember_fact(
            category=category,
            content=str(args["content"]),
            source="explicit",
            tags=tags,
        )
        return True, f"Remembered ({fact_id})", ""

    def _forget(self, args: Dict) -> OpResult:
        if self.memory is None:
            return False, "", "Memory is not available"
        if err := _require(args, "fact_id"):
            return False, "", err
        fact_id = str(args["fact_id"])
        if self.memory.forget_fact(fact_id):
            return True, f"Forgot {fact_id}", ""
        return False, "", f"No fact with id {fact_id}"

    def _update_core_memory(self, args: Dict) -> OpResult:
        if self.core_memory is None:
            return False, "", "Core memory is not available"
        if err := _require(args, "section", "value"):
            return False, "", err
        section = str(args["section"]).lower()
        key = str(args.get("key", ""))
        value = str(args["value"])

        if section == "identity":
            if key not in ("name", "profession", "location"):
                return False, "", "identity requires key of name/profession/location"
            self.core_memory.set_identity(key, value)
            return True, f"Core identity.{key} set", ""
        if section == "preference":
            if not key:
                return False, "", "preference requires a key"
            self.core_memory.add_preference(key, value)
            return True, f"Core preference {key} set", ""
        if section == "project":
            self.core_memory.add_project(value)
            return True, "Project added to core memory", ""
        if section == "important_fact":
            self.core_memory.add_custom_fact(value)
            return True, "Fact added to core memory", ""
        return False, "", f"Unknown core memory section: {section}"
