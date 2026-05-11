import os
import subprocess
from pathlib import Path
from typing import Tuple


class FileOps:
    """Handle file creation and execution operations"""

    # Default directory for file creation
    DEFAULT_OUTPUT_DIR = Path("C:/Users/aadit/OperatorPrograms")

    @classmethod
    def _ensure_default_dir(cls):
        """Ensure default output directory exists"""
        try:
            cls.DEFAULT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass  # If we can't create it, we'll try using the path anyway

    @classmethod
    def _resolve_path(cls, filepath: str) -> Path:
        """
        Resolve filepath, using default directory for relative paths.

        Args:
            filepath: Can be:
                - Relative: "script.py" -> C:/Users/aadit/OperatorPrograms/script.py
                - Absolute: "C:/temp/file.py" -> C:/temp/file.py

        Returns:
            Resolved Path object
        """
        path = Path(filepath)

        # If absolute path, use as-is
        if path.is_absolute():
            return path

        # If relative, put in default directory
        cls._ensure_default_dir()
        return cls.DEFAULT_OUTPUT_DIR / filepath

    @classmethod
    def create_file(cls, filepath: str, content: str) -> Tuple[bool, str, str]:
        """
        Create a file with content.

        Args:
            filepath: Path to file (e.g., "script.py" or "C:/temp/page.html")
                     Relative paths will be created in C:/Users/aadit/OperatorPrograms
            content: File content

        Returns:
            (success, output, error) tuple
        """
        try:
            path = cls._resolve_path(filepath)

            # Create parent directories if needed
            path.parent.mkdir(parents=True, exist_ok=True)

            # Write file
            path.write_text(content, encoding='utf-8')

            output = f"✓ Created: {path.absolute()}"
            return True, output, ""

        except Exception as e:
            return False, "", f"Failed to create file: {str(e)}"

    @classmethod
    def run_file(cls, filepath: str, wait: bool = False) -> Tuple[bool, str, str]:
        """
        Run a file based on its extension.

        Args:
            filepath: Path to file
            wait: Whether to wait for execution to complete

        Returns:
            (success, output, error) tuple
        """
        try:
            path = cls._resolve_path(filepath)

            if not path.exists():
                return False, "", f"File not found: {path}"

            ext = path.suffix.lower()

            if ext == '.html' or ext == '.htm':
                # Open in default browser
                os.startfile(str(path.absolute()))
                return True, f"✓ Opened in browser: {path.name}", ""

            elif ext == '.py':
                # Run with Python
                if wait:
                    result = subprocess.run(
                        ['python', str(path.absolute())],
                        capture_output=True,
                        text=True,
                        timeout=30
                    )
                    return result.returncode == 0, result.stdout, result.stderr
                else:
                    subprocess.Popen(
                        ['python', str(path.absolute())],
                        creationflags=subprocess.CREATE_NEW_CONSOLE
                    )
                    return True, f"✓ Running: {path.name}", ""

            elif ext in ['.bat', '.cmd']:
                subprocess.Popen(
                    ['cmd', '/c', str(path.absolute())],
                    creationflags=subprocess.CREATE_NEW_CONSOLE
                )
                return True, f"✓ Running: {path.name}", ""

            elif ext == '.ps1':
                subprocess.Popen(
                    ['powershell', '-ExecutionPolicy', 'Bypass', '-File', str(path.absolute())],
                    creationflags=subprocess.CREATE_NEW_CONSOLE
                )
                return True, f"✓ Running: {path.name}", ""

            else:
                # Try to open with default application
                os.startfile(str(path.absolute()))
                return True, f"✓ Opened: {path.name}", ""

        except Exception as e:
            return False, "", f"Failed to run file: {str(e)}"

    @classmethod
    def create_and_run(cls, filepath: str, content: str) -> Tuple[bool, str, str]:
        """
        Create a file and immediately run it.

        Args:
            filepath: Path to file
            content: File content

        Returns:
            (success, output, error) tuple
        """
        # Create file
        success, output, error = cls.create_file(filepath, content)
        if not success:
            return False, output, error

        # Run file
        success2, output2, error2 = cls.run_file(filepath)

        # Combine outputs
        combined_output = f"{output}\n{output2}".strip()
        return success2, combined_output, error2