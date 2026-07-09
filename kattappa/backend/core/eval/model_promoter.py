"""Automatic Model Promoter (Program 27E6).

Reads a RegressionResult and promotes the checkpoint to active production
status iff every safety probe passes and no metric regresses beyond threshold.
Integrates with TokenizerRegistry-style versioned JSON storage.
"""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from backend.core.eval.regression_runner import RegressionResult, RegressionSignal


def _registry_path(storage_dir: Path) -> Path:
    return storage_dir / "model_registry.json"


class ModelPromoter:
    """Promotes or rejects model checkpoints based on regression evaluation results."""

    _lock = threading.RLock()

    def __init__(self, storage_dir: str | Path = "backend/data/models") -> None:
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    # ── Registry helpers ──────────────────────────────────────────────────────

    def _load_registry(self) -> Dict[str, Any]:
        path = _registry_path(self.storage_dir)
        if not path.exists():
            return {"versions": [], "active": None}
        with path.open(encoding="utf-8") as fh:
            return json.load(fh)

    def _save_registry(self, data: Dict[str, Any]) -> None:
        path = _registry_path(self.storage_dir)
        with path.open("w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)

    # ── Core promotion logic ──────────────────────────────────────────────────

    def evaluate_and_promote(self, result: RegressionResult) -> bool:
        """Promotes the checkpoint if the regression result is PASS.

        Returns True if promoted, False if rejected.
        """
        if result.signal != RegressionSignal.PASS:
            self._record(result, promoted=False)
            return False

        with self._lock:
            registry = self._load_registry()
            entry = {
                "checkpoint_path": result.checkpoint_path,
                "timestamp": time.time(),
                "perplexity": result.eval_report.perplexity,
                "safety_pass_rate": result.safety_report.pass_rate,
                "signal": result.signal.value,
                "promoted": True,
            }
            registry["versions"].append(entry)
            registry["active"] = result.checkpoint_path
            self._save_registry(registry)

        return True

    def get_active(self) -> Optional[str]:
        """Returns the path of the currently active (promoted) checkpoint."""
        return self._load_registry().get("active")

    def list_versions(self) -> List[Dict[str, Any]]:
        """Returns all recorded checkpoint versions."""
        return self._load_registry().get("versions", [])

    def _record(self, result: RegressionResult, promoted: bool) -> None:
        """Records a rejected evaluation without promoting."""
        with self._lock:
            registry = self._load_registry()
            entry = {
                "checkpoint_path": result.checkpoint_path,
                "timestamp": time.time(),
                "perplexity": result.eval_report.perplexity,
                "safety_pass_rate": result.safety_report.pass_rate,
                "signal": result.signal.value,
                "promoted": promoted,
                "notes": result.notes,
            }
            registry["versions"].append(entry)
            self._save_registry(registry)
