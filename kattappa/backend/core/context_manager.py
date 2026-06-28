"""Context Manager — Phase K9.6.

Synthesizes conversation history, active goals, tool states, memory blocks,
user profiles, recent failure rates, and environmental telemetry into a
unified, compressed ExecutionContext.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from backend.core.config import load_config
from backend.core.logger import log_event

logger = logging.getLogger(__name__)


@dataclass
class ExecutionContext:
    session_id: str
    timestamp: float
    conversation_history: List[Dict[str, Any]] = field(default_factory=list)
    active_goals: List[Dict[str, Any]] = field(default_factory=list)
    recalled_memories: List[Dict[str, Any]] = field(default_factory=list)
    tool_reliability: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    user_preferences: Dict[str, Any] = field(default_factory=dict)
    recent_failures: List[Dict[str, Any]] = field(default_factory=list)
    environment: Dict[str, Any] = field(default_factory=dict)

    def compile(self) -> str:
        """Compress the entire context into a unified markdown representation."""
        lines = [
            f"# Execution Context ({time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime(self.timestamp))} UTC)",
            f"- **Session ID**: {self.session_id}",
        ]

        # 1. Environment
        if self.environment:
            env_str = ", ".join(f"{k}: {v}" for k, v in self.environment.items())
            lines.append(f"- **System Environment**: {env_str}")

        # 2. User Preferences
        if self.user_preferences:
            pref_str = ", ".join(f"{k}: {v}" for k, v in self.user_preferences.items())
            lines.append(f"- **User Profile**: {pref_str}")

        # 3. Recent Failures
        if self.recent_failures:
            lines.append("- **Recent Failure Diagnostics**:")
            for f in self.recent_failures:
                lines.append(f"  - [{f.get('domain', 'general')}] {f.get('statement', 'Unknown failure')}")

        # 4. Goals
        if self.active_goals:
            lines.append("- **Active Goal Stack**:")
            for g in self.active_goals[:5]:
                lines.append(f"  - [{g.get('node_type', 'TASK')}] {g.get('name')} (progress: {g.get('progress', 0.0) * 100:.0f}%)")

        # 5. Memories
        if self.recalled_memories:
            lines.append("- **Recalled Contextual Knowledge**:")
            for m in self.recalled_memories[:5]:
                content = m.get("content") or m.get("description") or ""
                lines.append(f"  - {content}")

        return "\n".join(lines)


class ContextManager:
    """Builds and manages active ExecutionContext instances."""

    @classmethod
    def build_execution_context(cls, session_id: str, query: str) -> Dict[str, Any]:
        """Gathers sub-context modules and compiles them into a unified context dict."""
        log_event("context_manager_build_start", f"Building Execution Context for {session_id}")

        # 1. Recalled Memories
        recalled = []
        try:
            from backend.core.cognitive_memory_bus import MEMORY_BUS
            reads = MEMORY_BUS.read(query, session_id=session_id, limit=5)
            for r in reads:
                recalled.extend(r.records)
        except Exception as e:
            logger.warning("ContextManager: failed to fetch memories: %s", e)

        # 2. Active Goals
        goals = []
        try:
            from backend.core.goal_hierarchy import GoalHierarchy
            db = GoalHierarchy()
            # Retrieve pending nodes
            with db._lock:
                conn = db._get_conn()
                rows = conn.execute("SELECT * FROM goal_nodes WHERE status = 'PENDING' LIMIT 5").fetchall()
                goals = [dict(r) for r in rows]
                conn.close()
        except Exception as e:
            logger.warning("ContextManager: failed to fetch goals: %s", e)

        # 3. Environment Telemetry
        env = {"hardware": "nominal"}
        try:
            from backend.core.state_manager import CognitiveStateManager
            env["cognitive_state"] = CognitiveStateManager.get_state().value
        except Exception:
            pass

        # 4. Recent Failures
        failures = []
        try:
            from backend.core.state_manager import CognitiveStateManager
            boosts = CognitiveStateManager.get_domain_boosts()
            for dom, factor in boosts.items():
                failures.append({"domain": dom, "statement": f"Attention boosted {factor}x due to repeated failures"})
        except Exception:
            pass

        # 5. User Profile (Theory of Mind)
        user_prefs = {"knowledge_level": "intermediate"}
        try:
            from backend.core.tom.user_model import TheoryOfMind
            # If TheoryOfMind is not fully active yet, we catch the import
            profile = TheoryOfMind.get_profile(session_id)
            if profile:
                user_prefs.update(profile)
        except Exception:
            pass

        # 6. Tool Reliability
        tools = {}
        try:
            from backend.core.tool_reliability import ToolReliabilityTracker
            tools = ToolReliabilityTracker.get_all_reliability()
        except Exception:
            pass

        context_obj = ExecutionContext(
            session_id=session_id,
            timestamp=time.time(),
            conversation_history=[],
            active_goals=goals,
            recalled_memories=recalled,
            tool_reliability=tools,
            user_preferences=user_prefs,
            recent_failures=failures,
            environment=env
        )

        compiled_md = context_obj.compile()
        log_event("context_manager_build_complete", f"ExecutionContext compiled ({len(compiled_md)} chars)")

        return {
            "session_id": session_id,
            "compiled_context": compiled_md,
            "raw": context_obj
        }
