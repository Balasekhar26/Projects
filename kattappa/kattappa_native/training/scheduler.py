"""
KM-5.3 — Cosine Learning Rate Scheduler with Warmup
=====================================================
Implements the standard LLM training schedule:
  1. Linear warmup from 0 → peak_lr over warmup_steps
  2. Cosine annealing from peak_lr → min_lr over remaining steps
"""

import math
import torch


def get_lr(step: int, warmup_steps: int, max_steps: int,
           peak_lr: float, min_lr: float = 1e-5) -> float:
    """
    Returns the learning rate for a given training step.

    Args:
        step:         Current training step (0-indexed).
        warmup_steps: Number of linear warmup steps.
        max_steps:    Total training steps.
        peak_lr:      Maximum learning rate (reached at end of warmup).
        min_lr:       Minimum learning rate (floor of cosine decay).
    """
    # Phase 1: Linear warmup
    if step < warmup_steps:
        return peak_lr * (step + 1) / warmup_steps

    # Phase 2: Cosine annealing
    progress = (step - warmup_steps) / max(max_steps - warmup_steps, 1)
    cosine_factor = 0.5 * (1.0 + math.cos(math.pi * progress))
    return min_lr + (peak_lr - min_lr) * cosine_factor


class CosineScheduler:
    """
    Stateful LR scheduler wrapping get_lr().

    Usage:
        scheduler = CosineScheduler(optimizer, total_steps=50000, warmup_ratio=0.02)
        for step in training_loop:
            scheduler.step()
    """

    def __init__(
        self,
        optimizer: torch.optim.Optimizer,
        total_steps: int,
        peak_lr: float = 3e-4,
        min_lr: float = 1e-5,
        warmup_ratio: float = 0.02,
    ):
        self.optimizer    = optimizer
        self.total_steps  = total_steps
        self.peak_lr      = peak_lr
        self.min_lr       = min_lr
        self.warmup_steps = max(1, int(total_steps * warmup_ratio))
        self._step        = 0

    def step(self):
        """Update optimizer lr and advance internal step counter."""
        lr = get_lr(
            self._step,
            warmup_steps=self.warmup_steps,
            max_steps=self.total_steps,
            peak_lr=self.peak_lr,
            min_lr=self.min_lr,
        )
        for group in self.optimizer.param_groups:
            group["lr"] = lr
        self._step += 1
        return lr

    def current_lr(self) -> float:
        return get_lr(
            self._step,
            warmup_steps=self.warmup_steps,
            max_steps=self.total_steps,
            peak_lr=self.peak_lr,
            min_lr=self.min_lr,
        )

    def state_dict(self) -> dict:
        return {"step": self._step, "total_steps": self.total_steps,
                "peak_lr": self.peak_lr, "min_lr": self.min_lr,
                "warmup_steps": self.warmup_steps}

    def load_state_dict(self, state: dict):
        self._step        = state["step"]
        self.total_steps  = state["total_steps"]
        self.peak_lr      = state["peak_lr"]
        self.min_lr       = state["min_lr"]
        self.warmup_steps = state["warmup_steps"]
