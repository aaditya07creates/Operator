from typing import Tuple
from pathlib import Path

try:
    import pyperclip
    PYPERCLIP_AVAILABLE = True
except ImportError:
    PYPERCLIP_AVAILABLE = False

try:
    import win32clipboard
    from PIL import Image
    import io
    WIN32_CLIPBOARD_AVAILABLE = True
except ImportError:
    WIN32_CLIPBOARD_AVAILABLE = False


class ClipboardOps:
    """Handle clipboard operations"""

    @classmethod
    def get_text(cls) -> Tuple[bool, str, str]:
        """
        Get text from clipboard.

        Returns:
            (success, output, error) tuple with clipboard text
        """
        try:
            if PYPERCLIP_AVAILABLE:
                text = pyperclip.paste()
                if text:
                    preview = text[:200] + "..." if len(text) > 200 else text
                    return True, f"📋 Clipboard: {preview}", ""
                else:
                    return True, "📋 Clipboard is empty", ""
            else:
                return False, "", "Clipboard operations require pyperclip. Install with: pip install pyperclip"

        except Exception as e:
            return False, "", f"Failed to get clipboard: {str(e)}"

    @classmethod
    def set_text(cls, text: str) -> Tuple[bool, str, str]:
        """
        Set text to clipboard.

        Args:
            text: Text to copy to clipboard

        Returns:
            (success, output, error) tuple
        """
        try:
            if PYPERCLIP_AVAILABLE:
                pyperclip.copy(text)
                preview = text[:100] + "..." if len(text) > 100 else text
                return True, f"✓ Copied to clipboard: {preview}", ""
            else:
                return False, "", "Clipboard operations require pyperclip. Install with: pip install pyperclip"

        except Exception as e:
            return False, "", f"Failed to set clipboard: {str(e)}"

    @classmethod
    def clear(cls) -> Tuple[bool, str, str]:
        """
        Clear clipboard contents.

        Returns:
            (success, output, error) tuple
        """
        try:
            if PYPERCLIP_AVAILABLE:
                pyperclip.copy('')
                return True, "✓ Clipboard cleared", ""
            else:
                return False, "", "Clipboard operations require pyperclip. Install with: pip install pyperclip"

        except Exception as e:
            return False, "", f"Failed to clear clipboard: {str(e)}"

    @classmethod
    def copy_current(cls) -> Tuple[bool, str, str]:
        """
        Trigger copy operation (simulates Ctrl+C).
        Note: This relies on key_ops to actually perform the keystroke.

        Returns:
            (success, output, error) tuple
        """
        try:
            from key_ops import KeyOps
            success, output, error = KeyOps.press_combo(['ctrl', 'c'])
            if success:
                return True, "✓ Copy command triggered (Ctrl+C)", ""
            else:
                return False, "", error
        except ImportError:
            return False, "", "Copy operation requires key_ops module"
        except Exception as e:
            return False, "", f"Failed to trigger copy: {str(e)}"

    @classmethod
    def paste_current(cls) -> Tuple[bool, str, str]:
        """
        Trigger paste operation (simulates Ctrl+V).
        Note: This relies on key_ops to actually perform the keystroke.

        Returns:
            (success, output, error) tuple
        """
        try:
            from key_ops import KeyOps
            success, output, error = KeyOps.press_combo(['ctrl', 'v'])
            if success:
                return True, "✓ Paste command triggered (Ctrl+V)", ""
            else:
                return False, "", error
        except ImportError:
            return False, "", "Paste operation requires key_ops module"
        except Exception as e:
            return False, "", f"Failed to trigger paste: {str(e)}"

    @classmethod
    def save_image(cls, filepath: str) -> Tuple[bool, str, str]:
        """
        Save clipboard image to file (Windows only).

        Args:
            filepath: Path to save image (e.g., "screenshot.png")

        Returns:
            (success, output, error) tuple
        """
        try:
            if not WIN32_CLIPBOARD_AVAILABLE:
                return False, "", "Image operations require win32clipboard and Pillow. Install with: pip install pywin32 Pillow"

            # Open clipboard
            win32clipboard.OpenClipboard()
            try:
                # Try to get image data
                if win32clipboard.IsClipboardFormatAvailable(win32clipboard.CF_DIB):
                    data = win32clipboard.GetClipboardData(win32clipboard.CF_DIB)

                    # Convert DIB to PIL Image
                    img = Image.open(io.BytesIO(data))

                    # Resolve path
                    path = Path(filepath)
                    if not path.is_absolute():
                        # Save to OperatorPrograms if relative
                        from file_ops import FileOps
                        path = FileOps.DEFAULT_OUTPUT_DIR / filepath
                        FileOps._ensure_default_dir()

                    # Ensure parent directory exists
                    path.parent.mkdir(parents=True, exist_ok=True)

                    # Save image
                    img.save(str(path))
                    return True, f"✓ Saved clipboard image to: {path.absolute()}", ""
                else:
                    return False, "", "No image found in clipboard"
            finally:
                win32clipboard.CloseClipboard()

        except Exception as e:
            return False, "", f"Failed to save clipboard image: {str(e)}"

    @classmethod
    def get_length(cls) -> Tuple[bool, str, str]:
        """
        Get length of clipboard text.

        Returns:
            (success, output, error) tuple with character count
        """
        try:
            if PYPERCLIP_AVAILABLE:
                text = pyperclip.paste()
                length = len(text)
                lines = text.count('\n') + 1 if text else 0
                words = len(text.split()) if text else 0

                return True, f"📋 Clipboard: {length} characters, {words} words, {lines} lines", ""
            else:
                return False, "", "Clipboard operations require pyperclip. Install with: pip install pyperclip"

        except Exception as e:
            return False, "", f"Failed to get clipboard length: {str(e)}"

    @classmethod
    def append_text(cls, text: str) -> Tuple[bool, str, str]:
        """
        Append text to current clipboard content.

        Args:
            text: Text to append

        Returns:
            (success, output, error) tuple
        """
        try:
            if PYPERCLIP_AVAILABLE:
                current = pyperclip.paste()
                new_content = current + text
                pyperclip.copy(new_content)
                return True, f"✓ Appended to clipboard: {text[:50]}...", ""
            else:
                return False, "", "Clipboard operations require pyperclip. Install with: pip install pyperclip"

        except Exception as e:
            return False, "", f"Failed to append to clipboard: {str(e)}"

    @classmethod
    def has_content(cls) -> Tuple[bool, str, str]:
        """
        Check if clipboard has content.

        Returns:
            (success, output, error) tuple with status
        """
        try:
            if PYPERCLIP_AVAILABLE:
                text = pyperclip.paste()
                if text:
                    return True, f"✓ Clipboard has content ({len(text)} chars)", ""
                else:
                    return True, "Clipboard is empty", ""
            else:
                return False, "", "Clipboard operations require pyperclip. Install with: pip install pyperclip"

        except Exception as e:
            return False, "", f"Failed to check clipboard: {str(e)}"
