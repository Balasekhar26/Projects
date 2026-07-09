"""DPO Alignment Trainer (Program 27E4).

Implements Direct Preference Optimization on top of a supervised
pretrained KattappaModel. Uses a frozen reference model and a trainable
policy model updated via the DPO loss.

DPO loss (Rafailov et al. 2023):
    L = -log σ( β * (log π(y_w|x) - log π_ref(y_w|x))
                  - β * (log π(y_l|x) - log π_ref(y_l|x)) )
"""
from __future__ import annotations

import copy
import math
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.optim import AdamW


@dataclass
class DPOConfig:
    beta: float = 0.1          # KL-penalty strength
    lr: float = 1e-5
    max_steps: int = 50
    grad_clip: float = 1.0


def _log_probs_from_logits(
    logits: torch.Tensor,
    labels: torch.Tensor,
) -> torch.Tensor:
    """Per-token log-probabilities for the label tokens, summed over sequence.

    logits: (B, T, V)
    labels: (B, T) — ignore_index = -100 marks padding
    Returns: (B,) scalar per example.
    """
    log_p = F.log_softmax(logits, dim=-1)  # (B, T, V)
    # Clamp label padding to 0 for gather (will be masked out)
    safe_labels = labels.clone()
    safe_labels[labels == -100] = 0
    token_log_p = log_p.gather(2, safe_labels.unsqueeze(2)).squeeze(2)  # (B, T)
    mask = (labels != -100).float()
    return (token_log_p * mask).sum(dim=-1)  # (B,)


def dpo_loss(
    policy_chosen_logps: torch.Tensor,
    policy_rejected_logps: torch.Tensor,
    ref_chosen_logps: torch.Tensor,
    ref_rejected_logps: torch.Tensor,
    beta: float,
) -> torch.Tensor:
    """Computes the DPO loss for a batch of preference pairs."""
    chosen_rewards = beta * (policy_chosen_logps - ref_chosen_logps)
    rejected_rewards = beta * (policy_rejected_logps - ref_rejected_logps)
    losses = -F.logsigmoid(chosen_rewards - rejected_rewards)
    return losses.mean()


class DPOTrainer:
    """Fine-tunes a KattappaModel via Direct Preference Optimization."""

    def __init__(
        self,
        policy_model: nn.Module,
        config: Optional[DPOConfig] = None,
        device: str = "cpu",
    ) -> None:
        self.config = config or DPOConfig()
        self.device = device

        # Policy model receives gradients
        self.policy = policy_model.to(device)

        # Reference model is a frozen copy of the initial SFT checkpoint
        self.reference = copy.deepcopy(policy_model).to(device)
        for param in self.reference.parameters():
            param.requires_grad_(False)
        self.reference.eval()

        self.optimizer = AdamW(self.policy.parameters(), lr=self.config.lr)

    def _encode_pair(
        self,
        tokenizer: Any,
        prompt: str,
        response: str,
        max_len: int = 256,
    ) -> torch.Tensor:
        """Encodes prompt+response into a label tensor (BOS prepended, padding -100)."""
        text = prompt + response
        ids = tokenizer.encode(text, out_type=int)
        ids = [2] + ids[:max_len - 1]  # prepend BOS, truncate
        return torch.tensor(ids, dtype=torch.long)

    def train_step(
        self,
        tokenizer: Any,
        pairs: List[Any],  # List[PreferencePair]
    ) -> float:
        """Runs one DPO optimisation step over a list of preference pairs."""
        self.policy.train()

        chosen_logps_list: List[torch.Tensor] = []
        rejected_logps_list: List[torch.Tensor] = []
        ref_chosen_logps_list: List[torch.Tensor] = []
        ref_rejected_logps_list: List[torch.Tensor] = []

        for pair in pairs:
            cho = self._encode_pair(tokenizer, pair.prompt, pair.chosen).unsqueeze(0).to(self.device)
            rej = self._encode_pair(tokenizer, pair.prompt, pair.rejected).unsqueeze(0).to(self.device)

            labels_cho = cho.clone(); labels_cho[0, 0] = -100
            labels_rej = rej.clone(); labels_rej[0, 0] = -100

            with torch.no_grad():
                ref_cho_logits = self.reference(cho)
                ref_rej_logits = self.reference(rej)
                ref_chosen_logps_list.append(_log_probs_from_logits(ref_cho_logits, labels_cho))
                ref_rejected_logps_list.append(_log_probs_from_logits(ref_rej_logits, labels_rej))

            pol_cho_logits = self.policy(cho)
            pol_rej_logits = self.policy(rej)
            chosen_logps_list.append(_log_probs_from_logits(pol_cho_logits, labels_cho))
            rejected_logps_list.append(_log_probs_from_logits(pol_rej_logits, labels_rej))

        loss = dpo_loss(
            torch.cat(chosen_logps_list),
            torch.cat(rejected_logps_list),
            torch.cat(ref_chosen_logps_list),
            torch.cat(ref_rejected_logps_list),
            beta=self.config.beta,
        )

        self.optimizer.zero_grad()
        loss.backward()
        nn.utils.clip_grad_norm_(self.policy.parameters(), self.config.grad_clip)
        self.optimizer.step()

        return loss.item()

    def fit(
        self,
        tokenizer: Any,
        preference_pairs: List[Any],
        batch_size: int = 4,
    ) -> List[Dict[str, float]]:
        """Runs DPO fine-tuning for max_steps steps."""
        history: List[Dict[str, float]] = []
        step = 0
        while step < self.config.max_steps and preference_pairs:
            batch = preference_pairs[step % len(preference_pairs) : step % len(preference_pairs) + batch_size]
            if not batch:
                batch = preference_pairs[:batch_size]
            loss_val = self.train_step(tokenizer, batch)
            history.append({"step": float(step), "dpo_loss": loss_val})
            step += 1
        return history
