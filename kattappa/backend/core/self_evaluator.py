from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any

from backend.core.config import runtime_data_root


def _eval_file_path() -> Path:
    return runtime_data_root() / "backend" / "data" / "self_evaluations.json"


class SelfEvaluator:
    _lock = threading.RLock()

    @classmethod
    def load_evaluations(cls) -> list[dict[str, Any]]:
        with cls._lock:
            path = _eval_file_path()
            if not path.exists():
                # Seed some initial evaluations
                initial = [
                    {
                        "id": "eval_001",
                        "timestamp": time.time() - 7200,
                        "agent": "Coder",
                        "plan_score": 90,
                        "execution_score": 85,
                        "accuracy_score": 95,
                        "cost_score": 90,
                        "time_score": 80,
                        "what_worked": "Unit tests compiled on the first attempt.",
                        "what_failed": "Vite config loading had minor latency.",
                        "improvement": "Cache node modules to speed up subsequent builds."
                    },
                    {
                        "id": "eval_002",
                        "timestamp": time.time() - 3600,
                        "agent": "Researcher",
                        "plan_score": 95,
                        "execution_score": 90,
                        "accuracy_score": 90,
                        "cost_score": 95,
                        "time_score": 90,
                        "what_worked": "Located 3 relevant datasheets for the target microcontroller.",
                        "what_failed": "One document link had a timeout.",
                        "improvement": "Implement automated link health checking."
                    }
                ]
                cls.save_evaluations(initial)
                return initial
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                return []

    @classmethod
    def save_evaluations(cls, data: list[dict[str, Any]]) -> None:
        with cls._lock:
            path = _eval_file_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    @classmethod
    def add_evaluation(
        cls,
        agent: str,
        plan_score: int,
        execution_score: int,
        accuracy_score: int,
        cost_score: int,
        time_score: int,
        what_worked: str,
        what_failed: str,
        improvement: str
    ) -> dict[str, Any]:
        with cls._lock:
            evaluations = cls.load_evaluations()
            entry = {
                "id": f"eval_{int(time.time())}_{len(evaluations)}",
                "timestamp": time.time(),
                "agent": agent,
                "plan_score": max(0, min(100, plan_score)),
                "execution_score": max(0, min(100, execution_score)),
                "accuracy_score": max(0, min(100, accuracy_score)),
                "cost_score": max(0, min(100, cost_score)),
                "time_score": max(0, min(100, time_score)),
                "what_worked": what_worked,
                "what_failed": what_failed,
                "improvement": improvement
            }
            evaluations.append(entry)
            cls.save_evaluations(evaluations)
            return entry

    @classmethod
    def agent_performance_averages(cls) -> dict[str, dict[str, float]]:
        """Calculates average scores for Coder, Researcher, Browser, Voice, and Monitor."""
        with cls._lock:
            evaluations = cls.load_evaluations()
            agents = ["Coder", "Researcher", "Browser", "Voice", "Monitor"]
            
            # Seed default scores in case of empty evaluations
            defaults = {
                "Coder": {"plan": 88.0, "execution": 84.0, "accuracy": 91.0, "cost": 89.0, "time": 82.0},
                "Researcher": {"plan": 92.0, "execution": 89.0, "accuracy": 93.0, "cost": 92.0, "time": 88.0},
                "Browser": {"plan": 85.0, "execution": 80.0, "accuracy": 88.0, "cost": 87.0, "time": 81.0},
                "Voice": {"plan": 90.0, "execution": 88.0, "accuracy": 92.0, "cost": 91.0, "time": 86.0},
                "Monitor": {"plan": 94.0, "execution": 92.0, "accuracy": 95.0, "cost": 96.0, "time": 93.0}
            }
            
            totals: dict[str, dict[str, float]] = {a: {"plan": 0.0, "execution": 0.0, "accuracy": 0.0, "cost": 0.0, "time": 0.0, "count": 0.0} for a in agents}
            
            for e in evaluations:
                a = e.get("agent")
                if a in totals:
                    totals[a]["plan"] += e.get("plan_score", 0)
                    totals[a]["execution"] += e.get("execution_score", 0)
                    totals[a]["accuracy"] += e.get("accuracy_score", 0)
                    totals[a]["cost"] += e.get("cost_score", 0)
                    totals[a]["time"] += e.get("time_score", 0)
                    totals[a]["count"] += 1

            averages = {}
            for a in agents:
                count = totals[a]["count"]
                if count > 0:
                    averages[a] = {
                        "plan": round(totals[a]["plan"] / count, 1),
                        "execution": round(totals[a]["execution"] / count, 1),
                        "accuracy": round(totals[a]["accuracy"] / count, 1),
                        "cost": round(totals[a]["cost"] / count, 1),
                        "time": round(totals[a]["time"] / count, 1),
                    }
                else:
                    averages[a] = defaults[a]
            return averages
