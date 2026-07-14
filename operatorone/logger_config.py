"""Logging for OPERATOR.

Console output goes through rich's RichHandler (UTF-8 safe, real colors on
Windows, no ANSI/emoji garbage) at WARNING by default so the terminal stays
clean during normal use. --debug lowers it to DEBUG. Everything at DEBUG and
above is always written to a daily log file under the user data dir.
"""

import logging
from datetime import datetime

from paths import Paths

try:
    from rich.console import Console
    from rich.logging import RichHandler
    _RICH = True
    _console = Console(stderr=True)
except ImportError:
    _RICH = False
    _console = None


class OperatorLogger:
    """Singleton wrapper exposing the small logging API the app uses."""

    _instance = None
    _logger = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if self._logger is not None:
            return

        self._logger = logging.getLogger('OPERATOR')
        self._logger.setLevel(logging.DEBUG)  # handlers filter; logger passes all
        self._logger.propagate = False
        self._logger.handlers.clear()

        self._console_handler = self._make_console_handler()
        self._logger.addHandler(self._console_handler)

        self._setup_file_handler()

    def _make_console_handler(self) -> logging.Handler:
        if _RICH:
            handler = RichHandler(
                console=_console,
                show_time=False,
                show_path=False,
                markup=False,
                rich_tracebacks=True,
            )
        else:
            import sys
            handler = logging.StreamHandler(sys.stderr)
            handler.setFormatter(logging.Formatter('%(levelname)s | %(message)s'))
        handler.setLevel(logging.WARNING)
        return handler

    def _setup_file_handler(self):
        try:
            log_file = Paths.get_logs_dir() / f'operator_{datetime.now():%Y%m%d}.log'
            file_handler = logging.FileHandler(log_file, encoding='utf-8')
            file_handler.setLevel(logging.DEBUG)
            file_handler.setFormatter(
                logging.Formatter('%(asctime)s | %(levelname)-8s | %(message)s', datefmt='%H:%M:%S')
            )
            self._logger.addHandler(file_handler)
        except Exception:
            pass  # never let logging setup crash startup

    @property
    def logger(self):
        return self._logger

    def set_level(self, level: str):
        """Set the *console* verbosity (file always keeps DEBUG)."""
        level_value = getattr(logging, level.upper(), None)
        if isinstance(level_value, int):
            self._console_handler.setLevel(level_value)

    # ==================== Structured helpers ====================
    # These log at INFO/DEBUG, so they land in the file but stay off the
    # console unless --debug is set.

    def header(self, title: str):
        self._logger.info(f"=== {title} ===")

    def command(self, cmd: str, max_length: int = 120):
        truncated = cmd if len(cmd) <= max_length else cmd[:max_length - 3] + "..."
        self._logger.info(f"EXEC: {truncated}")

    def command_result(self, command: str, success: bool, output_length: int):
        status = "OK" if success else "FAIL"
        self._logger.debug(f"{status}: {output_length} chars | {command[:80]}")

    def success(self, message: str):
        self._logger.info(message)

    def failure(self, message: str):
        self._logger.error(message)

    def kv(self, key: str, value: str):
        self._logger.info(f"  {key}: {value}")


# ==================== Global instance ====================

_op_logger_instance = OperatorLogger()
logger = _op_logger_instance.logger
op_logger = _op_logger_instance


def enable_debug():
    _op_logger_instance.set_level('DEBUG')
