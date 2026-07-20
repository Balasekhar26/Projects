"""Self Model — Phase K22 Introspection Engine.

Tracks Kattappa's own capabilities, resource load, active tool registry,
and historical failure rates to return self-confidence scores and boundary limits.
"""
from __future__ import annotations

import logging
import os
import socket
import ctypes
import sys
from typing import Any, Dict, Tuple

from backend.core.logger import log_event

logger = logging.getLogger(__name__)


class SelfModel:
    """Represents Kattappa's internal state, capabilities, and self-confidence boundaries."""

    @classmethod
    def get_capabilities(cls) -> Dict[str, Any]:
        """Returns the registered capabilities and tools currently installed."""
        try:
            from backend.core.orchestrator.registry import ORCHESTRATOR_REGISTRY
            agents = [a.name for a in ORCHESTRATOR_REGISTRY.all()]
        except Exception:
            agents = ["planner", "coder", "browser", "desktop", "researcher", "voice", "vision"]

        return {
            "installed_agents": agents,
            "available_tools": ["calculator", "file_writer", "shell_executor"],
            "max_concurrent_tasks": 4,
            "wisdom_engine_enabled": True
        }

    @classmethod
    def check_internet(cls) -> bool:
        """Verifies if the system can access the internet by checking connection to Google DNS."""
        try:
            socket.setdefaulttimeout(1.0)
            socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect(("8.8.8.8", 53))
            return True
        except Exception:
            return False

    @classmethod
    def is_admin(cls) -> bool:
        """Checks if the application process is running with Administrator/root privileges."""
        try:
            if sys.platform.startswith("win"):
                return ctypes.windll.shell32.IsUserAnAdmin() != 0
            else:
                return os.getuid() == 0
        except Exception:
            return False

    @classmethod
    def get_self_model_state(cls) -> Dict[str, Any]:
        """Assembles Kattappa's real-time hierarchical self-model state."""
        caps = cls.get_capabilities()
        installed_agents = [a.lower() for a in caps.get("installed_agents", [])]
        
        # 1. Capabilities
        capabilities = {
            "browser_control": "browser" in installed_agents,
            "desktop_control": os.getenv("KATTAPPA_DESKTOP_ENABLED", "false").lower() == "true",
            "shell_execution": os.getenv("KATTAPPA_SHELL_ENABLED", "false").lower() == "true",
            "code_generation": "coder" in installed_agents,
            "vision": "vision" in installed_agents or "vision_agent" in installed_agents,
            "voice": "voice" in installed_agents or "voice_agent" in installed_agents
        }

        # 2. Limitations
        has_internet = cls.check_internet()
        is_privileged = cls.is_admin()
        
        try:
            import psutil
            ram_high = psutil.virtual_memory().percent > 90.0
        except Exception:
            ram_high = False

        limitations = {
            "cannot_access_internet": not has_internet,
            "insufficient_permissions": not is_privileged,
            "memory_limit": ram_high,
            "missing_tool": []
        }

        # Check for missing tools with poor reliability
        try:
            from backend.core.tool_reliability import ToolReliabilityTracker
            all_rel = ToolReliabilityTracker.get_all_reliability()
            for t_name, rel in all_rel.items():
                if rel.get("confidence", 1.0) < 0.4:
                    limitations["missing_tool"].append(t_name)
        except Exception:
            pass

        # 3. Resources
        cpu_usage = 10.0
        ram_usage = 30.0
        battery_state = "ac"
        token_budget = 3000

        try:
            import psutil
            cpu_usage = psutil.cpu_percent(interval=None)
            ram_usage = psutil.virtual_memory().percent
            battery = psutil.sensors_battery()
            if battery:
                battery_state = f"{battery.percent}% {'charging' if battery.power_plugged else 'discharging'}"
        except Exception:
            pass

        try:
            from backend.core.adaptive_runtime import HardwareProfiler, PerformanceProfile, AdaptiveContext
            hw = HardwareProfiler.get_profile()
            profile = PerformanceProfile.resolve_profile(hw)
            limits = AdaptiveContext.get_limits(profile)
            token_budget = limits.get("max_context_tokens", 3000)
        except Exception:
            pass

        resources = {
            "cpu_usage": cpu_usage,
            "ram_usage": ram_usage,
            "token_budget": token_budget,
            "battery_state": battery_state
        }

        # 4. Confidence & Performance (compiled from telemetry trackers)
        planning_confidence = 0.85
        execution_confidence = 0.90
        memory_confidence = 0.92
        world_model_confidence = 0.88
        
        avg_latency = 1.0
        hallucination_rate = 0.0
        task_success_rate = 0.95
        recovery_rate = 0.88

        try:
            from backend.core.agent_reputation import AgentReputationTracker
            coder_rep = AgentReputationTracker.get_reputation("coder")
            planner_rep = AgentReputationTracker.get_reputation("planner")
            
            # Map values if execution has occurred
            if coder_rep and coder_rep.get("average_latency", 0.0) > 0.0:
                execution_confidence = coder_rep.get("confidence", 0.90)
                task_success_rate = coder_rep.get("success_rate", 0.95)
                avg_latency = coder_rep.get("average_latency", 1.0)
                hallucination_rate = coder_rep.get("hallucination_count", 0) / max(1, (coder_rep.get("success_count", 1) + coder_rep.get("failure_count", 0)))
            if planner_rep and planner_rep.get("average_latency", 0.0) > 0.0:
                planning_confidence = planner_rep.get("confidence", 0.85)
        except Exception:
            pass

        confidence = {
            "planning_confidence": planning_confidence,
            "execution_confidence": execution_confidence,
            "memory_confidence": memory_confidence,
            "world_model_confidence": world_model_confidence
        }

        performance = {
            "average_latency": avg_latency,
            "hallucination_rate": hallucination_rate,
            "task_success_rate": task_success_rate,
            "recovery_rate": recovery_rate
        }

        return {
            "capabilities": capabilities,
            "limitations": limitations,
            "resources": resources,
            "confidence": confidence,
            "performance": performance
        }

    @classmethod
    def evaluate_capability(
        cls,
        task_query: str,
        current_load: float = 0.2
    ) -> Tuple[bool, float, str]:
        """Evaluates whether the system has the capability to execute a task confidently.

        Returns:
            (can_execute, self_confidence_score, reason)
        """
        query_lower = task_query.lower()
        state = cls.get_self_model_state()

        # Check resource load boundaries
        if state["resources"]["cpu_usage"] >= 95.0 or state["resources"]["ram_usage"] >= 95.0:
            log_event("self_model_boundary_halt", f"System load limit exceeded (cpu={state['resources']['cpu_usage']})")
            return False, 0.10, "System resource limits reached. Cannot execute safely."

        # Check capability matches
        unsupported = ["train image model", "c++ compiler", "hack database", "mine crypto"]
        for term in unsupported:
            if term in query_lower:
                log_event("self_model_boundary_unsupported", f"Unsupported task requested: {term}")
                return False, 0.0, f"Unsupported capability: {term}"

        # Dynamic check for network restriction
        if state["limitations"]["cannot_access_internet"] and any(term in query_lower for term in ["download", "fetch", "web search"]):
            return False, 0.20, "Internet access is currently unavailable."

        # Base confidence calculation based on load and keyword matches
        confidence = state["confidence"]["execution_confidence"] - (current_load * 0.2)
        
        # Check specific tool dependency
        if "calculate" in query_lower and "calculator" not in state["limitations"]["missing_tool"]:
            # If not in missing_tool list, we are good
            pass

        log_event("self_model_evaluation", f"Self Model capability check passed (confidence={confidence:.2f})")
        return True, round(confidence, 2), "Task fits system capabilities and load limits"
