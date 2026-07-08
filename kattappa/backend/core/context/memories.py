"""Isolated Context Memory Layers (Program 9).

Stores working memory (live execution state), episodic memory, and semantic facts.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional



@dataclass
class WorkingMemoryLayer:
    active_task: Optional[str] = None
    execution_variables: Dict[str, Any] = field(default_factory=dict)
    planner_state: Dict[str, Any] = field(default_factory=dict)
    tool_outputs: Dict[str, Any] = field(default_factory=dict)

    def clear(self) -> None:
        self.active_task = None
        self.execution_variables.clear()
        self.planner_state.clear()
        self.tool_outputs.clear()


@dataclass
class EpisodicMemoryLayer:
    recent_runs: List[Dict[str, Any]] = field(default_factory=list)
    failures_log: List[Dict[str, Any]] = field(default_factory=list)

    def add_run(self, session_id: str, status: str, duration: float) -> None:
        self.recent_runs.append({
            "session_id": session_id,
            "status": status,
            "duration": duration,
        })

    def add_failure(self, node_id: str, error_message: str) -> None:
        self.failures_log.append({
            "node_id": node_id,
            "error": error_message,
        })


@dataclass
class SemanticMemoryLayer:
    static_policies: List[str] = field(default_factory=list)
    system_rules: List[str] = field(default_factory=list)

    def add_policy(self, rule: str) -> None:
        self.static_policies.append(rule)
