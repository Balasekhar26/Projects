from __future__ import annotations
from typing import Dict, Any, List

class ToolRouter:
    """Maps logical HTN steps to designated specialist agents and capability endpoints."""

    AGENT_MAP = {
        "check_calendar": "memory",
        "reserve_slot": "memory",
        "download_package": "browser",
        "run_installer": "terminal",
        "query_version_command": "terminal",
        "compile_code": "coder",
        "run_tests": "terminal",
        "deploy_binary": "builder",
    }

    @classmethod
    def route_step(cls, step_name: str) -> str:
        """Determines the appropriate agent to execute a plan step."""
        return cls.AGENT_MAP.get(step_name, "evaluator")

    @classmethod
    def get_agent_capabilities(cls, agent_name: str) -> List[str]:
        """Returns the permitted capabilities for a given agent."""
        # Simple lookup corresponding to agent registry roles
        capabilities = {
            "coder": ["python_execution", "edit_file"],
            "terminal": ["shell_execution"],
            "browser": ["network_request"],
            "memory": ["memory_read", "memory_write"],
            "builder": ["deploy"]
        }
        return capabilities.get(agent_name, [])
