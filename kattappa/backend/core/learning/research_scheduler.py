"""Research Scheduler (Program 29.0).

Coordinates the self-improvement research cycle: parses failure analytics,
proposes hypothese, registers experiments, runs tests, and applies updates.
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Dict, Optional

from backend.core.learning.research_ledger import ResearchLedger
from backend.core.learning.hypothesis_generator import HypothesisGenerator
from backend.core.learning.experiment_manager import ExperimentManager

logger = logging.getLogger(__name__)


class ResearchScheduler:
    """Orchestrates continuous autonomous improvement cycles for Kattappa."""

    def __init__(
        self,
        ledger: Optional[ResearchLedger] = None,
        generator: Optional[HypothesisGenerator] = None,
        manager: Optional[ExperimentManager] = None,
    ) -> None:
        self.ledger = ledger or ResearchLedger()
        self.generator = generator or HypothesisGenerator()
        self.manager = manager or ExperimentManager()

    def run_cycle(
        self,
        config_object: Any,
        analytics: Dict[str, Any],
        evaluation_fn: Callable[[], float],
        baseline_score: float,
    ) -> Optional[str]:
        """Runs a complete improvement iteration.

        1. Proposes parameter updates from failure logs.
        2. Selects first valid hypothesis.
        3. Registers experiment details in the persistent ledger.
        4. Triggers controlled test evaluations.
        5. Logs final execution promotion/rejection verdict.

        Returns:
            experiment_id of the executed run, or None if no hypotheses generated.
        """
        # 1. Propose hypothese from failure metrics
        hypotheses = self.generator.propose_hypotheses(analytics)
        if not hypotheses:
            logger.info("No optimization hypotheses generated from recent logs.")
            return None

        # Select first proposed candidate
        selected = hypotheses[0]
        hypothesis = selected["hypothesis"]
        parameters = selected["parameters"]

        # 2. Register experiment in ledger
        record = self.ledger.register_experiment(
            hypothesis=hypothesis,
            parameters=parameters,
            baseline_metrics={"score": baseline_score},
        )
        exp_id = record.experiment_id

        # Update status to running
        self.ledger.update_experiment(exp_id, status="running")

        # 3. Trigger experiment run
        result = self.manager.run_experiment(
            config_object=config_object,
            parameters=parameters,
            evaluation_fn=evaluation_fn,
            revert_on_failure=True,
            baseline_score=baseline_score,
        )

        # 4. Record outcome and verdict
        status = "completed" if result["success"] else "rolled_back"
        if result["verdict"] == "rejected":
            status = "rolled_back"

        self.ledger.update_experiment(
            experiment_id=exp_id,
            experimental_metrics={"score": result["score"], "error": result["error"]},
            status=status,
            verdict=result["verdict"],
        )

        return exp_id
