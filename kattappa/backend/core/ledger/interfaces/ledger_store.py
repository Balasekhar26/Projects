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

    @abstractmethod
    def record_metric(self, timestamp: float, metric_name: str, value: float, metadata: dict | None = None) -> None:
        """Records a metric observation directly to the storage engine."""
        pass

    @abstractmethod
    def get_metric_values(self, metric_name: str, since_timestamp: float | None = None) -> List[tuple[float, float]]:
        """Queries metric history from the storage engine."""
        pass

    @abstractmethod
    def record_decision(
        self,
        decision_id: str,
        trace_id: str,
        span_id: str,
        stage: str,
        timestamp: float,
        action: str,
        reason: str,
        alternatives: list,
        confidence: float,
        inputs: dict,
        outputs: dict,
        metadata: dict | None = None,
    ) -> None:
        """Records a cognitive decision event."""
        pass

    @abstractmethod
    def get_decisions(self, trace_id: str) -> List[Dict[str, Any]]:
        """Queries all decisions associated with a trace ID."""
        pass

    @abstractmethod
    def get_decisions_by_stage(self, stage: str) -> List[Dict[str, Any]]:
        """Queries all decisions associated with a specific cognitive stage."""
        pass

    @abstractmethod
    def record_outcome(
        self,
        calibration_id: str,
        decision_id: str,
        trace_id: str,
        stage: str,
        predicted_confidence: float,
        actual_result: int,
        error_message: str | None = None,
    ) -> None:
        """Records an execution outcome event."""
        pass

    @abstractmethod
    def get_calibrations(self, stage: str | None = None) -> List[Dict[str, Any]]:
        """Queries all recorded calibrations."""
        pass

    @abstractmethod
    def record_execution_receipt(
        self,
        action_id: str,
        capability: str,
        authorized_by: str,
        approval_scope: str,
        trace_id: str,
        span_id: str,
        metadata: dict | None = None,
    ) -> None:
        """Records an execution authorization receipt."""
        pass

    @abstractmethod
    def get_execution_receipts(self, trace_id: str) -> List[Dict[str, Any]]:
        """Queries execution receipts matching trace_id."""
        pass

    @abstractmethod
    def create_delegation_token(self, token: Dict[str, Any]) -> None:
        """Saves a delegation token."""
        pass

    @abstractmethod
    def get_delegation_token(self, token_id: str) -> Dict[str, Any] | None:
        """Retrieves a delegation token by ID."""
        pass

    @abstractmethod
    def update_token_usage(self, token_id: str, current_invocations: int, status: str) -> None:
        """Updates invocation count and status of a delegation token."""
        pass

    @abstractmethod
    def register_skill(self, skill: Dict[str, Any]) -> None:
        """Saves a skill definition."""
        pass

    @abstractmethod
    def get_skill(self, name: str) -> Dict[str, Any] | None:
        """Retrieves a skill definition by name."""
        pass

    @abstractmethod
    def list_skills(self) -> List[Dict[str, Any]]:
        """Lists all registered skills."""
        pass

    @abstractmethod
    def remove_skill(self, name: str) -> None:
        """Removes a skill definition by name."""
        pass

    # ── Goal Lifecycle ────────────────────────────────────────────────────────

    @abstractmethod
    def create_goal(self, goal: Dict[str, Any]) -> None:
        """Persists a new goal record."""
        pass

    @abstractmethod
    def get_goal(self, goal_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves a goal by ID, or None if not found."""
        pass

    @abstractmethod
    def update_goal_status(self, goal_id: str, status: str, retry_count: int | None = None) -> None:
        """Updates the status (and optionally retry_count) of a goal."""
        pass

    @abstractmethod
    def list_goals(self, status: str | None = None, owner: str | None = None) -> List[Dict[str, Any]]:
        """Lists goals optionally filtered by status and/or owner."""
        pass

    @abstractmethod
    def list_subgoals(self, parent_goal_id: str) -> List[Dict[str, Any]]:
        """Returns all direct child goals of the given parent goal."""
        pass

    # ─── Principal CRUD (M32 Identity System) ─────────────────────────────────

    @abstractmethod
    def create_principal(self, principal: Dict[str, Any]) -> None:
        """Persists a new principal."""
        pass

    @abstractmethod
    def get_principal(self, principal_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves a principal by ID, or None if not found."""
        pass

    @abstractmethod
    def get_principal_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        """Retrieves a principal by unique name, or None if not found."""
        pass

    @abstractmethod
    def update_principal_status(self, principal_id: str, is_active: bool, status: Optional[str] = None) -> None:
        """Activates or deactivates a principal (soft delete / status update)."""
        pass

    @abstractmethod
    def list_principals(
        self,
        principal_type: Optional[str] = None,
        active_only: bool = True,
    ) -> List[Dict[str, Any]]:
        """Returns all registered principals, optionally filtered."""
        pass

    # ─── Audit Ledger CRUD (M33 Immutable Audit Ledger) ───────────────────────
 
    @abstractmethod
    def append_audit_entry(self, entry: Dict[str, Any]) -> None:
        """Appends a cryptographically chained audit entry to the audit log."""
        pass
 
    @abstractmethod
    def get_latest_audit_hash(self) -> str:
        """Retrieves the entry_hash of the latest audit log entry, or zeroes-block if empty."""
        pass
 
    @abstractmethod
    def list_audit_entries(self) -> List[Dict[str, Any]]:
        """Returns all audit log entries, sorted by timestamp (oldest first)."""
        pass

    # ─── Capability Contracts CRUD (M35 Dynamic Negotiation) ─────────────────

    @abstractmethod
    def create_capability_contract(self, contract: Dict[str, Any]) -> None:
        """Persists a new capability contract (lease)."""
        pass

    @abstractmethod
    def get_active_capability_contracts(self, principal_id: str) -> List[Dict[str, Any]]:
        """Retrieves all active capability contracts for a principal."""
        pass

    @abstractmethod
    def get_metric_values(self, metric_name: str, since_timestamp: float | None = None) -> List[tuple[float, float]]:
        """Queries metric history from the storage engine."""
        pass

    @abstractmethod
    def record_decision(
        self,
        decision_id: str,
        trace_id: str,
        span_id: str,
        stage: str,
        timestamp: float,
        action: str,
        reason: str,
        alternatives: list,
        confidence: float,
        inputs: dict,
        outputs: dict,
        metadata: dict | None = None,
    ) -> None:
        """Records a cognitive decision event."""
        pass

    @abstractmethod
    def get_decisions(self, trace_id: str) -> List[Dict[str, Any]]:
        """Queries all decisions associated with a trace ID."""
        pass

    @abstractmethod
    def get_decisions_by_stage(self, stage: str) -> List[Dict[str, Any]]:
        """Queries all decisions associated with a specific cognitive stage."""
        pass

    @abstractmethod
    def record_outcome(
        self,
        calibration_id: str,
        decision_id: str,
        trace_id: str,
        stage: str,
        predicted_confidence: float,
        actual_result: int,
        error_message: str | None = None,
    ) -> None:
        """Records an execution outcome event."""
        pass

    @abstractmethod
    def get_calibrations(self, stage: str | None = None) -> List[Dict[str, Any]]:
        """Queries all recorded calibrations."""
        pass

    @abstractmethod
    def record_execution_receipt(
        self,
        action_id: str,
        capability: str,
        authorized_by: str,
        approval_scope: str,
        trace_id: str,
        span_id: str,
        metadata: dict | None = None,
    ) -> None:
        """Records an execution authorization receipt."""
        pass

    @abstractmethod
    def get_execution_receipts(self, trace_id: str) -> List[Dict[str, Any]]:
        """Queries execution receipts matching trace_id."""
        pass

    @abstractmethod
    def create_delegation_token(self, token: Dict[str, Any]) -> None:
        """Saves a delegation token."""
        pass

    @abstractmethod
    def get_delegation_token(self, token_id: str) -> Dict[str, Any] | None:
        """Retrieves a delegation token by ID."""
        pass

    @abstractmethod
    def update_token_usage(self, token_id: str, current_invocations: int, status: str) -> None:
        """Updates invocation count and status of a delegation token."""
        pass

    @abstractmethod
    def register_skill(self, skill: Dict[str, Any]) -> None:
        """Saves a skill definition."""
        pass

    @abstractmethod
    def get_skill(self, name: str) -> Dict[str, Any] | None:
        """Retrieves a skill definition by name."""
        pass

    @abstractmethod
    def list_skills(self) -> List[Dict[str, Any]]:
        """Lists all registered skills."""
        pass

    @abstractmethod
    def remove_skill(self, name: str) -> None:
        """Removes a skill definition by name."""
        pass

    # ── Goal Lifecycle ────────────────────────────────────────────────────────

    @abstractmethod
    def create_goal(self, goal: Dict[str, Any]) -> None:
        """Persists a new goal record."""
        pass

    @abstractmethod
    def get_goal(self, goal_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves a goal by ID, or None if not found."""
        pass

    @abstractmethod
    def update_goal_status(self, goal_id: str, status: str, retry_count: int | None = None) -> None:
        """Updates the status (and optionally retry_count) of a goal."""
        pass

    @abstractmethod
    def list_goals(self, status: str | None = None, owner: str | None = None) -> List[Dict[str, Any]]:
        """Lists goals optionally filtered by status and/or owner."""
        pass

    @abstractmethod
    def list_subgoals(self, parent_goal_id: str) -> List[Dict[str, Any]]:
        """Returns all direct child goals of the given parent goal."""
        pass

    # ─── Principal CRUD (M32 Identity System) ─────────────────────────────────

    @abstractmethod
    def create_principal(self, principal: Dict[str, Any]) -> None:
        """Persists a new principal."""
        pass

    @abstractmethod
    def get_principal(self, principal_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves a principal by ID, or None if not found."""
        pass

    @abstractmethod
    def get_principal_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        """Retrieves a principal by unique name, or None if not found."""
        pass

    @abstractmethod
    def update_principal_status(self, principal_id: str, is_active: bool, status: Optional[str] = None) -> None:
        """Activates or deactivates a principal (soft delete / status update)."""
        pass

    @abstractmethod
    def list_principals(
        self,
        principal_type: Optional[str] = None,
        active_only: bool = True,
    ) -> List[Dict[str, Any]]:
        """Returns all registered principals, optionally filtered."""
        pass

    # ─── Audit Ledger CRUD (M33 Immutable Audit Ledger) ───────────────────────
 
    @abstractmethod
    def append_audit_entry(self, entry: Dict[str, Any]) -> None:
        """Appends a cryptographically chained audit entry to the audit log."""
        pass
 
    @abstractmethod
    def get_latest_audit_hash(self) -> str:
        """Retrieves the entry_hash of the latest audit log entry, or zeroes-block if empty."""
        pass
 
    @abstractmethod
    def list_audit_entries(self) -> List[Dict[str, Any]]:
        """Returns all audit log entries, sorted by timestamp (oldest first)."""
        pass

    # ─── Capability Contracts CRUD (M35 Dynamic Negotiation) ─────────────────

    @abstractmethod
    def create_capability_contract(self, contract: Dict[str, Any]) -> None:
        """Persists a new capability contract (lease)."""
        pass

    @abstractmethod
    def get_active_capability_contracts(self, principal_id: str) -> List[Dict[str, Any]]:
        """Retrieves all active capability contracts for a principal."""
        pass

    @abstractmethod
    def update_capability_contract_status(self, contract_id: str, status: str) -> None:
        """Updates the status of a capability contract."""
        pass

    @abstractmethod
    def get_capability_contract(self, contract_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves a single capability contract by ID."""
        pass

    @abstractmethod
    def increment_contract_use_count(self, contract_id: str) -> None:
        """Atomically increments use_count on a capability contract. Default no-op for backward compat."""
        pass
