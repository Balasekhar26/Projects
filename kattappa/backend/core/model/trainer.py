"""Kattappa Training Engine (Program 27D).

Coordinates training execution: step optimization, Cosine learning rate scheduling,
gradient clipping, automatic mixed precision, and checkpoint preservation.
"""
from __future__ import annotations

import math
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.optim import AdamW
from torch.utils.data import DataLoader

from backend.core.model.config import KattappaConfig
from backend.core.model.architecture import KattappaModel


class KattappaTrainer:
    """Manages training lifecycle, optimization, checkpoints, and validation passes."""

    def __init__(
        self,
        model: KattappaModel,
        train_dataloader: DataLoader,
        val_dataloader: Optional[DataLoader] = None,
        lr: float = 5e-4,
        warmup_steps: int = 10,
        max_steps: int = 100,
        grad_accum_steps: int = 1,
        max_grad_norm: float = 1.0,
        checkpoint_dir: str | Path = "checkpoints",
        device: str = "cpu",
    ) -> None:
        self.model = model.to(device)
        self.train_dataloader = train_dataloader
        self.val_dataloader = val_dataloader
        self.lr = lr
        self.warmup_steps = warmup_steps
        self.max_steps = max_steps
        self.grad_accum_steps = grad_accum_steps
        self.max_grad_norm = max_grad_norm
        self.checkpoint_dir = Path(checkpoint_dir)
        self.device = device

        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)

        # Setup Optimizer (standard AdamW)
        self.optimizer = AdamW(self.model.parameters(), lr=self.lr, weight_decay=0.01)

        self.current_step = 0
        self.current_epoch = 0

    def _get_lr(self, step: int) -> float:
        """Computes Cosine Annealing Learning Rate with linear warmup."""
        if step < self.warmup_steps:
            return self.lr * float(step + 1) / float(self.warmup_steps)

        if step >= self.max_steps:
            return self.lr * 0.1

        # Cosine decay down to 10% of base lr
        progress = float(step - self.warmup_steps) / float(self.max_steps - self.warmup_steps)
        cosine_decay = 0.5 * (1.0 + math.cos(math.pi * progress))
        decayed_lr = self.lr * (0.1 + 0.9 * cosine_decay)
        return decayed_lr

    def _update_lr(self) -> None:
        step_lr = self._get_lr(self.current_step)
        for param_group in self.optimizer.param_groups:
            param_group["lr"] = step_lr

    def save_checkpoint(self, path: str | Path) -> None:
        """Saves a training state checkpoint."""
        checkpoint_path = Path(path)
        state = {
            "step": self.current_step,
            "epoch": self.current_epoch,
            "model_state_dict": self.model.state_dict(),
            "optimizer_state_dict": self.optimizer.state_dict(),
            "config": self.model.config.to_dict(),
        }
        torch.save(state, checkpoint_path)

    def load_checkpoint(self, path: str | Path) -> None:
        """Loads a training state checkpoint to resume."""
        checkpoint_path = Path(path)
        if not checkpoint_path.exists():
            raise FileNotFoundError(f"Checkpoint not found: {checkpoint_path}")

        state = torch.load(checkpoint_path, map_location=self.device)
        self.current_step = state["step"]
        self.current_epoch = state["epoch"]
        self.model.load_state_dict(state["model_state_dict"])
        self.optimizer.load_state_dict(state["optimizer_state_dict"])

    def train_step(self, batch: Dict[str, torch.Tensor]) -> float:
        """Runs a single forward and backward optimization step."""
        self.model.train()
        input_ids = batch["input_ids"].to(self.device)
        labels = batch["labels"].to(self.device)

        # Autocast mixed-precision helper (defaults to CPU/CUDA standard)
        device_type = "cuda" if "cuda" in self.device else "cpu"
        # AMP is supported on CPU with bfloat16 or float16 where possible
        amp_dtype = torch.bfloat16 if device_type == "cpu" else torch.float16

        with torch.amp.autocast(device_type=device_type, dtype=amp_dtype):
            logits = self.model(input_ids)
            # Flatten for standard CrossEntropyLoss calculation
            # logits: (B, T, V) -> (B * T, V)
            # labels: (B, T) -> (B * T)
            loss = F.cross_entropy(logits.view(-1, logits.size(-1)), labels.view(-1), ignore_index=-100)
            # Scale loss for gradient accumulation
            loss = loss / self.grad_accum_steps

        loss.backward()

        loss_val = loss.item() * self.grad_accum_steps

        # Perform optimizer step when accumulation budget is reached
        if (self.current_step + 1) % self.grad_accum_steps == 0:
            # Gradient clipping
            nn.utils.clip_grad_norm_(self.model.parameters(), self.max_grad_norm)
            self._update_lr()
            self.optimizer.step()
            self.optimizer.zero_grad()

        self.current_step += 1
        return loss_val

    def evaluate(self) -> float:
        """Computes evaluation loss on the validation dataset."""
        if not self.val_dataloader:
            return 0.0

        self.model.eval()
        total_loss = 0.0
        count = 0

        with torch.no_grad():
            for batch in self.val_dataloader:
                input_ids = batch["input_ids"].to(self.device)
                labels = batch["labels"].to(self.device)

                logits = self.model(input_ids)
                loss = F.cross_entropy(logits.view(-1, logits.size(-1)), labels.view(-1), ignore_index=-100)
                total_loss += loss.item()
                count += 1

        return total_loss / count if count > 0 else 0.0

    def fit(self, epochs: int = 1) -> List[Dict[str, float]]:
        """Executes full multi-epoch optimization loop."""
        history = []
        for epoch in range(epochs):
            self.current_epoch = epoch
            epoch_loss = 0.0
            steps = 0

            for batch in self.train_dataloader:
                if self.current_step >= self.max_steps:
                    break

                step_loss = self.train_step(batch)
                epoch_loss += step_loss
                steps += 1

            avg_train_loss = epoch_loss / steps if steps > 0 else 0.0
            avg_val_loss = self.evaluate()

            history.append({
                "epoch": float(epoch),
                "train_loss": avg_train_loss,
                "val_loss": avg_val_loss,
                "lr": self.optimizer.param_groups[0]["lr"],
            })

            # Auto-save checkpoints at epoch boundaries
            self.save_checkpoint(self.checkpoint_dir / f"epoch_{epoch}.pt")

        return history
