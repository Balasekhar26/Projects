"""
KM-5.3 — Checkpoint Manager
=============================
Saves and loads full training state: model weights, optimizer state,
scheduler state, step count, and best validation PPL.
"""

import os
import json
import torch
from pathlib import Path
from typing import Optional
from datetime import datetime


def state_to_cpu(state):
    """Recursively moves all PyTorch tensors in a state dict/list to CPU."""
    if isinstance(state, dict):
        return {k: state_to_cpu(v) for k, v in state.items()}
    elif isinstance(state, list):
        return [state_to_cpu(v) for v in state]
    elif isinstance(state, torch.Tensor):
        return state.cpu()
    else:
        return state


class CheckpointManager:
    """
    Manages checkpoint saves and loads for Kattappa training.

    Saves:
        checkpoint_step_{N}.pt    — full state dict
        checkpoint_best.pt        — best validation PPL checkpoint (symlink copy)
        training_log.jsonl        — per-eval metrics log

    Args:
        checkpoint_dir:  Directory to write checkpoints.
        keep_last_n:     Number of rolling checkpoints to retain (default 3).
    """

    def __init__(self, checkpoint_dir: str, keep_last_n: int = 3):
        self.checkpoint_dir = Path(checkpoint_dir)
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)
        self.keep_last_n = keep_last_n
        self.best_val_ppl = float("inf")
        self._saved_steps = []

        self.log_path = self.checkpoint_dir / "training_log.jsonl"

    def save(
        self,
        step: int,
        model: torch.nn.Module,
        optimizer: torch.optim.Optimizer,
        scheduler,
        val_ppl: Optional[float] = None,
        extra: Optional[dict] = None,
    ) -> str:
        """Save a checkpoint and return its path."""
        # Copy to CPU to avoid MPS memory spikes and serialization issues on GPU
        model_state_cpu = state_to_cpu(model.state_dict())
        optimizer_state_cpu = state_to_cpu(optimizer.state_dict())

        state = {
            "step": step,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "model_state_dict": model_state_cpu,
            "optimizer_state_dict": optimizer_state_cpu,
            "scheduler_state_dict": scheduler.state_dict() if hasattr(scheduler, "state_dict") else {},
            "val_ppl": val_ppl,
            "best_val_ppl": self.best_val_ppl,
        }
        if extra:
            state.update(extra)

        path = self.checkpoint_dir / f"checkpoint_step_{step:07d}.pt"
        torch.save(state, path)
        self._saved_steps.append((step, path))

        ppl_str = f"{val_ppl:.4f}" if val_ppl is not None else "N/A"
        print(f"  💾  Checkpoint saved: {path.name}  (val_ppl={ppl_str})")

        # Update best checkpoint
        if val_ppl is not None and val_ppl < self.best_val_ppl:
            self.best_val_ppl = val_ppl
            best_path = self.checkpoint_dir / "checkpoint_best.pt"
            torch.save(state, best_path)
            print(f"  🏆  New best val PPL: {val_ppl:.4f} → {best_path.name}")

        # Prune old checkpoints
        self._prune()

        # Append to training log
        self._log_metrics(step, val_ppl, extra)
        return str(path)

    def load(
        self,
        path: Optional[str] = None,
        model: Optional[torch.nn.Module] = None,
        optimizer: Optional[torch.optim.Optimizer] = None,
        scheduler=None,
        device: str = "cpu",
    ) -> dict:
        """Load a checkpoint. Defaults to loading checkpoint_best.pt if path is None."""
        if path is None:
            path = str(self.checkpoint_dir / "checkpoint_best.pt")

        if not os.path.exists(path):
            raise FileNotFoundError(f"Checkpoint not found: {path}")

        # Always load checkpoint to CPU first to avoid GPU/MPS memory allocation spikes
        state = torch.load(path, map_location="cpu")
        if model is not None:
            model.load_state_dict(state["model_state_dict"])
        if optimizer is not None:
            optimizer.load_state_dict(state["optimizer_state_dict"])
        if scheduler is not None and hasattr(scheduler, "load_state_dict"):
            scheduler.load_state_dict(state.get("scheduler_state_dict", {}))

        self.best_val_ppl = state.get("best_val_ppl", float("inf"))
        print(f"  📂  Loaded checkpoint to CPU: {path}  (step={state['step']}, best_ppl={self.best_val_ppl:.4f})")
        return state


    def _prune(self):
        """Delete old checkpoints beyond keep_last_n."""
        while len(self._saved_steps) > self.keep_last_n:
            _, old_path = self._saved_steps.pop(0)
            if old_path.exists():
                old_path.unlink()

    def _log_metrics(self, step: int, val_ppl: Optional[float], extra: Optional[dict]):
        entry = {
            "step": step,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "val_ppl": val_ppl,
        }
        if extra:
            entry.update({k: v for k, v in extra.items()
                          if isinstance(v, (int, float, str, bool))})
        with open(self.log_path, "a") as f:
            f.write(json.dumps(entry) + "\n")

    def latest_step(self) -> int:
        """Returns step number of the latest saved checkpoint, or 0."""
        if self._saved_steps:
            return self._saved_steps[-1][0]
        # Scan disk
        pts = sorted(self.checkpoint_dir.glob("checkpoint_step_*.pt"))
        if pts:
            return int(pts[-1].stem.split("_")[-1])
        return 0
