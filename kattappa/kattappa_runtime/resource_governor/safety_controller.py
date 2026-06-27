"""
Safety Controller — Step 30 (Proactive Admission Control)
==========================================================

Acts as an OS-style protective scheduler. Enforces absolute limits, gates executions,
serializes heavyweight tasks using file locks, and predicts memory requirements
proactively before launching steps.
"""

from __future__ import annotations

import contextlib
import fcntl
import gc
import os
import time
from typing import Optional

import torch

from kattappa_runtime.resource_governor.monitor import ResourceMonitor
from kattappa_runtime.resource_governor.schema import (
    AppleSiliconPressure,
    ApprovalResult,
    SafetyThresholds,
    SafetyVerdict,
    SystemResourceMetrics,
    TrainerBudget,
    TrainingConfig,
)


@contextlib.contextmanager
def heavyweight_task(task_name: str, lock_path: Optional[str] = None):
    """
    Guarantees that only one heavyweight operation (training, evaluation, 
    checkpointing, indexing, embedding, preprocessing) runs at a time.
    Uses Unix fcntl flock on a global lock file.
    """
    if lock_path is None:
        lock_path = os.path.expanduser("~/.gemini/antigravity-ide/kattappa_heavyweight.lock")
        
    os.makedirs(os.path.dirname(lock_path), exist_ok=True)
    
    # Open lock file
    lock_file = open(lock_path, "w")
    try:
        # Request exclusive lock (blocks if another process/thread holds it)
        fcntl.flock(lock_file, fcntl.LOCK_EX)
        lock_file.write(task_name)
        lock_file.flush()
        yield
    finally:
        try:
            fcntl.flock(lock_file, fcntl.LOCK_UN)
            lock_file.close()
        except Exception:
            pass


