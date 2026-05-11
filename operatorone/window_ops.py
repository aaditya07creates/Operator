import subprocess
from typing import Tuple, List, Dict, Optional
from dataclasses import dataclass

try:
    import pygetwindow as gw
    PYGETWINDOW_AVAILABLE = True
except ImportError:
    PYGETWINDOW_AVAILABLE = False

try:
    import win32gui
    import win32con
    import win32process
    WIN32_AVAILABLE = True
except ImportError:
    WIN32_AVAILABLE = False


@dataclass
class WindowInfo:
    """Information about a window"""
    title: str
    handle: int
    process_name: str = ""
    is_visible: bool = True
    is_minimized: bool = False
    is_maximized: bool = False
    position: tuple = (0, 0, 0, 0)  # (x, y, width, height)


class WindowOps:
    """Handle window management operations"""

    @classmethod
    def get_monitor_info(cls) -> Tuple[bool, str, str]:
        """
        Get information about all monitors.

        Returns:
            (success, output, error) tuple with monitor details
        """
        try:
            import mss
            with mss.mss() as sct:
                monitors = sct.monitors[1:]  # Skip index 0 (all monitors combined)

                if not monitors:
                    return True, "No monitors detected", ""

                output = f"🖥️  Monitors ({len(monitors)}):\n"
                for i, mon in enumerate(monitors, 1):
                    output += f"• Monitor {i}: {mon['width']}x{mon['height']} at ({mon['left']}, {mon['top']})\n"

                return True, output.strip(), ""
        except ImportError:
            return False, "", "Monitor detection requires mss library. Install with: pip install mss"
        except Exception as e:
            return False, "", f"Failed to get monitor info: {str(e)}"

    @classmethod
    def list_windows(cls) -> Tuple[bool, str, str]:
        """
        List all open windows.

        Returns:
            (success, output, error) tuple with formatted window list
        """
        try:
            if not PYGETWINDOW_AVAILABLE and not WIN32_AVAILABLE:
                return False, "", "Window operations require pygetwindow or pywin32. Install with: pip install pygetwindow pywin32"

            windows = []

            if PYGETWINDOW_AVAILABLE:
                # Use pygetwindow (simpler API)
                all_windows = gw.getAllWindows()
                for window in all_windows:
                    if window.title.strip() and window.visible:
                        windows.append(f"• {window.title}")
            elif WIN32_AVAILABLE:
                # Fallback to win32gui
                def enum_callback(hwnd, results):
                    if win32gui.IsWindowVisible(hwnd):
                        title = win32gui.GetWindowText(hwnd)
                        if title.strip():
                            results.append(f"• {title}")

                window_list = []
                win32gui.EnumWindows(enum_callback, window_list)
                windows = window_list

            if not windows:
                return True, "No visible windows found", ""

            output = f"📋 Open Windows ({len(windows)}):\n" + "\n".join(windows[:20])
            if len(windows) > 20:
                output += f"\n... and {len(windows) - 20} more"

            return True, output, ""

        except Exception as e:
            return False, "", f"Failed to list windows: {str(e)}"

    @classmethod
    def focus_window(cls, window_title: str) -> Tuple[bool, str, str]:
        """
        Focus/activate a window by title (partial match).

        Args:
            window_title: Window title to search for (case-insensitive)

        Returns:
            (success, output, error) tuple
        """
        try:
            if PYGETWINDOW_AVAILABLE:
                # Find windows matching title
                all_windows = gw.getAllWindows()
                matching = [w for w in all_windows if window_title.lower() in w.title.lower() and w.visible]

                if not matching:
                    # Provide helpful error with available windows
                    available = [w.title for w in all_windows if w.visible and w.title.strip()][:5]
                    hint = f"\n💡 Available windows: {', '.join(available)}" if available else ""
                    return False, "", f"No window found matching '{window_title}'{hint}\n💡 Try: window:list to see all windows"

                # Focus the first match
                window = matching[0]
                window.activate()
                return True, f"✓ Focused: {window.title}", ""

            elif WIN32_AVAILABLE:
                # Fallback to win32gui
                hwnd = None
                def enum_callback(h, results):
                    if win32gui.IsWindowVisible(h):
                        title = win32gui.GetWindowText(h)
                        if window_title.lower() in title.lower():
                            results.append(h)

                handles = []
                win32gui.EnumWindows(enum_callback, handles)

                if not handles:
                    # Provide helpful error
                    return False, "", f"No window found matching '{window_title}'\n💡 Try: window:list to see all windows"

                hwnd = handles[0]
                win32gui.SetForegroundWindow(hwnd)
                title = win32gui.GetWindowText(hwnd)
                return True, f"✓ Focused: {title}", ""

            else:
                return False, "", "Window operations require pygetwindow or pywin32"

        except Exception as e:
            return False, "", f"Failed to focus window: {str(e)}"

    @classmethod
    def close_window(cls, window_title: str) -> Tuple[bool, str, str]:
        """
        Close a window by title (partial match).

        Args:
            window_title: Window title to search for

        Returns:
            (success, output, error) tuple
        """
        try:
            if PYGETWINDOW_AVAILABLE:
                all_windows = gw.getAllWindows()
                matching = [w for w in all_windows if window_title.lower() in w.title.lower() and w.visible]

                if not matching:
                    # Provide helpful error with available windows
                    available = [w.title for w in all_windows if w.visible and w.title.strip()][:5]
                    hint = f"\n💡 Available windows: {', '.join(available)}" if available else ""
                    return False, "", f"No window found matching '{window_title}'{hint}\n💡 Try: window:list to see all windows"

                # Close all matching windows
                closed = []
                for window in matching:
                    try:
                        window.close()
                        closed.append(window.title)
                    except:
                        pass

                if closed:
                    return True, f"✓ Closed {len(closed)} window(s): {', '.join(closed[:3])}", ""
                else:
                    return False, "", "Failed to close windows"

            elif WIN32_AVAILABLE:
                handles = []
                def enum_callback(h, results):
                    if win32gui.IsWindowVisible(h):
                        title = win32gui.GetWindowText(h)
                        if window_title.lower() in title.lower():
                            results.append((h, title))

                win32gui.EnumWindows(enum_callback, handles)

                if not handles:
                    return False, "", f"No window found matching '{window_title}'"

                closed = []
                for hwnd, title in handles:
                    try:
                        win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
                        closed.append(title)
                    except:
                        pass

                if closed:
                    return True, f"✓ Closed {len(closed)} window(s)", ""
                else:
                    return False, "", "Failed to close windows"

            else:
                return False, "", "Window operations require pygetwindow or pywin32"

        except Exception as e:
            return False, "", f"Failed to close window: {str(e)}"

    @classmethod
    def minimize_window(cls, window_title: str) -> Tuple[bool, str, str]:
        """Minimize a window by title."""
        try:
            if PYGETWINDOW_AVAILABLE:
                all_windows = gw.getAllWindows()

                # Prioritize exact matches, then partial matches
                exact_matches = [w for w in all_windows if window_title.lower() == w.title.lower() and w.visible]
                partial_matches = [w for w in all_windows if window_title.lower() in w.title.lower() and w.visible and w not in exact_matches]

                matching = exact_matches + partial_matches

                if not matching:
                    # Provide helpful error with available windows
                    available = [w.title for w in all_windows if w.visible and w.title.strip()][:5]
                    hint = f"\n💡 Available windows: {', '.join(available)}" if available else ""
                    return False, "", f"No window found matching '{window_title}'{hint}\n💡 Try: window:list to see all windows"

                window = matching[0]

                # Show which window was matched if multiple matches
                match_info = ""
                if len(matching) > 1:
                    match_info = f" (matched 1 of {len(matching)} windows)"

                window.minimize()
                return True, f"✓ Minimized: {window.title}{match_info}", ""

            elif WIN32_AVAILABLE:
                handles = []
                def enum_callback(h, results):
                    if win32gui.IsWindowVisible(h):
                        title = win32gui.GetWindowText(h)
                        if window_title.lower() in title.lower():
                            results.append((h, title))

                win32gui.EnumWindows(enum_callback, handles)

                if not handles:
                    return False, "", f"No window found matching '{window_title}'"

                hwnd, title = handles[0]
                win32gui.ShowWindow(hwnd, win32con.SW_MINIMIZE)
                return True, f"✓ Minimized: {title}", ""

            else:
                return False, "", "Window operations require pygetwindow or pywin32"

        except Exception as e:
            return False, "", f"Failed to minimize window: {str(e)}"

    @classmethod
    def maximize_window(cls, window_title: str) -> Tuple[bool, str, str]:
        """Maximize a window by title."""
        try:
            if PYGETWINDOW_AVAILABLE:
                all_windows = gw.getAllWindows()
                matching = [w for w in all_windows if window_title.lower() in w.title.lower() and w.visible]

                if not matching:
                    # Provide helpful error with available windows
                    available = [w.title for w in all_windows if w.visible and w.title.strip()][:5]
                    hint = f"\n💡 Available windows: {', '.join(available)}" if available else ""
                    return False, "", f"No window found matching '{window_title}'{hint}\n💡 Try: window:list to see all windows"

                window = matching[0]
                window.maximize()
                return True, f"✓ Maximized: {window.title}", ""

            elif WIN32_AVAILABLE:
                handles = []
                def enum_callback(h, results):
                    if win32gui.IsWindowVisible(h):
                        title = win32gui.GetWindowText(h)
                        if window_title.lower() in title.lower():
                            results.append((h, title))

                win32gui.EnumWindows(enum_callback, handles)

                if not handles:
                    return False, "", f"No window found matching '{window_title}'"

                hwnd, title = handles[0]
                win32gui.ShowWindow(hwnd, win32con.SW_MAXIMIZE)
                return True, f"✓ Maximized: {title}", ""

            else:
                return False, "", "Window operations require pygetwindow or pywin32"

        except Exception as e:
            return False, "", f"Failed to maximize window: {str(e)}"

    @classmethod
    def resize_window(cls, window_title: str, width: int, height: int) -> Tuple[bool, str, str]:
        """
        Resize a window by title.

        Args:
            window_title: Window title to search for
            width: New width in pixels
            height: New height in pixels

        Returns:
            (success, output, error) tuple
        """
        try:
            if PYGETWINDOW_AVAILABLE:
                all_windows = gw.getAllWindows()
                matching = [w for w in all_windows if window_title.lower() in w.title.lower() and w.visible]

                if not matching:
                    # Provide helpful error with available windows
                    available = [w.title for w in all_windows if w.visible and w.title.strip()][:5]
                    hint = f"\n💡 Available windows: {', '.join(available)}" if available else ""
                    return False, "", f"No window found matching '{window_title}'{hint}\n💡 Try: window:list to see all windows"

                window = matching[0]
                window.resizeTo(width, height)
                return True, f"✓ Resized {window.title} to {width}x{height}", ""

            elif WIN32_AVAILABLE:
                handles = []
                def enum_callback(h, results):
                    if win32gui.IsWindowVisible(h):
                        title = win32gui.GetWindowText(h)
                        if window_title.lower() in title.lower():
                            results.append((h, title))

                win32gui.EnumWindows(enum_callback, handles)

                if not handles:
                    return False, "", f"No window found matching '{window_title}'"

                hwnd, title = handles[0]
                left, top, right, bottom = win32gui.GetWindowRect(hwnd)
                win32gui.MoveWindow(hwnd, left, top, width, height, True)
                return True, f"✓ Resized {title} to {width}x{height}", ""

            else:
                return False, "", "Window operations require pygetwindow or pywin32"

        except Exception as e:
            return False, "", f"Failed to resize window: {str(e)}"

    @classmethod
    def move_window(cls, window_title: str, x: int, y: int) -> Tuple[bool, str, str]:
        """
        Move a window to specific coordinates.

        Args:
            window_title: Window title to search for
            x: X coordinate (pixels from left)
            y: Y coordinate (pixels from top)

        Returns:
            (success, output, error) tuple
        """
        try:
            if PYGETWINDOW_AVAILABLE:
                all_windows = gw.getAllWindows()
                matching = [w for w in all_windows if window_title.lower() in w.title.lower() and w.visible]

                if not matching:
                    # Provide helpful error with available windows
                    available = [w.title for w in all_windows if w.visible and w.title.strip()][:5]
                    hint = f"\n💡 Available windows: {', '.join(available)}" if available else ""
                    return False, "", f"No window found matching '{window_title}'{hint}\n💡 Try: window:list to see all windows"

                window = matching[0]
                window.moveTo(x, y)
                return True, f"✓ Moved {window.title} to ({x}, {y})", ""

            elif WIN32_AVAILABLE:
                handles = []
                def enum_callback(h, results):
                    if win32gui.IsWindowVisible(h):
                        title = win32gui.GetWindowText(h)
                        if window_title.lower() in title.lower():
                            results.append((h, title))

                win32gui.EnumWindows(enum_callback, handles)

                if not handles:
                    return False, "", f"No window found matching '{window_title}'\n💡 Try: window:list to see all windows"

                hwnd, title = handles[0]
                left, top, right, bottom = win32gui.GetWindowRect(hwnd)
                width = right - left
                height = bottom - top
                win32gui.MoveWindow(hwnd, x, y, width, height, True)
                return True, f"✓ Moved {title} to ({x}, {y})", ""

            else:
                return False, "", "Window operations require pygetwindow or pywin32"

        except Exception as e:
            return False, "", f"Failed to move window: {str(e)}"

    @classmethod
    def move_to_monitor(cls, window_title: str, monitor_num: int) -> Tuple[bool, str, str]:
        """
        Move a window to a specific monitor.

        Args:
            window_title: Window title to search for
            monitor_num: Monitor number (1-indexed)

        Returns:
            (success, output, error) tuple
        """
        try:
            import mss

            # Get monitor info
            with mss.mss() as sct:
                monitors = sct.monitors[1:]  # Skip index 0

                if monitor_num < 1 or monitor_num > len(monitors):
                    return False, "", f"Invalid monitor number. You have {len(monitors)} monitor(s). Use 1-{len(monitors)}."

                target_monitor = monitors[monitor_num - 1]

            if PYGETWINDOW_AVAILABLE:
                all_windows = gw.getAllWindows()

                # Prioritize exact matches
                exact_matches = [w for w in all_windows if window_title.lower() == w.title.lower() and w.visible]
                partial_matches = [w for w in all_windows if window_title.lower() in w.title.lower() and w.visible and w not in exact_matches]
                matching = exact_matches + partial_matches

                if not matching:
                    available = [w.title for w in all_windows if w.visible and w.title.strip()][:5]
                    hint = f"\n💡 Available windows: {', '.join(available)}" if available else ""
                    return False, "", f"No window found matching '{window_title}'{hint}"

                window = matching[0]

                # Move to center of target monitor
                center_x = target_monitor['left'] + (target_monitor['width'] - window.width) // 2
                center_y = target_monitor['top'] + (target_monitor['height'] - window.height) // 2

                window.moveTo(center_x, center_y)
                return True, f"✓ Moved {window.title} to Monitor {monitor_num}", ""

            elif WIN32_AVAILABLE:
                handles = []
                def enum_callback(h, results):
                    if win32gui.IsWindowVisible(h):
                        title = win32gui.GetWindowText(h)
                        if window_title.lower() in title.lower():
                            results.append((h, title))

                win32gui.EnumWindows(enum_callback, handles)

                if not handles:
                    return False, "", f"No window found matching '{window_title}'"

                hwnd, title = handles[0]
                left, top, right, bottom = win32gui.GetWindowRect(hwnd)
                width = right - left
                height = bottom - top
                win32gui.MoveWindow(hwnd, x, y, width, height, True)
                return True, f"✓ Moved {title} to ({x}, {y})", ""

            else:
                return False, "", "Window operations require pygetwindow or pywin32"

        except Exception as e:
            return False, "", f"Failed to move window: {str(e)}"
