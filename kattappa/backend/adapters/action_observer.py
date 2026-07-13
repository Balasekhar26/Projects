from __future__ import annotations
from typing import Any, Dict
from backend.adapters.action_interface import ActionResult

class ActionObserver:
    """Listens to adapter execution signals and reflects consequences into WorldState."""

    @staticmethod
    def observe(
        action_name: str,
        result: ActionResult,
        world_state: Any
    ) -> None:
        """Translates external result side-effects into the living universe snapshot."""
        if not result.success:
            return

        # 1. Update calendar slots upon successful reserve events
        if action_name == "create_meeting":
            slot = result.data.get("slot", "")
            if slot and slot not in world_state.calendar_busy_slots:
                world_state.calendar_busy_slots.append(slot)

        # 2. Update reminders list upon successful notification scheduling
        elif action_name == "schedule_notification":
            reminder_id = result.data.get("time", "now")
            world_state.pending_reminders.append({
                "id": reminder_id,
                "msg": result.data.get("message", "Reminder")
            })
