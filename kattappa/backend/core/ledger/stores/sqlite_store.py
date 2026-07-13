import json
import sqlite3
import threading
import time
from typing import List, Optional, Dict, Any
from backend.core.ledger.interfaces.ledger_store import LedgerStore
from backend.core.ledger.models.event import LedgerEvent
from backend.core.ledger.models.snapshot import LedgerSnapshot
from backend.core.ledger.models.enums import EventType


class SQLiteLedgerStore(LedgerStore):
    def __init__(self, db_path: str = ":memory:") -> None:
        self._db_path = db_path
        self._lock = threading.RLock()
        # For :memory: databases, all operations MUST share the same connection
        # because each new sqlite3.connect(":memory:") opens a completely fresh DB.
        # For file-based DBs we open a new connection per call (simpler, avoids
        # long-lived connection state), but still need check_same_thread=False.
        if db_path == ":memory:":
            self._shared_conn = sqlite3.connect(db_path, check_same_thread=False)
        else:
            self._shared_conn = None
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        if self._shared_conn is not None:
            return self._shared_conn
        return sqlite3.connect(self._db_path, check_same_thread=False)

    def _close_connection(self, conn: sqlite3.Connection) -> None:
        """Close conn only when it is NOT the persistent shared connection.

        For :memory: databases, the single shared connection must remain open
        for the lifetime of the store. For file-based connections, each call
        opens a fresh connection that should be closed after use.
        """
        if self._shared_conn is None:
            conn.close()

    def __del__(self) -> None:
        """Ensure the shared in-memory connection is properly closed on GC.

        Uses a bare except to guard against recursion when coverage tools
        install trace hooks that can be active during garbage collection.
        """
        conn = getattr(self, "_shared_conn", None)
        if conn is not None:
            try:
                self._shared_conn = None
                conn.close()
            except Exception:  # noqa: BLE001
                pass

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
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS metrics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp_utc REAL,
                    metric_name TEXT,
                    value REAL,
                    metadata TEXT
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS decisions (
                    decision_id TEXT PRIMARY KEY,
                    trace_id TEXT,
                    span_id TEXT,
                    stage TEXT,
                    timestamp_utc REAL,
                    action TEXT,
                    reason TEXT,
                    alternatives_considered TEXT,
                    confidence REAL,
                    inputs TEXT,
                    outputs TEXT,
                    metadata TEXT
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_events_goal_id ON events (goal_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_events_session_id ON events (session_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_events_correlation_id ON events (correlation_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_events_event_type ON events (event_type)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_events_timestamp ON events (timestamp_utc)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_snapshots_goal_id ON snapshots (goal_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_metrics_name ON metrics (metric_name)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_metrics_timestamp ON metrics (timestamp_utc)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_decisions_trace ON decisions (trace_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_decisions_stage ON decisions (stage)")
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS calibrations (
                    calibration_id TEXT PRIMARY KEY,
                    decision_id TEXT,
                    trace_id TEXT,
                    stage TEXT,
                    predicted_confidence REAL,
                    actual_result INTEGER,
                    error_message TEXT,
                    timestamp_utc REAL,
                    FOREIGN KEY (decision_id) REFERENCES decisions(decision_id) ON DELETE CASCADE
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_calibrations_trace ON calibrations (trace_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_calibrations_stage ON calibrations (stage)")
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS execution_receipts (
                    action_id TEXT PRIMARY KEY,
                    capability TEXT NOT NULL,
                    authorized_by TEXT NOT NULL,
                    approval_scope TEXT NOT NULL,
                    timestamp_utc REAL NOT NULL,
                    trace_id TEXT NOT NULL,
                    span_id TEXT NOT NULL,
                    metadata TEXT NOT NULL DEFAULT '{}'
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_receipts_trace ON execution_receipts (trace_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_receipts_capability ON execution_receipts (capability)")
            cursor.execute("""
                CREATE TRIGGER IF NOT EXISTS receipts_prevent_update
                BEFORE UPDATE ON execution_receipts
                BEGIN
                    SELECT RAISE(FAIL, 'Updates to execution_receipts are prohibited.');
                END;
            """)
            cursor.execute("""
                CREATE TRIGGER IF NOT EXISTS receipts_prevent_delete
                BEFORE DELETE ON execution_receipts
                BEGIN
                    SELECT RAISE(FAIL, 'Deletions from execution_receipts are prohibited.');
                END;
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS delegation_tokens (
                    token_id TEXT PRIMARY KEY,
                    capabilities TEXT NOT NULL,
                    trace_id TEXT NOT NULL,
                    expires_at REAL NOT NULL,
                    max_invocations INTEGER NOT NULL,
                    current_invocations INTEGER NOT NULL DEFAULT 0,
                    allowed_paths TEXT NOT NULL,
                    allowed_domains TEXT NOT NULL,
                    issued_by TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'ACTIVE',
                    signature TEXT,
                    signature_mode TEXT
                )
            """)
            # Dynamic schema migration for delegation_tokens columns (M34 Cryptographic Tokens)
            cursor.execute("PRAGMA table_info(delegation_tokens)")
            cols = [col[1] for col in cursor.fetchall()]
            if "signature" not in cols:
                cursor.execute("ALTER TABLE delegation_tokens ADD COLUMN signature TEXT")
            if "signature_mode" not in cols:
                cursor.execute("ALTER TABLE delegation_tokens ADD COLUMN signature_mode TEXT")

            cursor.execute("CREATE INDEX IF NOT EXISTS idx_tokens_trace ON delegation_tokens (trace_id)")
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS skills (
                    skill_id TEXT PRIMARY KEY,
                    name TEXT UNIQUE NOT NULL,
                    version TEXT NOT NULL,
                    description TEXT,
                    entrypoint TEXT NOT NULL,
                    sandbox_type TEXT NOT NULL,
                    timeout_seconds INTEGER NOT NULL DEFAULT 30,
                    max_memory_mb INTEGER,
                    allow_network INTEGER NOT NULL DEFAULT 0,
                    allowed_paths TEXT NOT NULL DEFAULT '[]'
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS skill_permissions (
                    skill_id TEXT NOT NULL,
                    capability TEXT NOT NULL,
                    FOREIGN KEY(skill_id) REFERENCES skills(skill_id) ON DELETE CASCADE
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS skill_dependencies (
                    skill_id TEXT NOT NULL,
                    dependency_name TEXT NOT NULL,
                    version_constraint TEXT NOT NULL,
                    FOREIGN KEY(skill_id) REFERENCES skills(skill_id) ON DELETE CASCADE
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_skills_name ON skills (name)")
            # Goals table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS goals (
                    goal_id         TEXT PRIMARY KEY,
                    title           TEXT NOT NULL,
                    description     TEXT,
                    status          TEXT NOT NULL DEFAULT 'CREATED',
                    priority        INTEGER NOT NULL DEFAULT 5,
                    owner           TEXT,
                    owner_id        TEXT,
                    deadline_utc    REAL,
                    confidence      REAL DEFAULT 1.0,
                    retry_count     INTEGER DEFAULT 0,
                    max_retries     INTEGER DEFAULT 3,
                    parent_goal_id  TEXT,
                    created_at      REAL,
                    updated_at      REAL,
                    metadata        TEXT DEFAULT '{}'
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_goals_status ON goals (status)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_goals_priority ON goals (priority DESC)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_goals_parent ON goals (parent_goal_id)")
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS principals (
                    principal_id   TEXT PRIMARY KEY,
                    name           TEXT UNIQUE NOT NULL,
                    principal_type TEXT NOT NULL,
                    trust_level    INTEGER NOT NULL DEFAULT 2,
                    capabilities   TEXT DEFAULT '[]',
                    metadata       TEXT DEFAULT '{}',
                    created_at     REAL,
                    is_active      INTEGER DEFAULT 1,
                    status         TEXT DEFAULT 'ACTIVE',
                    expires_at     REAL,
                    public_key     TEXT
                )
            """)
            # Dynamic schema migration for public_key column (M34 Cryptographic Tokens)
            cursor.execute("PRAGMA table_info(principals)")
            columns = [col[1] for col in cursor.fetchall()]
            if "public_key" not in columns:
                cursor.execute("ALTER TABLE principals ADD COLUMN public_key TEXT")

            cursor.execute("CREATE INDEX IF NOT EXISTS idx_principals_name ON principals (name)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_principals_type ON principals (principal_type)")
            # Audit log table (M33 Immutable Audit Ledger)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS audit_log (
                    audit_id         TEXT PRIMARY KEY,
                    timestamp        REAL NOT NULL,
                    principal_id     TEXT NOT NULL,
                    action           TEXT NOT NULL,
                    resource         TEXT,
                    decision         TEXT NOT NULL,
                    reason           TEXT,
                    arguments_hash   TEXT NOT NULL,
                    delegation_chain TEXT DEFAULT '[]',
                    previous_hash    TEXT NOT NULL,
                    entry_hash       TEXT NOT NULL
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_audit_principal ON audit_log (principal_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_audit_action ON audit_log (action)")
            # Capability Contracts table (M35 Dynamic Negotiation / M36 Constraint Engine)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS capability_contracts (
                    contract_id   TEXT PRIMARY KEY,
                    principal_id  TEXT NOT NULL,
                    capability    TEXT NOT NULL,
                    reason        TEXT,
                    expires_at    REAL NOT NULL,
                    status        TEXT NOT NULL DEFAULT 'ESCALATION_REQUIRED',
                    scope         TEXT,
                    max_uses      INTEGER,
                    use_count     INTEGER NOT NULL DEFAULT 0,
                    parent_contract_id TEXT
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_contracts_principal ON capability_contracts (principal_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_contracts_status ON capability_contracts (status)")
            # Dynamic migration for existing databases missing M36 constraint columns
            cursor.execute("PRAGMA table_info(capability_contracts)")
            existing_cols = [col[1] for col in cursor.fetchall()]
            for col_def in [
                ("scope", "TEXT"),
                ("max_uses", "INTEGER"),
                ("use_count", "INTEGER NOT NULL DEFAULT 0"),
                ("parent_contract_id", "TEXT"),
            ]:
                if col_def[0] not in existing_cols:
                    cursor.execute(f"ALTER TABLE capability_contracts ADD COLUMN {col_def[0]} {col_def[1]}")
            conn.commit()
            self._close_connection(conn)



    def append(self, event: LedgerEvent) -> None:
        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()
            # Check duplicate
            cursor.execute("SELECT 1 FROM events WHERE event_id = ?", (event.event_id,))
            if cursor.fetchone():
                self._close_connection(conn)
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
            self._close_connection(conn)

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
            self._close_connection(conn)
            if not row:
                return None
            return self._row_to_event(row)

    def children(self, event_id: str) -> List[LedgerEvent]:
        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM events")
            rows = cursor.fetchall()
            self._close_connection(conn)
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
                self._close_connection(conn)
                return []
            parent_ids = json.loads(row[0])
            if not parent_ids:
                self._close_connection(conn)
                return []
            # Fetch parents
            placeholders = ",".join("?" for _ in parent_ids)
            cursor.execute(
                f"SELECT * FROM events WHERE event_id IN ({placeholders})", parent_ids
            )
            rows = cursor.fetchall()
            self._close_connection(conn)
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
            self._close_connection(conn)
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
            self._close_connection(conn)
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
            self._close_connection(conn)
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
            self._close_connection(conn)

    def get_latest_snapshot(self, goal_id: str) -> Optional[LedgerSnapshot]:
        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM snapshots WHERE goal_id = ? ORDER BY timestamp_utc DESC LIMIT 1",
                (goal_id,),
            )
            row = cursor.fetchone()
            self._close_connection(conn)
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

    def record_metric(self, timestamp: float, metric_name: str, value: float, metadata: dict | None = None) -> None:
        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO metrics (timestamp_utc, metric_name, value, metadata)
                VALUES (?, ?, ?, ?)
            """,
                (timestamp, metric_name, value, json.dumps(metadata) if metadata is not None else None),
            )
            conn.commit()
            self._close_connection(conn)

    def get_metric_values(self, metric_name: str, since_timestamp: float | None = None) -> List[tuple[float, float]]:
        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()
            if since_timestamp is not None:
                cursor.execute(
                    "SELECT timestamp_utc, value FROM metrics WHERE metric_name = ? AND timestamp_utc >= ? ORDER BY timestamp_utc ASC",
                    (metric_name, since_timestamp),
                )
            else:
                cursor.execute(
                    "SELECT timestamp_utc, value FROM metrics WHERE metric_name = ? ORDER BY timestamp_utc ASC",
                    (metric_name,),
                )
            rows = cursor.fetchall()
            self._close_connection(conn)
            return [(r[0], r[1]) for r in rows]

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
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO decisions (
                    decision_id, trace_id, span_id, stage, timestamp_utc,
                    action, reason, alternatives_considered, confidence,
                    inputs, outputs, metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    decision_id,
                    trace_id,
                    span_id,
                    stage,
                    timestamp,
                    action,
                    reason,
                    json.dumps(alternatives) if alternatives is not None else None,
                    confidence,
                    json.dumps(inputs) if inputs is not None else None,
                    json.dumps(outputs) if outputs is not None else None,
                    json.dumps(metadata) if metadata is not None else None,
                ),
            )
            conn.commit()
            self._close_connection(conn)

    def get_decisions(self, trace_id: str) -> List[Dict[str, Any]]:
        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM decisions WHERE trace_id = ? ORDER BY timestamp_utc ASC", (trace_id,))
            rows = cursor.fetchall()
            self._close_connection(conn)
            decisions = []
            for r in rows:
                decisions.append({
                    "decision_id": r[0],
                    "trace_id": r[1],
                    "span_id": r[2],
                    "stage": r[3],
                    "timestamp_utc": r[4],
                    "action": r[5],
                    "reason": r[6],
                    "alternatives_considered": json.loads(r[7]) if r[7] is not None else [],
                    "confidence": r[8],
                    "inputs": json.loads(r[9]) if r[9] is not None else {},
                    "outputs": json.loads(r[10]) if r[10] is not None else {},
                    "metadata": json.loads(r[11]) if r[11] is not None else {},
                })
            return decisions

    def get_decisions_by_stage(self, stage: str) -> List[Dict[str, Any]]:
        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM decisions WHERE stage = ? ORDER BY timestamp_utc DESC", (stage,))
            rows = cursor.fetchall()
            self._close_connection(conn)
            decisions = []
            for r in rows:
                decisions.append({
                    "decision_id": r[0],
                    "trace_id": r[1],
                    "span_id": r[2],
                    "stage": r[3],
                    "timestamp_utc": r[4],
                    "action": r[5],
                    "reason": r[6],
                    "alternatives_considered": json.loads(r[7]) if r[7] is not None else [],
                    "confidence": r[8],
                    "inputs": json.loads(r[9]) if r[9] is not None else {},
                    "outputs": json.loads(r[10]) if r[10] is not None else {},
                    "metadata": json.loads(r[11]) if r[11] is not None else {},
                })
            return decisions

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
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO calibrations (
                    calibration_id, decision_id, trace_id, stage,
                    predicted_confidence, actual_result, error_message, timestamp_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    calibration_id,
                    decision_id,
                    trace_id,
                    stage,
                    predicted_confidence,
                    actual_result,
                    error_message,
                    time.time(),
                ),
            )
            conn.commit()
            self._close_connection(conn)

    def get_calibrations(self, stage: str | None = None) -> List[Dict[str, Any]]:
        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()
            if stage is not None:
                cursor.execute(
                    "SELECT * FROM calibrations WHERE stage = ? ORDER BY timestamp_utc ASC",
                    (stage,),
                )
            else:
                cursor.execute("SELECT * FROM calibrations ORDER BY timestamp_utc ASC")
            rows = cursor.fetchall()
            self._close_connection(conn)
            calibrations = []
            for r in rows:
                calibrations.append({
                    "calibration_id": r[0],
                    "decision_id": r[1],
                    "trace_id": r[2],
                    "stage": r[3],
                    "predicted_confidence": r[4],
                    "actual_result": r[5],
                    "error_message": r[6],
                    "timestamp_utc": r[7],
                })
            return calibrations

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
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO execution_receipts (
                    action_id, capability, authorized_by, approval_scope,
                    timestamp_utc, trace_id, span_id, metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    action_id,
                    capability,
                    authorized_by,
                    approval_scope,
                    time.time(),
                    trace_id,
                    span_id,
                    json.dumps(metadata) if metadata is not None else "{}",
                ),
            )
            conn.commit()
            self._close_connection(conn)

    def get_execution_receipts(self, trace_id: str) -> List[Dict[str, Any]]:
        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM execution_receipts WHERE trace_id = ? ORDER BY timestamp_utc ASC",
                (trace_id,),
            )
            rows = cursor.fetchall()
            self._close_connection(conn)
            receipts = []
            for r in rows:
                receipts.append({
                    "action_id": r[0],
                    "capability": r[1],
                    "authorized_by": r[2],
                    "approval_scope": r[3],
                    "timestamp_utc": r[4],
                    "trace_id": r[5],
                    "span_id": r[6],
                    "metadata": json.loads(r[7]) if r[7] is not None else {},
                })
            return receipts

    def create_delegation_token(self, token: Dict[str, Any]) -> None:
        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO delegation_tokens (
                    token_id, capabilities, trace_id, expires_at,
                    max_invocations, current_invocations, allowed_paths,
                    allowed_domains, issued_by, status, signature, signature_mode
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    token["token_id"],
                    json.dumps(token["capabilities"]),
                    token["trace_id"],
                    token["expires_at"],
                    token["max_invocations"],
                    token["current_invocations"],
                    json.dumps(token["allowed_paths"]),
                    json.dumps(token["allowed_domains"]),
                    token["issued_by"],
                    token["status"],
                    token.get("signature"),
                    token.get("signature_mode"),
                ),
            )
            conn.commit()
            self._close_connection(conn)

    def get_delegation_token(self, token_id: str) -> Dict[str, Any] | None:
        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute(
                "SELECT token_id, capabilities, trace_id, expires_at, max_invocations, "
                "current_invocations, allowed_paths, allowed_domains, issued_by, status, "
                "signature, signature_mode FROM delegation_tokens WHERE token_id = ?",
                (token_id,),
            )
            row = cursor.fetchone()
            self._close_connection(conn)
            if not row:
                return None
            return {
                "token_id": row[0],
                "capabilities": json.loads(row[1]) if row[1] is not None else [],
                "trace_id": row[2],
                "expires_at": row[3],
                "max_invocations": row[4],
                "current_invocations": row[5],
                "allowed_paths": json.loads(row[6]) if row[6] is not None else [],
                "allowed_domains": json.loads(row[7]) if row[7] is not None else [],
                "issued_by": row[8],
                "status": row[9],
                "signature": row[10] if len(row) > 10 else None,
                "signature_mode": row[11] if len(row) > 11 else None,
            }


    def update_token_usage(self, token_id: str, current_invocations: int, status: str) -> None:
        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE delegation_tokens SET current_invocations = ?, status = ? WHERE token_id = ?",
                (current_invocations, status, token_id),
            )
            conn.commit()
            self._close_connection(conn)

    def register_skill(self, skill: Dict[str, Any]) -> None:
        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()
            # 1. Insert skill
            cursor.execute(
                """
                INSERT OR REPLACE INTO skills (
                    skill_id, name, version, description, entrypoint, sandbox_type, timeout_seconds,
                    max_memory_mb, allow_network, allowed_paths
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    skill["skill_id"],
                    skill["name"],
                    skill["version"],
                    skill.get("description"),
                    skill["entrypoint"],
                    skill["sandbox_type"],
                    skill.get("timeout_seconds", 30),
                    skill.get("max_memory_mb"),
                    1 if skill.get("allow_network", False) else 0,
                    json.dumps(skill.get("allowed_paths", [])),
                ),
            )
            
            # Clear old permissions and dependencies in case of replace
            cursor.execute("DELETE FROM skill_permissions WHERE skill_id = ?", (skill["skill_id"],))
            cursor.execute("DELETE FROM skill_dependencies WHERE skill_id = ?", (skill["skill_id"],))
            
            # 2. Insert permissions
            for cap in skill.get("required_capabilities", []):
                cursor.execute(
                    "INSERT INTO skill_permissions (skill_id, capability) VALUES (?, ?)",
                    (skill["skill_id"], cap),
                )
                
            # 3. Insert dependencies
            for dep in skill.get("dependencies", []):
                cursor.execute(
                    "INSERT INTO skill_dependencies (skill_id, dependency_name, version_constraint) VALUES (?, ?, ?)",
                    (skill["skill_id"], dep["name"], dep["version"]),
                )
            conn.commit()
            self._close_connection(conn)

    def get_skill(self, name: str) -> Dict[str, Any] | None:
        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM skills WHERE name = ?", (name,))
            row = cursor.fetchone()
            if not row:
                self._close_connection(conn)
                return None
                
            skill_id = row[0]
            # Fetch permissions
            cursor.execute("SELECT capability FROM skill_permissions WHERE skill_id = ?", (skill_id,))
            perms = [r[0] for r in cursor.fetchall()]
            
            # Fetch dependencies
            cursor.execute("SELECT dependency_name, version_constraint FROM skill_dependencies WHERE skill_id = ?", (skill_id,))
            deps = [{"name": r[0], "version": r[1]} for r in cursor.fetchall()]
            
            self._close_connection(conn)
            return {
                "skill_id": row[0],
                "name": row[1],
                "version": row[2],
                "description": row[3],
                "entrypoint": row[4],
                "sandbox_type": row[5],
                "timeout_seconds": row[6],
                "max_memory_mb": row[7],
                "allow_network": bool(row[8]),
                "allowed_paths": json.loads(row[9]) if row[9] else [],
                "required_capabilities": perms,
                "dependencies": deps,
            }

    def list_skills(self) -> List[Dict[str, Any]]:
        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM skills")
            names = [r[0] for r in cursor.fetchall()]
            self._close_connection(conn)
            skills_list = []
            for name in names:
                skill = self.get_skill(name)
                if skill:
                    skills_list.append(skill)
            return skills_list

    def remove_skill(self, name: str) -> None:
        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("DELETE FROM skills WHERE name = ?", (name,))
            conn.commit()
            self._close_connection(conn)

    # ─────────────────────────────────────────────────────────────────────────
    # Goal Lifecycle CRUD
    # ─────────────────────────────────────────────────────────────────────────

    def create_goal(self, goal: dict) -> None:
        """Persists a new goal record."""
        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR IGNORE INTO goals (
                    goal_id, title, description, status, priority, owner, owner_id,
                    deadline_utc, confidence, retry_count, max_retries,
                    parent_goal_id, created_at, updated_at, metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    goal["goal_id"],
                    goal["title"],
                    goal.get("description"),
                    goal.get("status", "CREATED"),
                    goal.get("priority", 5),
                    goal.get("owner"),
                    goal.get("owner_id"),
                    goal.get("deadline_utc"),
                    goal.get("confidence", 1.0),
                    goal.get("retry_count", 0),
                    goal.get("max_retries", 3),
                    goal.get("parent_goal_id"),
                    goal.get("created_at"),
                    goal.get("updated_at"),
                    json.dumps(goal.get("metadata", {})),
                ),
            )
            conn.commit()
            self._close_connection(conn)

    def get_goal(self, goal_id: str) -> dict | None:
        """Retrieves a goal by ID, or None if not found."""
        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute(
                "SELECT goal_id, title, description, status, priority, owner, owner_id, "
                "deadline_utc, confidence, retry_count, max_retries, "
                "parent_goal_id, created_at, updated_at, metadata "
                "FROM goals WHERE goal_id = ?",
                (goal_id,),
            )
            row = cursor.fetchone()
            self._close_connection(conn)
            if row is None:
                return None
            return self._row_to_goal(row)

    def update_goal_status(
        self,
        goal_id: str,
        status: str,
        retry_count: int | None = None,
    ) -> None:
        """Updates the status (and optionally retry_count) of an existing goal."""
        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()
            now = __import__('time').time()
            if retry_count is not None:
                cursor.execute(
                    "UPDATE goals SET status = ?, retry_count = ?, updated_at = ? WHERE goal_id = ?",
                    (status, retry_count, now, goal_id),
                )
            else:
                cursor.execute(
                    "UPDATE goals SET status = ?, updated_at = ? WHERE goal_id = ?",
                    (status, now, goal_id),
                )
            conn.commit()
            self._close_connection(conn)

    def list_goals(
        self,
        status: str | None = None,
        owner: str | None = None,
    ) -> list[dict]:
        """Lists goals, optionally filtered by status and/or owner."""
        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()
            query = (
                "SELECT goal_id, title, description, status, priority, owner, "
                "deadline_utc, confidence, retry_count, max_retries, "
                "parent_goal_id, created_at, updated_at, metadata "
                "FROM goals WHERE 1=1"
            )
            params: list = []
            if status is not None:
                query += " AND status = ?"
                params.append(status)
            if owner is not None:
                query += " AND owner = ?"
                params.append(owner)
            query += " ORDER BY priority DESC, created_at ASC"
            cursor.execute(query, params)
            rows = cursor.fetchall()
            self._close_connection(conn)
            return [self._row_to_goal(r) for r in rows]

    def list_subgoals(self, parent_goal_id: str) -> list[dict]:
        """Returns all direct child goals of the given parent."""
        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute(
                "SELECT goal_id, title, description, status, priority, owner, "
                "deadline_utc, confidence, retry_count, max_retries, "
                "parent_goal_id, created_at, updated_at, metadata "
                "FROM goals WHERE parent_goal_id = ? ORDER BY priority DESC",
                (parent_goal_id,),
            )
            rows = cursor.fetchall()
            self._close_connection(conn)
            return [self._row_to_goal(r) for r in rows]

    @staticmethod
    def _row_to_goal(row: tuple) -> dict:
        return {
            "goal_id":        row[0],
            "title":          row[1],
            "description":    row[2],
            "status":         row[3],
            "priority":       row[4],
            "owner":          row[5],
            "owner_id":       row[6],
            "deadline_utc":   row[7],
            "confidence":     row[8],
            "retry_count":    row[9],
            "max_retries":    row[10],
            "parent_goal_id": row[11],
            "created_at":     row[12],
            "updated_at":     row[13],
            "metadata":       json.loads(row[14]) if row[14] else {},
        }

    # ─── Principal CRUD (M32 Identity System) ─────────────────────────────────

    def create_principal(self, principal: dict) -> None:
        """Persists a new principal. Uses INSERT OR IGNORE for idempotent bootstrap."""
        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR IGNORE INTO principals (
                    principal_id, name, principal_type, trust_level,
                    capabilities, metadata, created_at, is_active, status, expires_at, public_key
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    principal["principal_id"],
                    principal["name"],
                    principal["principal_type"],
                    int(principal.get("trust_level", 2)),
                    json.dumps(principal.get("capabilities") or []),
                    json.dumps(principal.get("metadata") or {}),
                    principal.get("created_at"),
                    1 if principal.get("is_active", True) else 0,
                    principal.get("status", "ACTIVE"),
                    principal.get("expires_at"),
                    principal.get("public_key"),
                ),
            )
            conn.commit()
            self._close_connection(conn)

    def get_principal(self, principal_id: str) -> dict | None:
        """Retrieves a principal by ID, or None if not found."""
        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute(
                "SELECT principal_id, name, principal_type, trust_level, "
                "capabilities, metadata, created_at, is_active, status, expires_at, public_key "
                "FROM principals WHERE principal_id = ?",
                (principal_id,),
            )
            row = cursor.fetchone()
            self._close_connection(conn)
            return self._row_to_principal(row) if row else None

    def get_principal_by_name(self, name: str) -> dict | None:
        """Retrieves a principal by unique name, or None if not found."""
        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute(
                "SELECT principal_id, name, principal_type, trust_level, "
                "capabilities, metadata, created_at, is_active, status, expires_at, public_key "
                "FROM principals WHERE name = ?",
                (name,),
            )
            row = cursor.fetchone()
            self._close_connection(conn)
            return self._row_to_principal(row) if row else None

    def update_principal_status(self, principal_id: str, is_active: bool, status: str | None = None) -> None:
        """Activates or deactivates a principal (soft delete / lifecycle status update)."""
        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()
            effective_status = status
            if effective_status is None:
                effective_status = "ACTIVE" if is_active else "SUSPENDED"
            cursor.execute(
                "UPDATE principals SET is_active = ?, status = ? WHERE principal_id = ?",
                (1 if is_active else 0, effective_status, principal_id),
            )
            conn.commit()
            self._close_connection(conn)

    def list_principals(
        self,
        principal_type: str | None = None,
        active_only: bool = True,
    ) -> list[dict]:
        """Returns principals, optionally filtered by type and/or active status."""
        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()
            base = (
                "SELECT principal_id, name, principal_type, trust_level, "
                "capabilities, metadata, created_at, is_active, status, expires_at, public_key FROM principals"
            )
            conditions: list[str] = []
            params: list = []
            if active_only:
                conditions.append("is_active = 1")
            if principal_type:
                conditions.append("principal_type = ?")
                params.append(principal_type)
            query = base + (" WHERE " + " AND ".join(conditions) if conditions else "")
            query += " ORDER BY created_at"
            cursor.execute(query, params)
            rows = cursor.fetchall()
            self._close_connection(conn)
            return [self._row_to_principal(r) for r in rows]

    @staticmethod
    def _row_to_principal(row: tuple) -> dict:
        return {
            "principal_id":   row[0],
            "name":           row[1],
            "principal_type": row[2],
            "trust_level":    int(row[3]),
            "capabilities":   json.loads(row[4]) if row[4] else [],
            "metadata":       json.loads(row[5]) if row[5] else {},
            "created_at":     row[6],
            "is_active":      bool(row[7]),
            "status":         row[8] if len(row) > 8 else "ACTIVE",
            "expires_at":     row[9] if len(row) > 9 else None,
            "public_key":     row[10] if len(row) > 10 else None,
        }


    # ─── Audit Ledger CRUD (M33 Immutable Audit Ledger) ───────────────────────

    def append_audit_entry(self, entry: dict) -> None:
        """Appends a cryptographically chained audit entry to the audit log."""
        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR IGNORE INTO audit_log (
                    audit_id, timestamp, principal_id, action, resource,
                    decision, reason, arguments_hash, delegation_chain,
                    previous_hash, entry_hash
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    entry["audit_id"],
                    entry["timestamp"],
                    entry["principal_id"],
                    entry["action"],
                    entry.get("resource"),
                    entry["decision"],
                    entry.get("reason"),
                    entry["arguments_hash"],
                    json.dumps(entry.get("delegation_chain") or []),
                    entry["previous_hash"],
                    entry["entry_hash"],
                ),
            )
            conn.commit()
            self._close_connection(conn)

    def get_latest_audit_hash(self) -> str:
        """Retrieves the entry_hash of the latest audit log entry, or zeroes-block if empty."""
        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT entry_hash FROM audit_log ORDER BY timestamp DESC, rowid DESC LIMIT 1")
            row = cursor.fetchone()
            self._close_connection(conn)
            if row:
                return row[0]
            # Genesis hash: 64 zeroes block
            return "0000000000000000000000000000000000000000000000000000000000000000"

    def list_audit_entries(self) -> list[dict]:
        """Returns all audit log entries, sorted by timestamp (oldest first)."""
        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute(
                "SELECT audit_id, timestamp, principal_id, action, resource, "
                "decision, reason, arguments_hash, delegation_chain, "
                "previous_hash, entry_hash FROM audit_log ORDER BY timestamp ASC, rowid ASC"
            )
            rows = cursor.fetchall()
            self._close_connection(conn)
            return [self._row_to_audit_entry(r) for r in rows]

    @staticmethod
    def _row_to_audit_entry(row: tuple) -> dict:
        return {
            "audit_id":         row[0],
            "timestamp":        row[1],
            "principal_id":     row[2],
            "action":           row[3],
            "resource":         row[4],
            "decision":         row[5],
            "reason":           row[6],
            "arguments_hash":   row[7],
            "delegation_chain": json.loads(row[8]) if row[8] else [],
            "previous_hash":    row[9],
            "entry_hash":       row[10],
        }

    # ─── Capability Contracts CRUD (M35 Dynamic Negotiation) ─────────────────

    def create_capability_contract(self, contract: Dict[str, Any]) -> None:
        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO capability_contracts (
                    contract_id, principal_id, capability, reason, expires_at, status,
                    scope, max_uses, use_count, parent_contract_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    contract["contract_id"],
                    contract["principal_id"],
                    contract["capability"],
                    contract.get("reason"),
                    contract["expires_at"],
                    contract["status"],
                    contract.get("scope"),
                    contract.get("max_uses"),
                    contract.get("use_count", 0),
                    contract.get("parent_contract_id"),
                ),
            )
            conn.commit()
            self._close_connection(conn)

    def get_active_capability_contracts(self, principal_id: str) -> List[Dict[str, Any]]:
        with self._lock:
            import time
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT contract_id, principal_id, capability, reason, expires_at, status,
                       scope, max_uses, use_count, parent_contract_id
                FROM capability_contracts
                WHERE principal_id = ? AND status = 'APPROVED' AND expires_at > ?
                """,
                (principal_id, time.time()),
            )
            rows = cursor.fetchall()
            self._close_connection(conn)
            return [self._row_to_contract(r) for r in rows]

    def update_capability_contract_status(self, contract_id: str, status: str) -> None:
        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE capability_contracts SET status = ? WHERE contract_id = ?",
                (status, contract_id),
            )
            conn.commit()
            self._close_connection(conn)

    def get_capability_contract(self, contract_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT contract_id, principal_id, capability, reason, expires_at, status,
                       scope, max_uses, use_count, parent_contract_id
                FROM capability_contracts WHERE contract_id = ?
                """,
                (contract_id,),
            )
            row = cursor.fetchone()
            self._close_connection(conn)
            return self._row_to_contract(row) if row else None

    def increment_contract_use_count(self, contract_id: str) -> None:
        """Atomically increments the use_count for a capability contract lease."""
        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE capability_contracts SET use_count = use_count + 1 WHERE contract_id = ?",
                (contract_id,),
            )
            conn.commit()
            self._close_connection(conn)

    def get_contracts_by_parent(self, parent_contract_id: str) -> List[Dict[str, Any]]:
        """Returns all contracts that have the given parent_contract_id (delegation chain children)."""
        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT contract_id, principal_id, capability, reason, expires_at, status,
                       scope, max_uses, use_count, parent_contract_id
                FROM capability_contracts WHERE parent_contract_id = ?
                """,
                (parent_contract_id,),
            )
            rows = cursor.fetchall()
            self._close_connection(conn)
            return [self._row_to_contract(r) for r in rows]

    @staticmethod
    def _row_to_contract(row: tuple) -> Dict[str, Any]:
        return {
            "contract_id": row[0],
            "principal_id": row[1],
            "capability": row[2],
            "reason": row[3],
            "expires_at": row[4],
            "status": row[5],
            "scope": row[6] if len(row) > 6 else None,
            "max_uses": row[7] if len(row) > 7 else None,
            "use_count": row[8] if len(row) > 8 else 0,
            "parent_contract_id": row[9] if len(row) > 9 else None,
        }


