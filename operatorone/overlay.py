"""Spotlight-style global overlay for OPERATOR.

A borderless, always-on-top input bar that a global hotkey summons over
whatever app is focused. Type a request and press Enter; type '/' to pick a
tool from an autocomplete list. Risky actions raise a confirmation dialog.

Threading model:
- Tkinter owns the main thread (all widget calls happen here).
- OperatorCore runs on a background asyncio loop (AsyncWorker).
- The global hotkey listener runs on its own pynput thread.
- Cross-thread UI updates are marshalled back with root.after(...).
"""

import asyncio
import concurrent.futures
import queue
import threading
import tkinter as tk
from typing import Callable, Optional

from config import Config
from logger_config import op_logger
from safety import RiskTier
from voice_input import VoiceInput

# Pure-black capsule theme
BG = "#0b0b0d"
BG_INPUT = "#141418"
FG = "#ececf0"
FG_DIM = "#7c7c88"
ACCENT = "#63e6c2"   # soft mint — less blue than the old cyan
OK = "#00ff88"
ERR = "#ff5555"
WARN = "#ffcc00"
DANGER = "#ff5555"
BORDER = "#2c2c33"
DIVIDER = "#1d1d22"

SPINNER = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"   # braille spinner frames for the prompt icon

# Color key rendered fully transparent (Windows layered window) so the card
# can have rounded capsule corners. Must never be used as a real widget color.
TRANS_KEY = "#000001"

PLACEHOLDER = "Ask anything —  / for tools · Ctrl+Alt+V to speak"

WIDTH = 760            # capsule width
PAD = 3                # canvas padding around the card (room for the outline)
RADIUS = 34            # capsule corner radius (clamped to height/2)
INSET_X = 24           # content inset so square widgets stay inside the curve
INSET_Y = 6
MAX_OUTPUT_LINES = 14  # visible output lines before it scrolls
MARGIN_BOTTOM = 48     # gap between the capsule and the bottom screen edge
ANIM_FRAMES = 12       # frames per animation
ANIM_MS = 12           # ms per frame (~145 ms total)

def _ease_out(t: float) -> float:
    return 1 - (1 - t) ** 3


def _round_rect(canvas, x1, y1, x2, y2, r, **kw):
    """Rounded rectangle as a smoothed polygon."""
    pts = [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2,
           x2 - r, y2, x1 + r, y2, x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]
    return canvas.create_polygon(pts, smooth=True, **kw)


class AsyncWorker:
    """Runs an asyncio event loop on a background thread."""

    def __init__(self):
        self.loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    def submit(self, coro) -> concurrent.futures.Future:
        return asyncio.run_coroutine_threadsafe(coro, self.loop)

    def stop(self):
        self.loop.call_soon_threadsafe(self.loop.stop)


