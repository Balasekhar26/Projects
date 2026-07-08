"""Constraint Solver Enums and Structs (Program 12.2).
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Callable, Dict, List, Optional
from backend.core.planning.plan import Plan


class Severity(str, Enum):
    HARD = "HARD"
    SOFT = "SOFT"


class ConstraintNamespace(str, Enum):
    TEMPORAL = "TEMPORAL"
    FINANCIAL = "FINANCIAL"
    POLICY = "POLICY"
    HARDWARE = "HARDWARE"


class ConstraintViolation:
    """Detailed diagnosis of a violated constraint, explaining reason and remediation steps."""

    def __init__(
        self,
        constraint_id: str,
        reason: str,
        severity: Severity,
        remediation: Optional[str] = None,
    ) -> None:
        self.constraint_id = constraint_id
        self.reason = reason
        self.severity = severity
        self.remediation = remediation or "No remediation suggested."

    def to_dict(self) -> Dict[str, Any]:
        return {
            "constraint_id": self.constraint_id,
            "reason": self.reason,
            "severity": self.severity.value,
            "remediation": self.remediation,
        }


class Constraint:
    """Evaluation rule validating candidate plans against current state boundaries."""

    def __init__(
        self,
        constraint_id: str,
        name: str,
        namespace: ConstraintNamespace,
        severity: Severity,
        validator_func: Callable[[Plan, Dict[str, Any]], Optional[str]],
        penalty: float = 0.0,
        remediation: Optional[str] = None,
    ) -> None:
        self.constraint_id = constraint_id
        self.name = name
        self.namespace = namespace
        self.severity = severity
        self.validator_func = validator_func
        self.penalty = penalty  # Penalty value deducted from utility (for SOFT constraints)
        self.remediation = remediation

    def evaluate(self, plan: Plan, world_state: Dict[str, Any]) -> Optional[ConstraintViolation]:
        """Runs the validation function. Returns a ConstraintViolation if violated, otherwise None."""
        violation_reason = self.validator_func(plan, world_state)
        if violation_reason:
            return ConstraintViolation(
                constraint_id=self.constraint_id,
                reason=violation_reason,
                severity=self.severity,
                remediation=self.remediation,
            )
        return None


class ConstraintResult:
    """Summary of constraint evaluation run, tracking plan feasibility and soft penalties."""

    def __init__(self) -> None:
        self.is_feasible: bool = True
        self.violations: List[ConstraintViolation] = []
        self.utility_penalty: float = 0.0

    def add_violation(self, violation: ConstraintViolation, penalty: float = 0.0) -> None:
        self.violations.append(violation)
        if violation.severity == Severity.HARD:
            self.is_feasible = False
        else:
            self.utility_penalty += penalty

    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_feasible": self.is_feasible,
            "utility_penalty": self.utility_penalty,
            "violations": [v.to_dict() for v in self.violations],
        }
