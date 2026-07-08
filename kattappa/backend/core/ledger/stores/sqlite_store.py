import json
import sqlite3
import threading
from typing import List, Optional, Dict, Any
from backend.core.ledger.interfaces.ledger_store import LedgerStore
from backend.core.ledger.models.event import LedgerEvent
from backend.core.ledger.models.snapshot import LedgerSnapshot
from backend.core.ledger.models.enums import EventType


class SQLiteLedgerStore(LedgerStore):
    def __init__(self, db_path: str = ":memory:") -> None:
        self._db_path = db_path
        self._lock = threading.Lock()
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        return sqlite3.connect(self._db_path)

    def _init_db(self) -> None:
        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS events (
                    event_id TEXT PRIMARY KEY,
                    parent_event_ids TEXT,
                    goal_id TEXT,
                    session_id TEXT,
                    correlation_id TEXT,
                    timestamp_utc REAL,
                    actor TEXT,
                    subsystem TEXT,
                    event_type TEXT,
                    payload TEXT,
                    evidence TEXT,
                    confidence REAL,
                    status TEXT,
                    metadata TEXT,
                    schema_version INTEGER,
                    event_version INTEGER
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS snapshots (
                    snapshot_id TEXT PRIMARY KEY,
                    goal_id TEXT,
                    last_event_id TEXT,
                    timestamp_utc REAL,
                    state TEXT,
                    metadata TEXT
                )
            """)
            conn.commit()
            conn.close()

    def append(self, event: LedgerEvent) -> None:
        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()
            # Check duplicate
            cursor.execute("SELECT 1 FROM events WHERE event_id = ?", (event.event_id,))
            if cursor.fetchone():
                conn.close()
                raise ValueError(f"Event with ID {event.event_id} already exists.")

            cursor.execute(
                """
                INSERT INTO events (
                    event_id, parent_event_ids, goal_id, session_id, correlation_id,
                    timestamp_utc, actor, subsystem, event_type, payload,
                    evidence, confidence, status, metadata, schema_version, event_version
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    event.event_id,
                    json.dumps(event.parent_event_ids),
                    event.goal_id,
                    event.session_id,
                    event.correlation_id,
                    event.timestamp_utc,
                    event.actor,
                    event.subsystem,
                    event.event_type.value,
                    json.dumps(event.payload),
                    json.dumps(event.evidence) if event.evidence is not None else None,
                    event.confidence,
                    event.status,
                    json.dumps(event.metadata),
                    event.schema_version,
                    event.event_version,
                ),
            )
            conn.commit()
            conn.close()

    def _row_to_event(self, row: tuple) -> LedgerEvent:
        return LedgerEvent(
            event_id=row[0],
            parent_event_ids=json.loads(row[1]),
            goal_id=row[2],
            session_id=row[3],
            correlation_id=row[4],
            timestamp_utc=row[5],
            actor=row[6],
            subsystem=row[7],
            event_type=EventType(row[8]),
            payload=json.loads(row[9]),
            evidence=json.loads(row[10]) if row[10] is not None else None,
            confidence=row[11],
            status=row[12],
            metadata=json.loads(row[13]),
            schema_version=row[14],
            event_version=row[15],
        )

    def get(self, event_id: str) -> Optional[LedgerEvent]:
        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM events WHERE event_id = ?", (event_id,))
            row = cursor.fetchone()
            conn.close()
            if not row:
                return None
            return self._row_to_event(row)

    def children(self, event_id: str) -> List[LedgerEvent]:
        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM events")
            rows = cursor.fetchall()
            conn.close()
            events = []
            for row in rows:
                ev = self._row_to_event(row)
                if event_id in ev.parent_event_ids:
                    events.append(ev)
            return events

    def parents(self, event_id: str) -> List[LedgerEvent]:
        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute(
                "SELECT parent_event_ids FROM events WHERE event_id = ?", (event_id,)
            )
            row = cursor.fetchone()
            if not row:
                conn.close()
                return []
            parent_ids = json.loads(row[0])
            if not parent_ids:
                conn.close()
                return []
            # Fetch parents
            placeholders = ",".join("?" for _ in parent_ids)
            cursor.execute(
                f"SELECT * FROM events WHERE event_id IN ({placeholders})", parent_ids
            )
            rows = cursor.fetchall()
            conn.close()
            return [self._row_to_event(r) for r in rows]

    def ancestors(self, event_id: str) -> List[LedgerEvent]:
        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()
            visited = set()
            ancestor_events = []

            def dfs(eid: str) -> None:
                cursor.execute(
                    "SELECT parent_event_ids FROM events WHERE event_id = ?", (eid,)
                )
                row = cursor.fetchone()
                if not row:
                    return
                parent_ids = json.loads(row[0])
                for pid in parent_ids:
                    if pid not in visited:
                        visited.add(pid)
                        cursor.execute(
                            "SELECT * FROM events WHERE event_id = ?", (pid,)
                        )
                        prow = cursor.fetchone()
                        if prow:
                            ancestor_events.append(self._row_to_event(prow))
                        dfs(pid)

            dfs(event_id)
            conn.close()
            ancestor_events.sort(key=lambda x: x.timestamp_utc)
            return ancestor_events

    def descendants(self, event_id: str) -> List[LedgerEvent]:
        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()
            visited = set()
            descendant_events = []

            def dfs(eid: str) -> None:
                cursor.execute(
                    "SELECT * FROM events WHERE parent_event_ids LIKE ?",
                    (f'%"{eid}"%',),
                )
                prows = cursor.fetchall()
                for prow in prows:
                    child = self._row_to_event(prow)
                    if child.event_id not in visited:
                        visited.add(child.event_id)
                        descendant_events.append(child)
                        dfs(child.event_id)

            dfs(event_id)
            conn.close()
            descendant_events.sort(key=lambda x: x.timestamp_utc)
            return descendant_events

    def query(self, filters: Dict[str, Any]) -> List[LedgerEvent]:
        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()
            query_str = "SELECT * FROM events"
            params = []
            if filters:
                conds = []
                for k, v in filters.items():
                    if k == "event_type":
                        conds.append("event_type = ?")
                        params.append(v.value if isinstance(v, EventType) else v)
                    elif k == "min_confidence":
                        conds.append("confidence >= ?")
                        params.append(v)
                    elif k == "max_confidence":
                        conds.append("confidence <= ?")
                        params.append(v)
                    elif k == "start_time":
                        conds.append("timestamp_utc >= ?")
                        params.append(v)
                    elif k == "end_time":
                        conds.append("timestamp_utc <= ?")
                        params.append(v)
                    elif k == "metadata":
                        # Post-filtered in python
                        pass
                    else:
                        conds.append(f"{k} = ?")
                        params.append(v)
                if conds:
                    query_str += " WHERE " + " AND ".join(conds)
            cursor.execute(query_str, params)
            rows = cursor.fetchall()
            conn.close()
            events = [self._row_to_event(r) for r in rows]

            if "metadata" in filters and isinstance(filters["metadata"], dict):
                meta_filter = filters["metadata"]
                events = [
                    e
                    for e in events
                    if all(e.metadata.get(mk) == mv for mk, mv in meta_filter.items())
                ]
            return events

    def save_snapshot(self, snapshot: LedgerSnapshot) -> None:
        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO snapshots (
                    snapshot_id, goal_id, last_event_id, timestamp_utc, state, metadata
                ) VALUES (?, ?, ?, ?, ?, ?)
            """,
                (
                    snapshot.snapshot_id,
                    snapshot.goal_id,
                    snapshot.last_event_id,
                    snapshot.timestamp_utc,
                    json.dumps(snapshot.state),
                    json.dumps(snapshot.metadata),
                ),
            )
            conn.commit()
            conn.close()

    def get_latest_snapshot(self, goal_id: str) -> Optional[LedgerSnapshot]:
        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM snapshots WHERE goal_id = ? ORDER BY timestamp_utc DESC LIMIT 1",
                (goal_id,),
            )
            row = cursor.fetchone()
            conn.close()
            if not row:
                return None
            return LedgerSnapshot(
                snapshot_id=row[0],
                goal_id=row[1],
                last_event_id=row[2],
                timestamp_utc=row[3],
                state=json.loads(row[4]),
                metadata=json.loads(row[5]),
            )