class SafetyController:
    """
    Predictive safety scheduler gating the launch of training steps and enforcing 
    strict operating limits for Apple Silicon system stability.
    """
    def __init__(
        self,
        monitor: ResourceMonitor,
        thresholds: Optional[SafetyThresholds] = None,
        budget: Optional[TrainerBudget] = None,
        config: Optional[TrainingConfig] = None,
    ):
        self.monitor = monitor
        self.thresholds = thresholds or SafetyThresholds()
        self.budget = budget or TrainerBudget()
        self.config = config or TrainingConfig()

        self.healthy_steps_counter = 0
        self.previous_swap_used_gb: Optional[float] = None

    def estimate_memory_detailed(self, batch_size: int, seq_len: int, checkpointing: bool = False) -> dict:
        """
        Predicts total memory requirements in GB with detailed breakdown:
        - weights
        - optimizer
        - gradients
        - activations
        - checkpoint buffer
        - MPS overhead
        - OS reserve
        - total projected usage
        """
        num_params = 137_000_000
        bytes_per_param = self.budget.bytes_per_param  # FP16/BF16 is 2.0

        weights_gb = (num_params * bytes_per_param) / (1024 ** 3)
        gradients_gb = (num_params * bytes_per_param) / (1024 ** 3)
        
        # Adam FP32 state: 8 bytes/param (moments only)
        optimizer_gb = (num_params * 8.0) / (1024 ** 3)

        # Activations (16 bytes per activation token-layer is highly reliable)
        activations_gb = (batch_size * seq_len * self.budget.d_model * self.budget.n_layers * 16.0) / (1024 ** 3)

        # Checkpoint buffer
        ckpt_overhead_gb = weights_gb if checkpointing else 0.0

        # MPS Overhead: Metal context + internal driver allocations (modeled as 50% of model weight/optim footprint)
        mps_overhead_gb = (weights_gb + gradients_gb + optimizer_gb) * 0.5

        # OS Reserve
        os_reserve_gb = self.budget.macos_reserve_gb

        total_projected_gb = weights_gb + gradients_gb + optimizer_gb + activations_gb + ckpt_overhead_gb + mps_overhead_gb + os_reserve_gb

        return {
            "estimated_weights_gb": weights_gb,
            "estimated_optimizer_memory_gb": optimizer_gb,
            "estimated_gradients_gb": gradients_gb,
            "estimated_activation_memory_gb": activations_gb,
            "estimated_checkpoint_buffers_gb": ckpt_overhead_gb,
            "estimated_mps_overhead_gb": mps_overhead_gb,
            "estimated_os_reserve_gb": os_reserve_gb,
            "total_projected_gb": total_projected_gb,
        }

    def estimate_memory_requirements(self, batch_size: int, seq_len: int, checkpointing: bool = False) -> float:
        """
        Predicts total memory requirements in GB (weights + optimizer + activations + overhead + OS reserve).
        """
        return self.estimate_memory_detailed(batch_size, seq_len, checkpointing)["total_projected_gb"]

    def approve_training_config(self, requested_batch: int, requested_seq_len: int) -> ApprovalResult:
        """
        Gates initial training launch by checking predicted memory against the physical budget.
        """
        metrics = self.monitor.get_metrics()
        if metrics.swap_file_count > self.thresholds.max_safe_swapfiles:
            return ApprovalResult(
                approved=False,
                requested_batch=requested_batch,
                requested_seq_len=requested_seq_len,
                max_safe_batch=self.config.min_microbatch,
                max_safe_seq_len=self.config.initial_seq_len,
                estimated_activation_memory_gb=0.0,
                reason=f"Existing swapfile count {metrics.swap_file_count} exceeds safe limit ({self.thresholds.max_safe_swapfiles})",
            )

        # Perform proactive projection
        est_gb = self.estimate_memory_requirements(requested_batch, requested_seq_len)
        limit_gb = self.budget.kattappa_budget_gb

        if est_gb <= limit_gb:
            return ApprovalResult(
                approved=True,
                requested_batch=requested_batch,
                requested_seq_len=requested_seq_len,
                max_safe_batch=requested_batch,
                max_safe_seq_len=requested_seq_len,
                estimated_activation_memory_gb=est_gb,
                reason="Projected memory requirement fits within budget.",
            )

        # Scale down batch first, then sequence length
        max_safe_batch = requested_batch
        max_safe_seq_len = requested_seq_len

        while est_gb > limit_gb:
            if max_safe_batch > self.config.min_microbatch:
                max_safe_batch -= 1
            elif max_safe_seq_len > self.config.initial_seq_len:
                lower_seqs = [s for s in self.config.seq_len_steps if s < max_safe_seq_len]
                if lower_seqs:
                    max_safe_seq_len = max(lower_seqs)
                else:
                    max_safe_seq_len = self.config.initial_seq_len
            else:
                max_safe_batch = self.config.min_microbatch
                max_safe_seq_len = self.config.initial_seq_len
                break
            est_gb = self.estimate_memory_requirements(max_safe_batch, max_safe_seq_len)

        return ApprovalResult(
            approved=False,
            requested_batch=requested_batch,
            requested_seq_len=requested_seq_len,
            max_safe_batch=max_safe_batch,
            max_safe_seq_len=max_safe_seq_len,
            estimated_activation_memory_gb=est_gb,
            reason=f"Projected requirement {est_gb:.2f} GB exceeds budget {limit_gb} GB. Recommending scaled limits.",
        )

    def assess(self) -> SafetyVerdict:
        """
        Checks real-time system metrics against warnings and strict pause limits.
        """
        metrics = self.monitor.get_metrics()
        reasons_pause = []
        reasons_warn = []

        # 1. Swap Space (limit: 1.0 GB)
        if metrics.swap_used_gb >= self.thresholds.swap_pause_gb:
            reasons_pause.append(f"Swap usage ({metrics.swap_used_gb:.2f} GB) exceeded limit ({self.thresholds.swap_pause_gb} GB)")
        elif metrics.swap_used_gb >= self.thresholds.swap_warn_gb:
            reasons_warn.append(f"Swap usage ({metrics.swap_used_gb:.2f} GB) exceeded warning ({self.thresholds.swap_warn_gb} GB)")

        # SSD Swap Growth
        if self.previous_swap_used_gb is not None:
            swap_growth = metrics.swap_used_gb - self.previous_swap_used_gb
            if swap_growth >= self.thresholds.swap_growth_pause_gb:
                reasons_pause.append(f"SSD Swap growth ({swap_growth:.3f} GB) exceeded pause limit ({self.thresholds.swap_growth_pause_gb} GB)")
            elif swap_growth >= self.thresholds.swap_growth_warn_gb:
                reasons_warn.append(f"SSD Swap growth ({swap_growth:.3f} GB) exceeded warning limit ({self.thresholds.swap_growth_warn_gb} GB)")
        self.previous_swap_used_gb = metrics.swap_used_gb

        # 2. Compressed Memory (limit: 25%)
        if metrics.compressed_memory_pct >= self.thresholds.compressed_mem_pause_pct:
            reasons_pause.append(f"Compressed memory ({metrics.compressed_memory_pct:.1f}%) exceeded limit ({self.thresholds.compressed_mem_pause_pct}%)")
        elif metrics.compressed_memory_pct >= self.thresholds.compressed_mem_warn_pct:
            reasons_warn.append(f"Compressed memory ({metrics.compressed_memory_pct:.1f}%) exceeded warning ({self.thresholds.compressed_mem_warn_pct}%)")

        # 3. MPS Memory Usage (limit: 9.0 GB)
        if metrics.unified_memory_used_gb >= self.thresholds.mps_pause_gb:
            reasons_pause.append(f"MPS unified memory ({metrics.unified_memory_used_gb:.2f} GB) exceeded limit ({self.thresholds.mps_pause_gb} GB)")
        elif metrics.unified_memory_used_gb >= self.thresholds.mps_warn_gb:
            reasons_warn.append(f"MPS unified memory ({metrics.unified_memory_used_gb:.2f} GB) exceeded warning ({self.thresholds.mps_warn_gb} GB)")

        # 4. SSD Free Space (limit: 100 GB)
        if metrics.ssd_free_gb <= self.thresholds.ssd_pause_gb:
            reasons_pause.append(f"SSD free space ({metrics.ssd_free_gb:.1f} GB) below limit ({self.thresholds.ssd_pause_gb} GB)")
        elif metrics.ssd_free_gb <= self.thresholds.ssd_warn_gb:
            reasons_warn.append(f"SSD free space ({metrics.ssd_free_gb:.1f} GB) below warning ({self.thresholds.ssd_warn_gb} GB)")

        # 5. Pageout Rate (limit: 2.0 pageouts/sec)
        if metrics.pageouts_per_sec >= self.thresholds.pageouts_pause_rate:
            reasons_pause.append(f"Pageout rate ({metrics.pageouts_per_sec:.1f}/s) exceeded limit ({self.thresholds.pageouts_pause_rate}/s)")

        # 6. macOS Memory Pressure Level
        # Enforce configurable memory_pause_level threshold
        if metrics.memory_pressure == AppleSiliconPressure.CRITICAL:
            if getattr(self.thresholds, "memory_pause_level", "WARNING") in ["CRITICAL", "WARNING"]:
                reasons_pause.append("macOS memory pressure level is CRITICAL")
            else:
                reasons_warn.append("macOS memory pressure level is CRITICAL")
        elif metrics.memory_pressure == AppleSiliconPressure.WARN:
            if getattr(self.thresholds, "memory_pause_level", "WARNING") == "WARNING":
                reasons_pause.append("macOS memory pressure level is WARN")
            else:
                reasons_warn.append("macOS memory pressure level is WARN")


        # Compile verdict
        has_pause = len(reasons_pause) > 0
        has_warn = len(reasons_warn) > 0
        
        is_paused = has_pause and (self.config.safety_mode == "strict")
        
        if is_paused:
            reason = "PAUSED: " + " | ".join(reasons_pause)
            self.healthy_steps_counter = 0
            # Recommend immediate microbatch scaling
            rec_batch = max(self.config.min_microbatch, int(metrics.swap_file_count - 1))
            return SafetyVerdict(
                ok=False,
                pause=True,
                warn=has_warn,
                reason=reason,
                recommended_microbatch=rec_batch,
                metrics_snapshot=metrics,
            )
        elif has_pause or has_warn:
            reason = "WARNING: " + " | ".join(reasons_pause + reasons_warn)
            return SafetyVerdict(
                ok=True,
                pause=False,
                warn=True,
                reason=reason,
                metrics_snapshot=metrics,
            )
        
        # Nominal / healthy state
        self.healthy_steps_counter += 1
        rec_batch = None
        if self.healthy_steps_counter >= self.thresholds.stable_steps_to_grow:
            rec_batch = min(self.config.max_microbatch, self.config.min_microbatch + 1)
        
        return SafetyVerdict(
            ok=True,
            pause=False,
            warn=False,
            reason="System healthy.",
            recommended_microbatch=rec_batch,
            metrics_snapshot=metrics,
        )

    def wait_for_safe(self, timeout_s: float = 300.0) -> bool:
        """
        Blocks the execution of the thread until the system returns to a safe status.
        Runs emergency collections during the wait.
        """
        start_time = time.time()
        self.emergency_gc()
        
        verdict = self.assess()
        if verdict.ok:
            return True

        print(f"⌛  SafetyController gating: {verdict.reason}. Waiting for recovery...")
        
        while time.time() - start_time < timeout_s:
            self.emergency_gc()
            time.sleep(5.0)
            
            # Force update metrics
            self.monitor.force_poll()
            verdict = self.assess()
            if verdict.ok:
                print("⚡  System recovered. Resuming execution.")
                return True
                
        print(f"❌  SafetyController timeout reached ({timeout_s}s). Resuming under warning.")
        return False

    def emergency_gc(self):
        """Forces Python GC collect and empties PyTorch MPS memory cache."""
        gc.collect()
        if torch.backends.mps.is_available():
            try:
                torch.mps.empty_cache()
            except Exception:
                pass
