"""Constraint Validators Implementation (Program 5G-4).

Implements base validator class and concrete validators for Temporal,
Resource, Dependency, Privacy, Energy, and Location constraint checks.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Set
from backend.core.planning.constraints.models import ConstraintViolation
from backend.core.planning.plan_graph import DependencyGraph


class ConstraintValidator:
    """Base interface for all plan graph constraint validators."""

    def __init__(self, validator_id: str, name: str) -> None:
        self.validator_id = validator_id
        self.name = name

    def validate(
        self,
        plan_graph: DependencyGraph,
        world_state: Dict[str, Any],
    ) -> List[ConstraintViolation]:
        """Validates the plan graph against the given world state.

        Returns a list of ConstraintViolation objects.
        """
        raise NotImplementedError("Subclasses must implement validate()")


class TemporalValidator(ConstraintValidator):
    """Validates deadlines, timeouts, and ordering constraints."""

    def __init__(self) -> None:
        super().__init__("temporal_validator", "Temporal Constraint Validator")

    def validate(
        self,
        plan_graph: DependencyGraph,
        world_state: Dict[str, Any],
    ) -> List[ConstraintViolation]:
        violations = []
        current_time = world_state.get("current_time", time.time())
        cumulative_duration = 0.0

        try:
            order = plan_graph.get_topological_sort()
        except ValueError as exc:
            # If there's a cycle, the dependency validator handles it, but we handle it gracefully here
            return []

        for node_id in order:
            node = plan_graph.nodes[node_id]
            op = node.operator
            duration = getattr(op, "estimated_time", 1.0)
            cumulative_duration += duration

            # Check if node has a deadline constraint in parameters or metadata
            deadline = op.parameters.get("deadline")
            if deadline is not None:
                if current_time + cumulative_duration > deadline:
                    violations.append(
                        ConstraintViolation(
                            constraint_id=self.validator_id,
                            node_id=node_id,
                            explanation=(
                                f"Task '{op.name}' expected to finish at "
                                f"{current_time + cumulative_duration:.1f}, exceeding deadline of {deadline:.1f}"
                            ),
                            severity="Critical",
                            suggested_fix=f"Increase deadline or optimize prior task execution times.",
                        )
                    )
        return violations


class ResourceValidator(ConstraintValidator):
    """Validates resource allocations and concurrent conflict detections."""

    def __init__(self) -> None:
        super().__init__("resource_validator", "Resource Constraint Validator")

    def validate(
        self,
        plan_graph: DependencyGraph,
        world_state: Dict[str, Any],
    ) -> List[ConstraintViolation]:
        violations = []

        try:
            layers = plan_graph.get_parallel_layers()
        except ValueError:
            return []

        # Check each parallel execution layer for resource conflicts
        for idx, layer in enumerate(layers):
            resource_usage: Dict[str, str] = {}  # resource_name -> node_id
            for node_id in layer:
                node = plan_graph.nodes[node_id]
                op = node.operator
                # Read required exclusive resources from operator parameters
                required = op.parameters.get("required_resources", [])
                for res in required:
                    if res in resource_usage:
                        other_node_id = resource_usage[res]
                        violations.append(
                            ConstraintViolation(
                                constraint_id=self.validator_id,
                                node_id=node_id,
                                explanation=(
                                    f"Resource conflict on '{res}' in parallel layer {idx}: "
                                    f"required by both '{op.name}' and node '{other_node_id}'"
                                ),
                                severity="Critical",
                                suggested_fix=f"Reschedule tasks sequentially to resolve concurrent resource use.",
                            )
                        )
                    else:
                        resource_usage[res] = node_id

        return violations


class DependencyValidator(ConstraintValidator):
    """Checks for cycle loops and unsatisfied preconditions relative to prior effects."""

    def __init__(self) -> None:
        super().__init__("dependency_validator", "Dependency & Cycle Validator")

    def validate(
        self,
        plan_graph: DependencyGraph,
        world_state: Dict[str, Any],
    ) -> List[ConstraintViolation]:
        violations = []

        # 1. Check cycles
        if not plan_graph.is_acyclic():
            violations.append(
                ConstraintViolation(
                    constraint_id=self.validator_id,
                    node_id=None,
                    explanation="Plan graph contains circular dependency loops.",
                    severity="Critical",
                    suggested_fix="Remove circular edges from the execution network.",
                )
            )
            return violations  # Cannot check preconditions if cycle exists

        # 2. Check preconditions propagation topologically
        current_state = dict(world_state)
        order = plan_graph.get_topological_sort()

        for node_id in order:
            node = plan_graph.nodes[node_id]
            op = node.operator

            # Check preconditions
            for key, val in op.preconditions.items():
                if current_state.get(key) != val:
                    violations.append(
                        ConstraintViolation(
                            constraint_id=self.validator_id,
                            node_id=node_id,
                            explanation=(
                                f"Unsatisfied precondition '{key}={val}' for task '{op.name}'. "
                                f"Current simulated state is '{key}={current_state.get(key)}'"
                            ),
                            severity="Critical",
                            suggested_fix=f"Insert a task that produces '{key}={val}' before '{op.name}'.",
                        )
                    )

            # Propagate effects
            current_state.update(op.effects)

        return violations


class PrivacyValidator(ConstraintValidator):
    """Enforces privacy checks by detecting unauthorized access to keys, contacts, or tokens."""

    def __init__(self) -> None:
        super().__init__("privacy_validator", "Privacy Constraint Validator")

    def validate(
        self,
        plan_graph: DependencyGraph,
        world_state: Dict[str, Any],
    ) -> List[ConstraintViolation]:
        violations = []
        authorized = world_state.get("privacy_authorized", False)

        for node_id, node in plan_graph.nodes.items():
            op = node.operator
            # Check if operator name or parameters access private properties
            requires_privacy = (
                "private" in op.name.lower() or
                op.parameters.get("access_private_data", False)
            )

            if requires_privacy and not authorized:
                violations.append(
                    ConstraintViolation(
                        constraint_id=self.validator_id,
                        node_id=node_id,
                        explanation=(
                            f"Task '{op.name}' attempts to access sensitive private data "
                            f"without authorization flags."
                        ),
                        severity="Critical",
                        suggested_fix="Request user permission or set 'privacy_authorized=True' in the context.",
                    )
                )

        return violations


class EnergyValidator(ConstraintValidator):
    """Validates plan execution against battery/power budget constraints."""

    def __init__(self) -> None:
        super().__init__("energy_validator", "Energy Constraint Validator")

    def validate(
        self,
        plan_graph: DependencyGraph,
        world_state: Dict[str, Any],
    ) -> List[ConstraintViolation]:
        violations = []
        battery = world_state.get("battery_level", 100.0)
        total_energy_cost = 0.0

        for node in plan_graph.nodes.values():
            op = node.operator
            # Cost represents energy cost
            energy_cost = op.parameters.get("energy_cost", 0.0)
            total_energy_cost += energy_cost

        if total_energy_cost > battery:
            violations.append(
                ConstraintViolation(
                    constraint_id=self.validator_id,
                    node_id=None,
                    explanation=(
                        f"Plan requires {total_energy_cost:.1f}% battery power, "
                        f"exceeding available capacity of {battery:.1f}%"
                    ),
                    severity="Critical",
                    suggested_fix="Charge the device battery or remove high-power tasks.",
                )
            )

        return violations


class LocationValidator(ConstraintValidator):
    """Checks travel constraints and physical feasibility of sequence tasks."""

    def __init__(self) -> None:
        super().__init__("location_validator", "Location Constraint Validator")

    def validate(
        self,
        plan_graph: DependencyGraph,
        world_state: Dict[str, Any],
    ) -> List[ConstraintViolation]:
        violations = []
        current_loc = world_state.get("current_location", "origin")

        try:
            order = plan_graph.get_topological_sort()
        except ValueError:
            return []

        for node_id in order:
            node = plan_graph.nodes[node_id]
            op = node.operator
            required_loc = op.parameters.get("required_location")

            if required_loc is not None and required_loc != current_loc:
                # If target location is different and no transition/travel task exists, raise violation
                violations.append(
                    ConstraintViolation(
                        constraint_id=self.validator_id,
                        node_id=node_id,
                        explanation=(
                            f"Task '{op.name}' requires location '{required_loc}' "
                            f"but current location is '{current_loc}'"
                        ),
                        severity="Warning",
                        suggested_fix=f"Insert a travel task to transition from '{current_loc}' to '{required_loc}'.",
                    )
                )
                # Assume agent travels to target location
                current_loc = required_loc

        return violations
