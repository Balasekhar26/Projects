from __future__ import annotations
import json
import time
import uuid
from pathlib import Path
from typing import Any, Dict
from backend.tools.base_tool import Tool, ToolResult
from backend.runtime.execution_context import ExecutionContext

class ReminderTool(Tool):
    """Schedules reminders and persists state in backend/data/reminders.json."""
    name = "reminder_tool"

    def __init__(self) -> None:
        self.db_path = Path("backend/data/reminders.json")
        self._ensure_db()

    def _ensure_db(self) -> None:
        if not self.db_path.exists():
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.db_path, "w") as f:
                json.dump([], f)

    def _load_reminders(self) -> list:
        try:
            with open(self.db_path, "r") as f:
                return json.load(f)
        except Exception:
            return []

    def _save_reminders(self, reminders: list) -> None:
        try:
            with open(self.db_path, "w") as f:
                json.dump(reminders, f, indent=2)
        except Exception:
            pass

    def execute(
        self,
        parameters: Dict[str, Any],
        context: ExecutionContext
    ) -> ToolResult:
        start_time = time.time()
        reminder_id = f"rem-{uuid.uuid4().hex[:6]}"
        reminders = self._load_reminders()

        new_reminder = {
            "id": reminder_id,
            "time": parameters.get("time", "tomorrow 5pm"),
            "message": parameters.get("message", "Reminder"),
            "created_at": time.time()
        }
        reminders.append(new_reminder)
        self._save_reminders(reminders)

        latency = (time.time() - start_time) * 1000
        return ToolResult(
            success=True,
            confidence=0.99,
            latency_ms=latency,
            output={"reminder_id": reminder_id, "status": "SCHEDULED", "reminder": new_reminder},
            error=None,
            artifact_ids=[reminder_id]
        )
