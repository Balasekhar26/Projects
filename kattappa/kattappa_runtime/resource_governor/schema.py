"""
Resource Governor Schema — Step 30
===================================

Foundational configurations, thresholds, budgets, and runtime metric definitions
for Kattappa's Resource Governor (KRG).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional


@dataclass
class SystemResourceMetrics:
    """
    Real-time physical system resources metrics.
    """
    cpu_percent: float = 0.0
    ram_percent: float = 0.0
    gpu_percent: float = 0.0
    unified_memory_used_gb: float = 0.0
    vram_used_gb: float = 0.0
    disk_io_read_bytes_sec: float = 0.0
    disk_io_write_bytes_sec: float = 0.0
    net_io_recv_bytes_sec: float = 0.0
    net_io_sent_bytes_sec: float = 0.0
    temperature_c: float = 45.0  # Default moderate temperature
    battery_percent: float = 100.0
    power_draw_watts: float = 15.0
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


@dataclass
class SubsystemBudget:
    """
    Defines resource budget limit shares for a subsystem.
    Shares are expressed as fractions [0.0, 1.0] of the global limit.
    """
    subsystem: str
    cpu_share: float = 1.0
    ram_share: float = 1.0
    gpu_share: float = 1.0


@dataclass
class SubsystemStats:
    """
    Performance and concurrency metrics for active subsystems.
    """
    latency_ms: float = 0.0
    queue_length: int = 0
    active_agents: List[str] = field(default_factory=list)
    running_workflows: List[str] = field(default_factory=list)


@dataclass
class GovernanceConfig:
    """
    Global governance policy, thresholds, and limits.
    Default targets enforce an absolute <= 50% limit on major resources.
    """
    global_cpu_limit: float = 0.50
    global_ram_limit: float = 0.50
    global_gpu_limit: float = 0.50
    global_unified_memory_limit: float = 0.50
    global_vram_limit: float = 0.50
    global_disk_io_limit_mb_s: float = 50.0  # limit sustained disk speed
    global_net_io_limit_mb_s: float = 10.0   # limit sustained network speed
    
    # SSD space safety targets: keep max(15% of disk, 100 GB)
    min_free_disk_space_ratio: float = 0.15
    min_free_disk_space_bytes: int = 100 * 1024 * 1024 * 1024  # 100 GB
    
    # Critical thresholds
    thermal_throttling_temp_c: float = 85.0
    battery_eco_threshold: float = 20.0
    
    # Allocations
    subsystem_budgets: Dict[str, SubsystemBudget] = field(default_factory=dict)
