
import subprocess
import re
from typing import Tuple
from dataclasses import dataclass
from enum import Enum

from config import Config
from learning_system import LearningSystem
from logger_config import op_logger
from file_ops import FileOps
from key_ops import KeyOps
from window_ops import WindowOps
from clipboard_ops import ClipboardOps
from process_ops import ProcessOps
from file_explorer_ops import FileExplorerOps
from web_ops import WebOps


class CommandType(Enum):
    """Types of commands for different execution strategies"""
    GUI_APP = "gui_app"
    CLI_COMMAND = "cli_command"
    POWERSHELL = "powershell"
    BATCH = "batch"
    FILE_OP = "file_op"       # File operations
    KEY_OP = "key_op"         # Keyboard operations
    WINDOW_OP = "window_op"   # Window management operations
    CLIPBOARD_OP = "clipboard_op"  # Clipboard operations
    PROCESS_OP = "process_op" # Process management operations
    FILE_EXPLORER_OP = "file_explorer_op"  # File explorer operations (search, move, rename, etc.)
    WEB_OP = "web_op"         # Web operations (search, news)


@dataclass
class ExecutionResult:
    """Result of command execution"""
    command: str
    success: bool
    output: str
    error: str
    execution_time: float = 0.0

    def __bool__(self):
        return self.success


