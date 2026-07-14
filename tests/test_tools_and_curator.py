"""Slash-command parsing and executor dispatch/gating."""

import asyncio

import pytest


# ==================== Slash command parsing ====================

def test_slash_only_at_start(temp_data):
    import tools
    assert tools.process_tool_command("open C:/Users/me/notes.txt")[0] is False
    assert tools.process_tool_command("what is 2/3 of 9")[0] is False
    assert tools.process_tool_command("summarize http://a.com/b/c")[0] is False


def test_slash_recognized(temp_data):
    import tools
    ok, res, _ = tools.process_tool_command("/help")
    assert ok and res.success
    ok, res, _ = tools.process_tool_command("  /tiers")
    assert ok
    ok, res, _ = tools.process_tool_command("/bogus")
    assert ok and not res.success and "Unknown tool" in res.error


# ==================== Executor dispatch + safety gating ====================

def _run(coro):
    return asyncio.run(coro)


def test_blocked_never_runs(temp_data):
    from executor import CommandExecutor
    BS = chr(92)
    rm = "Remove" + "-Item"

    async def confirm(display, tier, reason):
        raise AssertionError("BLOCKED must never prompt")

    ex = CommandExecutor(confirm_callback=confirm)
    r = _run(ex.execute_tool_call("run_shell", {"command": f"{rm} C:{BS}Windows -Recurse"}))
    assert not r.success and "Blocked" in r.error


def test_caution_declined(temp_data):
    from executor import CommandExecutor

    async def confirm(display, tier, reason):
        return False

    ex = CommandExecutor(confirm_callback=confirm)
    r = _run(ex.execute_tool_call("keyboard", {"action": "type", "text": "hi"}))
    assert not r.success and "declined" in r.error.lower()


def test_safe_shell_runs(temp_data):
    from executor import CommandExecutor
    ex = CommandExecutor()
    r = _run(ex.execute_tool_call("run_shell", {"command": "echo hello"}))
    assert r.success and "hello" in r.output


def test_unknown_tool(temp_data):
    from executor import CommandExecutor
    ex = CommandExecutor()
    r = _run(ex.execute_tool_call("nonexistent", {}))
    assert not r.success and "Unknown tool" in r.error


def test_write_then_read_file_roundtrip(tmp_path):
    from executor import CommandExecutor

    async def approve(display, tier, reason):
        return True  # writing outside the sandbox is CAUTION

    ex = CommandExecutor(confirm_callback=approve)
    target = str(tmp_path / "note.txt")

    w = _run(ex.execute_tool_call("write_file", {"path": target, "content": "hello ops"}))
    assert w.success

    r = _run(ex.execute_tool_call("read_file", {"path": target}))  # read is SAFE
    assert r.success and "hello ops" in r.output


def test_read_missing_file_fails(tmp_path):
    from executor import CommandExecutor
    ex = CommandExecutor()
    r = _run(ex.execute_tool_call("read_file", {"path": str(tmp_path / "nope.txt")}))
    assert not r.success and "not found" in r.error.lower()


# ==================== Memory is self-managed (no background curator) ====================

def test_remember_and_forget_roundtrip(temp_data):
    """OPERATOR edits its own memory in first person via the tools — the only
    path that writes facts. Nothing curates behind it."""
    from memory import MemoryManager

    mem = MemoryManager()
    fact_id = mem.remember_fact(category="personal", content="User prefers concise answers")
    assert fact_id
    facts = mem.learning_system.learnings["knowledge_base"]["facts"]
    assert any("concise answers" in f["content"] for f in facts)

    assert mem.forget_fact(fact_id)
    facts = mem.learning_system.learnings["knowledge_base"]["facts"]
    assert not any(f["id"] == fact_id for f in facts)


def test_no_curator_module():
    """The background curator was removed; importing it should fail."""
    import importlib
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("memory_curator")
