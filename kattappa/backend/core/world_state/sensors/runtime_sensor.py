from __future__ import annotations
import os
from backend.core.world_state.sensors.base_sensor import BaseSensor

class RuntimeSensor(BaseSensor):
    def collect(self) -> dict:
        active_count = 0
        try:
            from backend.core.goal_memory import GoalMemory
            db = GoalMemory._get_conn()
            cursor = db.cursor()
            cursor.execute("SELECT COUNT(*) FROM goals WHERE status = 'ACTIVE'")
            row = cursor.fetchone()
            if row:
                active_count = row[0]
        except Exception:
            pass
            
        return {
            "runtime": {
                "active_tasks": active_count,
                "queued_tasks": 0,
                "failed_tasks": 0,
                "agent_health": "NOMINAL"
            },
            "user_context": {
                "preferred_language": "Telugu",
                "preferred_voice": "Kattappa_Male_v1",
                "interaction_mode": "text"
            }
        }
