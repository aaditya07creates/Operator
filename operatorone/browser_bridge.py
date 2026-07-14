"""Localhost WebSocket bridge between OPERATOR and its Chrome extension.

The companion extension (see extension/ in the repo root) connects OUT to
ws://127.0.0.1:<port> from the user's everyday Chrome. OPERATOR sends JSON
requests {id, action, params} and the extension answers {id, ok, result|error}.
That means no debug flags, no separate browser profile — actions run in the
browser the user actually works in, and results come back as text (no vision).

Threading model: the server runs an asyncio loop on a dedicated daemon
thread (started lazily on first use). Executor handlers are synchronous and
run in worker threads, so `request()` marshals onto the bridge loop with
run_coroutine_threadsafe and blocks on the returned future. One extension
connection is active at a time; a new connection replaces the old.
"""

import asyncio
import json
import threading
import time
import uuid
from typing import Dict, Optional, Tuple

from config import Config
from logger_config import op_logger

NOT_CONNECTED = (
    "Browser extension not connected. Open Chrome → chrome://extensions → "
    "enable Developer mode → 'Load unpacked' → select the extension/ folder "
    "in the OPERATOR repo. It connects automatically."
)


class BrowserBridge:
    """Singleton WebSocket server the extension connects to."""

    _instance: Optional["BrowserBridge"] = None
    _instance_lock = threading.Lock()

    def __init__(self, port: int):
        self.port = port
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self._ws = None                      # active extension connection
        self._pending: Dict[str, asyncio.Future] = {}
        self._started = threading.Event()    # set once the server is listening
        self._start_lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._start_error: str = ""

    @classmethod
    def get(cls) -> "BrowserBridge":
        with cls._instance_lock:
            if cls._instance is None:
                cls._instance = cls(Config.BROWSER_BRIDGE_PORT)
            return cls._instance

    # ==================== Lifecycle ====================

    def start(self) -> bool:
        """Start the server thread (idempotent). True if listening."""
        with self._start_lock:
            if self._thread is not None:
                return self._started.wait(timeout=5) and not self._start_error
            self._thread = threading.Thread(
                target=self._run_loop, name="browser-bridge", daemon=True
            )
            self._thread.start()
        ok = self._started.wait(timeout=5)
        return ok and not self._start_error

    def _run_loop(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        try:
            self.loop.run_until_complete(self._serve())
            self.loop.run_forever()
        except Exception as e:
            self._start_error = str(e)
            op_logger.logger.error(f"Browser bridge failed to start: {e}")
            self._started.set()  # unblock waiters; connected() stays False

    async def _serve(self):
        import websockets
        self._server = await websockets.serve(
            self._handler, "127.0.0.1", self.port, max_size=4 * 1024 * 1024
        )
        op_logger.logger.info(f"Browser bridge listening on ws://127.0.0.1:{self.port}")
        self._started.set()

    async def _handler(self, websocket):
        if self._ws is not None:
            op_logger.logger.info("Browser extension reconnected (replacing old connection)")
        else:
            op_logger.logger.info("Browser extension connected")
        self._ws = websocket
        try:
            async for raw in websocket:
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                fut = self._pending.pop(str(msg.get("id", "")), None)
                if fut is not None and not fut.done():
                    fut.set_result(msg)
        except Exception:
            pass
        finally:
            if self._ws is websocket:
                self._ws = None
                op_logger.logger.info("Browser extension disconnected")

    # ==================== Requests ====================

    def connected(self) -> bool:
        return self._ws is not None

    def _wait_for_connection(self, wait_seconds: float) -> bool:
        """Poll for the extension handshake. Its reconnect loop retries every
        1-15s, so a short wait bridges the gap between server start and the
        extension's next attempt."""
        deadline = time.monotonic() + wait_seconds
        while self._ws is None and time.monotonic() < deadline:
            time.sleep(0.25)
        return self._ws is not None

    def request(self, action: str, params: Dict, timeout: float = 20.0,
                connect_wait: float = 12.0) -> Tuple[bool, str, str]:
        """Send one request to the extension and wait for its reply.

        Thread-safe; call from any thread. Returns (success, output, error)
        matching the executor's OpResult convention.
        """
        if not self.start():
            return False, "", self._start_error or "Browser bridge could not start"
        if self._ws is None and connect_wait > 0:
            op_logger.logger.info("Waiting for browser extension to connect...")
            self._wait_for_connection(connect_wait)
        if self._ws is None:
            return False, "", NOT_CONNECTED

        async def _send() -> dict:
            req_id = uuid.uuid4().hex
            fut = self.loop.create_future()
            self._pending[req_id] = fut
            try:
                await self._ws.send(json.dumps(
                    {"id": req_id, "action": action, "params": params or {}}
                ))
                return await asyncio.wait_for(fut, timeout=timeout)
            finally:
                self._pending.pop(req_id, None)

        try:
            cfut = asyncio.run_coroutine_threadsafe(_send(), self.loop)
            msg = cfut.result(timeout=timeout + 5)
        except (asyncio.TimeoutError, TimeoutError):
            return False, "", f"Browser action timed out after {timeout}s"
        except Exception as e:
            return False, "", f"Browser bridge error: {e}"

        if msg.get("ok"):
            result = msg.get("result", "")
            if not isinstance(result, str):
                result = json.dumps(result, ensure_ascii=False, indent=1)
            if len(result) > Config.MAX_OUTPUT_LENGTH * 3:
                result = result[:Config.MAX_OUTPUT_LENGTH * 3] + "\n... (truncated)"
            return True, result, ""
        return False, "", str(msg.get("error", "Browser action failed"))
