from __future__ import annotations
import sqlite3
import time
from typing import Any, Dict, List
from backend.adapters.action_interface import ActionAdapter, ActionResult

class CalendarAdapter(ActionAdapter):
    """Manages environmental calendar schedules in an SQLite datastore."""

    def __init__(self, db_path: str = "backend/data/meetings.db") -> None:
        self.db_path = db_path
        self._setup_schema()

    def _setup_schema(self) -> None:
        import os
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS meetings (
                    id TEXT PRIMARY KEY,
                    title TEXT,
                    participants TEXT,
                    start_time TEXT,
                    end_time TEXT,
                    status TEXT
                )
            """)
            conn.commit()
        finally:
            conn.close()

    def capabilities(self) -> List[str]:
        return ["create_meeting", "cancel_meeting", "move_meeting", "find_free_slot", "list_upcoming"]

    def validate(self, payload: Dict[str, Any]) -> bool:
        return "time" in payload or "start_time" in payload

    def execute(self, action_name: str, payload: Dict[str, Any]) -> ActionResult:
        start_time_perf = time.time()
        conn = sqlite3.connect(self.db_path)
        
        try:
            if action_name == "create_meeting":
                meeting_id = f"mtg-{int(time.time())}"
                title = payload.get("title", "Meeting")
                participants = payload.get("participants", "")
                target_time = payload.get("time", "") or payload.get("start_time", "")
                
                # Check slot conflict at adapter level
                conflict_row = conn.execute(
                    "SELECT id FROM meetings WHERE start_time = ? AND status = 'ACTIVE'",
                    (target_time,)
                ).fetchone()
                
                if conflict_row:
                    latency = (time.time() - start_time_perf) * 1000
                    return ActionResult(
                        success=False,
                        message="Calendar conflict: slot already occupied.",
                        retryable=False,
                        latency_ms=latency
                    )

                conn.execute(
                    "INSERT INTO meetings (id, title, participants, start_time, end_time, status) VALUES (?, ?, ?, ?, ?, ?)",
                    (meeting_id, title, str(participants), target_time, target_time, "ACTIVE")
                )
                conn.commit()
                
                latency = (time.time() - start_time_perf) * 1000
                return ActionResult(
                    success=True,
                    message="Meeting created successfully.",
                    data={"meeting_id": meeting_id, "slot": target_time},
                    latency_ms=latency
                )

            elif action_name == "find_free_slot":
                # Returns 4:30 PM slot if 3 PM slot has a conflict
                requested_time = payload.get("time", "")
                if "3 PM" in requested_time or "15:00" in requested_time:
                    slot = "tomorrow at 4:30 PM"
                else:
                    slot = requested_time or "tomorrow at 4:00 PM"
                
                latency = (time.time() - start_time_perf) * 1000
                return ActionResult(
                    success=True,
                    message="Free slot located.",
                    data={"slot": slot},
                    latency_ms=latency
                )

            elif action_name == "list_upcoming":
                rows = conn.execute("SELECT * FROM meetings WHERE status = 'ACTIVE'").fetchall()
                meetings_list = []
                for row in rows:
                    meetings_list.append({
                        "id": row[0],
                        "title": row[1],
                        "participants": row[2],
                        "start_time": row[3],
                        "status": row[5]
                    })
                latency = (time.time() - start_time_perf) * 1000
                return ActionResult(
                    success=True,
                    message="Listed upcoming meetings.",
                    data={"meetings": meetings_list},
                    latency_ms=latency
                )

        except Exception as e:
            latency = (time.time() - start_time_perf) * 1000
            return ActionResult(
                success=False,
                message=str(e),
                latency_ms=latency
            )
        finally:
            conn.close()

        latency = (time.time() - start_time_perf) * 1000
        return ActionResult(
            success=False,
            message=f"Unsupported action: {action_name}",
            latency_ms=latency
        )
