import logging
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional


class ColoredFormatter(logging.Formatter):
    """Enhanced formatter with colors and emojis"""

    # ANSI color codes
    COLORS = {
        'DEBUG': '\033[36m',      # Cyan
        'INFO': '\033[32m',       # Green
        'WARNING': '\033[33m',    # Yellow
        'ERROR': '\033[31m',      # Red
        'CRITICAL': '\033[35m',   # Magenta
        'RESET': '\033[0m',       # Reset
        'BOLD': '\033[1m',        # Bold
        'DIM': '\033[2m',         # Dim
    }

    # Emoji prefixes (simplified for Windows compatibility)
    PREFIXES = {
        'DEBUG': '🔍',
        'INFO': '📘',
        'WARNING': '⚠️',
        'ERROR': '❌',
        'CRITICAL': '🚨',
    }

    def format(self, record):
        # Add color and emoji to levelname
        levelname = record.levelname
        if levelname in self.COLORS:
            prefix = self.PREFIXES.get(levelname, '')
            record.levelname = (
                f"{self.COLORS[levelname]}{prefix} {levelname}{self.COLORS['RESET']}"
            )

        return super().format(record)


class PerformanceTracker:
    """Track operation performance"""

    def __init__(self):
        self.timings = {}
        self.start_times = {}

    def start(self, operation: str):
        """Start timing an operation"""
        self.start_times[operation] = time.time()

    def end(self, operation: str) -> Optional[float]:
        """End timing and return duration in ms"""
        if operation not in self.start_times:
            return None

        duration = (time.time() - self.start_times[operation]) * 1000

        if operation not in self.timings:
            self.timings[operation] = []
        self.timings[operation].append(duration)

        del self.start_times[operation]
        return duration

    def get_stats(self, operation: str) -> dict:
        """Get statistics for an operation"""
        if operation not in self.timings or not self.timings[operation]:
            return {}

        times = self.timings[operation]
        return {
            'count': len(times),
            'avg': sum(times) / len(times),
            'min': min(times),
            'max': max(times),
            'total': sum(times)
        }


