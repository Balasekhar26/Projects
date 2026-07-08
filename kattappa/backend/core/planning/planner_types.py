"""Planner Core Enums and Types (Program 12.0).
"""
from __future__ import annotations

from enum import Enum
from backend.core.goal_manager import GoalStatus


class GoalPriority(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
