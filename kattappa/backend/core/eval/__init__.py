"""Kattappa Alignment & Evaluation package (Program 27E)."""
from __future__ import annotations

from backend.core.eval.eval_harness import EvalHarness, EvalReport
from backend.core.eval.preference_builder import PreferenceBuilder, PreferencePair
from backend.core.eval.safety_eval import SafetyEval, SafetyReport
from backend.core.eval.dpo_trainer import DPOTrainer, DPOConfig, dpo_loss
from backend.core.eval.regression_runner import RegressionRunner, RegressionResult, RegressionSignal
from backend.core.eval.model_promoter import ModelPromoter

__all__ = [
    "EvalHarness", "EvalReport",
    "PreferenceBuilder", "PreferencePair",
    "SafetyEval", "SafetyReport",
    "DPOTrainer", "DPOConfig", "dpo_loss",
    "RegressionRunner", "RegressionResult", "RegressionSignal",
    "ModelPromoter",
]
