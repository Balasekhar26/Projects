"""Constraint Engine Orchestration (Program 5G-4).

Manages pluggable validators, enabling/disabling checks, executing reports,
and producing repair suggestions.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from backend.core.planning.constraints.models import ConstraintReport, ConstraintViolation
from backend.core.planning.constraints.validators import (
    ConstraintValidator,
    TemporalValidator,
    ResourceValidator,
    DependencyValidator,
    PrivacyValidator,
    EnergyValidator,
    LocationValidator,
)
from backend.core.planning.plan_graph import DependencyGraph

logger = logging.getLogger(__name__)


class ConstraintEngine:
    """Orchestrates plan graph validation passes over pluggable validators."""

    _instance: Optional[ConstraintEngine] = None

    def __init__(self) -> None:
        self.validators: Dict[str, ConstraintValidator] = {}
        self.enabled_validators: Dict[str, bool] = {}

        # Register default built-in validators
        self.register_validator(TemporalValidator())
        self.register_validator(ResourceValidator())
        self.register_validator(DependencyValidator())
        self.register_validator(PrivacyValidator())
        self.register_validator(EnergyValidator())
        self.register_validator(LocationValidator())

    @classmethod
    def get_instance(cls) -> ConstraintEngine:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def register_validator(self, validator: ConstraintValidator) -> None:
        self.validators[validator.validator_id] = validator
        self.enabled_validators[validator.validator_id] = True

    def enable_validator(self, validator_id: str) -> None:
        if validator_id in self.validators:
            self.enabled_validators[validator_id] = True
            logger.info("Constraint validator enabled: %s", validator_id)

    def disable_validator(self, validator_id: str) -> None:
        if validator_id in self.validators:
            self.enabled_validators[validator_id] = False
            logger.info("Constraint validator disabled: %s", validator_id)

    def validate(
        self,
        plan_graph: DependencyGraph,
        world_state: Dict[str, Any],
    ) -> ConstraintReport:
        """Runs all enabled validators against the plan graph."""
        violations: List[ConstraintViolation] = []
        warnings: List[ConstraintViolation] = []

        for val_id, validator in self.validators.items():
            if not self.enabled_validators.get(val_id, False):
                continue

            try:
                result = validator.validate(plan_graph, world_state)
                for violation in result:
                    if violation.severity == "Critical":
                        violations.append(violation)
                    else:
                        warnings.append(violation)
            except Exception as exc:
                logger.error("Error executing validator %s: %s", val_id, str(exc))
                # Add validation failure as a critical violation
                violations.append(
                    ConstraintViolation(
                        constraint_id=val_id,
                        node_id=None,
                        explanation=f"Validator internal crash error: {str(exc)}",
                        severity="Critical",
                    )
                )

        passed = len(violations) == 0
        metrics = {
            "total_nodes": len(plan_graph.nodes),
            "validators_executed": sum(1 for v in self.enabled_validators.values() if v),
        }

        return ConstraintReport(
            passed=passed,
            violations=violations,
            warnings=warnings,
            metrics=metrics,
        )

    @staticmethod
    def get_repair_suggestions(report: ConstraintReport) -> List[str]:
        """Extracts unique suggested fixes from report violations and warnings."""
        suggestions: List[str] = []
        seen: Set[str] = set()

        all_violations = report.violations + report.warnings
        for v in all_violations:
            if v.suggested_fix and v.suggested_fix not in seen:
                suggestions.append(v.suggested_fix)
                seen.add(v.suggested_fix)

        return suggestions

    def get_validators(self) -> List[Dict[str, Any]]:
        """Returns the list and state of registered validators."""
        return [
            {
                "validator_id": val.validator_id,
                "name": val.name,
                "enabled": self.enabled_validators.get(val.validator_id, False),
            }
            for val in self.validators.values()
        ]
