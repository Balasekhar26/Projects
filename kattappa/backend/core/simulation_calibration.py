from __future__ import annotations

import json
import sqlite3
import threading
import time
from typing import Any, Dict, List, Optional

from backend.core.config import load_config, runtime_data_root
from backend.core.logger import log_event


def _weights_path() -> Path:
    from pathlib import Path
    return runtime_data_root() / "backend" / "data" / "simulation_calibration_weights.json"


class SimulationCalibrator:
    """Simulation Calibrator Subsystem (Layer 8 - Step 8.2).

    Compares simulation predictions against actual outcomes to compute scaling
    calibration factors for success probability, execution duration, and rollback risk.
    """

    _lock = threading.RLock()
    _schema_ensured = False
    _cached_weights: Dict[str, Dict[str, float]] = {}

    @classmethod
    def _get_sqlite_conn(cls) -> sqlite3.Connection:
        config = load_config()
        config.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(config.sqlite_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA foreign_keys = ON")
        with cls._lock:
            if not cls._schema_ensured:
                cls._ensure_schema(conn)
                cls._schema_ensured = True
        return conn

    @classmethod
    def _ensure_schema(cls, conn: sqlite3.Connection) -> None:
        with cls._lock:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS hm_simulation_calibration_records (
                    id TEXT PRIMARY KEY,
                    agent TEXT NOT NULL,
                    action TEXT NOT NULL,
                    predicted_success REAL NOT NULL,
                    actual_success BOOLEAN NOT NULL,
                    predicted_duration_ms INTEGER NOT NULL,
                    actual_duration_ms INTEGER NOT NULL,
                    predicted_rollback REAL NOT NULL,
                    actual_rollback BOOLEAN NOT NULL,
                    timestamp REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_sim_cal_agent_action ON hm_simulation_calibration_records(agent, action);
                """
            )
            conn.commit()

    @classmethod
    def record_prediction_outcome(
        cls,
        agent: str,
        action: str,
        predicted_success: float,
        actual_success: bool,
        predicted_duration_ms: int,
        actual_duration_ms: int,
        predicted_rollback: float,
        actual_rollback: bool,
    ) -> None:
        """Records a single prediction-outcome observation for calibration auditing."""
        import uuid
        now = time.time()
        record_id = str(uuid.uuid4())
        with cls._lock:
            conn = cls._get_sqlite_conn()
            try:
                conn.execute(
                    """
                    INSERT INTO hm_simulation_calibration_records (
                        id, agent, action, predicted_success, actual_success,
                        predicted_duration_ms, actual_duration_ms, predicted_rollback, actual_rollback, timestamp
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        record_id,
                        agent.lower().strip(),
                        action.upper().strip(),
                        max(0.0, min(1.0, predicted_success)),
                        1 if actual_success else 0,
                        max(0, predicted_duration_ms),
                        max(0, actual_duration_ms),
                        max(0.0, min(1.0, predicted_rollback)),
                        1 if actual_rollback else 0,
                        now,
                    )
                )
                conn.commit()
            except Exception as e:
                conn.rollback()
                raise e
            finally:
                conn.close()

    @classmethod
    def recalibrate(cls) -> Dict[str, Any]:
        """Runs the calibration computation and updates the saved weights ledger."""
        with cls._lock:
            conn = cls._get_sqlite_conn()
            try:
                rows = conn.execute("SELECT * FROM hm_simulation_calibration_records").fetchall()
            finally:
                conn.close()

            if not rows:
                return {"status": "no_data", "count": 0}

            # Group entries by (agent, action)
            grouped: Dict[tuple[str, str], List[dict]] = {}
            for r in rows:
                key = (r["agent"], r["action"])
                grouped.setdefault(key, []).append(dict(r))

            new_weights: Dict[str, Dict[str, float]] = {}
            for (agent, action), entries in grouped.items():
                pred_succ = [e["predicted_success"] for e in entries]
                act_succ = [float(e["actual_success"]) for e in entries]
                pred_dur = [float(e["predicted_duration_ms"]) for e in entries]
                act_dur = [float(e["actual_duration_ms"]) for e in entries]
                pred_roll = [e["predicted_rollback"] for e in entries]
                act_roll = [float(e["actual_rollback"]) for e in entries]

                avg_pred_succ = sum(pred_succ) / len(pred_succ)
                avg_act_succ = sum(act_succ) / len(act_succ)
                avg_pred_dur = sum(pred_dur) / len(pred_dur)
                avg_act_dur = sum(act_dur) / len(act_dur)
                avg_pred_roll = sum(pred_roll) / len(pred_roll)
                avg_act_roll = sum(act_roll) / len(act_roll)

                # Compute calibration ratio: actual / predicted (clamped between 0.1 and 2.0 to avoid spikes)
                success_factor = avg_act_succ / avg_pred_succ if avg_pred_succ > 0 else 1.0
                duration_factor = avg_act_dur / avg_pred_dur if avg_pred_dur > 0 else 1.0
                rollback_factor = avg_act_roll / avg_pred_roll if avg_pred_roll > 0 else 1.0

                key_str = f"{agent}:{action}"
                new_weights[key_str] = {
                    "success_factor": max(0.1, min(2.0, success_factor)),
                    "duration_factor": max(0.1, min(2.0, duration_factor)),
                    "rollback_factor": max(0.1, min(2.0, rollback_factor)),
                }

            # Compute Brier calibration score
            # Brier Score = 1/N * sum((predicted - actual)^2)
            squared_errors = []
            for r in rows:
                se = (r["predicted_success"] - float(r["actual_success"])) ** 2
                squared_errors.append(se)
            brier_score = sum(squared_errors) / len(squared_errors) if squared_errors else 0.0

            cls._cached_weights = new_weights
            cls._save_weights_to_file(new_weights)
            log_event("simulation_calibration", {"records_calibrated": len(rows), "brier_score": brier_score})

            return {
                "status": "success",
                "count": len(rows),
                "brier_score": round(brier_score, 4),
                "weights": new_weights,
            }

    @classmethod
    def get_calibration_factor(cls, agent: str, action: str) -> float:
        """Returns the success probability calibration scaling factor for a specific agent and action."""
        weights = cls.get_all_weights()
        key = f"{agent.lower().strip()}:{action.upper().strip()}"
        if key in weights:
            return weights[key].get("success_factor", 1.0)
        # Check agent-only wildcard fallback
        agent_wildcard = f"{agent.lower().strip()}:*"
        if agent_wildcard in weights:
            return weights[agent_wildcard].get("success_factor", 1.0)
        return 1.0

    @classmethod
    def get_duration_calibration_factor(cls, agent: str, action: str) -> float:
        """Returns the duration calibration scaling factor for a specific agent and action."""
        weights = cls.get_all_weights()
        key = f"{agent.lower().strip()}:{action.upper().strip()}"
        if key in weights:
            return weights[key].get("duration_factor", 1.0)
        return 1.0

    @classmethod
    def get_rollback_calibration_factor(cls, agent: str, action: str) -> float:
        """Returns the rollback risk calibration scaling factor for a specific agent and action."""
        weights = cls.get_all_weights()
        key = f"{agent.lower().strip()}:{action.upper().strip()}"
        if key in weights:
            return weights[key].get("rollback_factor", 1.0)
        return 1.0

    @classmethod
    def get_all_weights(cls) -> Dict[str, Dict[str, float]]:
        """Loads and returns all active calibration weights."""
        with cls._lock:
            if cls._cached_weights:
                return cls._cached_weights
            path = _weights_path()
            if not path.exists():
                return {}
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                cls._cached_weights = data
                return data
            except Exception:
                return {}

    @classmethod
    def _save_weights_to_file(cls, weights: Dict[str, Dict[str, float]]) -> None:
        path = _weights_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(weights, indent=2), encoding="utf-8")
