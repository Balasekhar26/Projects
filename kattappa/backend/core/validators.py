"""Tool-Backed Validators (Phase 3).

The reasoning layers (Scientist/Engineer/Critic/...) are one base model in
different costumes, so their agreement is correlated. Validators are the
antidote: **deterministic, tool-backed reality checks** that produce genuinely
independent evidence. They never call an LLM.

Each validator returns a :class:`ValidatorResult` that:

* plugs into Consensus v2 as an independent evidence source (PASS ->
  ``tool_verified`` 1.0; a veto-class FAIL becomes a consensus ``Veto``), and
* signals when a human must approve (per the Phase 3 approval rules).

Validators (build order):

1. SecurityValidator    - secrets, dangerous ops, injection, unsafe perms (veto)
2. CompilerValidator    - does the code parse / build (veto)
3. PhysicsMathValidator - conservation, power/battery budgets, units (veto)
4. TestValidator        - regressions / coverage (no veto; triggers approval)
5. DataIntegrityValidator - duplicates, invalid refs, orphans, corruption

This module imports the consensus value types one-way (no cycle) and never
touches the memory system.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping

from backend.core.consensus_engine import AgentOutput, Decision, EvidenceType, Veto


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

class ValidationStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"


class Severity(str, Enum):
    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

    @property
    def rank(self) -> int:
        return {
            Severity.NONE: 0, Severity.LOW: 1, Severity.MEDIUM: 2,
            Severity.HIGH: 3, Severity.CRITICAL: 4,
        }[self]


@dataclass(frozen=True)
class Finding:
    message: str
    severity: Severity
    code: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"message": self.message, "severity": self.severity.value, "code": self.code}


@dataclass(frozen=True)
class ValidatorResult:
    validator: str
    status: ValidationStatus
    severity: Severity
    veto: bool
    requires_human_approval: bool
    findings: tuple[Finding, ...] = ()
    details: Mapping[str, Any] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return self.status is ValidationStatus.PASS

    def to_consensus_output(self) -> AgentOutput:
        """Independent evidence source for Consensus v2."""
        return AgentOutput(
            agent=self.validator,
            decision=Decision.APPROVE if self.passed else Decision.REJECT,
            confidence=100.0,
            evidence=(EvidenceType.TOOL_VERIFIED,),
            veto=(Veto(self.validator, self.passed,
                       "" if self.passed else f"{self.validator} FAIL ({self.severity.value})")
                  if self.veto else None),
            source_id=f"validator:{self.validator}",
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "validator": self.validator,
            "status": self.status.value,
            "severity": self.severity.value,
            "veto": self.veto,
            "requires_human_approval": self.requires_human_approval,
            "findings": [f.to_dict() for f in self.findings],
            "details": dict(self.details),
        }


def _peak_severity(findings: list[Finding]) -> Severity:
    return max((f.severity for f in findings), key=lambda s: s.rank, default=Severity.NONE)


# ---------------------------------------------------------------------------
# Base
# ---------------------------------------------------------------------------

class Validator:
    name: str = "validator"
    veto: bool = False

    def validate(self, payload: Any) -> ValidatorResult:  # pragma: no cover - abstract
        raise NotImplementedError

    @staticmethod
    def _gather_text(payload: Any) -> str:
        if isinstance(payload, str):
            return payload
        if isinstance(payload, Mapping):
            parts = []
            for key in ("code", "text", "command", "config", "content"):
                value = payload.get(key)
                if isinstance(value, str):
                    parts.append(value)
            return "\n".join(parts)
        return ""


# ---------------------------------------------------------------------------
# 1. Security Validator
# ---------------------------------------------------------------------------

_SECURITY_PATTERNS: tuple[tuple[str, Severity, str], ...] = (
    (r"-----BEGIN (?:RSA |EC |OPENSSH |DSA |)PRIVATE KEY-----", Severity.CRITICAL, "private_key"),
    (r"AKIA[0-9A-Z]{16}", Severity.CRITICAL, "aws_key"),
    (r"ghp_[A-Za-z0-9]{20,}", Severity.CRITICAL, "github_token"),
    (r"sk-[A-Za-z0-9]{20,}", Severity.CRITICAL, "api_key"),
    (r"(?i)(password|passwd|secret|api[_-]?key|token)\s*[:=]\s*['\"][^'\"]{4,}['\"]",
     Severity.HIGH, "hardcoded_secret"),
    (r"rm\s+-rf\b", Severity.HIGH, "destructive_command"),
    (r"\beval\s*\(", Severity.HIGH, "eval"),
    (r"\bexec\s*\(", Severity.HIGH, "exec"),
    (r"os\.system\s*\(", Severity.HIGH, "os_system"),
    (r"shell\s*=\s*True", Severity.HIGH, "shell_true"),
    (r"pickle\.loads?\s*\(", Severity.MEDIUM, "pickle"),
    (r"yaml\.load\s*\((?![^)]*Safe)", Severity.MEDIUM, "yaml_load"),
    (r"chmod\s+777|0o?777", Severity.MEDIUM, "loose_permissions"),
    (r"(?i)execute\s*\(\s*[f'\"].*(%s|\+|\{)", Severity.MEDIUM, "sql_injection"),
)


class SecurityValidator(Validator):
    name = "Security"
    veto = True

    def validate(self, payload: Any) -> ValidatorResult:
        text = self._gather_text(payload)
        findings: list[Finding] = []
        for pattern, severity, code in _SECURITY_PATTERNS:
            if re.search(pattern, text):
                findings.append(Finding(f"{code} detected", severity, code))
        peak = _peak_severity(findings)
        status = ValidationStatus.FAIL if peak.rank >= Severity.HIGH.rank else ValidationStatus.PASS
        return ValidatorResult(
            self.name, status, peak, self.veto,
            requires_human_approval=peak.rank >= Severity.HIGH.rank,
            findings=tuple(findings),
        )


# ---------------------------------------------------------------------------
# 2. Compiler Validator
# ---------------------------------------------------------------------------

class CompilerValidator(Validator):
    name = "Compiler"
    veto = True

    def validate(self, payload: Any) -> ValidatorResult:
        code = payload.get("code") if isinstance(payload, Mapping) else payload
        language = (payload.get("language", "python") if isinstance(payload, Mapping) else "python")
        if not isinstance(code, str) or not code.strip():
            return ValidatorResult(self.name, ValidationStatus.PASS, Severity.NONE, self.veto,
                                   False, details={"note": "no code supplied"})
        if str(language).lower() != "python":
            return ValidatorResult(self.name, ValidationStatus.PASS, Severity.NONE, self.veto,
                                   False, details={"note": f"language {language!r} not compiled"})
        errors: list[dict[str, Any]] = []
        try:
            compile(code, "<compiler-validator>", "exec")
        except SyntaxError as exc:
            errors.append({"line": exc.lineno, "offset": exc.offset, "message": exc.msg})
        status = ValidationStatus.FAIL if errors else ValidationStatus.PASS
        findings = tuple(Finding(f"line {e['line']}: {e['message']}", Severity.HIGH, "syntax")
                         for e in errors)
        return ValidatorResult(
            self.name, status, Severity.HIGH if errors else Severity.NONE, self.veto,
            requires_human_approval=bool(errors), findings=findings,
            details={"compile_errors": errors},
        )


# ---------------------------------------------------------------------------
# 3. Physics / Math Validator
# ---------------------------------------------------------------------------

class PhysicsMathValidator(Validator):
    name = "PhysicsMath"
    veto = True

    def validate(self, payload: Any) -> ValidatorResult:
        data = payload if isinstance(payload, Mapping) else {}
        findings: list[Finding] = []
        details: dict[str, Any] = {}

        # Energy conservation (perpetual motion).
        if "energy_in" in data and "energy_out" in data:
            ein, eout = float(data["energy_in"]), float(data["energy_out"])
            details["energy_in"], details["energy_out"] = ein, eout
            if eout > ein:
                findings.append(Finding(
                    f"energy_out ({eout}) exceeds energy_in ({ein}): violates conservation",
                    Severity.HIGH, "energy_conservation"))

        # Power budget.
        if "power_supply_w" in data and "power_loads_w" in data:
            supply = float(data["power_supply_w"])
            loads = [float(x) for x in data["power_loads_w"]]
            details["power_supply_w"], details["power_demand_w"] = supply, sum(loads)
            if sum(loads) > supply:
                findings.append(Finding(
                    f"power demand {sum(loads)}W exceeds supply {supply}W",
                    Severity.HIGH, "power_budget"))

        # Battery life.
        if "battery_mah" in data and "load_ma" in data:
            load = float(data["load_ma"])
            hours = float(data["battery_mah"]) / load if load else float("inf")
            details["battery_life_hours"] = round(hours, 3)
            required = data.get("required_hours")
            if required is not None and hours < float(required):
                findings.append(Finding(
                    f"battery life {hours:.2f}h below required {required}h",
                    Severity.MEDIUM, "battery_life"))

        # Unit consistency.
        unit = data.get("unit_check")
        if isinstance(unit, Mapping) and unit.get("expected") != unit.get("actual"):
            findings.append(Finding(
                f"unit mismatch: expected {unit.get('expected')!r}, got {unit.get('actual')!r}",
                Severity.HIGH, "unit_mismatch"))

        peak = _peak_severity(findings)
        # A physics violation (HIGH) fails; a soft budget miss (MEDIUM) warns.
        status = ValidationStatus.FAIL if peak.rank >= Severity.HIGH.rank else ValidationStatus.PASS
        return ValidatorResult(
            self.name, status, peak, self.veto,
            requires_human_approval=peak.rank >= Severity.HIGH.rank,
            findings=tuple(findings), details=details,
        )


# ---------------------------------------------------------------------------
# 4. Test Validator
# ---------------------------------------------------------------------------

class TestValidator(Validator):
    name = "Test"
    veto = False

    def validate(self, payload: Any) -> ValidatorResult:
        data = payload if isinstance(payload, Mapping) else {}
        total = int(data.get("total", 0))
        passed = int(data.get("passed", 0))
        failed = int(data.get("failed", max(0, total - passed)))
        coverage = data.get("coverage")
        min_coverage = data.get("min_coverage")

        findings: list[Finding] = []
        if failed > 0:
            findings.append(Finding(f"{failed} test(s) failing", Severity.HIGH, "regression"))
        if coverage is not None and min_coverage is not None and float(coverage) < float(min_coverage):
            findings.append(Finding(
                f"coverage {coverage}% below minimum {min_coverage}%", Severity.MEDIUM, "coverage"))

        status = ValidationStatus.FAIL if failed > 0 else ValidationStatus.PASS
        return ValidatorResult(
            self.name, status, _peak_severity(findings), self.veto,
            requires_human_approval=failed > 0, findings=tuple(findings),
            details={"total": total, "passed": passed, "failed": failed, "coverage": coverage},
        )


# ---------------------------------------------------------------------------
# 5. Data Integrity Validator
# ---------------------------------------------------------------------------

class DataIntegrityValidator(Validator):
    name = "DataIntegrity"
    veto = False

    def validate(self, payload: Any) -> ValidatorResult:
        data = payload if isinstance(payload, Mapping) else {}
        records = list(data.get("records", []))
        findings: list[Finding] = []

        ids: list[str] = []
        for rec in records:
            if not isinstance(rec, Mapping) or "id" not in rec:
                findings.append(Finding("record missing 'id' field", Severity.HIGH, "corrupted"))
                continue
            ids.append(str(rec["id"]))

        # Duplicate writes.
        seen: set[str] = set()
        for rid in ids:
            if rid in seen:
                findings.append(Finding(f"duplicate record id {rid!r}", Severity.HIGH, "duplicate"))
            seen.add(rid)

        # Invalid references / orphans.
        id_set = set(ids)
        for rec in records:
            if not isinstance(rec, Mapping):
                continue
            for ref in rec.get("refs", []) or []:
                if str(ref) not in id_set:
                    findings.append(Finding(
                        f"record {rec.get('id')!r} references missing id {ref!r}",
                        Severity.HIGH, "invalid_reference"))

        peak = _peak_severity(findings)
        status = ValidationStatus.FAIL if findings else ValidationStatus.PASS
        return ValidatorResult(
            self.name, status, peak, self.veto,
            requires_human_approval=peak.rank >= Severity.HIGH.rank,
            findings=tuple(findings), details={"record_count": len(records)},
        )


# ---------------------------------------------------------------------------
# Suite
# ---------------------------------------------------------------------------

DEFAULT_VALIDATORS: dict[str, Validator] = {
    v.name: v for v in (
        SecurityValidator(), CompilerValidator(), PhysicsMathValidator(),
        TestValidator(), DataIntegrityValidator(),
    )
}


@dataclass(frozen=True)
class ValidationReport:
    results: list[ValidatorResult]

    @property
    def vetoed(self) -> bool:
        return any(r.veto and not r.passed for r in self.results)

    @property
    def all_passed(self) -> bool:
        return all(r.passed for r in self.results)

    @property
    def requires_human_approval(self) -> bool:
        return any(r.requires_human_approval for r in self.results)

    def consensus_outputs(self) -> list[AgentOutput]:
        """Validators as independent evidence sources for Consensus v2."""
        return [r.to_consensus_output() for r in self.results]

    def to_dict(self) -> dict[str, Any]:
        return {
            "results": [r.to_dict() for r in self.results],
            "vetoed": self.vetoed,
            "all_passed": self.all_passed,
            "requires_human_approval": self.requires_human_approval,
        }


def run_validators(payload: Any, validators: list[str] | None = None) -> ValidationReport:
    names = validators or list(DEFAULT_VALIDATORS)
    results: list[ValidatorResult] = []
    for name in names:
        validator = DEFAULT_VALIDATORS.get(name)
        if validator is not None:
            results.append(validator.validate(payload))
    return ValidationReport(results)
