import time
from typing import Tuple, List

# Try to import pynput, provide helpful error if not available
try:
    from pynput.keyboard import Key, Controller
    PYNPUT_AVAILABLE = True
except ImportError:
    PYNPUT_AVAILABLE = False
    Key = None
    Controller = None


class KeyOps:
    """Handle keyboard input operations"""

    # Key name mapping
    KEY_MAP = {
        # Modifier keys
        'ctrl': 'ctrl',
        'control': 'ctrl',
        'shift': 'shift',
        'alt': 'alt',
        'win': 'cmd',
        'windows': 'cmd',
        'cmd': 'cmd',

        # Special keys
        'enter': 'enter',
        'return': 'enter',
        'space': 'space',
        'spacebar': 'space',
        'tab': 'tab',
        'backspace': 'backspace',
        'delete': 'delete',
        'del': 'delete',
        'escape': 'esc',
        'esc': 'esc',

        # Arrow keys
        'up': 'up',
        'down': 'down',
        'left': 'left',
        'right': 'right',

        # Function keys
        'f1': 'f1', 'f2': 'f2', 'f3': 'f3', 'f4': 'f4',
        'f5': 'f5', 'f6': 'f6', 'f7': 'f7', 'f8': 'f8',
        'f9': 'f9', 'f10': 'f10', 'f11': 'f11', 'f12': 'f12',

        # Other
        'home': 'home',
        'end': 'end',
        'pageup': 'page_up',
        'pagedown': 'page_down',
        'insert': 'insert',
        'printscreen': 'print_screen',
        'pause': 'pause',
        'capslock': 'caps_lock',
        'numlock': 'num_lock',
        'scrolllock': 'scroll_lock',
    }

    _keyboard = None

    @classmethod
    def _get_keyboard(cls):
        """Get or create keyboard controller"""
        if not PYNPUT_AVAILABLE:
            return None
        if cls._keyboard is None:
            cls._keyboard = Controller()
        return cls._keyboard

    @classmethod
    def _check_available(cls) -> Tuple[bool, str]:
        """Check if keyboard operations are available"""
        if not PYNPUT_AVAILABLE:
            return False, "pynput not installed. Run: pip install pynput"
        return True, ""

    @classmethod
    def _parse_key(cls, key_str: str):
        """Parse key string to Key object or character"""
        key_lower = key_str.lower()

        if key_lower in cls.KEY_MAP:
            key_name = cls.KEY_MAP[key_lower]
            return getattr(Key, key_name)
        elif len(key_str) == 1:
            return key_str
        else:
            # Try as-is for single character keys
            return key_str

    @classmethod
    def press_key(cls, key_str: str, delay: float = 0.01) -> Tuple[bool, str, str]:
        """
        Press and release a single key.

        Args:
            key_str: Key name (e.g., 'a', 'enter', 'ctrl')
            delay: Delay between press and release in seconds

        Returns:
            (success, output, error) tuple
        """
        available, error = cls._check_available()
        if not available:
            return False, "", error

        try:
            keyboard = cls._get_keyboard()
            key = cls._parse_key(key_str)
            keyboard.press(key)
            time.sleep(delay)
            keyboard.release(key)
            return True, f"✓ Pressed: {key_str}", ""
        except Exception as e:
            return False, "", f"Failed to press key: {str(e)}"

    @classmethod
    def key_combo(cls, keys: List[str], delay: float = 0.05) -> Tuple[bool, str, str]:
        """
        Press a key combination (e.g., Ctrl+C).

        Args:
            keys: List of key names to press together
            delay: Delay between operations

        Returns:
            (success, output, error) tuple
        """
        available, error = cls._check_available()
        if not available:
            return False, "", error

        try:
            keyboard = cls._get_keyboard()

            # Parse all keys
            parsed_keys = [cls._parse_key(k) for k in keys]

            # Press all keys
            for key in parsed_keys:
                keyboard.press(key)
                time.sleep(delay)

            # Release in reverse order
            for key in reversed(parsed_keys):
                keyboard.release(key)
                time.sleep(delay)

            return True, f"✓ Combo: {'+'.join(keys)}", ""
        except Exception as e:
            return False, "", f"Failed to execute combo: {str(e)}"

    @classmethod
    def type_text(cls, text: str, delay: float = 0.01) -> Tuple[bool, str, str]:
        """
        Type text with delay between characters.

        Args:
            text: Text to type
            delay: Delay between characters in seconds

        Returns:
            (success, output, error) tuple
        """
        available, error = cls._check_available()
        if not available:
            return False, "", error

        try:
            keyboard = cls._get_keyboard()
            for char in text:
                keyboard.press(char)
                keyboard.release(char)
                time.sleep(delay)
            return True, f"✓ Typed: {text}", ""
        except Exception as e:
            return False, "", f"Failed to type text: {str(e)}"

    @classmethod
    def key_sequence(cls, keys: List[str], delay: float = 0.1) -> Tuple[bool, str, str]:
        """
        Press keys in sequence (one after another).

        Args:
            keys: List of key names
            delay: Delay between key presses

        Returns:
            (success, output, error) tuple
        """
        available, error = cls._check_available()
        if not available:
            return False, "", error

        try:
            for key_str in keys:
                success, output, error = cls.press_key(key_str, delay=0.01)
                if not success:
                    return False, "", error
                time.sleep(delay)
            return True, f"✓ Sequence: {' -> '.join(keys)}", ""
        except Exception as e:
            return False, "", f"Failed to execute sequence: {str(e)}"