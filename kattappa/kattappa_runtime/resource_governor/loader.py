"""
Lazy Loader & Agent Lifecycle Manager — Step 30
=================================================

Implements dynamic module loading and agent sleep/wake lifecycles to save system
resources.
"""

from __future__ import annotations

import importlib
import time
from typing import Dict, List, Any, Optional

from kattappa_runtime.resource_governor.governor import ResourceGovernor


class LazyLoader:
    """
    Imports and loads subsystems on demand rather than at startup.
    Keeps memory footprint low.
    """
    def __init__(self, governor: ResourceGovernor):
        self.governor = governor
        self.loaded_subsystems: Dict[str, Any] = {}
        # Mapping of subsystem names to import paths
        self.module_mappings = {
            "planner": "kattappa_runtime.planner.engine",
            "research": "kattappa_runtime.research.engine",
            "knowledge_graph": "kattappa_runtime.knowledge_graph.engine",
            "workflow": "kattappa_runtime.workflow.engine",
            "learning": "kattappa_runtime.learning.engine",
            "reflection": "kattappa_runtime.reflection.engine",
            "self_improvement": "kattappa_runtime.self_improvement.engine",
        }

    def load_subsystem(self, name: str) -> Any:
        """
        Dynamically imports and returns a subsystem class/module.
        """
        if name in self.loaded_subsystems:
            return self.loaded_subsystems[name]

        path = self.module_mappings.get(name)
        if not path:
            raise ValueError(f"Unknown lazy subsystem: {name}")

        # Check budget before loading
        if not self.governor.request_permission(name, estimated_ram=1.0):
            # If system is under heavy load, refuse or trigger maintenance first
            self.governor.execute_maintenance()
            if not self.governor.request_permission(name, estimated_ram=0.5):
                raise RuntimeError(f"Resource Governor blocked lazy load of {name} due to RAM constraints.")

        # Perform dynamic import
        module = importlib.import_module(path)
        self.loaded_subsystems[name] = module
        return module

    def unload_all(self):
        """Unload and clear references to loaded subsystems."""
        self.loaded_subsystems.clear()
        self.governor.execute_maintenance()


class AgentLifecycleManager:
    """
    Manages sleep/wake states for active agents to ensure inactive agents
    do not consume memory or background threads.
    """
    def __init__(self, governor: ResourceGovernor):
        self.governor = governor
        self.agent_states: Dict[str, str] = {}  # agent_name -> 'active' | 'sleeping'
        self.last_active_time: Dict[str, float] = {}  # agent_name -> timestamp

    def register_agent(self, agent_name: str):
        """Register a new agent in sleeping state."""
        self.agent_states[agent_name] = "sleeping"
        self.last_active_time[agent_name] = time.time()

    def wake_agent(self, agent_name: str):
        """Transition agent to active state."""
        if agent_name not in self.agent_states:
            self.register_agent(agent_name)
        self.agent_states[agent_name] = "active"
        self.last_active_time[agent_name] = time.time()

    def sleep_agent(self, agent_name: str):
        """Transition agent to sleeping state, releasing resources."""
        if agent_name in self.agent_states:
            self.agent_states[agent_name] = "sleeping"
            # Trigger maintenance to collect garbage of the sleeping agent
            self.governor.execute_maintenance()

    def get_active_agents(self) -> List[str]:
        """List all active agent names."""
        return [k for k, v in self.agent_states.items() if v == "active"]

    def get_sleeping_agents(self) -> List[str]:
        """List all sleeping agent names."""
        return [k for k, v in self.agent_states.items() if v == "sleeping"]

    def check_inactivity_and_sleep(self, inactivity_timeout: float = 10.0):
        """
        Automatically puts agents to sleep if inactive for the specified timeout.
        """
        now = time.time()
        for name, last_time in list(self.last_active_time.items()):
            if self.agent_states.get(name) == "active":
                if now - last_time >= inactivity_timeout:
                    self.sleep_agent(name)
