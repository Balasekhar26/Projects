"""Experiment Runner — Phase K12.

Lightweight hypothesis testing substrate. Executes sandboxed evaluation trials
for learning hypotheses proposed during reflection, and publishes results to
the Cognitive Blackboard.
"""
from __future__ import annotations

import random
import time
from dataclasses import dataclass
from typing import Any, Dict

from backend.core.logger import log_event
from backend.core.blackboard import BLACKBOARD


@dataclass
class ExperimentResult:
    hypothesis_id: str
    confirmed: bool
    trials_run: int
    success_rate: float
    metric_delta: float
    timestamp: float


class ExperimentRunner:
    """Runs lightweight evaluation tests for reflection hypotheses."""

    @classmethod
    def run_experiment(cls, hypothesis: Dict[str, Any]) -> ExperimentResult:
        """Simulates or runs verification trials for a given hypothesis.

        Parameters
        ----------
        hypothesis : Dict[str, Any]
            The hypothesis proposed by reflection (requires statement, domain, confidence).
        """
        hyp_id = hypothesis.get("id") or "hyp-unknown"
        statement = hypothesis.get("statement") or ""
        domain = hypothesis.get("domain") or "general"
        confidence = hypothesis.get("confidence") or 0.5

        log_event("experiment_start", f"Running experiment for hypothesis {hyp_id}: {statement!r}")

        # Lightweight verification check
        # In a real system, this runs a benchmark or queries a test suite.
        # Here we simulate trials: high initial confidence increases chance of confirmation.
        trials = 5
        successes = 0
        for _ in range(trials):
            # Base probability is linked to hypothesis confidence + random jitter
            prob = min(0.95, max(0.1, confidence + random.uniform(-0.15, 0.15)))
            if random.random() < prob:
                successes += 1

        success_rate = successes / trials
        # Confirm hypothesis if success rate is >= 70%
        confirmed = success_rate >= 0.70
        metric_delta = round((success_rate - 0.5) * 20.0, 2)  # simulated percentage change

        result = ExperimentResult(
            hypothesis_id=hyp_id,
            confirmed=confirmed,
            trials_run=trials,
            success_rate=success_rate,
            metric_delta=metric_delta,
            timestamp=time.time(),
        )

        # Publish experiment result to Blackboard
        try:
            BLACKBOARD.publish(
                publisher="experiment_runner",
                topic="experiment_result",
                payload={
                    "hypothesis_id": result.hypothesis_id,
                    "confirmed": result.confirmed,
                    "trials_run": result.trials_run,
                    "success_rate": result.success_rate,
                    "metric_delta": result.metric_delta,
                },
                confidence=0.9,
            )
        except Exception as e:
            log_event("experiment_blackboard_error", f"Failed to publish experiment to blackboard: {e}")

        log_event(
            "experiment_complete",
            f"Finished trials for {hyp_id} | confirmed={confirmed} (rate={success_rate:.2f})",
        )
        return result
