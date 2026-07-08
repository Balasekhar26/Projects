from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any
from backend.core.ledger.models.event import LedgerEvent
from backend.core.ledger.models.snapshot import LedgerSnapshot


class LedgerStore(ABC):
    @abstractmethod
    def append(self, event: LedgerEvent) -> None:
        """Appends an event to the ledger store immutably."""
        pass

    @abstractmethod
    def get(self, event_id: str) -> Optional[LedgerEvent]:
        """Retrieves an event by its unique ID."""
        pass

    @abstractmethod
    def children(self, event_id: str) -> List[LedgerEvent]:
        """Retrieves all events referencing the target event as a parent."""
        pass

    @abstractmethod
    def parents(self, event_id: str) -> List[LedgerEvent]:
        """Retrieves all parent events for the target event."""
        pass

    @abstractmethod
    def ancestors(self, event_id: str) -> List[LedgerEvent]:
        """Retrieves all direct and indirect ancestors of the target event (ordered oldest to newest)."""
        pass

    @abstractmethod
    def descendants(self, event_id: str) -> List[LedgerEvent]:
        """Retrieves all direct and indirect descendants of the target event (ordered oldest to newest)."""
        pass

    @abstractmethod
    def query(self, filters: Dict[str, Any]) -> List[LedgerEvent]:
        """Queries events matching specific key-value filters (e.g. goal_id, subsystem)."""
        pass

    @abstractmethod
    def save_snapshot(self, snapshot: LedgerSnapshot) -> None:
        """Saves a state snapshot for a goal."""
        pass

    @abstractmethod
    def get_latest_snapshot(self, goal_id: str) -> Optional[LedgerSnapshot]:
        """Retrieves the most recent snapshot for the target goal."""
        pass