class OperatorLogger:
    """
    Enhanced logger with structured output and performance tracking.
    Singleton pattern ensures consistent logging across modules.
    """

    _instance = None
    _logger = None
    _perf_tracker = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if self._logger is not None:
            return

        # Setup logger
        self._logger = logging.getLogger('OPERATOR')
        self._logger.setLevel(logging.INFO)  # Default to INFO, not DEBUG
        self._logger.propagate = False  # Prevent duplicate logs

        # Clear any existing handlers
        self._logger.handlers.clear()

        # Console handler with colors
        self._setup_console_handler()

        # Performance tracker
        self._perf_tracker = PerformanceTracker()

        # File logging (disabled by default, enable if needed)
        # self._setup_file_handler()

    def _setup_console_handler(self):
        """Setup colorful console logging"""
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)

        # Simple format for cleaner output
        console_format = '%(levelname)s | %(message)s'
        console_formatter = ColoredFormatter(console_format)
        console_handler.setFormatter(console_formatter)

        self._logger.addHandler(console_handler)

    def _setup_file_handler(self):
        """Setup file logging (call this to enable file logs)"""
        log_dir = Path.home() / '.operator' / 'logs'
        log_dir.mkdir(parents=True, exist_ok=True)

        log_file = log_dir / f'operator_{datetime.now():%Y%m%d}.log'

        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setLevel(logging.DEBUG)

        # More detailed format for files
        file_format = '%(asctime)s | %(levelname)-8s | %(message)s'
        file_formatter = logging.Formatter(file_format, datefmt='%H:%M:%S')
        file_handler.setFormatter(file_formatter)

        self._logger.addHandler(file_handler)
        self._logger.info(f"File logging enabled: {log_file}")

    @property
    def logger(self):
        """Get the underlying logger"""
        return self._logger

    def set_level(self, level: str):
        """
        Change log level dynamically.

        Args:
            level: 'DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'
        """
        level_map = {
            'DEBUG': logging.DEBUG,
            'INFO': logging.INFO,
            'WARNING': logging.WARNING,
            'ERROR': logging.ERROR,
            'CRITICAL': logging.CRITICAL
        }

        if level.upper() in level_map:
            self._logger.setLevel(level_map[level.upper()])
            for handler in self._logger.handlers:
                handler.setLevel(level_map[level.upper()])

    # ==================== Structured Logging Methods ====================

    def header(self, title: str, width: int = 60):
        """Print a major header"""
        self._logger.info("=" * width)
        self._logger.info(f"  {title}")
        self._logger.info("=" * width)

    def section(self, title: str, width: int = 60):
        """Print a section divider"""
        self._logger.info("")
        self._logger.info("─" * width)
        self._logger.info(f"  {title}")
        self._logger.info("─" * width)

    def command(self, cmd: str, max_length: int = 80):
        """Log a command being executed"""
        truncated = cmd if len(cmd) <= max_length else cmd[:max_length-3] + "..."
        self._logger.info(f"⚙️  EXEC: {truncated}")

    def success(self, message: str):
        """Log success message"""
        self._logger.info(f"✓ {message}")

    def failure(self, message: str):
        """Log failure message"""
        self._logger.error(f"✗ {message}")

    def kv(self, key: str, value: str, indent: int = 2):
        """Log key-value pair with optional indentation"""
        prefix = "  " * indent
        self._logger.info(f"{prefix}├─ {key}: {value}")

    def bullet(self, text: str, indent: int = 2):
        """Log a bullet point"""
        prefix = "  " * indent
        self._logger.info(f"{prefix}• {text}")

    # ==================== Performance Tracking ====================

    def perf_start(self, operation: str):
        """Start timing an operation"""
        self._perf_tracker.start(operation)

    def perf_end(self, operation: str, log: bool = True) -> Optional[float]:
        """
        End timing and optionally log the duration.

        Returns:
            Duration in milliseconds
        """
        duration = self._perf_tracker.end(operation)

        if log and duration is not None:
            self._logger.debug(f"⏱️  {operation}: {duration:.1f}ms")

        return duration

    def perf_stats(self, operation: str) -> dict:
        """Get performance statistics for an operation"""
        return self._perf_tracker.get_stats(operation)

    # ==================== AI-Specific Logging ====================

    def ai_request(self, provider: str, message_length: int, streaming: bool = False):
        """Log AI request"""
        mode = "streaming" if streaming else "standard"
        self._logger.debug(f"→ AI Request [{provider}] | {message_length} chars | {mode}")

    def ai_response(self, provider: str, response_length: int, duration_ms: Optional[int] = None):
        """Log AI response"""
        duration_str = f" | {duration_ms:.0f}ms" if duration_ms else ""
        self._logger.debug(f"← AI Response [{provider}] | {response_length} chars{duration_str}")

    # ==================== Command Execution Logging ====================

    def command_result(self, command: str, success: bool, output_length: int):
        """Log command execution result"""
        status = "✓" if success else "✗"
        cmd_short = command[:60] + "..." if len(command) > 60 else command
        self._logger.debug(f"{status} Result: {output_length} chars | {cmd_short}")

    # ==================== Memory/Learning Logging ====================

    def learning_action(self, action: str, learning_type: str, note: str):
        """Log learning system actions"""
        note_short = note[:50] + "..." if len(note) > 50 else note
        self._logger.info(f"📚 {action} [{learning_type}]: {note_short}")

    def memory_stats(self, stats: dict):
        """Log memory statistics"""
        self._logger.info(f"💾 Memory: {stats.get('apps_known', 0)} apps, "
                         f"{stats.get('patterns_learned', 0)} patterns, "
                         f"{stats.get('fixes_recorded', 0)} fixes")

    # ==================== Context Updates ====================

    def context_update(self, context_type: str, details: str):
        """Log context updates"""
        self._logger.debug(f"🔄 Context [{context_type}]: {details}")

    # ==================== Progress Indicators ====================

    def progress(self, current: int, total: int, operation: str = ""):
        """Log progress"""
        percentage = (current / total) * 100 if total > 0 else 0
        op_str = f" {operation}" if operation else ""
        self._logger.info(f"📊 Progress{op_str}: {current}/{total} ({percentage:.0f}%)")

    # ==================== Validation & Safety ====================

    def validation_blocked(self, command: str, reason: str):
        """Log blocked command"""
        cmd_short = command[:50] + "..." if len(command) > 50 else command
        self._logger.warning(f"🛑 Blocked: {cmd_short}")
        self._logger.warning(f"   Reason: {reason}")

    # ==================== Error Handling ====================

    def exception(self, error: Exception, context: str = ""):
        """Log exception with optional context"""
        context_str = f" in {context}" if context else ""
        self._logger.error(f"💥 Exception{context_str}: {type(error).__name__}: {str(error)}")

    # ==================== Summary Reports ====================

    def summary(self, title: str, stats: dict):
        """Print a summary report"""
        self.section(title)
        for key, value in stats.items():
            self.kv(key.replace('_', ' ').title(), str(value))


# ==================== Global Instance ====================

# Create singleton instance
_op_logger_instance = OperatorLogger()

# Convenience exports
logger = _op_logger_instance.logger
op_logger = _op_logger_instance


# ==================== Utility Functions ====================

def get_logger():
    """Get the global OPERATOR logger instance"""
    return _op_logger_instance.logger


def enable_debug():
    """Enable debug logging"""
    _op_logger_instance.set_level('DEBUG')


def enable_file_logging():
    """Enable file logging"""
    _op_logger_instance._setup_file_handler()


def get_perf_stats(operation: str) -> dict:
    """Get performance statistics for an operation"""
    return _op_logger_instance.perf_stats(operation)