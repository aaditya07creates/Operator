"""Browser bridge + tool tests. A fake extension client stands in for Chrome:
real WebSocket traffic over localhost, no browser needed."""

import asyncio
import json
import threading

import pytest

import safety
from safety import RiskTier


# ==================== Safety tiers ====================

def test_browser_tiers():
    assert safety.assess("browser", {"action": "tabs"}).tier == RiskTier.SAFE
    assert safety.assess("browser", {"action": "read"}).tier == RiskTier.SAFE
    assert safety.assess("browser", {"action": "navigate", "url": "https://x.com"}).tier == RiskTier.SAFE
    # click/fill auto-run — confirmations killed multi-step web flows
    assert safety.assess("browser", {"action": "click", "element": 3}).tier == RiskTier.SAFE
    assert safety.assess("browser", {"action": "fill", "element": 1, "text": "hi"}).tier == RiskTier.SAFE
    assert safety.assess("browser", {"action": "close_tab"}).tier == RiskTier.CAUTION


# ==================== Executor arg validation (no bridge needed) ====================

def _run(coro):
    return asyncio.run(coro)


def test_browser_requires_args(temp_data):
    from executor import CommandExecutor

    async def approve(display, tier, reason):
        return True  # click/fill are CAUTION; approve so arg validation runs

    ex = CommandExecutor(confirm_callback=approve)

    r = _run(ex.execute_tool_call("browser", {"action": "navigate"}))
    assert not r.success and "url" in r.error

    r = _run(ex.execute_tool_call("browser", {"action": "click"}))
    assert not r.success and "element" in r.error

    r = _run(ex.execute_tool_call("browser", {"action": "bogus"}))
    assert not r.success and "Unknown browser action" in r.error


# ==================== Bridge round-trip with a fake extension ====================

class FakeExtension:
    """Connects to the bridge like the real extension and answers requests."""

    def __init__(self, port):
        self.port = port
        self.connected = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self):
        asyncio.run(self._client())

    async def _client(self):
        import websockets
        async with websockets.connect(f"ws://127.0.0.1:{self.port}") as ws:
            self.connected.set()
            async for raw in ws:
                msg = json.loads(raw)
                action = msg["action"]
                if action == "ping":
                    reply = {"id": msg["id"], "ok": True, "result": "pong"}
                elif action == "read":
                    reply = {"id": msg["id"], "ok": True,
                             "result": {"url": "https://ex.com", "title": "Ex",
                                        "text": "hello page",
                                        "elements": [{"i": 0, "tag": "a", "text": "Link"}]}}
                elif action == "explode":
                    reply = {"id": msg["id"], "ok": False, "error": "boom"}
                else:
                    reply = {"id": msg["id"], "ok": True, "result": "done"}
                await ws.send(json.dumps(reply))


@pytest.fixture(scope="module")
def bridge():
    # Module-scoped: one server thread for all tests (the daemon thread holds
    # the port until process exit, so a second instance could not rebind it).
    from browser_bridge import BrowserBridge
    b = BrowserBridge(port=8391)  # dedicated test port
    assert b.start(), "bridge failed to start"
    return b


def test_bridge_not_connected_message(bridge):
    # connect_wait=0: don't sit through the grace period in tests
    ok, out, err = bridge.request("ping", {}, connect_wait=0)
    assert not ok and "not connected" in err.lower()


def test_bridge_roundtrip(bridge):
    import time
    ext = FakeExtension(bridge.port)
    assert ext.connected.wait(timeout=5), "fake extension never connected"
    # Client-side connect can complete before the server handler registers
    # the socket; wait for the bridge's own view of the connection.
    deadline = time.time() + 5
    while not bridge.connected() and time.time() < deadline:
        time.sleep(0.05)
    assert bridge.connected(), "bridge never registered the connection"

    ok, out, err = bridge.request("ping", {})
    assert ok and out == "pong"

    ok, out, err = bridge.request("read", {})
    assert ok and "hello page" in out and "Link" in out

    ok, out, err = bridge.request("explode", {})
    assert not ok and err == "boom"
