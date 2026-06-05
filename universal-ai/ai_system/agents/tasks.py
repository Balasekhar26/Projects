from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from ai_system.core.config import load_settings


@dataclass
class TaskStep:
    title: str
    status: str = "pending"
    result: str = ""


@dataclass
class TaskRun:
    id: str
    goal: str
    created_at: str
    status: str = "planned"
    steps: list[TaskStep] = field(default_factory=list)
    final_answer: str = ""


class TaskStore:
    def __init__(self) -> None:
        self.dir = load_settings().root / "workflows" / "runs"
        self.dir.mkdir(parents=True, exist_ok=True)

    def save(self, run: TaskRun) -> Path:
        path = self.dir / f"{run.id}.json"
        payload = asdict(run)
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")
        return path

    def create(self, goal: str, steps: list[str]) -> TaskRun:
        run = TaskRun(
            id=str(uuid4()),
            goal=goal,
            created_at=datetime.now(timezone.utc).isoformat(),
            steps=[TaskStep(title=step) for step in steps],
        )
        self.save(run)
        return run

    def latest(self, limit: int = 10) -> list[TaskRun]:
        runs: list[TaskRun] = []
        for path in sorted(self.dir.glob("*.json"), reverse=True)[:limit]:
            data = json.loads(path.read_text(encoding="utf-8"))
            data["steps"] = [TaskStep(**step) for step in data.get("steps", [])]
            runs.append(TaskRun(**data))
        return runs
