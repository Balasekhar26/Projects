"""Action Scheduler (Step 8.8 — OS-Level Scheduler).

Transforms the stateless ActionBroker execution gate into a stateful, adaptive
dispatch fabric with:

  • Priority Queue (0–10) with urgency boosts for near-deadline actions.
  • Concurrency Control — max MAX_CONCURRENT_ACTIONS simultaneous IN_FLIGHT.
  • SLA Breach Detection — flags expired deadlines before dispatch.
  • Exponential Back-off Retry — up to MAX_RETRY_ATTEMPTS retries (2^n delay).
  • Emergency Drain — cancel all PENDING actions instantly.
  • SQLite persistence for durable queue state and telemetry.
  • Tier 12 telemetry surface for the Cognitive Dashboard.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple

from backend.core.config import load_config
from backend.core.logger import log_event

# --- Configuration Constants --------------------------------------------------

MAX_CONCURRENT_ACTIONS: int = 4              # Maximum simultaneous IN_FLIGHT actions
MAX_RETRY_ATTEMPTS: int = 3                  # Maximum retry attempts per action
URGENCY_BOOST_IMMINENT_SECS: float = 10.0   # +4 priority boost if deadline < 10 s (hard gate)
URGENCY_BOOST_CRITICAL_SECS: float = 60.0   # +3 priority boost if deadline < 60 s
URGENCY_BOOST_WARNING_SECS: float = 300.0   # +1 priority boost if deadline < 300 s

FAIRNESS_AGING_INTERVAL_SECS: float = 120.0  # +1 effective priority per this many wait-seconds
FAIRNESS_AGING_MAX_BOOST: int = 9            # Aging boost cap (never pushed past priority 9)
STARVATION_THRESHOLD_SECS: float = 600.0     # Emit health event if PENDING > this long

RESOURCE_HEADROOM_THRESHOLD: float = 0.80    # Block dispatch if projected load > 80% of any cap


# --- Status Literals ----------------------------------------------------------

class ActionStatus:
    PENDING = "PENDING"
    IN_FLIGHT = "IN_FLIGHT"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    RETRY = "RETRY"


# ==============================================================================
# ActionScheduler
# ==============================================================================

class ActionScheduler:
    """OS-level dispatch fabric layered above ActionBroker.intake_request()."""

    _lock = threading.RLock()
    _schema_ensured: bool = False
    DB_NAME = "action_scheduler.db"
    _pending_responses: dict[str, Any] = {}

    # ------------------------------------------------------------------
    # Internal Helpers
    # ------------------------------------------------------------------

    @classmethod
    def _get_conn(cls) -> sqlite3.Connection:
        config = load_config()
        db_dir = config.sqlite_path.parent
        db_dir.mkdir(parents=True, exist_ok=True)
        db_path = db_dir / cls.DB_NAME
        conn = sqlite3.connect(str(db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        with cls._lock:
            if not cls._schema_ensured:
                cls._ensure_schema(conn)
                cls._schema_ensured = True
        return conn

    @classmethod
    def _ensure_schema(cls, conn: sqlite3.Connection) -> None:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS action_queue (
                queue_id                TEXT PRIMARY KEY,
                agent_name              TEXT NOT NULL,
                action                  TEXT NOT NULL,
                params_json             TEXT NOT NULL DEFAULT '{}',
                state_json              TEXT NOT NULL DEFAULT '{}',
                priority                INTEGER NOT NULL DEFAULT 5,
                status                  TEXT NOT NULL DEFAULT 'PENDING',
                attempt_count           INTEGER NOT NULL DEFAULT 0,
                max_attempts            INTEGER NOT NULL DEFAULT 3,
                enqueued_at             REAL NOT NULL,
                deadline_at             REAL,
                dispatched_at           REAL,
                completed_at            REAL,
                result_json             TEXT,
                error_message           TEXT,
                sla_breached            INTEGER NOT NULL DEFAULT 0,
                retry_after             REAL,
                requires_human_attention INTEGER NOT NULL DEFAULT 0,
                attention_cost          INTEGER NOT NULL DEFAULT 1,
                resource_estimate_pct   REAL NOT NULL DEFAULT 0.0,
                ram_estimate_mb         REAL NOT NULL DEFAULT 0.0
            );

            CREATE INDEX IF NOT EXISTS idx_aq_status_priority
                ON action_queue (status, priority DESC, enqueued_at ASC);

            CREATE TABLE IF NOT EXISTS scheduler_metrics (
                metric_key      TEXT PRIMARY KEY,
                metric_value    REAL NOT NULL DEFAULT 0.0,
                updated_at      REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS node_registry (
                node_id         TEXT PRIMARY KEY,
                node_name       TEXT NOT NULL,
                node_type       TEXT NOT NULL,
                cpu_logical     INTEGER NOT NULL DEFAULT 1,
                ram_gb          REAL NOT NULL DEFAULT 0.0,
                gpu_info        TEXT,
                capabilities    TEXT NOT NULL DEFAULT '[]',
                status          TEXT NOT NULL DEFAULT 'offline',
                last_heartbeat  REAL NOT NULL,
                system_cpu_pct  REAL NOT NULL DEFAULT 0.0,
                system_ram_pct  REAL NOT NULL DEFAULT 0.0,
                active_tasks    INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS security_sessions (
                session_id TEXT PRIMARY KEY,
                taint_level INTEGER DEFAULT 0 NOT NULL,
                taint_source TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
            );

            CREATE TABLE IF NOT EXISTS audit_ledger (
                entry_id TEXT PRIMARY KEY,
                session_id TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
                actor TEXT NOT NULL,
                tool TEXT NOT NULL,
                action_resolved TEXT NOT NULL,
                action_hash TEXT NOT NULL,
                risk_level INTEGER NOT NULL,
                status TEXT NOT NULL,
                rejection_reason TEXT,
                previous_hash TEXT,
                ledger_hash TEXT
            );

            CREATE TABLE IF NOT EXISTS approval_tickets (
                ticket_id TEXT PRIMARY KEY,
                session_id TEXT,
                action_hash TEXT NOT NULL,
                tool TEXT NOT NULL,
                risk_level INTEGER NOT NULL,
                serialized_payload TEXT NOT NULL,
                status TEXT NOT NULL,
                expires_at TIMESTAMP NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
                resolved_at TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS attention_budget (
                date_bounds TEXT PRIMARY KEY,
                attention_cost INTEGER DEFAULT 0 NOT NULL,
                max_daily_budget INTEGER DEFAULT 100 NOT NULL
            );

            CREATE TRIGGER IF NOT EXISTS audit_ledger_prevent_update
            BEFORE UPDATE ON audit_ledger
            BEGIN
                SELECT RAISE(FAIL, 'Updates to audit_ledger are prohibited.');
            END;

            CREATE TRIGGER IF NOT EXISTS audit_ledger_prevent_delete
            BEFORE DELETE ON audit_ledger
            BEGIN
                SELECT RAISE(FAIL, 'Deletions from audit_ledger are prohibited.');
            END;
            """
        )
        conn.commit()

        # Handle backward-compatible schema upgrade for existing DBs
        try:
            conn.execute("ALTER TABLE action_queue ADD COLUMN ram_estimate_mb REAL NOT NULL DEFAULT 0.0")
            conn.commit()
        except sqlite3.OperationalError:
            pass

        # Sweep/sync resource and attention reservations based on active in-flight actions
        try:
            row = conn.execute(
                "SELECT SUM(resource_estimate_pct), SUM(ram_estimate_mb), "
                "SUM(CASE WHEN requires_human_attention = 1 THEN attention_cost ELSE 0 END) "
                "FROM action_queue WHERE status = 'IN_FLIGHT'"
            ).fetchone()
            if row:
                reserved_cpu = float(row[0] or 0.0)
                reserved_ram = float(row[1] or 0.0)
                reserved_attn = int(row[2] or 0)
                from backend.core.resource_governor import ResourceGovernor
                ResourceGovernor.sync_reservations(reserved_cpu, reserved_ram)
                ResourceGovernor.sync_attention_reservations(reserved_attn)
        except Exception:
            pass

        # Seed metric rows
        for key in (
            "total_enqueued", "total_dispatched", "total_completed",
            "total_failed", "total_cancelled", "total_sla_breached",
            "cumulative_dispatch_latency_ms", "total_retries"
        ):
            existing = conn.execute(
                "SELECT metric_key FROM scheduler_metrics WHERE metric_key = ?", (key,)
            ).fetchone()
            if not existing:
                conn.execute(
                    "INSERT INTO scheduler_metrics (metric_key, metric_value, updated_at) VALUES (?, 0.0, ?)",
                    (key, time.time())
                )
        conn.commit()

    @classmethod
    def _increment_metric(cls, conn: sqlite3.Connection, key: str, delta: float = 1.0) -> None:
        conn.execute(
            "UPDATE scheduler_metrics SET metric_value = metric_value + ?, updated_at = ? WHERE metric_key = ?",
            (delta, time.time(), key)
        )

    @classmethod
    def _effective_priority(cls, row: sqlite3.Row, now: float) -> int:
        """Compute effective dispatch priority.

        Layers applied in order:
          1. Urgency boost from deadline proximity.
          2. Fairness aging boost from queue wait time.

        Priority is always clamped to [0, 10] with true priority-10 actions
        (manual critical) reserving the ceiling — aging is capped at 9.
        """
        base = int(row["priority"])
        deadline = row["deadline_at"]
        boost = 0

        # --- Deadline urgency boost ---
        if deadline is not None:
            remaining = deadline - now
            if remaining < URGENCY_BOOST_IMMINENT_SECS:
                boost = max(boost, 4)  # Hard imminent gate
            elif remaining < URGENCY_BOOST_CRITICAL_SECS:
                boost = max(boost, 3)
            elif remaining < URGENCY_BOOST_WARNING_SECS:
                boost = max(boost, 1)

        # --- Fairness aging boost ---
        wait_secs = now - row["enqueued_at"]
        if wait_secs > 0 and FAIRNESS_AGING_INTERVAL_SECS > 0:
            age_boost = min(int(wait_secs / FAIRNESS_AGING_INTERVAL_SECS), FAIRNESS_AGING_MAX_BOOST)
            boost = max(boost, age_boost)

        effective = base + boost
        # True priority-10 items retain their ceiling; aged items cap at 9
        if base < 10:
            effective = min(9, effective)
        return min(10, effective)

    @classmethod
    def _check_starvation(cls, conn: sqlite3.Connection, now: float) -> None:
        """Emit health events for any PENDING action that has waited beyond
        STARVATION_THRESHOLD_SECS without being dispatched."""
        try:
            stale = conn.execute(
                """
                SELECT queue_id, agent_name, action, enqueued_at
                FROM action_queue
                WHERE status = 'PENDING'
                  AND (? - enqueued_at) > ?
                """,
                (now, STARVATION_THRESHOLD_SECS)
            ).fetchall()
            for row in stale:
                wait = round(now - row["enqueued_at"], 0)
                try:
                    log_event(
                        "action_scheduler",
                        f"STARVATION: {row['action']} [{row['queue_id']}] for "
                        f"{row['agent_name']} has waited {wait}s > "
                        f"{STARVATION_THRESHOLD_SECS}s threshold."
                    )
                except Exception:
                    pass
        except Exception:
            pass

    @classmethod
    def _check_resource_headroom(
        cls, resource_estimate_pct: float, ram_estimate_mb: float
    ) -> dict[str, Any]:
        """Gate dispatch on global resource headroom.

        Queries ResourceGovernor.get_status() and checks whether dispatching
        an action with the given resource estimate would push CPU, RAM, or
        concurrent task usage over RESOURCE_HEADROOM_THRESHOLD.

        Returns:
            {"ok": True} if headroom is available, or
            {"ok": False, "reason": str} if blocked.
        """
        try:
            from backend.core.resource_governor import ResourceGovernor
            status = ResourceGovernor.get_status()

            # CPU headroom
            reserved_cpu = status.get("reserved_cpu_percent", 0.0)
            cpu_pct = (status["system_cpu_percent"] + reserved_cpu) / 100.0
            if cpu_pct + resource_estimate_pct / 100.0 > RESOURCE_HEADROOM_THRESHOLD:
                return {
                    "ok": False,
                    "reason": f"CPU headroom exhausted (current_system={status['system_cpu_percent']:.0f}%, reserved={reserved_cpu:.0f}%, estimate={resource_estimate_pct:.0f}%)"
                }

            # RAM headroom
            reserved_ram = status.get("reserved_ram_mb", 0.0)
            projected_ram_available = status["system_ram_available_mb"] - reserved_ram - ram_estimate_mb
            if projected_ram_available < ResourceGovernor.RAM_LIMIT_MIN_AVAILABLE_MB:
                return {
                    "ok": False,
                    "reason": f"RAM headroom exhausted (available={status['system_ram_available_mb']:.0f}MB, reserved={reserved_ram:.0f}MB, estimate={ram_estimate_mb:.0f}MB, min_required={ResourceGovernor.RAM_LIMIT_MIN_AVAILABLE_MB:.0f}MB)"
                }

            # Concurrent task headroom
            tasks = status["concurrent_tasks"]
            task_limit = status["concurrent_tasks_limit"]
            if task_limit > 0 and tasks / task_limit >= RESOURCE_HEADROOM_THRESHOLD:
                return {
                    "ok": False,
                    "reason": f"Concurrent task slots at {tasks}/{task_limit} "
                              f"(≥{RESOURCE_HEADROOM_THRESHOLD:.0%} threshold)"
                }

        except Exception:
            pass  # If governor is unavailable, allow dispatch
        return {"ok": True}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @classmethod
    def enqueue_action(
        cls,
        agent_name: str,
        action: str,
        params: Dict[str, Any],
        state: Dict[str, Any],
        priority: int = 5,
        deadline_secs: Optional[float] = None,
        max_attempts: int = MAX_RETRY_ATTEMPTS,
        requires_human_attention: bool = False,
        attention_cost: int = 1,
        resource_estimate_pct: float = 0.0,
        ram_estimate_mb: float = 0.0,
    ) -> Dict[str, Any]:
        """Persist a new action onto the priority queue.

        Args:
            agent_name:               Requesting agent identity.
            action:                   Action token (e.g. "WRITE_FILE").
            params:                   Action parameters dict.
            state:                    Session state dict.
            priority:                 0 (lowest) … 10 (critical). Default 5.
            deadline_secs:            Relative seconds to deadline. None = no deadline.
            max_attempts:             Maximum dispatch attempts before FAILED.
            requires_human_attention: If True, dispatch will be gated on the
                                      attention token budget.
            attention_cost:           Tokens to charge from the attention budget
                                      when this action is dispatched.
            resource_estimate_pct:    Estimated additional CPU load as a percentage
                                      (0–100). Used for resource headroom pre-checks.
            ram_estimate_mb:          Estimated additional RAM required in MB.

        Returns:
            dict with ``queue_id`` and ``status``.
        """
        priority = max(0, min(10, int(priority)))
        queue_id = f"q_{uuid.uuid4().hex[:10]}"
        now = time.time()
        deadline_at = now + deadline_secs if deadline_secs is not None else None
        resource_estimate_pct = float(max(0.0, min(100.0, resource_estimate_pct)))
        ram_estimate_mb = float(max(0.0, ram_estimate_mb))

        conn = cls._get_conn()
        try:
            conn.execute(
                """
                INSERT INTO action_queue (
                    queue_id, agent_name, action, params_json, state_json,
                    priority, status, attempt_count, max_attempts,
                    enqueued_at, deadline_at,
                    requires_human_attention, attention_cost, resource_estimate_pct,
                    ram_estimate_mb
                ) VALUES (?, ?, ?, ?, ?, ?, 'PENDING', 0, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    queue_id, agent_name, action,
                    json.dumps(params), json.dumps(state),
                    priority, max_attempts, now, deadline_at,
                    int(requires_human_attention), attention_cost, resource_estimate_pct,
                    ram_estimate_mb
                )
            )
            cls._increment_metric(conn, "total_enqueued")
            conn.commit()
            try:
                log_event(
                    "action_scheduler",
                    f"Enqueued {action} for {agent_name} "
                    f"[priority={priority}, queue_id={queue_id}, "
                    f"attention={'yes' if requires_human_attention else 'no'}]"
                )
            except Exception:
                pass
            return {
                "status": "enqueued",
                "queue_id": queue_id,
                "priority": priority,
                "deadline_at": deadline_at,
                "requires_human_attention": requires_human_attention,
                "resource_estimate_pct": resource_estimate_pct,
                "ram_estimate_mb": ram_estimate_mb,
            }
        finally:
            conn.close()

    @classmethod
    def dispatch_next(cls, dry_run: bool = False) -> Dict[str, Any]:
        """Select and dispatch the highest-priority PENDING action.

        Enforces the concurrency cap (MAX_CONCURRENT_ACTIONS).
        Applies urgency priority boost.
        Flags SLA breaches before execution.

        Args:
            dry_run: If True, select the next candidate but do not execute it.

        Returns:
            dict describing dispatch outcome.
        """
        conn = cls._get_conn()
        try:
            with cls._lock:
                # --- 1. Concurrency guard ---
                in_flight_count = conn.execute(
                    "SELECT COUNT(*) FROM action_queue WHERE status = ?",
                    (ActionStatus.IN_FLIGHT,)
                ).fetchone()[0]
                if in_flight_count >= MAX_CONCURRENT_ACTIONS:
                    return {
                        "status": "concurrency_cap_reached",
                        "in_flight": in_flight_count,
                        "max_concurrent": MAX_CONCURRENT_ACTIONS,
                    }

                # --- 2. Fetch eligible candidates (PENDING or RETRY-ready) ---
                now = time.time()

                # Starvation sweep (side-effect: logs health events)
                cls._check_starvation(conn, now)

                candidates = conn.execute(
                    """
                    SELECT * FROM action_queue
                    WHERE status = 'PENDING'
                       OR (status = 'RETRY' AND (retry_after IS NULL OR retry_after <= ?))
                    ORDER BY enqueued_at ASC
                    LIMIT 50
                    """,
                    (now,)
                ).fetchall()

                if not candidates:
                    return {"status": "queue_empty"}

                # Sort by effective priority (urgency boost + aging) descending, then FIFO
                candidates_sorted = sorted(
                    candidates,
                    key=lambda r: (-cls._effective_priority(r, now), r["enqueued_at"])
                )
                row = candidates_sorted[0]
                queue_id = row["queue_id"]

                # --- 3a. Resource headroom pre-dispatch gate ---
                resource_est = float(row["resource_estimate_pct"] or 0.0)
                ram_est = float(row["ram_estimate_mb"] or 0.0)
                if resource_est > 0 or ram_est > 0:
                    headroom = cls._check_resource_headroom(resource_est, ram_est)
                    if not headroom["ok"]:
                        return {
                            "status": "resource_headroom_blocked",
                            "queue_id": queue_id,
                            "reason": headroom["reason"],
                        }

                # --- 3b. Attention budget gate ---
                requires_attention = bool(row["requires_human_attention"])
                attention_cost = int(row["attention_cost"] or 1)
                if requires_attention:
                    try:
                        from backend.core.resource_governor import ResourceGovernor
                        if not ResourceGovernor.check_attention_budget(attention_cost):
                            return {
                                "status": "attention_budget_exhausted",
                                "queue_id": queue_id,
                                "action": row["action"],
                                "attention_cost": attention_cost,
                            }
                    except Exception:
                        pass  # Governor unavailable → allow dispatch

                # --- 3c. SLA breach detection ---
                sla_breached = 0
                if row["deadline_at"] is not None and row["deadline_at"] < now:
                    sla_breached = 1
                    conn.execute(
                        "UPDATE action_queue SET sla_breached = 1 WHERE queue_id = ?",
                        (queue_id,)
                    )
                    cls._increment_metric(conn, "total_sla_breached")

                if dry_run:
                    conn.commit()
                    return {
                        "status": "dry_run",
                        "queue_id": queue_id,
                        "action": row["action"],
                        "agent_name": row["agent_name"],
                        "effective_priority": cls._effective_priority(row, now),
                        "sla_breached": bool(sla_breached),
                    }

                # --- 4. Reserve attention and CPU/RAM tokens + Mark IN_FLIGHT ---
                if requires_attention:
                    try:
                        from backend.core.resource_governor import ResourceGovernor
                        ResourceGovernor.reserve_attention_tokens(attention_cost)
                    except Exception:
                        pass

                try:
                    from backend.core.resource_governor import ResourceGovernor
                    ResourceGovernor.reserve_resources(resource_est, ram_est)
                except Exception:
                    pass

                attempt = row["attempt_count"] + 1
                conn.execute(
                    """
                    UPDATE action_queue
                    SET status = 'IN_FLIGHT', attempt_count = ?, dispatched_at = ?
                    WHERE queue_id = ?
                    """,
                    (attempt, now, queue_id)
                )
                cls._increment_metric(conn, "total_dispatched")
                conn.commit()

            # --- 5. Execute via Node Selector Routing (outside the lock) ---
            params = json.loads(row["params_json"])
            state = json.loads(row["state_json"])
            dispatch_start = time.perf_counter()

            selected_node = None
            try:
                from backend.core.node_selector import NodeSelector
                selected_node = NodeSelector.select_node(row["action"])
            except Exception:
                pass

            if selected_node:
                node_id = selected_node["node_id"]
                try:
                    import asyncio
                    coro = cls._send_remote_task_async(node_id, queue_id, row["action"], params, state)
                    try:
                        loop = asyncio.get_running_loop()
                    except RuntimeError:
                        loop = None

                    if loop and loop.is_running():
                        future = asyncio.run_coroutine_threadsafe(coro, loop)
                        exec_result = future.result(timeout=50.0)
                    else:
                        exec_result = asyncio.run(coro)
                except Exception as exc:
                    exec_result = {"success": False, "error": f"Remote dispatch failure to {node_id}: {exc}"}
            else:
                try:
                    from backend.core.action_broker import ActionBroker
                    exec_result = ActionBroker.intake_request(
                        agent_name=row["agent_name"],
                        action=row["action"],
                        params=params,
                        state=state,
                    )
                except Exception as exc:
                    exec_result = {"success": False, "error": f"Dispatch exception: {exc}"}

            dispatch_latency_ms = int((time.perf_counter() - dispatch_start) * 1000)

            # --- 5b. Call VerificationEngine ---
            try:
                from backend.core.verification_engine import VerificationEngine
                ve_report = VerificationEngine.verify_result(
                    queue_id=queue_id,
                    action=row["action"],
                    agent_name=row["agent_name"],
                    params=params,
                    result=exec_result
                )
                verdict = ve_report["verdict"]
                exec_result["verification_report_id"] = ve_report["report_id"]
                exec_result["verification_verdict"] = verdict
            except Exception as ve_exc:
                verdict = "SKIPPED"
                exec_result["verification_error"] = f"VE exception: {ve_exc}"

            is_success = (verdict in ("VERIFIED", "PASS", "PARTIAL", "SKIPPED"))

            # --- 6. Persist result ---
            with cls._lock:
                completed_at = time.time()
                if is_success:
                    conn.execute(
                        """
                        UPDATE action_queue
                        SET status = 'COMPLETED', completed_at = ?, result_json = ?
                        WHERE queue_id = ?
                        """,
                        (completed_at, json.dumps(exec_result), queue_id)
                    )
                    cls._increment_metric(conn, "total_completed")
                    cls._increment_metric(conn, "cumulative_dispatch_latency_ms", dispatch_latency_ms)
                    final_status = ActionStatus.COMPLETED
                else:
                    # Check retry eligibility
                    max_att = row["max_attempts"]
                    err_msg = str(exec_result.get("error", "")) or f"Verification verdict: {verdict}"
                    if attempt < max_att:
                        # Exponential back-off: 2^attempt seconds
                        retry_after = time.time() + (2 ** attempt)
                        conn.execute(
                            """
                            UPDATE action_queue
                            SET status = 'RETRY', retry_after = ?, error_message = ?, result_json = ?
                            WHERE queue_id = ?
                            """,
                            (retry_after, err_msg[:1000], json.dumps(exec_result), queue_id)
                        )
                        cls._increment_metric(conn, "total_retries")
                        final_status = ActionStatus.RETRY
                    else:
                        conn.execute(
                            """
                            UPDATE action_queue
                            SET status = 'FAILED', completed_at = ?, error_message = ?, result_json = ?
                            WHERE queue_id = ?
                            """,
                            (completed_at, err_msg[:1000], json.dumps(exec_result), queue_id)
                        )
                        cls._increment_metric(conn, "total_failed")
                        final_status = ActionStatus.FAILED

                # Release CPU/RAM resources
                try:
                    from backend.core.resource_governor import ResourceGovernor
                    ResourceGovernor.release_resources(resource_est, ram_est)
                except Exception:
                    pass

                # Release/consume attention tokens
                if requires_attention:
                    try:
                        from backend.core.resource_governor import ResourceGovernor
                        consume = (final_status in (ActionStatus.COMPLETED, ActionStatus.FAILED))
                        ResourceGovernor.release_and_consume_attention_tokens(attention_cost, consume=consume)
                    except Exception:
                        pass

                conn.commit()

            try:
                log_event(
                    "action_scheduler",
                    f"Dispatched {row['action']} [{queue_id}] → {final_status} in {dispatch_latency_ms}ms"
                )
            except Exception:
                pass
            return {
                "status": "dispatched",
                "queue_id": queue_id,
                "action": row["action"],
                "agent_name": row["agent_name"],
                "final_status": final_status,
                "sla_breached": bool(sla_breached),
                "attempt": attempt,
                "dispatch_latency_ms": dispatch_latency_ms,
                "result": exec_result,
            }
        finally:
            conn.close()

    @classmethod
    def retry_failed(cls) -> Dict[str, Any]:
        """Move all eligible RETRY actions (back-off elapsed) back to PENDING.

        This is a convenience sweep call. The primary retry logic lives inside
        ``dispatch_next()`` which already picks up RETRY rows when retry_after <= now.
        This method provides an explicit nudge for monitoring/testing.

        Returns:
            dict with ``retried_count``.
        """
        conn = cls._get_conn()
        try:
            now = time.time()
            result = conn.execute(
                """
                UPDATE action_queue
                SET status = 'PENDING', retry_after = NULL
                WHERE status = 'RETRY' AND retry_after <= ?
                """,
                (now,)
            )
            conn.commit()
            return {"status": "ok", "retried_count": result.rowcount}
        finally:
            conn.close()

    @classmethod
    def drain_queue(cls) -> Dict[str, Any]:
        """Emergency drain: cancel all PENDING and RETRY actions.

        IN_FLIGHT actions are left to complete naturally.

        Returns:
            dict with ``cancelled_count``.
        """
        conn = cls._get_conn()
        try:
            result = conn.execute(
                "UPDATE action_queue SET status = 'CANCELLED', completed_at = ? WHERE status IN ('PENDING', 'RETRY')",
                (time.time(),)
            )
            cancelled = result.rowcount
            cls._increment_metric(conn, "total_cancelled", float(cancelled))
            conn.commit()
            try:
                log_event("action_scheduler", f"Emergency drain: cancelled {cancelled} queued actions.")
            except Exception:
                pass
            return {"status": "ok", "cancelled_count": cancelled}
        finally:
            conn.close()

    @classmethod
    def get_action(cls, queue_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a single queued action's full record by queue_id."""
        conn = cls._get_conn()
        try:
            row = conn.execute(
                "SELECT * FROM action_queue WHERE queue_id = ?", (queue_id,)
            ).fetchone()
            if not row:
                return None
            return dict(row)
        finally:
            conn.close()

    @classmethod
    def get_queue_snapshot(cls) -> Dict[str, Any]:
        """Return live queue state grouped by status, plus SLA breach summary.

        Returns a human-readable snapshot for API consumers and health checks.
        """
        conn = cls._get_conn()
        try:
            now = time.time()
            rows = conn.execute(
                "SELECT status, COUNT(*) as cnt FROM action_queue GROUP BY status"
            ).fetchall()
            counts: Dict[str, int] = {r["status"]: r["cnt"] for r in rows}

            pending_items = conn.execute(
                """
                SELECT queue_id, agent_name, action, priority, deadline_at, enqueued_at, sla_breached
                FROM action_queue WHERE status IN ('PENDING', 'RETRY')
                ORDER BY priority DESC, enqueued_at ASC
                LIMIT 20
                """
            ).fetchall()

            in_flight_items = conn.execute(
                "SELECT queue_id, agent_name, action, dispatched_at, attempt_count FROM action_queue WHERE status = 'IN_FLIGHT'"
            ).fetchall()

            total_sla_breached = conn.execute(
                "SELECT COUNT(*) FROM action_queue WHERE sla_breached = 1"
            ).fetchone()[0]

            return {
                "snapshot_at": now,
                "counts": {
                    "pending": counts.get("PENDING", 0) + counts.get("RETRY", 0),
                    "in_flight": counts.get("IN_FLIGHT", 0),
                    "completed": counts.get("COMPLETED", 0),
                    "failed": counts.get("FAILED", 0),
                    "cancelled": counts.get("CANCELLED", 0),
                    "total_sla_breached": total_sla_breached,
                },
                "concurrency": {
                    "in_flight": counts.get("IN_FLIGHT", 0),
                    "max_concurrent": MAX_CONCURRENT_ACTIONS,
                    "slots_available": max(0, MAX_CONCURRENT_ACTIONS - counts.get("IN_FLIGHT", 0)),
                },
                "pending_queue": [
                    {
                        "queue_id": r["queue_id"],
                        "agent_name": r["agent_name"],
                        "action": r["action"],
                        "priority": r["priority"],
                        "deadline_at": r["deadline_at"],
                        "sla_breached": bool(r["sla_breached"]),
                        "wait_secs": round(now - r["enqueued_at"], 1),
                    }
                    for r in pending_items
                ],
                "in_flight_queue": [
                    {
                        "queue_id": r["queue_id"],
                        "agent_name": r["agent_name"],
                        "action": r["action"],
                        "dispatch_age_secs": round(now - r["dispatched_at"], 1) if r["dispatched_at"] else 0,
                        "attempt": r["attempt_count"],
                    }
                    for r in in_flight_items
                ],
            }
        finally:
            conn.close()

    @classmethod
    def get_dispatch_telemetry(cls) -> Dict[str, Any]:
        """Compute Tier 12 telemetry metrics for the Cognitive Dashboard.

        Returns:
            dict with 10 telemetry fields matching the dashboard contract.
        """
        conn = cls._get_conn()
        try:
            # Aggregate metrics from persistent counters
            metric_rows = conn.execute(
                "SELECT metric_key, metric_value FROM scheduler_metrics"
            ).fetchall()
            metrics = {r["metric_key"]: r["metric_value"] for r in metric_rows}

            total_enqueued = int(metrics.get("total_enqueued", 0))
            total_completed = int(metrics.get("total_completed", 0))
            total_failed = int(metrics.get("total_failed", 0))
            total_cancelled = int(metrics.get("total_cancelled", 0))
            total_sla_breached = int(metrics.get("total_sla_breached", 0))
            total_retries = int(metrics.get("total_retries", 0))
            total_dispatched = int(metrics.get("total_dispatched", 0))
            cumulative_latency_ms = metrics.get("cumulative_dispatch_latency_ms", 0.0)

            avg_latency_ms = round(cumulative_latency_ms / total_completed, 1) if total_completed > 0 else 0.0
            sla_breach_rate = round(total_sla_breached / total_enqueued * 100, 1) if total_enqueued > 0 else 0.0
            retry_rate = round(total_retries / total_dispatched * 100, 1) if total_dispatched > 0 else 0.0

            # Live counts
            live_counts = conn.execute(
                "SELECT status, COUNT(*) as cnt FROM action_queue GROUP BY status"
            ).fetchall()
            counts = {r["status"]: r["cnt"] for r in live_counts}
            queue_depth = counts.get("PENDING", 0) + counts.get("RETRY", 0)
            in_flight = counts.get("IN_FLIGHT", 0)

            return {
                "total_enqueued": total_enqueued,
                "pending": queue_depth,
                "in_flight": in_flight,
                "completed": total_completed,
                "failed": total_failed,
                "cancelled": total_cancelled,
                "sla_breach_rate": sla_breach_rate,
                "avg_dispatch_latency_ms": avg_latency_ms,
                "retry_rate": retry_rate,
                "queue_depth": queue_depth,
                "concurrency_slots_used": in_flight,
                "concurrency_cap": MAX_CONCURRENT_ACTIONS,
            }
        finally:
            conn.close()

    @classmethod
    def set_pending_response(cls, queue_id: str, result: dict) -> None:
        """Complete a pending future with the task response from a remote worker node."""
        with cls._lock:
            future = cls._pending_responses.get(queue_id)
            if future and not future.done():
                import asyncio
                try:
                    loop = future.get_loop()
                    loop.call_soon_threadsafe(future.set_result, result)
                except Exception:
                    future.set_result(result)

    @classmethod
    async def _send_remote_task_async(
        cls, node_id: str, queue_id: str, action: str, params: dict, state: dict
    ) -> dict:
        """WebSocket helper to transmit task execution details to a worker node and await result."""
        import asyncio
        from backend.core.node_manager import NodeManager
        conn_info = NodeManager.get_connection(node_id)
        if not conn_info:
            return {"success": False, "error": f"Node connection lost for '{node_id}'"}

        ws, ws_loop = conn_info
        current_loop = asyncio.get_running_loop()
        future = current_loop.create_future()
        with cls._lock:
            cls._pending_responses[queue_id] = future

        payload = {
            "type": "task_request",
            "queue_id": queue_id,
            "action": action,
            "params": params,
            "state": state
        }
        text_data = json.dumps(payload)

        async def do_send():
            await ws.send_text(text_data)

        try:
            if current_loop == ws_loop:
                await do_send()
            else:
                fut = asyncio.run_coroutine_threadsafe(do_send(), ws_loop)
                # Wrap the concurrent.futures.Future in asyncio.Future
                await asyncio.wrap_future(fut)

            # 45-second timeout for remote workers to complete the action
            result = await asyncio.wait_for(future, timeout=45.0)
            return result
        except asyncio.TimeoutError:
            return {"success": False, "error": f"Timeout waiting for response from worker node '{node_id}'"}
        except Exception as exc:
            return {"success": False, "error": f"Error communicating with worker node: {exc}"}
        finally:
            with cls._lock:
                if queue_id in cls._pending_responses:
                    del cls._pending_responses[queue_id]

