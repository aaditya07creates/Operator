import os
from pathlib import Path
import platform


class Paths:
    """Centralized path management for OPERATOR"""

    @staticmethod
    def get_user_data_dir() -> Path:
        """Get the user data directory for OPERATOR, creating it if needed."""
        system = platform.system()

        if system == "Windows":
            base = os.getenv('LOCALAPPDATA', os.path.expanduser('~\\AppData\\Local'))
            data_dir = Path(base) / 'OPERATOR'
        elif system == "Darwin":  # macOS
            data_dir = Path.home() / 'Library' / 'Application Support' / 'OPERATOR'
        else:  # Linux and others
            base = os.getenv('XDG_DATA_HOME', os.path.expanduser('~/.local/share'))
            data_dir = Path(base) / 'OPERATOR'

        # Create directory if it doesn't exist
        data_dir.mkdir(parents=True, exist_ok=True)

        return data_dir

    @staticmethod
    def get_learning_file() -> str:
        return str(Paths.get_user_data_dir() / 'operator_learnings.json')

    @staticmethod
    def get_backup_dir() -> Path:
        backup_dir = Paths.get_user_data_dir() / 'backups'
        backup_dir.mkdir(exist_ok=True)
        return backup_dir

    @staticmethod
    def get_backup_file(timestamp: str = None) -> str:
        if timestamp:
            filename = f'operator_learnings_backup_{timestamp}.json'
        else:
            filename = 'operator_learnings_backup.json'

        return str(Paths.get_backup_dir() / filename)

    @staticmethod
    def get_logs_dir() -> Path:
        logs_dir = Paths.get_user_data_dir() / 'logs'
        logs_dir.mkdir(exist_ok=True)
        return logs_dir

    @staticmethod
    def get_info() -> dict:
        return {
            'user_data_dir': str(Paths.get_user_data_dir()),
            'learning_file': Paths.get_learning_file(),
            'backup_dir': str(Paths.get_backup_dir()),
            'logs_dir': str(Paths.get_logs_dir()),
            'platform': platform.system()
        }
