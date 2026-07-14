"""Risk-tiered safety classification for tool calls.

Replaces the old regex-denylist CommandValidator. Every tool call gets a
SafetyVerdict:

- SAFE       runs automatically
- CAUTION    requires user confirmation
- DANGEROUS  requires user confirmation (rendered prominently)
- BLOCKED    never runs

Shell commands are classified by pattern; other tools have per-action tiers.
"""

import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Dict

from file_ops import FileOps


class RiskTier(Enum):
    SAFE = "safe"
    CAUTION = "caution"
    DANGEROUS = "dangerous"
    BLOCKED = "blocked"


@dataclass
class SafetyVerdict:
    tier: RiskTier
    reason: str


# Catastrophic or persistence-establishing commands: never run, regardless
# of confirmation. Patterns are matched case-insensitively on the raw string.
BLOCKED_PATTERNS = [
    (r'\bformat(?:\.com)?\s+[a-z]:', "Formats a drive"),
    (r'\bformat-volume\b', "Formats a volume"),
    (r'\bdiskpart\b', "Disk partitioning"),
    (r'\bvssadmin\b.*\bdelete\b', "Deletes shadow copies"),
    (r'\bwbadmin\b.*\bdelete\b', "Deletes backups"),
    (r'\bcipher\b.*/w', "Wipes disk free space"),
    (r'\bbcdedit\b', "Modifies boot configuration"),
    (r'(?=.*\b(?:rd|rmdir|del|erase)\b)(?=.*/s)(?=.*(?:[a-z]:\\(?:\s|"|\'|$)|\\windows\b|\\system32\b|%systemroot%|%windir%))',
     "Recursive delete of a system path or drive root"),
    (r'(?=.*\bremove-item\b)(?=.*-recurse)(?=.*(?:[a-z]:\\(?:\s|"|\'|$)|\\windows\b|\\system32\b|c:\\users\\?(?:\s|"|\'|$)|\$env:systemroot|\$env:windir))',
     "Recursive delete of a system path or drive root"),
    (r'\breg\s+add\b.*\\(?:run|runonce)\b', "Registry autorun persistence"),
    (r'\bschtasks\b.*/create', "Creates a scheduled task"),
    (r'\b(?:set|add)-mppreference\b', "Modifies Windows Defender settings"),
    (r'\bset-executionpolicy\b', "Changes PowerShell execution policy"),
    (r'-(?:e|en|enc|encodedcommand)\s+[a-z0-9+/=]{16,}', "Encoded PowerShell command"),
    (r'\b(?:iwr|invoke-webrequest|curl|wget)\b.*\|\s*(?:iex|invoke-expression)', "Download-and-execute"),
    (r'\biex\s*\(', "Dynamic PowerShell execution"),
    (r'\binvoke-expression\b', "Dynamic PowerShell execution"),
    (r'\bcertutil\b.*-urlcache', "Certutil download technique"),
    (r'\bmshta\b', "MSHTA execution technique"),
    (r'\bbitsadmin\b', "BITS transfer technique"),
    (r'\bshutdown\b', "Shuts down or restarts the machine"),
    (r'\bnet\s+user\b.*/add', "Creates a user account"),
    (r'\bnet\s+localgroup\s+administrators\b', "Modifies the administrators group"),
    (r'%0\|%0', "Fork bomb"),
    (r'\btaskkill\b.*(?:explorer\.exe|winlogon|csrss|lsass|services\.exe)', "Kills a critical system process"),
    (r'\bstop-process\b.*(?:explorer|winlogon|csrss|lsass)', "Kills a critical system process"),
]

# Destructive-but-legitimate commands: run only after prominent confirmation.
DANGEROUS_SHELL_PATTERNS = [
    (r'\b(?:del|erase|rd|rmdir)\b', "Deletes files or directories"),
    (r'\bremove-item\b|\bri\s', "Deletes files or directories"),
    (r'\breg\s+(?:add|delete)\b', "Modifies the registry"),
    (r'\bset-itemproperty\b.*hk(?:lm|cu)', "Modifies the registry"),
    (r'\bsc\s+(?:config|stop|delete|create)\b', "Modifies a Windows service"),
    (r'\b(?:stop|restart)-service\b|\bnet\s+stop\b', "Stops a Windows service"),
    (r'\btaskkill\b|\bstop-process\b|\bkill\s', "Terminates a process"),
    (r'\bnetsh\b', "Changes network configuration"),
    (r'\bmove\b.*(?:\\windows|\\system32)', "Moves system files"),
    (r'\battrib\b', "Changes file attributes"),
    (r'\brunas\b', "Runs as another user"),
]

# First tokens of read-only commands that are always safe to run.
SAFE_SHELL_STARTERS = {
    # cmd
    'dir', 'type', 'echo', 'where', 'whoami', 'hostname', 'systeminfo',
    'ipconfig', 'ping', 'tasklist', 'tree', 'ver', 'vol', 'findstr', 'more',
    'start', 'explorer', 'timeout', 'cd', 'chdir', 'path', 'help', 'assoc',
    'date', 'time', 'title', 'cls',
    # powershell (read-only verbs)
    'get-childitem', 'gci', 'ls', 'get-process', 'gps', 'get-item',
    'get-content', 'gc', 'cat', 'get-service', 'get-date', 'get-location',
    'get-appxpackage', 'select-string', 'test-path', 'resolve-path',
    'get-ciminstance', 'get-wmiobject', 'get-itemproperty', 'get-command',
    'get-host', 'measure-object', 'write-output', 'write-host',
}


