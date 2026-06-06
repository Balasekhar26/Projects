from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class WritingIssue:
    rule: str
    message: str
    start: int
    end: int
    replacement: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule": self.rule,
            "message": self.message,
            "start": self.start,
            "end": self.end,
            "replacement": self.replacement,
        }


def harper_status() -> dict[str, Any]:
    command = _harper_command()
    return {
        "engine": "harper",
        "installed": command is not None,
        "command": command,
        "fallback": "kattappa-local-writing-rules",
        "license": "Apache-2.0",
        "network_required": False,
        "install_hint": "Install Harper locally, then make harper or harper-ls available on PATH.",
    }


def check_with_harper(text: str) -> dict[str, Any]:
    normalized = text.strip()
    if not normalized:
        return _result("empty", [], normalized, "No text supplied.")

    command = _harper_command()
    if command:
        external = _try_harper_cli(command, normalized)
        if external:
            return external

    issues = _fallback_issues(normalized)
    corrected = _apply_replacements(normalized, issues)
    return _result("kattappa-local-writing-rules", issues, corrected)


def _harper_command() -> str | None:
    for command in ("harper", "harper-ls"):
        path = shutil.which(command)
        if path:
            return path
    return None


def _try_harper_cli(command: str, text: str) -> dict[str, Any] | None:
    try:
        completed = subprocess.run(
            [command, "--help"],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
    except Exception:
        return None
    if completed.returncode not in {0, 1}:
        return None
    return _result(
        "harper-detected",
        _fallback_issues(text),
        _apply_replacements(text, _fallback_issues(text)),
        "Harper is detected; direct CLI diagnostics are not enabled yet, so local fallback rules ran.",
    )


def _fallback_issues(text: str) -> list[WritingIssue]:
    issues: list[WritingIssue] = []
    for match in re.finditer(r"\b([A-Za-z]+)\s+\1\b", text, flags=re.IGNORECASE):
        issues.append(
            WritingIssue(
                "repeated_word",
                f"Repeated word: {match.group(1)}",
                match.start(1),
                match.end(),
                match.group(1),
            )
        )
    for match in re.finditer(r" {2,}", text):
        issues.append(
            WritingIssue(
                "extra_space",
                "Multiple spaces found.",
                match.start(),
                match.end(),
                " ",
            )
        )
    for match in re.finditer(r"\b(i)\b", text):
        issues.append(
            WritingIssue(
                "capitalization",
                "The pronoun I should be capitalized.",
                match.start(),
                match.end(),
                "I",
            )
        )
    for match in re.finditer(r"\b(ain't|dont|doesnt|cant|wont)\b", text, flags=re.IGNORECASE):
        replacement = {
            "ain't": "is not",
            "dont": "do not",
            "doesnt": "does not",
            "cant": "cannot",
            "wont": "will not",
        }.get(match.group(1).lower())
        issues.append(
            WritingIssue(
                "informal_or_missing_apostrophe",
                f"Consider replacing '{match.group(1)}'.",
                match.start(),
                match.end(),
                replacement,
            )
        )
    return issues


def _apply_replacements(text: str, issues: list[WritingIssue]) -> str:
    corrected = text
    for issue in sorted(issues, key=lambda item: item.start, reverse=True):
        if issue.replacement is not None:
            corrected = corrected[: issue.start] + issue.replacement + corrected[issue.end :]
    return corrected


def _result(
    engine: str,
    issues: list[WritingIssue],
    corrected_text: str,
    note: str = "",
) -> dict[str, Any]:
    return {
        "engine": engine,
        "issues": [issue.to_dict() for issue in issues],
        "issue_count": len(issues),
        "corrected_text": corrected_text,
        "network_required": False,
        "note": note,
    }
