"""Continuous Regression Runner (Program 27E5).

Wires EvalHarness and SafetyEval into an automated pipeline that runs
after every checkpoint is saved and emits a PASS / FAIL / REGRESSION signal.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

import torch

from backend.core.eval.eval_harness import EvalHarness, EvalReport
from backend.core.eval.safety_eval import SafetyEval, SafetyReport
from backend.core.model.config import KattappaConfig
from backend.core.model.architecture import KattappaModel


class RegressionSignal(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    REGRESSION = "REGRESSION"


@dataclass
class RegressionResult:
    """Full output of a regression evaluation run."""

    signal: RegressionSignal
    checkpoint_path: str
    eval_report: EvalReport
    safety_report: SafetyReport
    baseline_perplexity: Optional[float] = None
    perplexity_delta: Optional[float] = None
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "signal": self.signal.value,
            "checkpoint_path": self.checkpoint_path,
            "eval": self.eval_report.to_dict(),
            "safety": self.safety_report.to_dict(),
            "baseline_perplexity": self.baseline_perplexity,
            "perplexity_delta": self.perplexity_delta,
            "notes": self.notes,
        }


class RegressionRunner:
    """Automated regression evaluation pipeline."""

    def __init__(
        self,
        eval_harness: Optional[EvalHarness] = None,
        safety_eval: Optional[SafetyEval] = None,
        perplexity_tolerance: float = 0.02,   # 2% regression threshold
        device: str = "cpu",
    ) -> None:
        self.harness = eval_harness or EvalHarness(device=device)
        self.safety = safety_eval or SafetyEval()
        self.perplexity_tolerance = perplexity_tolerance
        self.device = device

    def evaluate(
        self,
        checkpoint_path: str | Path,
        eval_dataset: Any,
        safety_texts: Optional[List[str]] = None,
        baseline_perplexity: Optional[float] = None,
    ) -> RegressionResult:
        """Loads checkpoint, runs full evaluation, returns RegressionResult."""
        path = Path(checkpoint_path)
        notes: List[str] = []

        # ── Load model from checkpoint ────────────────────────────────────────
        if not path.exists():
            return RegressionResult(
                signal=RegressionSignal.FAIL,
                checkpoint_path=str(path),
                eval_report=EvalReport(),
                safety_report=SafetyReport(),
                notes=[f"Checkpoint not found: {path}"],
            )

        state = torch.load(path, map_location=self.device)
        cfg_dict = state.get("config", {})
        cfg = KattappaConfig(**{k: v for k, v in cfg_dict.items() if k in KattappaConfig.__dataclass_fields__})
        model = KattappaModel(cfg).to(self.device)
        model.load_state_dict(state["model_state_dict"])
        model.eval()

        # ── EvalHarness run ───────────────────────────────────────────────────
        eval_report = self.harness.run(model, tokenizer=None, dataset=eval_dataset)

        # ── Safety run ────────────────────────────────────────────────────────
        safety_report = self.safety.run_suite(safety_texts or [])

        # ── Signal determination ──────────────────────────────────────────────
        signal = RegressionSignal.PASS
        perplexity_delta: Optional[float] = None

        if not safety_report.all_passed:
            signal = RegressionSignal.FAIL
            notes.append(f"Safety failures: {[p.name for p in safety_report.probes if not p.passed]}")

        if baseline_perplexity is not None:
            perplexity_delta = (eval_report.perplexity - baseline_perplexity) / baseline_perplexity
            if perplexity_delta > self.perplexity_tolerance:
                signal = RegressionSignal.REGRESSION
                notes.append(
                    f"Perplexity regression: {eval_report.perplexity:.4f} vs baseline "
                    f"{baseline_perplexity:.4f} (+{perplexity_delta * 100:.2f}%)"
                )

        return RegressionResult(
            signal=signal,
            checkpoint_path=str(path),
            eval_report=eval_report,
            safety_report=safety_report,
            baseline_perplexity=baseline_perplexity,
            perplexity_delta=perplexity_delta,
            notes=notes,
        )
