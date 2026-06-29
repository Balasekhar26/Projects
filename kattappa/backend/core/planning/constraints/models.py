"""Constraint Engine Models (Program 5G-4).

Defines Constraint definitions, violations, and final report containers.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional



@dataclass
class Constraint:
    """Defines a semantic rule to validate execution feasibility."""
    constraint_id: str
    name: str
    type: str  # Temporal, Resource, Dependency, Privacy, Energy, Location
    severity: str = "Critical"  # Critical, Warning
    enabled: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ConstraintViolation:
    """Details a failed rule check on a specific plan node."""
    constraint_id: str
    node_id: Optional[str]
    explanation: str
    severity: str = "Critical"
    suggested_fix: Optional[str] = None


@dataclass
class ConstraintReport:
    """Collates all constraint violations and warnings for a plan graph."""
    passed: bool
    violations: List[ConstraintViolation] = field(default_factory=list)
    warnings: List[ConstraintViolation] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)
