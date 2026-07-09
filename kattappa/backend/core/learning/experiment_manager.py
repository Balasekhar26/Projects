"""Experiment Manager (Program 29.0).

Executes testing runs under temporary configuration parameter overrides,
comparing outcomes against baselines.
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Dict, Optional

from backend.core.learning.rollback_engine import RollbackEngine

logger = logging.getLogger(__name__)


class ExperimentManager:
    """Orchestrates controlled updates and evaluations under parameter overrides."""

    def __init__(self, rollback_engine: Optional[RollbackEngine] = None) -> None:
        self.rollback = rollback_engine or RollbackEngine()

    def run_experiment(
        self,
        config_object: Any,
        parameters: Dict[str, Any],
        evaluation_fn: Callable[[], float],
        revert_on_failure: bool = True,
        baseline_score: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Applies temporary overrides, runs validation check, and computes performance.

        Args:
            config_object:     Configuration target (dict or object with attributes).
            parameters:        Dict of key-value parameters to apply.
            evaluation_fn:     Callable computing metric score (e.g. lower is better).
            revert_on_failure: Revert to baseline configuration if metric regresses.
            baseline_score:    Prior baseline score to compare against.

        Returns:
            Dict containing experiment result status, scores, and promotion verdict.
        """
        # 1. Backup baseline state
        state_id = self.rollback.backup_state(config_object)

        # 2. Apply parameter overrides
        for k, v in parameters.items():
            if isinstance(config_object, dict):
                config_object[k] = v
            elif hasattr(config_object, "__dict__"):
                setattr(config_object, k, v)

        # 3. Execute evaluation run
        try:
            exp_score = evaluation_fn()
            success = True
            error_msg = ""
        except Exception as e:
            exp_score = float("inf")
            success = False
            error_msg = str(e)
            logger.error(f"Experiment execution failed: {e}")

        # 4. Compare results
        promoted = False
        if success and baseline_score is not None:
            # Assumes lower score is better (e.g. perplexity, error rate)
            if exp_score < baseline_score:
                promoted = True

        # 5. Handle rollback or promotion
        if not promoted and revert_on_failure:
            self.rollback.restore_state(config_object, state_id)
            verdict = "rejected"
        else:
            verdict = "promoted" if promoted else "undecided"

        # Clean backup snapshot
        self.rollback.clean_backup(state_id)

        return {
            "success": success,
            "score": exp_score,
            "verdict": verdict,
            "error": error_msg,
        }
