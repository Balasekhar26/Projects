"""
Resource Governor — Step 30 (Proactive Safety Hardening)
=========================================================

Implements the central ResourceGovernor coordinating permissions, thermal load
scaling, absolute subsystem budget checks, and training adaptivity.
"""

from __future__ import annotations

import gc
import psutil
from typing import Dict, Any, Optional
import torch

from kattappa_runtime.resource_governor.schema import GovernanceConfig, SubsystemBudget
from kattappa_runtime.resource_governor.monitor import ResourceMonitor


class ResourceGovernor:
    """
    Decides subsystem permissions, applies thermal throttling, and guides
    adaptive training batch parameters.
    """
    def __init__(self, monitor: ResourceMonitor, config: Optional[GovernanceConfig] = None):
        self.monitor = monitor
        self.config = config or GovernanceConfig()
        self._init_default_budgets()

    def _init_default_budgets(self):
        # Set default absolute budgets (matching strict background budgets)
        if not self.config.subsystem_budgets:
            self.config.subsystem_budgets = {
                "planner": SubsystemBudget(subsystem="planner", cpu_limit_percent=3.0, ram_limit_mb=500.0),
                "research": SubsystemBudget(subsystem="research", cpu_limit_percent=3.0, ram_limit_mb=500.0),
                "workflow": SubsystemBudget(subsystem="workflow", cpu_limit_percent=2.0, ram_limit_mb=300.0),
                "memory": SubsystemBudget(subsystem="memory", cpu_limit_percent=2.0, ram_limit_mb=300.0),
                "knowledge_graph": SubsystemBudget(subsystem="knowledge_graph", cpu_limit_percent=3.0, ram_limit_mb=500.0),
                "model": SubsystemBudget(subsystem="model", cpu_limit_percent=2.0, ram_limit_mb=300.0),
            }

    def request_permission(
        self,
        subsystem: str,
        estimated_cpu: float = 0.0,
        estimated_ram: float = 0.0,
        estimated_gpu: float = 0.0,
    ) -> bool:
        """
        Request permission to run an operation.
        Returns True if the system state and subsystem budgets allow it; otherwise False.
        """
        metrics = self.monitor.get_metrics()

        # 1. Global Hard Safety Limits Check (30% CPU, 35% RAM, 35% GPU rule)
        if metrics.cpu_percent + estimated_cpu > (self.config.global_cpu_limit * 100):
            return False
        if metrics.ram_percent + estimated_ram > (self.config.global_ram_limit * 100):
            return False
        if metrics.gpu_percent + estimated_gpu > (self.config.global_gpu_limit * 100):
            return False

        # Check sustained Disk & Network IO limits
        total_disk_io_mb = (metrics.disk_io_read_bytes_sec + metrics.disk_io_write_bytes_sec) / (1024 * 1024)
        if total_disk_io_mb > self.config.global_disk_io_limit_mb_s:
            return False

        total_net_io_mb = (metrics.net_io_recv_bytes_sec + metrics.net_io_sent_bytes_sec) / (1024 * 1024)
        if total_net_io_mb > self.config.global_net_io_limit_mb_s:
            return False

        # 2. Subsystem Budget Absolute Limits Checks
        budget = self.config.subsystem_budgets.get(subsystem)
        if budget:
            # Check CPU absolute limit
            if estimated_cpu > budget.cpu_limit_percent:
                return False

            # Convert estimated_ram (percentage of total RAM) to MB
            try:
                total_ram_mb = psutil.virtual_memory().total / (1024 * 1024)
            except Exception:
                total_ram_mb = 16384.0 # default fallback
            estimated_ram_mb = (estimated_ram / 100.0) * total_ram_mb

            if estimated_ram_mb > budget.ram_limit_mb:
                return False

            # Check GPU absolute limit
            if estimated_gpu > budget.gpu_limit_percent:
                return False

        return True

    def get_max_workers(self, default_workers: int) -> int:
        """
        Adapts worker thread count based on temperature to prevent thermal throttling.
        """
        metrics = self.monitor.get_metrics()
        temp = metrics.temperature_c

        if temp >= self.config.thermal_throttling_temp_c:
            # Critical temp: enforce single execution thread
            return 1
        elif temp >= (self.config.thermal_throttling_temp_c - 10.0):
            # Approaching throttle temp: cut worker count in half
            return max(1, default_workers // 2)
        
        return default_workers

    def project_training_step(
        self,
        current_step: int,
        current_ram_percent: float,
        current_gpu_memory_gb: float,
        batch_size: int,
        grad_accum_steps: int,
    ) -> Dict[str, Any]:
        """
        Monitors pre-training resource usage and projects requirements.
        Recommends dynamic adjustments to prevent OOM/swapping.
        """
        recommendation = {
            "should_reduce_batch": False,
            "should_increase_accum": False,
            "should_delay_checkpoint": False,
            "should_clear_cache": False,
            "should_gc": False,
        }

        # Check against global limits
        ram_limit_percent = self.config.global_ram_limit * 100
        # Estimate total device capacity (default to 16GB if unallocated)
        total_mps_limit_gb = (self.config.global_unified_memory_limit * 16.0)

        # Trigger garbage collection/cache clear if approaching limits
        if current_ram_percent >= (ram_limit_percent - 5.0) or current_gpu_memory_gb >= (total_mps_limit_gb - 1.0):
            recommendation["should_clear_cache"] = True
            recommendation["should_gc"] = True

        # Enforce micro-batch reductions if we violate limits
        if current_ram_percent > ram_limit_percent or current_gpu_memory_gb > total_mps_limit_gb:
            recommendation["should_reduce_batch"] = True
            recommendation["should_increase_accum"] = True
            recommendation["should_delay_checkpoint"] = True

        # Delay checkpointing during high RAM/GPU memory pressure spikes
        if current_ram_percent >= (ram_limit_percent - 2.0):
            recommendation["should_delay_checkpoint"] = True

        return recommendation

    def execute_maintenance(self):
        """Free memory caches and run garbage collection."""
        gc.collect()
        if torch.backends.mps.is_available():
            try:
                torch.mps.empty_cache()
            except Exception:
                pass