class OperatorOverlay:
    def __init__(self, provider_name: Optional[str] = None):
        self.worker = AsyncWorker()

        self.root = tk.Tk()
        self.root.withdraw()
        self.root.title("OPERATOR")
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.configure(bg=TRANS_KEY)
        try:
            # Everything painted in TRANS_KEY disappears → rounded corners
            self.root.attributes("-transparentcolor", TRANS_KEY)
        except tk.TclError:
            pass

        self._busy = False
        self._fitting = False     # re-entry guard for _fit()
        self._recording = False
        self.voice = VoiceInput(Config.WHISPER_MODEL)
        # Tkinter is single-threaded: worker/hotkey threads never touch widgets
        # directly, they enqueue callables that this pump drains on the Tk thread
        self._ui_queue: "queue.Queue[Callable]" = queue.Queue()
        self._build_ui()
        self._pump()

        # Build the core on the async loop (constructor is sync but does I/O)
        self._set_status("Starting OPERATOR...", ACCENT)
        fut = self.worker.submit(self._build_core(provider_name))
        fut.add_done_callback(self._on_core_ready)

        self._hotkey_listener = None
        self._start_hotkey()

        # Global Esc/Enter bindings
        self.root.bind("<Escape>", lambda e: self.hide())

    def _enqueue(self, fn: Callable):
        """Schedule a UI update to run on the Tk main thread."""
        self._ui_queue.put(fn)

    def _pump(self):
        """Drain queued UI callbacks on the Tk thread; reschedule itself."""
        try:
            while True:
                self._ui_queue.get_nowait()()
        except queue.Empty:
            pass
        except Exception:
            op_logger.logger.exception("Overlay UI callback failed")
        self.root.after(40, self._pump)

    async def _build_core(self, provider_name):
        from orchestrator import OperatorCore
        return OperatorCore(
            provider_name=provider_name or Config.DEFAULT_AI_PROVIDER,
            confirm_callback=self._confirm,
            on_tool_event=self._on_tool_event,
        )

    def _on_core_ready(self, fut):
        try:
            self.core = fut.result()
            # Silently collapse the "Starting..." line — a clean capsule reads
            # as ready; no status text needed.
            self._enqueue(self._hide_output)
        except Exception as e:
            op_logger.logger.exception("Overlay core init failed")
            self.core = None
            self._enqueue(lambda: self._set_status(f"Init failed: {e}", ERR))

    # ==================== UI construction ====================

    def _build_ui(self):
        # Canvas paints the black capsule; the content frame sits inside it.
        self.canvas = tk.Canvas(self.root, bg=TRANS_KEY, highlightthickness=0, bd=0)
        self.canvas.pack(fill="both", expand=True)
        self._bg_item = _round_rect(self.canvas, 0, 0, 10, 10, RADIUS,
                                    fill=BG, outline=BORDER, width=1)

        # Inset the (square) content frame so it never covers the transparent
        # rounded-corner pixels of the canvas card.
        self.frame = tk.Frame(self.canvas, bg=BG)
        self._frame_item = self.canvas.create_window(
            INSET_X, INSET_Y, anchor="nw", window=self.frame,
            width=WIDTH - 2 * INSET_X,
        )

        # Bottom-anchored stack: input row sits at the bottom of the capsule;
        # suggestions, divider, and output stack upward above it.
        row = tk.Frame(self.frame, bg=BG)
        row.pack(fill="x", side="bottom")
        self.row = row
        self.icon = tk.Label(row, text=" ❯", bg=BG, fg=ACCENT,
                             font=("Segoe UI", 9, "bold"))
        self.icon.pack(side="left", padx=(4, 0))
        self.entry = tk.Entry(
            row, bg=BG, fg=FG, font=("Segoe UI", 8), bd=0,
            insertbackground=ACCENT, highlightthickness=0,
            disabledbackground=BG, disabledforeground=FG_DIM,
        )
        self.entry.pack(side="left", fill="x", expand=True, ipady=12, padx=(8, 10))
        self._spinner_job = None

        # Ghost placeholder: a floating label OVER the entry, never real text
        # in it — the cursor sits in a genuinely empty field.
        self.ph = tk.Label(row, text=PLACEHOLDER, bg=BG, fg=FG_DIM,
                           font=("Segoe UI", 8))
        self.ph.place(in_=self.entry, x=2, rely=0.5, anchor="w")
        self.ph.bind("<Button-1>", lambda e: self.entry.focus_set())

        # ----- Divider + result/status area (hidden until content) -----
        self.divider = tk.Frame(self.frame, bg=DIVIDER, height=1)
        self.output = tk.Text(
            self.frame, height=1, bg=BG, fg=FG, wrap="word",
            font=("Segoe UI", 8), bd=0, padx=10, pady=10,
            highlightthickness=0, insertbackground=FG,
        )
        self.output.tag_configure("dim", foreground=FG_DIM)
        self.output.tag_configure("ok", foreground=OK)
        self.output.tag_configure("err", foreground=ERR)
        self.output.tag_configure("accent", foreground=ACCENT)
        self.output.configure(state="disabled")

        # ----- Autocomplete list (hidden until '/') -----
        self.suggest = tk.Listbox(
            self.frame, bg=BG_INPUT, fg=FG, font=("Segoe UI", 8),
            bd=0, highlightthickness=0, selectbackground=ACCENT,
            selectforeground=BG, activestyle="none", height=0,
        )

        self.entry.bind("<Return>", self._on_submit)
        self.entry.bind("<KeyRelease>", self._on_key)
        self.entry.bind("<Up>", self._suggest_move_up)
        self.entry.bind("<Down>", self._suggest_move_down)
        self.entry.bind("<Tab>", self._suggest_accept)

        self._anim_job = None
        self.frame.bind("<Configure>", lambda e: self._fit(animate=True))
        self._fit()

    # ----- working spinner (animates the prompt icon; no bar needed) -----

    def _start_spinner(self):
        self._stop_spinner()
        self._spin_frame = 0
        self._spin()

    def _spin(self):
        self.icon.configure(text=f"  {SPINNER[self._spin_frame % len(SPINNER)]}")
        self._spin_frame += 1
        self._spinner_job = self.root.after(80, self._spin)

    def _stop_spinner(self):
        if self._spinner_job:
            self.root.after_cancel(self._spinner_job)
            self._spinner_job = None
        self.icon.configure(text="  ❯")

    # ----- placeholder -----

    def _ph_update(self, *_):
        """Show the ghost hint only while the entry is truly empty."""
        if self.entry.get():
            self.ph.place_forget()
        else:
            self.ph.place(in_=self.entry, x=2, rely=0.5, anchor="w")

    # ----- geometry -----

    def _target_geometry(self):
        """(w, h, x, y) for the capsule, bottom-center with a margin."""
        self.root.update_idletasks()
        w = WIDTH
        h = self.frame.winfo_reqheight() + 2 * INSET_Y
        x = (self.root.winfo_screenwidth() - w) // 2
        y = self.root.winfo_screenheight() - MARGIN_BOTTOM - h
        return w, h, x, y

    def _apply_geometry(self, w, h, x, y):
        self.root.geometry(f"{w}x{h}+{x}+{y}")
        self.canvas.configure(width=w, height=h)
        r = min(RADIUS, max(4, (h - 2) // 2))   # true capsule while slim
        self.canvas.coords(self._bg_item, *self._rect_points(1, 1, w - 2, h - 2, r))

    def _fit(self, animate=False):
        """Resize to content, bottom edge pinned (output grows upward)."""
        if self._fitting:
            return
        self._fitting = True
        try:
            w, h, x, y = self._target_geometry()
            current_h = self.root.winfo_height()
            visible = self.root.state() != "withdrawn"
            if not animate or not visible or abs(h - current_h) < 3:
                self._apply_geometry(w, h, x, y)
                return
            if self._anim_job:
                self.root.after_cancel(self._anim_job)
                self._anim_job = None
            bottom = y + h
            self._animate_height(w, x, bottom, current_h, h, 1)
        finally:
            self._fitting = False

    def _animate_height(self, w, x, bottom, h_from, h_to, frame):
        t = _ease_out(frame / ANIM_FRAMES)
        h = int(h_from + (h_to - h_from) * t)
        self._apply_geometry(w, h, x, bottom - h)
        if frame < ANIM_FRAMES:
            self._anim_job = self.root.after(
                ANIM_MS, lambda: self._animate_height(w, x, bottom, h_from, h_to, frame + 1))
        else:
            self._anim_job = None

    @staticmethod
    def _rect_points(x1, y1, x2, y2, r):
        return [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2,
                x2 - r, y2, x1 + r, y2, x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]

    # ==================== Show / hide ====================

    def toggle(self):
        # Called from the pynput hotkey thread
        self._enqueue(self._toggle)

    def _toggle(self):
        if self.root.state() == "withdrawn":
            self._show()
        else:
            self.hide()

    def _show(self):
        if not self._busy:
            self.entry.delete(0, "end")
            self._ph_update()
            self._hide_output()   # every summon starts as a clean capsule
        try:
            self.root.attributes("-alpha", 0.0)
        except tk.TclError:
            pass
        self.root.deiconify()
        self.root.lift()
        self.root.attributes("-topmost", True)
        self._force_focus()
        self.root.after(60, self._force_focus)
        self._slide_in()

    def _slide_in(self, frame=1):
        """Entrance: rise from below the resting spot while fading to opaque."""
        w, h, x, y = self._target_geometry()
        t = _ease_out(frame / ANIM_FRAMES)
        offset = int(26 * (1 - t))
        self._apply_geometry(w, h, x, y + offset)
        try:
            self.root.attributes("-alpha", t)
        except tk.TclError:
            pass
        if frame < ANIM_FRAMES:
            self.root.after(ANIM_MS, lambda: self._slide_in(frame + 1))

    def _force_focus(self):
        """Actually steal keyboard focus. Windows blocks SetForegroundWindow
        from background processes; briefly holding ALT lifts that lock."""
        try:
            import win32api
            import win32con
            import win32gui
            hwnd = win32gui.GetParent(self.root.winfo_id()) or self.root.winfo_id()
            win32api.keybd_event(win32con.VK_MENU, 0, 0, 0)
            try:
                win32gui.SetForegroundWindow(hwnd)
            finally:
                win32api.keybd_event(win32con.VK_MENU, 0, win32con.KEYEVENTF_KEYUP, 0)
        except Exception:
            pass
        self.entry.focus_force()

    def hide(self, *_):
        self._hide_suggest()
        self.root.withdraw()

    # ==================== Status / output ====================

    def _set_status(self, text, color=FG_DIM):
        self.output.configure(state="normal")
        self.output.delete("1.0", "end")
        self.output.insert("1.0", text)
        self.output.tag_add("dim", "1.0", "end")
        self.output.configure(state="disabled")
        self._show_output()

    def _set_output(self, text, tag=None):
        self.output.configure(state="normal")
        self.output.delete("1.0", "end")
        self.output.insert("1.0", text)
        if tag:
            self.output.tag_add(tag, "1.0", "end")
        self.output.configure(state="disabled")
        self._fit_output_height()
        self._show_output()

    def _append_output(self, text, tag="dim"):
        self.output.configure(state="normal")
        start = self.output.index("end-1c")
        self.output.insert("end", text + "\n")
        if tag:
            self.output.tag_add(tag, start, "end-1c")
        self.output.configure(state="disabled")
        self._fit_output_height()
        self.output.see("end")
        self._show_output()

    def _fit_output_height(self):
        """Size the output to its *wrapped* line count (long paragraphs wrap
        into many display lines); past the cap it scrolls with the wheel."""
        self.output.configure(height=1)
        self.output.update_idletasks()
        try:
            lines = int(self.output.count("1.0", "end", "displaylines")[0])
        except (TypeError, tk.TclError):
            lines = int(self.output.index("end-1c").split(".")[0])
        self.output.configure(height=max(1, min(lines, MAX_OUTPUT_LINES)))

    def _show_output(self):
        if not self.output.winfo_ismapped():
            anchor = self.suggest if self.suggest.winfo_ismapped() else self.row
            self.divider.pack(side="bottom", fill="x", after=anchor)
            self.output.pack(side="bottom", fill="both", expand=True, after=self.divider)
        self._fit(animate=True)

    def _hide_output(self):
        """Collapse the result area back to the bare capsule."""
        if self.output.winfo_ismapped():
            self.output.pack_forget()
            self.divider.pack_forget()
            self._fit(animate=True)

    # ==================== Submit ====================

    def _on_submit(self, event=None):
        # If a suggestion is highlighted, accept it instead of submitting
        if self.suggest.winfo_ismapped() and self.suggest.curselection():
            return self._suggest_accept()

        text = self.entry.get().strip()
        if not text or self._busy:
            return "break"
        if getattr(self, "core", None) is None:
            self._set_status("Still starting up...", WARN)
            return "break"

        self._hide_suggest()
        self._busy = True
        self.entry.configure(state="disabled")
        # No "Working..." bar — the prompt icon animates while the request
        # runs, and the panel only slides open for real content.
        self._start_spinner()

        fut = self.worker.submit(self.core.process_task(text))
        fut.add_done_callback(self._on_task_done)
        return "break"

    def _on_task_done(self, fut):
        try:
            result = fut.result()
            message = (result.message or "").strip() or ("Done." if result.success else "Failed.")
            tag = "ok" if result.success else "err"
        except Exception as e:
            op_logger.logger.exception("Overlay task failed")
            message, tag = f"Error: {e}", "err"

        def finish():
            self._stop_spinner()
            self._set_output(message, tag)
            self.entry.configure(state="normal")
            self.entry.delete(0, "end")
            self._ph_update()
            self.entry.focus_set()
            self._busy = False

        self._enqueue(finish)

    def _on_tool_event(self, display, success):
        def show():
            if success is None:
                self._append_output(f"▶ {display}", "dim")
            else:
                self._append_output(f"{'✓' if success else '✗'} {display}",
                                    "ok" if success else "err")
        self._enqueue(show)

    # ==================== Confirmation (async bridge) ====================

    async def _confirm(self, display, tier: RiskTier, reason: str) -> bool:
        fut: concurrent.futures.Future = concurrent.futures.Future()
        self._enqueue(lambda: self._show_confirm(display, tier, reason, fut))
        return await asyncio.wrap_future(fut)

    def _show_confirm(self, display, tier, reason, fut):
        color = DANGER if tier == RiskTier.DANGEROUS else WARN
        dialog = tk.Toplevel(self.root)
        dialog.overrideredirect(True)
        dialog.attributes("-topmost", True)
        dialog.configure(bg=BG)

        frame = tk.Frame(dialog, bg=BG, highlightthickness=2,
                         highlightbackground=color, highlightcolor=color)
        frame.pack(fill="both", expand=True)

        tk.Label(frame, text=f"Confirm {tier.value.upper()} action", bg=BG, fg=color,
                 font=("Segoe UI", 11, "bold")).pack(anchor="w", padx=16, pady=(14, 4))
        tk.Label(frame, text=display, bg=BG, fg=FG, font=("Consolas", 10),
                 wraplength=460, justify="left").pack(anchor="w", padx=16)
        tk.Label(frame, text=reason, bg=BG, fg=FG_DIM, font=("Segoe UI", 9),
                 wraplength=460, justify="left").pack(anchor="w", padx=16, pady=(2, 12))

        btns = tk.Frame(frame, bg=BG)
        btns.pack(anchor="e", padx=16, pady=(0, 14))

        done = {"v": False}

        def resolve(value):
            if done["v"]:
                return
            done["v"] = True
            fut.set_result(value)
            dialog.destroy()

        tk.Button(btns, text="Deny", command=lambda: resolve(False),
                  bg=BG_INPUT, fg=FG, bd=0, padx=16, pady=6,
                  activebackground="#333").pack(side="right", padx=(8, 0))
        tk.Button(btns, text="Allow", command=lambda: resolve(True),
                  bg=color, fg=BG, bd=0, padx=16, pady=6,
                  activebackground=color).pack(side="right")

        dialog.bind("<Escape>", lambda e: resolve(False))
        dialog.bind("<Return>", lambda e: resolve(True))

        dialog.update_idletasks()
        w, h = 500, dialog.winfo_reqheight()
        sw, sh = dialog.winfo_screenwidth(), dialog.winfo_screenheight()
        dialog.geometry(f"{w}x{h}+{(sw - w) // 2}+{(sh - h) // 2}")
        dialog.lift()
        dialog.focus_force()

    # ==================== Tool autocomplete ====================

    def _tool_names(self):
        from tools import ToolRegistry
        return sorted(ToolRegistry.list_tools())

    def _on_key(self, event):
        if event.keysym in ("Up", "Down", "Tab", "Return", "Escape"):
            return
        text = self.entry.get()
        self._ph_update()
        if text.startswith("/"):
            frag = text[1:].lower()
            matches = [f"/{n}" for n in self._tool_names() if n.startswith(frag)]
            self._show_suggest(matches)
        else:
            self._hide_suggest()

    def _show_suggest(self, matches):
        if not matches:
            self._hide_suggest()
            return
        self.suggest.delete(0, "end")
        for m in matches:
            self.suggest.insert("end", m)
        self.suggest.configure(height=min(len(matches), 6))
        if not self.suggest.winfo_ismapped():
            # Directly above the input row, below divider/output
            self.suggest.pack(side="bottom", fill="x", after=self.row)
        self._fit(animate=True)

    def _hide_suggest(self):
        if self.suggest.winfo_ismapped():
            self.suggest.pack_forget()
            self._fit(animate=True)

    def _suggest_move(self, delta):
        if not self.suggest.winfo_ismapped():
            return
        size = self.suggest.size()
        if not size:
            return
        cur = self.suggest.curselection()
        idx = (cur[0] + delta) if cur else (0 if delta > 0 else size - 1)
        idx = max(0, min(size - 1, idx))
        self.suggest.selection_clear(0, "end")
        self.suggest.selection_set(idx)
        self.suggest.see(idx)

    def _suggest_move_up(self, event):
        if self.suggest.winfo_ismapped():
            self._suggest_move(-1)
            return "break"

    def _suggest_move_down(self, event):
        if self.suggest.winfo_ismapped():
            self._suggest_move(1)
            return "break"

    def _suggest_accept(self, event=None):
        if not self.suggest.winfo_ismapped():
            return
        cur = self.suggest.curselection()
        idx = cur[0] if cur else 0
        if self.suggest.size():
            value = self.suggest.get(idx)
            self.entry.delete(0, "end")
            self.entry.insert(0, value + " ")
            self.entry.icursor("end")
            self._ph_update()
        self._hide_suggest()
        return "break"

    # ==================== Global hotkey ====================

    def _start_hotkey(self):
        try:
            from pynput import keyboard
        except ImportError:
            op_logger.logger.error("pynput not installed; global hotkey disabled")
            return
        hotkeys = {Config.OVERLAY_HOTKEY: self.toggle}
        if self.voice.dependencies_available():
            hotkeys[Config.VOICE_HOTKEY] = self.toggle_voice
        try:
            self._hotkey_listener = keyboard.GlobalHotKeys(hotkeys)
            self._hotkey_listener.start()
            op_logger.logger.info(f"Overlay hotkey active: {Config.OVERLAY_HOTKEY}")
            if Config.VOICE_HOTKEY in hotkeys:
                op_logger.logger.info(f"Voice hotkey active: {Config.VOICE_HOTKEY}")
        except Exception as e:
            op_logger.logger.error(f"Could not register hotkeys: {e}")

    # ==================== Voice (push-to-talk) ====================

    def toggle_voice(self):
        # Called from the pynput hotkey thread
        self._enqueue(self._voice_pressed)

    def _voice_pressed(self):
        """Toggle voice capture. Runs on the Tk thread."""
        if not self.voice.is_available():
            self._show()
            self._set_status(f"Voice unavailable: {self.voice.unavailable_reason()}", WARN)
            return
        if getattr(self, "core", None) is None:
            self._show()
            self._set_status("Still starting up...", WARN)
            return
        if self._recording:
            # Second press: stop recording early; the worker finishes up
            self.voice.stop()
            return
        if self._busy:
            return

        self._show()
        self._recording = True
        self._set_status("🎤 Listening… speak, then pause", ACCENT)
        threading.Thread(target=self._voice_worker, daemon=True).start()

    def _voice_worker(self):
        """Record → transcribe on a background thread, then submit the text."""
        text = ""
        try:
            if not self.voice.model_ready():
                self._enqueue(lambda: self._set_status("Loading speech model…", ACCENT))
                self.voice.ensure_model()
                self._enqueue(lambda: self._set_status("🎤 Listening… speak, then pause", ACCENT))
            audio = self.voice.record_until_silence()
            if audio is not None:
                self._enqueue(lambda: self._set_status("Transcribing…", ACCENT))
                text = self.voice.transcribe(audio)
        except Exception:
            op_logger.logger.exception("Voice input failed")
        finally:
            self._recording = False

        def done():
            if text:
                self.entry.delete(0, "end")
                self.entry.insert(0, text)
                self._ph_update()
                self._on_submit()
            else:
                self._set_status("Didn't catch that — press the voice key to retry", WARN)

        self._enqueue(done)

    # ==================== Lifecycle ====================

    def run(self):
        try:
            self.root.mainloop()
        finally:
            if self._hotkey_listener:
                self._hotkey_listener.stop()
            try:
                if getattr(self, "core", None):
                    self.core.conversation_memory.end_session()
                    self.core.memory.learning_system.flush()
            except Exception:
                pass
            self.worker.stop()


def run(provider_name: Optional[str] = None) -> int:
    is_valid, warnings = Config.validate_config()
    for w in warnings:
        print(f"Warning: {w}")
    if not is_valid:
        print("Configuration invalid. Set MISTRAL_API_KEY or GEMINI_API_KEY.")
        return 1

    print(f"OPERATOR overlay running. Press {Config.OVERLAY_HOTKEY} to summon it. Ctrl+C here to quit.")
    OperatorOverlay(provider_name).run()
    return 0