def _classify_shell(command: str) -> SafetyVerdict:
    lowered = command.lower().strip()

    for pattern, reason in BLOCKED_PATTERNS:
        if re.search(pattern, lowered):
            return SafetyVerdict(RiskTier.BLOCKED, reason)

    for pattern, reason in DANGEROUS_SHELL_PATTERNS:
        if re.search(pattern, lowered):
            return SafetyVerdict(RiskTier.DANGEROUS, reason)

    # `powershell -Command "..."` wrappers: classify the inner command too
    inner = re.sub(r'^powershell(?:\.exe)?\s+(?:-\w+\s+)*(?:-command\s+)?"?', '', lowered).strip('"\' ')
    first_token = (inner.split() or [''])[0]
    if first_token in SAFE_SHELL_STARTERS:
        return SafetyVerdict(RiskTier.SAFE, "Read-only or launch command")

    return SafetyVerdict(RiskTier.CAUTION, "Unrecognized shell command")


def _is_in_sandbox(path_str: str) -> bool:
    """True if the path resolves inside the OperatorPrograms output folder."""
    try:
        path = Path(path_str)
        if not path.is_absolute():
            return True  # relative paths resolve into OperatorPrograms
        resolved = path.resolve()
        sandbox = FileOps.DEFAULT_OUTPUT_DIR.resolve()
        return sandbox == resolved or sandbox in resolved.parents
    except Exception:
        return False


def assess(tool_name: str, args: Dict) -> SafetyVerdict:
    """Classify a tool call into a risk tier."""
    args = args or {}
    action = str(args.get("action", "")).lower()

    if tool_name == "run_shell":
        return _classify_shell(str(args.get("command", "")))

    if tool_name == "write_file":
        if _is_in_sandbox(str(args.get("path", ""))):
            return SafetyVerdict(RiskTier.SAFE, "Write inside OperatorPrograms")
        return SafetyVerdict(RiskTier.CAUTION, "Write outside OperatorPrograms")

    if tool_name == "run_file":
        return SafetyVerdict(RiskTier.DANGEROUS, "Executes a file")

    if tool_name == "keyboard":
        return SafetyVerdict(RiskTier.CAUTION, "Sends keystrokes to the focused window")

    if tool_name == "manage_window":
        if action == "close":
            return SafetyVerdict(RiskTier.CAUTION, "Closes a window")
        return SafetyVerdict(RiskTier.SAFE, "Window management")

    if tool_name == "clipboard":
        if action in ("get",):
            return SafetyVerdict(RiskTier.SAFE, "Reads clipboard")
        if action == "save_image":
            if _is_in_sandbox(str(args.get("path", ""))):
                return SafetyVerdict(RiskTier.SAFE, "Saves clipboard image inside OperatorPrograms")
            return SafetyVerdict(RiskTier.CAUTION, "Saves clipboard image outside OperatorPrograms")
        return SafetyVerdict(RiskTier.CAUTION, "Modifies clipboard or injects keystrokes")

    if tool_name == "manage_process":
        if action == "kill":
            name = str(args.get("name", "")).lower()
            critical = {'explorer.exe', 'explorer', 'winlogon.exe', 'csrss.exe',
                        'lsass.exe', 'services.exe', 'svchost.exe'}
            if name in critical:
                return SafetyVerdict(RiskTier.BLOCKED, "Critical system process")
            return SafetyVerdict(RiskTier.CAUTION, "Terminates a process")
        return SafetyVerdict(RiskTier.SAFE, "Process inspection")

    if tool_name == "file_explorer":
        if action in ("search", "list", "info", "storage"):
            return SafetyVerdict(RiskTier.SAFE, "Read-only file operation")
        if action == "mkdir":
            return SafetyVerdict(RiskTier.SAFE, "Creates a directory")
        if action in ("delete", "delete_force"):
            return SafetyVerdict(RiskTier.DANGEROUS, "Deletes files or folders")
        return SafetyVerdict(RiskTier.CAUTION, "Modifies the filesystem")

    if tool_name == "read_file":
        return SafetyVerdict(RiskTier.SAFE, "Reads a file")

    if tool_name == "browser":
        # click/fill run without confirmation — friction kills multi-step web
        # flows, and page actions are recoverable. Only closing a tab asks.
        if action in ("tabs", "read", "open", "navigate", "click", "fill"):
            return SafetyVerdict(RiskTier.SAFE, "Browser interaction")
        if action == "close_tab":
            return SafetyVerdict(RiskTier.CAUTION, "Closes a browser tab")
        return SafetyVerdict(RiskTier.CAUTION, "Browser action")

    if tool_name in ("web_search", "remember", "forget", "update_core_memory"):
        return SafetyVerdict(RiskTier.SAFE, "No system side effects")

    return SafetyVerdict(RiskTier.CAUTION, f"Unknown tool: {tool_name}")