class CommandExecutor:
    def __init__(self, memory: LearningSystem):
        self.memory = memory
        self.execution_count = 0

    async def execute(self, command: str) -> ExecutionResult:
        import time
        start_time = time.time()

        self.execution_count += 1
        op_logger.command(command)

        cmd_type = self._detect_command_type(command)

        if cmd_type == CommandType.FILE_OP:
            success, output, error = self._execute_file_operation(command)
        elif cmd_type == CommandType.KEY_OP:
            success, output, error = self._execute_key_operation(command)
        elif cmd_type == CommandType.WINDOW_OP:
            success, output, error = self._execute_window_operation(command)
        elif cmd_type == CommandType.CLIPBOARD_OP:
            success, output, error = self._execute_clipboard_operation(command)
        elif cmd_type == CommandType.PROCESS_OP:
            success, output, error = self._execute_process_operation(command)
        elif cmd_type == CommandType.FILE_EXPLORER_OP:
            success, output, error = await self._execute_file_explorer_operation(command)
        elif cmd_type == CommandType.WEB_OP:
            success, output, error = self._execute_web_operation(command)
        elif cmd_type == CommandType.GUI_APP:
            success, output, error = await self._execute_gui_app(command)
        elif cmd_type == CommandType.POWERSHELL:
            success, output, error = await self._execute_powershell(command)
        else:
            success, output, error = await self._execute_standard(command)

        execution_time = time.time() - start_time

        # Log result
        op_logger.command_result(command, success, len(output) + len(error))

        result = ExecutionResult(
            command=command,
            success=success,
            output=output,
            error=error,
            execution_time=execution_time
        )

        return result

    def _detect_command_type(self, command: str) -> CommandType:
        cmd_lower = command.lower()

        if cmd_lower.startswith('file:'):
            return CommandType.FILE_OP
        if cmd_lower.startswith('key:'):
            return CommandType.KEY_OP
        if cmd_lower.startswith('window:'):
            return CommandType.WINDOW_OP
        if cmd_lower.startswith('clipboard:'):
            return CommandType.CLIPBOARD_OP
        if cmd_lower.startswith('process:'):
            return CommandType.PROCESS_OP
        if cmd_lower.startswith('file_explorer:'):
            return CommandType.FILE_EXPLORER_OP
        if cmd_lower.startswith('web:'):
            return CommandType.WEB_OP
        if cmd_lower.startswith('powershell'):
            return CommandType.POWERSHELL
        if cmd_lower.startswith('start '):
            return CommandType.GUI_APP
        if any(app in cmd_lower for app in Config.GUI_APPS):
            return CommandType.GUI_APP
        if 'shell:appsfolder' in cmd_lower:
            return CommandType.GUI_APP

        return CommandType.CLI_COMMAND

    def _execute_file_operation(self, command: str) -> Tuple[bool, str, str]:
        try:
            parts = command.split(':', 3)

            if len(parts) < 3:
                return False, "", "Invalid file operation format"

            operation = parts[1].lower()

            if operation == 'create':
                if len(parts) < 4:
                    return False, "", "file:create requires path and content"
                filepath = parts[2]
                content = parts[3]
                return FileOps.create_file(filepath, content)

            elif operation == 'run':
                filepath = parts[2]
                return FileOps.run_file(filepath)

            elif operation == 'create-run':
                if len(parts) < 4:
                    return False, "", "file:create-run requires path and content"
                filepath = parts[2]
                content = parts[3]
                return FileOps.create_and_run(filepath, content)

            else:
                return False, "", f"Unknown file operation: {operation}"

        except Exception as e:
            return False, "", f"File operation error: {str(e)}"

    def _execute_key_operation(self, command: str) -> Tuple[bool, str, str]:
        try:
            parts = command.split(':', 2)

            if len(parts) < 3:
                return False, "", "Invalid key operation format"

            operation = parts[1].lower()
            args = parts[2]

            if operation == 'press':
                return KeyOps.press_key(args)

            elif operation == 'combo':
                keys = args.split(':')
                return KeyOps.key_combo(keys)

            elif operation == 'type':
                return KeyOps.type_text(args)

            elif operation == 'seq':
                keys = args.split(':')
                return KeyOps.key_sequence(keys)

            else:
                return False, "", f"Unknown key operation: {operation}"

        except Exception as e:
            return False, "", f"Key operation error: {str(e)}"

    def _execute_window_operation(self, command: str) -> Tuple[bool, str, str]:
        try:
            parts = command.split(':', 1)

            if len(parts) < 2:
                return False, "", "Invalid window operation format"

            rest = parts[1]
            sub_parts = rest.split(':', 1)
            operation = sub_parts[0].lower()

            if operation == 'list':
                return WindowOps.list_windows()

            elif operation == 'monitors':
                return WindowOps.get_monitor_info()

            # Operations requiring window title
            if len(sub_parts) < 2:
                return False, "", f"window:{operation} requires window title"

            window_title = sub_parts[1]

            if operation == 'focus':
                return WindowOps.focus_window(window_title)

            elif operation == 'close':
                return WindowOps.close_window(window_title)

            elif operation == 'minimize':
                return WindowOps.minimize_window(window_title)

            elif operation == 'maximize':
                return WindowOps.maximize_window(window_title)

            elif operation == 'resize':
                # Format: window:resize:Title:width:height
                resize_parts = window_title.rsplit(':', 2)
                if len(resize_parts) < 3:
                    return False, "", "window:resize requires title:width:height"
                title, width, height = resize_parts[0], resize_parts[1], resize_parts[2]
                try:
                    return WindowOps.resize_window(title, int(width), int(height))
                except ValueError:
                    return False, "", "Width and height must be numbers"

            elif operation == 'move':
                # Format: window:move:Title:x:y
                move_parts = window_title.rsplit(':', 2)
                if len(move_parts) < 3:
                    return False, "", "window:move requires title:x:y"
                title, x, y = move_parts[0], move_parts[1], move_parts[2]
                try:
                    return WindowOps.move_window(title, int(x), int(y))
                except ValueError:
                    return False, "", "X and Y must be numbers"

            elif operation == 'monitor':
                # Format: window:monitor:Title:monitor_num
                monitor_parts = window_title.rsplit(':', 1)
                if len(monitor_parts) < 2:
                    return False, "", "window:monitor requires title:monitor_number"
                title, monitor_num = monitor_parts[0], monitor_parts[1]
                try:
                    return WindowOps.move_to_monitor(title, int(monitor_num))
                except ValueError:
                    return False, "", "Monitor number must be a number"

            else:
                return False, "", f"Unknown window operation: {operation}"

        except Exception as e:
            return False, "", f"Window operation error: {str(e)}"

    def _execute_clipboard_operation(self, command: str) -> Tuple[bool, str, str]:
        try:
            parts = command.split(':', 2)

            if len(parts) < 2:
                return False, "", "Invalid clipboard operation format"

            operation = parts[1].lower()

            if operation == 'get':
                return ClipboardOps.get_text()

            elif operation == 'set':
                if len(parts) < 3:
                    return False, "", "clipboard:set requires text"
                text = parts[2]
                return ClipboardOps.set_text(text)

            elif operation == 'clear':
                return ClipboardOps.clear()

            elif operation == 'copy':
                return ClipboardOps.copy_current()

            elif operation == 'paste':
                return ClipboardOps.paste_current()

            elif operation == 'image':
                if len(parts) < 3:
                    return False, "", "clipboard:image requires filepath"
                filepath = parts[2]
                return ClipboardOps.save_image(filepath)

            elif operation == 'length':
                return ClipboardOps.get_length()

            elif operation == 'append':
                if len(parts) < 3:
                    return False, "", "clipboard:append requires text"
                text = parts[2]
                return ClipboardOps.append_text(text)

            else:
                return False, "", f"Unknown clipboard operation: {operation}"

        except Exception as e:
            return False, "", f"Clipboard operation error: {str(e)}"

    def _execute_process_operation(self, command: str) -> Tuple[bool, str, str]:
        try:
            parts = command.split(':', 2)

            if len(parts) < 2:
                return False, "", "Invalid process operation format"

            operation = parts[1].lower()

            if operation == 'list':
                return ProcessOps.list_processes()

            elif operation == 'stats':
                return ProcessOps.system_stats()

            # Operations requiring identifier/argument
            if len(parts) < 3:
                return False, "", f"process:{operation} requires additional arguments"

            arg = parts[2]

            if operation == 'kill':
                return ProcessOps.kill_process(arg)

            elif operation == 'info':
                return ProcessOps.process_info(arg)

            elif operation == 'start':
                return ProcessOps.start_process(arg)

            elif operation == 'exists':
                return ProcessOps.process_exists(arg)

            elif operation == 'top':
                # Format: process:top:count:metric
                top_parts = arg.split(':', 1)
                count = int(top_parts[0]) if top_parts[0].isdigit() else 5
                metric = top_parts[1] if len(top_parts) > 1 else 'cpu'
                return ProcessOps.top_processes(count, metric)

            elif operation == 'priority':
                # Format: process:priority:name:level
                priority_parts = arg.rsplit(':', 1)
                if len(priority_parts) < 2:
                    return False, "", "process:priority requires name:level"
                identifier, priority = priority_parts[0], priority_parts[1]
                return ProcessOps.set_priority(identifier, priority)

            else:
                return False, "", f"Unknown process operation: {operation}"

        except Exception as e:
            return False, "", f"Process operation error: {str(e)}"

    async def _execute_file_explorer_operation(self, command: str) -> Tuple[bool, str, str]:
        try:
            parts = command.split(':', 2)

            if len(parts) < 2:
                return False, "", "Invalid file_explorer operation format"

            operation = parts[1].lower()

            # Define sensitive operations that need confirmation
            sensitive_ops = ['move', 'rename', 'copy', 'delete', 'delete_force', 'mkdir', 'mkdirs']
            needs_confirmation = operation in sensitive_ops

            # Operations without arguments
            if operation == 'list':
                if len(parts) >= 3:
                    return FileExplorerOps.list_directory(parts[2])
                else:
                    return FileExplorerOps.list_directory()

            # Operations requiring path/arguments
            if len(parts) < 3:
                return False, "", f"file_explorer:{operation} requires additional arguments"

            arg = parts[2]

            if needs_confirmation:
                descriptions = {
                    'mkdir': f"Create directory: {arg}",
                    'mkdirs': f"Create nested directories: {arg}",
                    'delete': f"Delete file/folder: {arg}",
                    'delete_force': f"Force delete folder (including all contents): {arg}"
                }

                # For operations with source:dest format
                if operation in ['move', 'rename', 'copy']:
                    args_split = arg.split(':', 1)
                    if len(args_split) == 2:
                        source, dest = args_split
                        descriptions_multi = {
                            'move': f"Move {source} to {dest}",
                            'rename': f"Rename {source} to {dest}",
                            'copy': f"Copy {source} to {dest}"
                        }
                        description = descriptions_multi.get(operation, f"Execute: {command}")
                    else:
                        description = f"Execute: {command}"
                else:
                    description = descriptions.get(operation, f"Execute: {command}")

                confirmed = await self._request_user_confirmation(command, description)

                if not confirmed:
                    return False, "Operation cancelled by user", ""

            # Execute the operation
            if operation == 'search':
                # Format: file_explorer:search:pattern:path
                search_parts = arg.split(':', 1)
                pattern = search_parts[0]
                path = search_parts[1] if len(search_parts) > 1 else None
                return FileExplorerOps.search_files(pattern, path)

            elif operation == 'storage':
                return FileExplorerOps.get_storage_usage(arg)

            elif operation == 'mkdir':
                return FileExplorerOps.create_directory(arg, nested=False)

            elif operation == 'mkdirs':
                return FileExplorerOps.create_directory(arg, nested=True)

            elif operation == 'move':
                # Format: file_explorer:move:source:dest
                move_parts = arg.split(':', 1)
                if len(move_parts) != 2:
                    return False, "", "move requires source:dest format"
                return FileExplorerOps.move_item(move_parts[0], move_parts[1])

            elif operation == 'rename':
                # Format: file_explorer:rename:old_path:new_name
                rename_parts = arg.split(':', 1)
                if len(rename_parts) != 2:
                    return False, "", "rename requires old_path:new_name format"
                return FileExplorerOps.rename_item(rename_parts[0], rename_parts[1])

            elif operation == 'copy':
                # Format: file_explorer:copy:source:dest
                copy_parts = arg.split(':', 1)
                if len(copy_parts) != 2:
                    return False, "", "copy requires source:dest format"
                return FileExplorerOps.copy_item(copy_parts[0], copy_parts[1])

            elif operation == 'delete':
                return FileExplorerOps.delete_item(arg, force=False)

            elif operation == 'delete_force':
                return FileExplorerOps.delete_item(arg, force=True)

            elif operation == 'info':
                return FileExplorerOps.get_item_info(arg)

            else:
                return False, "", f"Unknown file_explorer operation: {operation}"

        except Exception as e:
            return False, "", f"File explorer operation error: {str(e)}"

    def _execute_web_operation(self, command: str) -> Tuple[bool, str, str]:
        try:
            parts = command.split(':', 2)

            if len(parts) < 3:
                return False, "", "Invalid web operation format. Use: web:search:query or web:news:query"

            operation = parts[1].lower()
            query_and_limit = parts[2]

            # Check if max_results is specified (format: query:max_results)
            query_parts = query_and_limit.rsplit(':', 1)
            if len(query_parts) == 2 and query_parts[1].isdigit():
                query = query_parts[0]
                max_results = int(query_parts[1])
            else:
                query = query_and_limit
                max_results = 5  # Default

            # Execute the operation
            if operation == 'search':
                return WebOps.search(query, max_results)
            elif operation == 'news':
                return WebOps.search_news(query, max_results)
            else:
                return False, "", f"Unknown web operation: {operation}. Use 'search' or 'news'"

        except Exception as e:
            op_logger.logger.error(f"Web operation error: {e}")
            return False, "", f"Web operation error: {str(e)}"

    async def _request_user_confirmation(self, command: str, description: str) -> bool:
        print(f"\n[Confirm] {description}")
        try:
            response = input("Allow? [y/N]: ").strip().lower()
            return response in ('y', 'yes')
        except (EOFError, KeyboardInterrupt):
            return False

    async def _execute_gui_app(self, command: str) -> Tuple[bool, str, str]:
        command = self._prepare_command(command)

        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=5,
                encoding='utf-8',
                errors='replace',
                cwd=Config.HOME_DIR
            )

            success = result.returncode == 0

            if success:
                output = "✓ Application launched"
                error = ""
            else:
                output = result.stdout if result.stdout else ""
                error = result.stderr if result.stderr else "Application failed to start"

            return success, output, error

        except subprocess.TimeoutExpired:
            return True, "✓ Application launched", ""

        except Exception as e:
            return False, "", f"Execution error: {str(e)}"

    async def _execute_powershell(self, command: str) -> Tuple[bool, str, str]:
        if '-NonInteractive' not in command:
            command = command.replace('powershell ', 'powershell -NonInteractive ', 1)

        if '-Command' in command and '$ErrorActionPreference' not in command:
            command = command.replace(
                '-Command "',
                '-Command "$ErrorActionPreference=\'Stop\'; ',
                1
            )
            if not command.rstrip().endswith('"'):
                command = command.rstrip() + '"'

        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=Config.COMMAND_TIMEOUT,
                encoding='utf-8',
                errors='replace',
                cwd=Config.HOME_DIR
            )

            output = result.stdout.strip() if result.stdout else ""
            error = result.stderr.strip() if result.stderr else ""

            success = result.returncode == 0 and not self._has_powershell_error(error, output)

            if success and not output and 'Stop-Process' in command:
                output = "✓ Process terminated"

            return success, output, error

        except subprocess.TimeoutExpired:
            return False, "", f"Command timeout ({Config.COMMAND_TIMEOUT}s)"

        except Exception as e:
            return False, "", f"Execution error: {str(e)}"

    async def _execute_standard(self, command: str) -> Tuple[bool, str, str]:
        command = self._prepare_command(command)

        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=Config.COMMAND_TIMEOUT,
                encoding='utf-8',
                errors='replace',
                cwd=Config.HOME_DIR
            )

            output = result.stdout.strip() if result.stdout else ""
            error = result.stderr.strip() if result.stderr else ""

            success = result.returncode == 0

            if success and error:
                if self._contains_error_indicators(error):
                    success = False

            if not success and not error:
                error = f"Command exited with code {result.returncode}"

            return success, output, error

        except subprocess.TimeoutExpired:
            return False, "", f"Command timeout ({Config.COMMAND_TIMEOUT}s)"

        except Exception as e:
            return False, "", f"Execution error: {str(e)}"

    def _prepare_command(self, command: str) -> str:
        return command.strip()

    def _has_powershell_error(self, stderr: str, stdout: str) -> bool:
        if not stderr:
            return False

        error_patterns = [
            'error', 'exception', 'cannot find', 'does not exist',
            'not recognized', 'access is denied', 'invalid operation',
            'failed to', 'unable to'
        ]

        stderr_lower = stderr.lower()
        return any(pattern in stderr_lower for pattern in error_patterns)

    def _contains_error_indicators(self, text: str) -> bool:
        if not text:
            return False

        error_indicators = [
            'error', 'exception', 'failed', 'failure', 'cannot', 'unable',
            'not found', 'not recognized', 'access is denied', 'permission denied',
            'syntax error', 'unexpected token', 'missing', 'invalid',
            'does not exist', 'no such', 'not available',
            'unauthorized', 'forbidden'
        ]

        text_lower = text.lower()
        return any(indicator in text_lower for indicator in error_indicators)