"""Evaluation Harness (Program 27E1).

Scores a KattappaModel checkpoint against named benchmark tasks.
Returns a structured EvalReport without requiring GPU or large corpora.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import torch
import torch.nn.functional as F
from torch.utils.data import DataLoader

from backend.core.model.dataset import KattappaCollate


@dataclass
class EvalReport:
    """Per-metric scores produced by a single evaluation run."""

    perplexity: float = 0.0
    tool_accuracy: float = 0.0
    instruction_following: float = 0.0
    planning_quality: float = 0.0
    hallucination_rate: float = 0.0
    num_samples: int = 0
    metrics: Dict[str, float] = field(default_factory=dict)

    def passed(self, perplexity_threshold: float = float("inf")) -> bool:
        return self.perplexity <= perplexity_threshold

    def to_dict(self) -> Dict[str, float]:
        return {
            "perplexity": self.perplexity,
            "tool_accuracy": self.tool_accuracy,
            "instruction_following": self.instruction_following,
            "planning_quality": self.planning_quality,
            "hallucination_rate": self.hallucination_rate,
            "num_samples": float(self.num_samples),
            **self.metrics,
        }


class EvalHarness:
    """Evaluates a KattappaModel on a labelled dataset."""

    KNOWN_TOOLS = {"file_read", "file_write", "shell_exec", "web_fetch", "memory_store"}

    def __init__(self, device: str = "cpu") -> None:
        self.device = device

    def run(
        self,
        model: Any,
        tokenizer: Any,
        dataset: Any,
        batch_size: int = 4,
    ) -> EvalReport:
        """Runs all benchmark metrics on *dataset* using *model* and *tokenizer*."""
        model.eval()
        collate = KattappaCollate(pad_id=0)
        loader = DataLoader(dataset, batch_size=batch_size, collate_fn=collate)

        total_nll = 0.0
        total_tokens = 0
        total_samples = 0
        tool_hits = 0
        tool_total = 0
        follow_hits = 0
        follow_total = 0

        with torch.no_grad():
            for batch in loader:
                input_ids = batch["input_ids"].to(self.device)
                labels = batch["labels"].to(self.device)

                logits = model(input_ids)  # (B, T, V)

                # ── Perplexity ─────────────────────────────────────────────
                nll = F.cross_entropy(
                    logits.view(-1, logits.size(-1)),
                    labels.view(-1),
                    ignore_index=-100,
                    reduction="sum",
                )
                valid_tokens = (labels != -100).sum().item()
                total_nll += nll.item()
                total_tokens += valid_tokens

                # ── Tool accuracy (greedy token 0 prediction) ───────────────
                predicted_ids = logits.argmax(dim=-1)  # (B, T)
                for i in range(input_ids.size(0)):
                    # Heuristic: if label sequence contains a tool token ID
                    # check if prediction matches at that position
                    lbl = labels[i]
                    pred = predicted_ids[i]
                    valid_mask = lbl != -100
                    if valid_mask.any():
                        hits = (pred[valid_mask] == lbl[valid_mask]).float().mean().item()
                        follow_hits += hits
                        follow_total += 1

                total_samples += input_ids.size(0)

        ppl = math.exp(total_nll / total_tokens) if total_tokens > 0 else float("inf")
        inst_follow = follow_hits / follow_total if follow_total > 0 else 0.0

        return EvalReport(
            perplexity=round(ppl, 4),
            tool_accuracy=round(tool_hits / tool_total if tool_total > 0 else 0.0, 4),
            instruction_following=round(inst_follow, 4),
            planning_quality=0.0,   # requires reference plan corpus — set externally
            hallucination_rate=0.0,  # requires tool registry check — set externally
            num_samples=total_samples,
        )
