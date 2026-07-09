"""Research Ledger (Program 29.0).

Maintains a persistent, thread-safe record of hypotheses, experimental parameter
overrides, test metrics, and promotion/rollback outcomes.
"""
from __future__ import annotations

import json
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from backend.core.config import runtime_data_root


def _ledger_dir() -> Path:
    p = runtime_data_root() / "backend" / "data" / "research"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _ledger_path() -> Path:
    return _ledger_dir() / "research_ledger.json"


@dataclass
class ExperimentRecord:
    """Dataclass capturing a single self-improvement experiment run."""

    experiment_id: str
    hypothesis: str
    parameters: Dict[str, Any]
    status: str = "pending"  # "pending", "running", "completed", "rolled_back"
    baseline_metrics: Dict[str, Any] = field(default_factory=dict)
    experimental_metrics: Dict[str, Any] = field(default_factory=dict)
    verdict: str = "undecided"  # "undecided", "promoted", "rejected"
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ExperimentRecord:
        return cls(**data)


class ResearchLedger:
    """Thread-safe persistent ledger manager for self-improvement experiments."""

    _lock = threading.RLock()

    def __init__(self, storage_dir: Optional[str | Path] = None) -> None:
        self.storage_dir = Path(storage_dir) if storage_dir else _ledger_dir()
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.ledger_file = self.storage_dir / "research_ledger.json"

    def _load_ledger(self) -> Dict[str, Any]:
        if not self.ledger_file.exists():
            return {"experiments": []}
        try:
            with self.ledger_file.open(encoding="utf-8") as fh:
                return json.load(fh)
        except json.JSONDecodeError:
            return {"experiments": []}

    def _save_ledger(self, data: Dict[str, Any]) -> None:
        with self.ledger_file.open("w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)

    # ── APIs ──────────────────────────────────────────────────────────────────

    def register_experiment(
        self,
        hypothesis: str,
        parameters: Dict[str, Any],
        baseline_metrics: Dict[str, Any],
    ) -> ExperimentRecord:
        """Adds a new experiment record to the registry database."""
        with self._lock:
            ledger = self._load_ledger()
            exp_id = f"exp_{int(time.time())}_{len(ledger['experiments'])}"
            record = ExperimentRecord(
                experiment_id=exp_id,
                hypothesis=hypothesis,
                parameters=parameters,
                baseline_metrics=baseline_metrics,
            )
            ledger["experiments"].append(record.to_dict())
            self._save_ledger(ledger)
            return record

    def update_experiment(
        self,
        experiment_id: str,
        experimental_metrics: Optional[Dict[str, Any]] = None,
        status: Optional[str] = None,
        verdict: Optional[str] = None,
    ) -> Optional[ExperimentRecord]:
        """Updates metrics and state targets on a registered experiment."""
        with self._lock:
            ledger = self._load_ledger()
            for exp in ledger["experiments"]:
                if exp["experiment_id"] == experiment_id:
                    if experimental_metrics is not None:
                        exp["experimental_metrics"] = experimental_metrics
                    if status is not None:
                        exp["status"] = status
                    if verdict is not None:
                        exp["verdict"] = verdict

                    self._save_ledger(ledger)
                    return ExperimentRecord.from_dict(exp)
            return None

    def get_experiment(self, experiment_id: str) -> Optional[ExperimentRecord]:
        """Retrieves a single experiment run by ID."""
        with self._lock:
            ledger = self._load_ledger()
            for exp in ledger["experiments"]:
                if exp["experiment_id"] == experiment_id:
                    return ExperimentRecord.from_dict(exp)
            return None

    def list_experiments(self) -> List[ExperimentRecord]:
        """Returns all registered experiments."""
        with self._lock:
            ledger = self._load_ledger()
            return [ExperimentRecord.from_dict(exp) for exp in ledger["experiments"]]
