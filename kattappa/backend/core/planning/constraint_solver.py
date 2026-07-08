"""Constraint Solver Engine (Program 12.2).
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from backend.core.planning.plan import Plan
from backend.core.planning.constraint_types import (
    Constraint,
    ConstraintNamespace,
    ConstraintResult,
    Severity,
)

logger = logging.getLogger(__name__)


class ConstraintSolver:
    """Validator evaluating candidate execution plans against safety, resource, and policy constraints."""

    def __init__(self) -> None:
        self.constraints: List[Constraint] = []
        self._load_default_constraints()

    def register_constraint(self, constraint: Constraint) -> None:
        """Adds a constraint rule to the solver registry."""
        self.constraints.append(constraint)

    def validate_plan(self, plan: Plan, world_state: Dict[str, Any]) -> ConstraintResult:
        """Evaluates the plan against all registered constraints."""
        result = ConstraintResult()
        
        for constraint in self.constraints:
            violation = constraint.evaluate(plan, world_state)
            if violation:
                logger.warning(
                    "Constraint violation detected! ID: %s, Reason: %s",
                    constraint.constraint_id,
                    violation.reason,
                )
                result.add_violation(violation, penalty=constraint.penalty)

        return result

    def _load_default_constraints(self) -> None:
        """Seeds the solver with standard hard/soft validation rules."""
        
        # 1. Hard Temporal Constraint: Total plan duration must not exceed goal deadline
        def check_temporal_deadline(plan: Plan, world_state: Dict[str, Any]) -> Optional[str]:
            max_allowed_duration = world_state.get("max_plan_duration", 60.0)
            # Find total duration of critical path
            _, duration = plan.graph.calculate_critical_path()
            if duration > max_allowed_duration:
                return (
                    f"Plan critical path duration ({duration}s) exceeds the maximum allowed "
                    f"limit ({max_allowed_duration}s)."
                )
            return None

        self.register_constraint(Constraint(
            constraint_id="const_temporal_deadline_01",
            name="Max Plan Duration Limit",
            namespace=ConstraintNamespace.TEMPORAL,
            severity=Severity.HARD,
            validator_func=check_temporal_deadline,
            remediation="Select faster fallback rules or prune non-essential dependencies."
        ))

        # 2. Hard Financial Constraint: Plan dollars cost must not exceed available dollars budget
        def check_financial_budget(plan: Plan, world_state: Dict[str, Any]) -> Optional[str]:
            budget_limit = world_state.get("financial_budget", 50.0)
            accumulated_costs = plan.metadata.get("accumulated_costs", {})
            total_dollars = accumulated_costs.get("dollars", 0.0)
            
            if total_dollars > budget_limit:
                return f"Plan financial cost (${total_dollars}) exceeds budget limit (${budget_limit})."
            return None

        self.register_constraint(Constraint(
            constraint_id="const_financial_budget_01",
            name="Financial Budget Cap",
            namespace=ConstraintNamespace.FINANCIAL,
            severity=Severity.HARD,
            validator_func=check_financial_budget,
            remediation="Prune high-cost steps or request manual budget extensions."
        ))

        # 3. Soft Policy Constraint: Warn and penalize if cloud tasks are used during offline modes
        def check_offline_policy(plan: Plan, world_state: Dict[str, Any]) -> Optional[str]:
            is_offline = world_state.get("offline_mode", False)
            if is_offline:
                for node in plan.graph.nodes.values():
                    # If task requires api_tokens, it's considered online
                    cost_vector = getattr(node, "cost_vector", {})
                    if cost_vector.get("api_tokens", 0.0) > 0.0:
                        return f"Task '{node.title}' requires online API access during offline mode."
            return None

        self.register_constraint(Constraint(
            constraint_id="const_policy_offline_warning",
            name="Offline API Compliance",
            namespace=ConstraintNamespace.POLICY,
            severity=Severity.SOFT,
            validator_func=check_offline_policy,
            penalty=0.25,  # Deduct 0.25 utility score
            remediation="Ensure tasks fall back to local models when offline."
        ))
