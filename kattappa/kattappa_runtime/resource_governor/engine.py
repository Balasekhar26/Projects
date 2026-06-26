"""
Kattappa Resource Governor Engine (KRG) — Step 30
==================================================

The unified facade coordinating monitoring, budgeting, thermal scaling, dynamic routing,
context optimization, lazy loading, and hierarchical storage compression.
"""

from __future__ import annotations

from typing import Dict, List, Any, Optional

from kattappa_runtime.resource_governor.schema import GovernanceConfig, SystemResourceMetrics
from kattappa_runtime.resource_governor.monitor import ResourceMonitor
from kattappa_runtime.resource_governor.governor import ResourceGovernor
from kattappa_runtime.resource_governor.router import DynamicModelRouter
from kattappa_runtime.resource_governor.optimizer import ContextOptimizer
from kattappa_runtime.resource_governor.loader import LazyLoader, AgentLifecycleManager
from kattappa_runtime.resource_governor.storage import StorageManager, HierarchicalMemoryManager


class ResourceGovernorEngine:
    """
    The unified entry point for all resource governance in Kattappa.
    """
    def __init__(self, config: Optional[GovernanceConfig] = None):
        self.config = config or GovernanceConfig()
        
        # Initialize modules
        self.monitor = ResourceMonitor()
        self.governor = ResourceGovernor(self.monitor, self.config)
        self.router = DynamicModelRouter(self.governor)
        self.optimizer = ContextOptimizer(self.governor)
        self.loader = LazyLoader(self.governor)
        self.lifecycle = AgentLifecycleManager(self.governor)
        self.storage = StorageManager(self.governor)
        self.hierarchical_memory = HierarchicalMemoryManager()

    def start(self):
        """Start resource monitor background thread."""
        self.monitor.start()

    def stop(self):
        """Stop background threads and release resources."""
        self.monitor.stop()
        self.loader.unload_all()

    def request_permission(
        self,
        subsystem: str,
        estimated_cpu: float = 0.0,
        estimated_ram: float = 0.0,
        estimated_gpu: float = 0.0,
    ) -> bool:
        """Query governor if subsystem execution is permitted within limits."""
        return self.governor.request_permission(
            subsystem,
            estimated_cpu=estimated_cpu,
            estimated_ram=estimated_ram,
            estimated_gpu=estimated_gpu
        )

    def route_model(self, query: str) -> str:
        """Route user query dynamically to the right scale model."""
        return self.router.route(query)

    def optimize_context(
        self,
        prompt: str,
        history: List[Dict[str, str]],
        raw_documents: List[str],
        max_allowed_tokens: int = 2048,
    ) -> Dict[str, Any]:
        """Optimize input contexts to fit dynamic token limit budgets."""
        return self.optimizer.optimize_context(
            prompt, history, raw_documents, max_allowed_tokens=max_allowed_tokens
        )

    def load_subsystem(self, subsystem_name: str) -> Any:
        """Lazy load a subsystem on demand."""
        return self.loader.load_subsystem(subsystem_name)

    def register_agent(self, agent_name: str):
        """Register an agent under lifecycle tracking."""
        self.lifecycle.register_agent(agent_name)

    def wake_agent(self, agent_name: str):
        """Transition agent to active state."""
        self.lifecycle.wake_agent(agent_name)

    def sleep_agent(self, agent_name: str):
        """Sleep agent and free memory/garbage."""
        self.lifecycle.sleep_agent(agent_name)

    def check_disk_space(self) -> Dict[str, Any]:
        """Check current disk capacity health."""
        return self.storage.check_disk_space()

    def run_cleanup_cycle(self) -> List[str]:
        """Trigger garbage collections and file prunings."""
        self.governor.execute_maintenance()
        return self.storage.run_cleanup_cycle()

    def compress_memory_tier(
        self,
        hot_records: List[Dict[str, Any]],
        max_hot_size: int = 10,
    ) -> List[Dict[str, Any]]:
        """Evict older records from Hot (RAM) to SQLite (Warm) or Cold (Archive) tiers."""
        return self.hierarchical_memory.compress_memory_tier(hot_records, max_hot_size=max_hot_size)

    def get_metrics(self) -> SystemResourceMetrics:
        """Get latest system metrics snapshot."""
        return self.monitor.get_metrics()
