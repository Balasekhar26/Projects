from __future__ import annotations
from typing import Any, Dict, Optional
from backend.adapters.action_interface import ActionAdapter
from backend.adapters.calendar_adapter import CalendarAdapter
from backend.adapters.notification_adapter import NotificationAdapter
from backend.adapters.filesystem_adapter import FilesystemAdapter

class AdapterRegistry:
    """Manages the catalogue and hot-swappable discovery of action adapters."""

    def __init__(self) -> None:
        self.adapters: Dict[str, ActionAdapter] = {
            "calendar": CalendarAdapter(),
            "filesystem": FilesystemAdapter(),
            "notification": NotificationAdapter()
        }

    def get(self, name: str) -> Optional[ActionAdapter]:
        return self.adapters.get(name)

    def list_adapters(self) -> Dict[str, list[str]]:
        return {k: v.capabilities() for k, v in self.adapters.items()}

# Global single instance representing registry mapping context
REGISTRY = AdapterRegistry()
