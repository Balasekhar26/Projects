"""
Resource Governor Schema — Step 30 (Proactive Safety Hardening)
================================================================

Foundational configurations, thresholds, budgets, and runtime metric definitions
for Kattappa's Resource Governor (KRG) and the Safety Controller layer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional


# ── Apple Silicon Memory Pressure ─────────────────────────────────────────────

class AppleSiliconPressure(str, Enum):
    """
    macOS memory pressure levels reported by the `memory_pressure` CLI tool
    or derived from `vm_stat` compressor occupancy.
    """
    NOMINAL  = "nominal"   # System healthy; no corrective action needed
    WARN     = "warn"      # Elevated compression; reduce new allocations
    CRITICAL = "critical"  # Kernel actively reclaiming; pause training immediately


# ── System Resource Metrics ────────────────────────────────────────────────────

@dataclass
class SystemResourceMetrics:
    """
    Real-time physical system resource metrics, extended for Apple Silicon.
    """
    # Standard CPU / RAM
    cpu_percent: float = 0.0
    ram_percent: float = 0.0

    # Apple GPU (MPS) usage
    gpu_percent: float = 0.0
    unified_memory_used_gb: float = 0.0
    vram_used_gb: float = 0.0

    # MPS hard limit recommended by the OS driver
    mps_recommended_max_memory_gb: float = 0.0

    # I/O rates
    disk_io_read_bytes_sec: float = 0.0
    disk_io_write_bytes_sec: float = 0.0
    net_io_recv_bytes_sec: float = 0.0
    net_io_sent_bytes_sec: float = 0.0

    # Thermal / power
    temperature_c: float = 45.0
    battery_percent: float = 100.0
    power_draw_watts: float = 15.0

    # ── Apple Silicon specific ─────────────────────────────────────────────────
    swap_used_gb: float = 0.0
    swap_total_gb: float = 0.0
    swap_file_count: int = 0
    compressed_memory_pct: float = 0.0       # % of physical RAM occupied by compressor
    memory_pressure: AppleSiliconPressure = AppleSiliconPressure.NOMINAL
    ssd_free_gb: float = 500.0               # Free space on boot volume
    
    # Pageouts and Swapouts tracking
    pageouts_per_sec: float = 0.0
    swapouts_per_sec: float = 0.0

    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


# ── Subsystem Budget ───────────────────────────────────────────────────────────

@dataclass
class SubsystemBudget:
    """
    Defines resource budget limit shares for a subsystem with absolute limits.
    """
    subsystem: str
    cpu_limit_percent: float = 5.0
    ram_limit_mb: float = 500.0
    gpu_limit_percent: float = 5.0


@dataclass
class SubsystemStats:
    """
    Performance and concurrency metrics for active subsystems.
    """
    latency_ms: float = 0.0
    queue_length: int = 0
    active_agents: List[str] = field(default_factory=list)
    running_workflows: List[str] = field(default_factory=list)


# ── Governance Config ──────────────────────────────────────────────────────────

@dataclass
class GovernanceConfig:
    """
    Global governance policy, thresholds, and limits.
    Default targets enforce conservative limits.
    """
    global_cpu_limit: float = 0.30            # Conservative CPU target (30%)
    global_ram_limit: float = 0.35            # Conservative RAM target (35%)
    global_gpu_limit: float = 0.35            # Conservative GPU target (35%)
    global_unified_memory_limit: float = 0.35
    global_vram_limit: float = 0.35
    global_disk_io_limit_mb_s: float = 50.0  # limit sustained disk speed
    global_net_io_limit_mb_s: float = 10.0   # limit sustained network speed

    # SSD space safety targets: keep max(5% of disk, 5 GB)
    min_free_disk_space_ratio: float = 0.05
    min_free_disk_space_bytes: int = 5 * 1024 * 1024 * 1024  # 5 GB

    # Critical thresholds
    thermal_throttling_temp_c: float = 85.0
    battery_eco_threshold: float = 20.0

    # Allocations
    subsystem_budgets: Dict[str, SubsystemBudget] = field(default_factory=dict)


# ── Safety Controller Schemas ──────────────────────────────────────────────────

@dataclass
class SafetyThresholds:
    """
    Hard numeric thresholds for the SafetyController.
    """
    # Swap (Extremely conservative: max 1.0 GB swap)
    swap_warn_gb: float  = 0.5
    swap_pause_gb: float = 1.0

    # SSD Swap Growth rates (change in swap usage between steps)
    swap_growth_warn_gb: float  = 0.05
    swap_growth_pause_gb: float = 0.10

    # Compressor occupancy (% of physical RAM)
    compressed_mem_warn_pct: float  = 15.0
    compressed_mem_pause_pct: float = 25.0

    # MPS driver allocated memory (GB)
    mps_warn_gb: float  = 8.0
    mps_pause_gb: float = 9.0   # Training budget limit

    # Boot volume free space
    ssd_warn_gb: float  = 10.0
    ssd_pause_gb: float = 5.0

    # Memory pressure: True means we pause if pressure is anything other than NOMINAL (Green)
    pause_on_warn_pressure: bool = True
    pause_on_critical_pressure: bool = True
    memory_pause_level: str = "WARNING"  # Configurable: OFF, CRITICAL, WARNING


    # Pageout/Swapout rates triggers (pause if pageouts exceed rate)
    pageouts_pause_rate: float = 2.0  # Conservative: pageouts per second limit

    # Swap file count: more than this many files → refuse to start
    max_safe_swapfiles: int = 3

    # Consecutive healthy steps before attempting to grow microbatch
    stable_steps_to_grow: int = 50


@dataclass
class TrainerBudget:
    """
    Hard numeric memory budget for the training process.
    """
    total_ram_gb: float = 24.0
    kattappa_budget_gb: float = 9.0     # Training budget limit (max 37.5% of 24 GB)
    macos_reserve_gb: float = 6.0        # Reserved for OS + Metal + Python overhead
    emergency_reserve_gb: float = 9.0    # Reserve for browser, desktop, IDE, etc.

    # Model architecture for activation memory estimation
    d_model: int = 768
    n_layers: int = 12
    n_heads: int = 12
    bytes_per_param: float = 2.0         # BF16/FP16


@dataclass
class TrainingConfig:
    """
    Dynamic training configuration managed by the SafetyController.
    """
    # Sequence length curriculum
    initial_seq_len: int = 256
    target_seq_len: int = 2048
    seq_len_steps: List[int] = field(
        default_factory=lambda: [256, 512, 1024, 2048]
    )
    # Step markers for progression
    # Steps 0-5k: 256
    # 5k-15k: 512
    # 15k-30k: 1024
    # 30k+: 2048
    steps_per_stage: List[int] = field(
        default_factory=lambda: [5000, 15000, 30000]
    )

    # Microbatch limits
    min_microbatch: int = 1
    max_microbatch: int = 8

    # Safety mode: "strict" enforces all pause thresholds; "monitor" only warns
    safety_mode: str = "strict"


# ── SafetyController Result Types ─────────────────────────────────────────────

@dataclass
class SafetyVerdict:
    """
    Result returned by SafetyController.assess().
    """
    ok: bool
    pause: bool
    warn: bool
    reason: str
    recommended_microbatch: Optional[int] = None
    recommended_seq_len: Optional[int] = None
    metrics_snapshot: Optional[SystemResourceMetrics] = None


@dataclass
class ApprovalResult:
    """
    Result returned by SafetyController.approve_training_config().
    """
    approved: bool
    requested_batch: int
    requested_seq_len: int
    max_safe_batch: int
    max_safe_seq_len: int
    estimated_activation_memory_gb: float
    reason: str
