"""Safety Monitor (Program 28.0).

Inspects runtime command execution arguments, shell payloads, and operations
to identify and prevent unsafe system modifications and privilege escalation.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Set

UNSAFE_COMMAND_PATTERNS = [
    r"\brm\s+-rf\b",
    r"\bformat\s+[a-zA-Z]:",
    r"\bmkfs\b",
    r"\bdd\s+if\b",
    r"\bchmod\s+-R\s+777\b",
    r"\bchown\s+-R\b",
    r"powershell\s+-[eE]",
    r"\bsudo\s+",
]

DISALLOWED_BINARIES = {
    "curl",
    "wget",
    "nc",
    "netcat",
    "nmap",
    "telnet",
    "ssh",
    "scp",
    "ftp",
}


class SafetyMonitor:
    """Monitors real-time command strings and script lines for security risks."""

    def __init__(
        self,
        unsafe_patterns: Optional[List[str]] = None,
        disallowed_binaries: Optional[Set[str]] = None,
    ) -> None:
        self.unsafe_regexes = [
            re.compile(pat, re.IGNORECASE) for pat in (unsafe_patterns or UNSAFE_COMMAND_PATTERNS)
        ]
        self.disallowed_binaries = disallowed_binaries or DISALLOWED_BINARIES

    def is_safe_command(self, cmd: str) -> bool:
        """Inspects shell execution payloads against risk patterns and binaries."""
        # 1. Match unsafe regex commands
        for rx in self.unsafe_regexes:
            if rx.search(cmd):
                return False

        # 2. Prevent disallowed binary calls
        words = re.split(r"[&|;><\s`$()]", cmd)
        for w in words:
            clean = w.strip("'\"")
            if clean in self.disallowed_binaries:
                return False

        return True

    def inspect_action(self, tool_name: str, args: Dict[str, Any]) -> bool:
        """Evaluates tool specific argument payloads for unsafe parameters."""
        if tool_name == "shell_exec" or tool_name == "run_command":
            cmd = args.get("CommandLine") or args.get("command") or args.get("cmd")
            if cmd and not self.is_safe_command(str(cmd)):
                return False

        # Check for command injection in generic arguments
        for val in args.values():
            if isinstance(val, str):
                # If a parameter contains command chaining symbols and unsafe binaries
                if any(char in val for char in (";", "|", "&&", "||")):
                    for binary in self.disallowed_binaries:
                        if re.search(rf"\b{binary}\b", val):
                            return False

        return True
