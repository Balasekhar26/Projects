import time
import threading
from typing import List, Optional, Dict, Any
from backend.core.ledger.interfaces.ledger_store import LedgerStore
from backend.core.ledger.models.event import LedgerEvent
from backend.core.ledger.models.snapshot import LedgerSnapshot


class MemoryLedgerStore(LedgerStore):
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._events: List[LedgerEvent] = []
        self._snapshots: Dict[str, List[LedgerSnapshot]] = {}
        self._metrics: List[Dict[str, Any]] = []
        self._decisions: List[Dict[str, Any]] = []
        self._calibrations: List[Dict[str, Any]] = []
        self._receipts: List[Dict[str, Any]] = []
        self._tokens: List[Dict[str, Any]] = []
        self._skills: List[Dict[str, Any]] = []
        self._goals: List[Dict[str, Any]] = []
        self._principals: List[Dict[str, Any]] = []  # M32 Identity System
        self._audit_log: List[Dict[str, Any]] = []   # M33 Immutable Audit Ledger
        self._capability_contracts: List[Dict[str, Any]] = []  # M35 Dynamic Negotiation

    def append(self, event: LedgerEvent) -> None:
        with self._lock:
            if any(e.event_id == event.event_id for e in self._events):
                raise ValueError(f"Event with ID {event.event_id} already exists.")
            self._events.append(event)

    def get(self, event_id: str) -> Optional[LedgerEvent]:
        with self._lock:
            for event in self._events:
                if event.event_id == event_id:
                    return event
            return None

    def children(self, event_id: str) -> List[LedgerEvent]:
        with self._lock:
            return [e for e in self._events if event_id in e.parent_event_ids]

    def parents(self, event_id: str) -> List[LedgerEvent]:
        with self._lock:
            target = None
            for e in self._events:
                if e.event_id == event_id:
                    target = e
                    break
            if not target:
                return []
            return [e for e in self._events if e.event_id in target.parent_event_ids]

    def ancestors(self, event_id: str) -> List[LedgerEvent]:
        with self._lock:
            visited = set()
            ancestor_events = []

            def dfs(eid: str) -> None:
                event = None
                for e in self._events:
                    if e.event_id == eid:
                        event = e
                        break
                if not event:
                    return
                for pid in event.parent_event_ids:
                    if pid not in visited:
                        visited.add(pid)
                        pevent = None
                        for e in self._events:
                            if e.event_id == pid:
                                pevent = e
                                break
                        if pevent:
                            ancestor_events.append(pevent)
                        dfs(pid)

            dfs(event_id)
            ancestor_events.sort(key=lambda x: x.timestamp_utc)
            return ancestor_events

    def descendants(self, event_id: str) -> List[LedgerEvent]:
        with self._lock:
            visited = set()
            descendant_events = []

            def dfs(eid: str) -> None:
                children_events = [e for e in self._events if eid in e.parent_event_ids]
                for child in children_events:
                    if child.event_id not in visited:
                        visited.add(child.event_id)
                        descendant_events.append(child)
                        dfs(child.event_id)

            dfs(event_id)
            descendant_events.sort(key=lambda x: x.timestamp_utc)
            return descendant_events

    def query(self, filters: Dict[str, Any]) -> List[LedgerEvent]:
        from backend.core.ledger.models.enums import EventType

        with self._lock:
            results = list(self._events)
            for key, val in filters.items():
                if not results:
                    break
                if key == "event_type":
                    if isinstance(val, EventType):
                        results = [e for e in results if e.event_type == val]
                    else:
                        results = [e for e in results if e.event_type.value == val]
                elif key == "min_confidence":
                    results = [e for e in results if e.confidence >= val]
                elif key == "max_confidence":
                    results = [e for e in results if e.confidence <= val]
                elif key == "start_time":
                    results = [e for e in results if e.timestamp_utc >= val]
                elif key == "end_time":
                    results = [e for e in results if e.timestamp_utc <= val]
                elif key == "metadata":
                    if isinstance(val, dict):
                        results = [
                            e
                            for e in results
                            if all(e.metadata.get(mk) == mv for mk, mv in val.items())
                        ]
                else:
                    results = [e for e in results if getattr(e, key, None) == val]
            return results

    def save_snapshot(self, snapshot: LedgerSnapshot) -> None:
        with self._lock:
            self._snapshots.setdefault(snapshot.goal_id, []).append(snapshot)

    def get_latest_snapshot(self, goal_id: str) -> Optional[LedgerSnapshot]:
        with self._lock:
            snaps = self._snapshots.get(goal_id, [])
            if not snaps:
                return None
            return sorted(snaps, key=lambda s: s.timestamp_utc, reverse=True)[0]

    def record_metric(self, timestamp: float, metric_name: str, value: float, metadata: dict | None = None) -> None:
        with self._lock:
            self._metrics.append({
                "timestamp_utc": timestamp,
                "metric_name": metric_name,
                "value": value,
                "metadata": metadata
            })

    def clear_metrics(self) -> None:
        with self._lock:
            self._metrics.clear()

    def get_metric_values(self, metric_name: str, since_timestamp: float | None = None) -> List[tuple[float, float]]:
        with self._lock:
            results = []
            for m in self._metrics:
                if m["metric_name"] == metric_name:
                    if since_timestamp is None or m["timestamp_utc"] >= since_timestamp:
                        results.append((m["timestamp_utc"], m["value"]))
            return sorted(results, key=lambda x: x[0])

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
        with self._lock:
            self._decisions.append({
                "decision_id": decision_id,
                "trace_id": trace_id,
                "span_id": span_id,
                "stage": stage,
                "timestamp_utc": timestamp,
                "action": action,
                "reason": reason,
                "alternatives_considered": alternatives or [],
                "confidence": confidence,
                "inputs": inputs or {},
                "outputs": outputs or {},
                "metadata": metadata or {},
            })

    def get_decisions(self, trace_id: str) -> List[Dict[str, Any]]:
        with self._lock:
            results = [d for d in self._decisions if d["trace_id"] == trace_id]
            return sorted(results, key=lambda x: x["timestamp_utc"])

    def get_decisions_by_stage(self, stage: str) -> List[Dict[str, Any]]:
        with self._lock:
            results = [d for d in self._decisions if d["stage"] == stage]
            return sorted(results, key=lambda x: x["timestamp_utc"], reverse=True)

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
        with self._lock:
            self._calibrations.append({
                "calibration_id": calibration_id,
                "decision_id": decision_id,
                "trace_id": trace_id,
                "stage": stage,
                "predicted_confidence": predicted_confidence,
                "actual_result": actual_result,
                "error_message": error_message,
                "timestamp_utc": time.time(),
            })

    def get_calibrations(self, stage: str | None = None) -> List[Dict[str, Any]]:
        with self._lock:
            if stage is not None:
                results = [c for c in self._calibrations if c["stage"] == stage]
            else:
                results = list(self._calibrations)
            return sorted(results, key=lambda x: x["timestamp_utc"])

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
        with self._lock:
            self._receipts.append({
                "action_id": action_id,
                "capability": capability,
                "authorized_by": authorized_by,
                "approval_scope": approval_scope,
                "timestamp_utc": time.time(),
                "trace_id": trace_id,
                "span_id": span_id,
                "metadata": metadata or {},
            })

    def get_execution_receipts(self, trace_id: str) -> List[Dict[str, Any]]:
        with self._lock:
            results = [r for r in self._receipts if r["trace_id"] == trace_id]
            return sorted(results, key=lambda x: x["timestamp_utc"])

    def create_delegation_token(self, token: Dict[str, Any]) -> None:
        with self._lock:
            self._tokens.append(dict(token))

    def get_delegation_token(self, token_id: str) -> Dict[str, Any] | None:
        with self._lock:
            for t in self._tokens:
                if t["token_id"] == token_id:
                    return dict(t)
            return None

    def update_token_usage(self, token_id: str, current_invocations: int, status: str) -> None:
        with self._lock:
            for t in self._tokens:
                if t["token_id"] == token_id:
                    t["current_invocations"] = current_invocations
                    t["status"] = status
                    break

    def register_skill(self, skill: Dict[str, Any]) -> None:
        with self._lock:
            # Remove existing skill with the same name if present
            self._skills = [s for s in self._skills if s["name"] != skill["name"]]
            self._skills.append(dict(skill))

    def get_skill(self, name: str) -> Dict[str, Any] | None:
        with self._lock:
            for s in self._skills:
                if s["name"] == name:
                    return dict(s)
            return None

    def list_skills(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [dict(s) for s in self._skills]

    def remove_skill(self, name: str) -> None:
        with self._lock:
            self._skills = [s for s in self._skills if s["name"] != name]

    # ── Goal Lifecycle ────────────────────────────────────────────────────────

    def create_goal(self, goal: Dict[str, Any]) -> None:
        with self._lock:
            if not any(g["goal_id"] == goal["goal_id"] for g in self._goals):
                g = dict(goal)
                g.setdefault("owner_id", None)
                self._goals.append(g)

    def get_goal(self, goal_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            for g in self._goals:
                if g["goal_id"] == goal_id:
                    return dict(g)
            return None

    def update_goal_status(
        self,
        goal_id: str,
        status: str,
        retry_count: int | None = None,
    ) -> None:
        import time as _time
        with self._lock:
            for g in self._goals:
                if g["goal_id"] == goal_id:
                    g["status"] = status
                    g["updated_at"] = _time.time()
                    if retry_count is not None:
                        g["retry_count"] = retry_count
                    break

    def list_goals(
        self,
        status: str | None = None,
        owner: str | None = None,
    ) -> List[Dict[str, Any]]:
        with self._lock:
            results = list(self._goals)
            if status is not None:
                results = [g for g in results if g["status"] == status]
            if owner is not None:
                results = [g for g in results if g.get("owner") == owner]
            return [dict(g) for g in sorted(results, key=lambda g: (-g.get("priority", 5), g.get("created_at", 0)))]

    def list_subgoals(self, parent_goal_id: str) -> List[Dict[str, Any]]:
        with self._lock:
            return [
                dict(g) for g in self._goals
                if g.get("parent_goal_id") == parent_goal_id
            ]

    # ─── Principal CRUD (M32 Identity System) ─────────────────────────────────

    def create_principal(self, principal: Dict[str, Any]) -> None:
        with self._lock:
            if not any(p["principal_id"] == principal["principal_id"] for p in self._principals):
                p = dict(principal)
                p.setdefault("status", "ACTIVE")
                p.setdefault("expires_at", None)
                p.setdefault("public_key", None)
                self._principals.append(p)

    def get_principal(self, principal_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            for p in self._principals:
                if p["principal_id"] == principal_id:
                    return dict(p)
            return None

    def get_principal_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            for p in self._principals:
                if p["name"] == name:
                    return dict(p)
            return None

    def update_principal_status(self, principal_id: str, is_active: bool, status: str | None = None) -> None:
        with self._lock:
            for p in self._principals:
                if p["principal_id"] == principal_id:
                    p["is_active"] = is_active
                    p["status"] = status if status is not None else ("ACTIVE" if is_active else "SUSPENDED")
                    break

    def list_principals(
        self,
        principal_type: Optional[str] = None,
        active_only: bool = True,
    ) -> List[Dict[str, Any]]:
        with self._lock:
            results = list(self._principals)
            if active_only:
                results = [p for p in results if p.get("is_active", True)]
            if principal_type:
                results = [p for p in results if p.get("principal_type") == principal_type]
            return [dict(p) for p in sorted(results, key=lambda p: p.get("created_at", 0))]

    # ─── Audit Ledger CRUD (M33 Immutable Audit Ledger) ───────────────────────

    def append_audit_entry(self, entry: Dict[str, Any]) -> None:
        with self._lock:
            if not any(e["audit_id"] == entry["audit_id"] for e in self._audit_log):
                self._audit_log.append(dict(entry))

    def get_latest_audit_hash(self) -> str:
        with self._lock:
            if self._audit_log:
                # Sort by timestamp, then order inserted
                sorted_entries = sorted(self._audit_log, key=lambda e: e.get("timestamp", 0))
                return sorted_entries[-1]["entry_hash"]
            return "0000000000000000000000000000000000000000000000000000000000000000"

    def list_audit_entries(self) -> List[Dict[str, Any]]:
        with self._lock:
            # Sorted oldest first
            return [dict(e) for e in sorted(self._audit_log, key=lambda e: e.get("timestamp", 0))]

    # ─── Capability Contracts CRUD (M35 Dynamic Negotiation) ─────────────────

    def create_capability_contract(self, contract: Dict[str, Any]) -> None:
        with self._lock:
            # Remove existing contract with same ID if any, then append
            self._capability_contracts = [c for c in self._capability_contracts if c["contract_id"] != contract["contract_id"]]
            self._capability_contracts.append(dict(contract))

    def get_active_capability_contracts(self, principal_id: str) -> List[Dict[str, Any]]:
        with self._lock:
            results = []
            for c in self._capability_contracts:
                if (
                    c["principal_id"] == principal_id
                    and c["status"] == "APPROVED"
                    and c["expires_at"] > time.time()
                ):
                    results.append(dict(c))
            return results

    def update_capability_contract_status(self, contract_id: str, status: str) -> None:
        with self._lock:
            for c in self._capability_contracts:
                if c["contract_id"] == contract_id:
                    c["status"] = status
                    break

    def get_capability_contract(self, contract_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            for c in self._capability_contracts:
                if c["contract_id"] == contract_id:
                    return dict(c)
            return None

    def increment_contract_use_count(self, contract_id: str) -> None:
        """Atomically increments the use_count for a capability contract lease."""
        with self._lock:
            for c in self._capability_contracts:
                if c["contract_id"] == contract_id:
                    c["use_count"] = c.get("use_count", 0) + 1
                    break

    def get_contracts_by_parent(self, parent_contract_id: str) -> List[Dict[str, Any]]:
        """Returns all contracts that have the given parent_contract_id (delegation chain children)."""
        with self._lock:
            return [
                dict(c) for c in self._capability_contracts
                if c.get("parent_contract_id") == parent_contract_id
            ]

