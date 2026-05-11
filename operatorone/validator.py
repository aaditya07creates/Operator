import re
from typing import Tuple, List
from dataclasses import dataclass

from learning_system import LearningSystem
from logger_config import op_logger


@dataclass
class ValidationRule:
    """A validation rule"""
    name: str
    pattern: str
    is_dangerous: bool
    reason: str
    exceptions: List[str] = None  # Patterns that override this rule


class CommandValidator:
    """
    Validates commands for safety before execution.
    Blocks dangerous operations while allowing legitimate use.
    """

    def __init__(self, memory: LearningSystem):
        self.memory = memory
        self.validation_rules = self._build_validation_rules()

    def _build_validation_rules(self) -> List[ValidationRule]:
        """Build list of validation rules"""
        return [
            # Critical System Files
            ValidationRule(
                name="system32_deletion",
                pattern=r"(rm|del|rmdir|Remove-Item).*system32",
                is_dangerous=True,
                reason="Attempting to delete System32",
            ),

            ValidationRule(
                name="boot_files",
                pattern=r"(rm|del|Remove-Item).*(boot|ntldr|bootmgr)",
                is_dangerous=True,
                reason="Attempting to delete boot files",
            ),

            # Registry Dangers
            ValidationRule(
                name="registry_deletion",
                pattern=r"reg\s+delete.*HKLM.*/(f|force)",
                is_dangerous=True,
                reason="Dangerous registry deletion",
            ),

            # Recursive Deletions
            ValidationRule(
                name="recursive_c_drive",
                pattern=r"(rm|del|rmdir|Remove-Item).*C:\\.*/[srf]",
                is_dangerous=True,
                reason="Recursive deletion on C drive",
                exceptions=[r"C:\\(Users|Temp|tmp)"]  # Allow temp folders
            ),

            # Format Commands
            ValidationRule(
                name="format_drive",
                pattern=r"format\s+[a-zA-Z]:",
                is_dangerous=True,
                reason="Drive format command",
            ),

            # Process Killers (too broad)
            ValidationRule(
                name="kill_all_processes",
                pattern=r"(taskkill|Stop-Process).*\*.*(/f|-Force)",
                is_dangerous=True,
                reason="Attempting to kill all processes",
            ),

            # Explorer.exe (unless intentional)
            ValidationRule(
                name="kill_explorer",
                pattern=r"(taskkill|Stop-Process).*explorer\.exe",
                is_dangerous=True,
                reason="Killing Windows Explorer (will restart shell)",
                exceptions=[r"restart.*explorer"]  # Allow if "restart" in command
            ),

            # PowerShell Downloads (risky)
            ValidationRule(
                name="powershell_download",
                pattern=r"Invoke-WebRequest.*\|.*Invoke-Expression",
                is_dangerous=True,
                reason="Download and execute pattern (potential malware)",
            ),

            # Bcdedit (boot configuration)
            ValidationRule(
                name="boot_config",
                pattern=r"bcdedit",
                is_dangerous=True,
                reason="Modifying boot configuration",
            ),
        ]

    def validate(self, command: str) -> Tuple[bool, str]:
        """
        Validate a command for safety.

        Args:
            command: The command to validate

        Returns:
            (is_valid, reason) - reason is empty string if valid
        """

        # Check against all rules
        for rule in self.validation_rules:
            if self._matches_rule(command, rule):
                # Check for exceptions
                if rule.exceptions:
                    if any(re.search(exc, command, re.IGNORECASE) for exc in rule.exceptions):
                        continue  # Exception matched, skip this rule

                # Rule matched and no exception - block it
                op_logger.logger.warning(f"🛑 Blocked: {rule.name}")
                return False, rule.reason

        # No rules matched - safe to execute
        return True, ""

    def _matches_rule(self, command: str, rule: ValidationRule) -> bool:
        """Check if command matches a validation rule"""
        try:
            return bool(re.search(rule.pattern, command, re.IGNORECASE))
        except re.error:
            op_logger.logger.error(f"Invalid regex in rule {rule.name}: {rule.pattern}")
            return False

    def add_custom_rule(
            self,
            name: str,
            pattern: str,
            reason: str,
            exceptions: List[str] = None
    ):
        """
        Add a custom validation rule at runtime.

        Args:
            name: Rule identifier
            pattern: Regex pattern to match
            reason: Why this command is blocked
            exceptions: Optional exception patterns
        """
        rule = ValidationRule(
            name=name,
            pattern=pattern,
            is_dangerous=True,
            reason=reason,
            exceptions=exceptions
        )
        self.validation_rules.append(rule)
        op_logger.logger.info(f"Added custom rule: {name}")

    def remove_rule(self, name: str) -> bool:
        """Remove a validation rule by name"""
        original_len = len(self.validation_rules)
        self.validation_rules = [r for r in self.validation_rules if r.name != name]

        if len(self.validation_rules) < original_len:
            op_logger.logger.info(f"Removed rule: {name}")
            return True
        return False

    def list_rules(self) -> List[str]:
        """List all active validation rules"""
        return [f"{r.name}: {r.reason}" for r in self.validation_rules]