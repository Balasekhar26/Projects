import datetime
import json
import hashlib
import uuid
from typing import Dict, Any, Tuple
from backend.core.risk_classifier import RiskClassifier

class ApprovalEngine:
    def __init__(self, db_conn):
        self.db = db_conn
        self.classifier = RiskClassifier(db_conn)

    def set_session_taint(self, session_id: str, taint_level: int, source: str) -> None:
        """
        Raise session taint levels thread-safely in the database.
        Taint can only be upgraded (i.e. increased), never lowered by automated pipelines.
        """
        cursor = self.db.cursor()
        cursor.execute("SELECT taint_level FROM security_sessions WHERE session_id = ?", (session_id,))
        row = cursor.fetchone()
        if not row:
            cursor.execute(
                "INSERT INTO security_sessions (session_id, taint_level, taint_source) VALUES (?, ?, ?)",
                (session_id, taint_level, source)
            )
        else:
            current_taint = row[0]
            if taint_level > current_taint:
                cursor.execute(
                    "UPDATE security_sessions SET taint_level = ?, taint_source = ? WHERE session_id = ?",
                    (taint_level, source, session_id)
                )
        self.db.commit()

    def get_risk_cost(self, risk_level: int) -> int:
        if risk_level <= 1:
            return 0
        elif risk_level == 2:
            return 1
        elif risk_level == 3:
            return 3
        elif risk_level == 4:
            return 10
        else:
            return 20

    def check_and_increment_budget(self, risk_level: int) -> bool:
        today = datetime.date.today().isoformat()
        cost = self.get_risk_cost(risk_level)
        if cost == 0:
            return True
            
        cursor = self.db.cursor()
        cursor.execute("SELECT attention_cost, max_daily_budget FROM attention_budget WHERE date_bounds = ?", (today,))
        row = cursor.fetchone()
        if not row:
            try:
                cursor.execute(
                    "INSERT INTO attention_budget (date_bounds, attention_cost, max_daily_budget) VALUES (?, 0, 100)",
                    (today,)
                )
                self.db.commit()
            except Exception:
                pass
            current_cost = 0
            max_budget = 100
        else:
            current_cost, max_budget = row[0], row[1]
            
        if current_cost + cost > max_budget:
            return False
            
        # Atomic update
        cursor.execute(
            "UPDATE attention_budget SET attention_cost = attention_cost + ? WHERE date_bounds = ? AND attention_cost + ? <= max_daily_budget",
            (cost, today, cost)
        )
        self.db.commit()
        
        # Verify if the update succeeded
        cursor.execute("SELECT attention_cost FROM attention_budget WHERE date_bounds = ?", (today,))
        new_cost_row = cursor.fetchone()
        if new_cost_row and new_cost_row[0] >= current_cost + cost:
            return True
        return False

    def log_to_ledger(self, session_id: str, actor: str, tool: str, action_resolved: str, action_hash: str, risk_level: int, status: str, rejection_reason: str = None) -> None:
        """
        Appends to the audit ledger in a hash-chained manner.
        """
        cursor = self.db.cursor()
        
        # Fetch the latest ledger entry to get the previous hash
        cursor.execute("SELECT ledger_hash FROM audit_ledger ORDER BY timestamp DESC, entry_id DESC LIMIT 1")
        row = cursor.fetchone()
        previous_hash = row[0] if row else "GENESIS"
        
        entry_id = str(uuid.uuid4())
        timestamp = datetime.datetime.utcnow().isoformat()
        
        hash_payload = {
            "entry_id": entry_id,
            "session_id": session_id,
            "timestamp": timestamp,
            "actor": actor,
            "tool": tool,
            "action_resolved": action_resolved,
            "action_hash": action_hash,
            "risk_level": risk_level,
            "status": status,
            "rejection_reason": rejection_reason,
            "previous_hash": previous_hash
        }
        serialized = json.dumps(hash_payload, sort_keys=True, default=str)
        ledger_hash = hashlib.sha256(serialized.encode('utf-8')).hexdigest()
        
        cursor.execute(
            """
            INSERT INTO audit_ledger (
                entry_id, session_id, timestamp, actor, tool, action_resolved,
                action_hash, risk_level, status, rejection_reason, previous_hash, ledger_hash
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (entry_id, session_id, timestamp, actor, tool, action_resolved,
             action_hash, risk_level, status, rejection_reason, previous_hash, ledger_hash)
        )
        self.db.commit()
        from backend.core.ledger_anchor import LedgerAnchor
        LedgerAnchor.write_anchor(ledger_hash)

    def verify_audit_ledger_chain(self) -> bool:
        """
        Validates the integrity of the entire audit ledger cryptographic chain.
        Returns True if the chain is unbroken and valid, False otherwise.
        """
        cursor = self.db.cursor()
        cursor.execute("SELECT * FROM audit_ledger ORDER BY timestamp ASC, entry_id ASC")
        rows = cursor.fetchall()
        
        expected_prev_hash = "GENESIS"
        for row in rows:
            # Reconstruct hash payload matching log_to_ledger format
            hash_payload = {
                "entry_id": row["entry_id"],
                "session_id": row["session_id"],
                "timestamp": row["timestamp"],
                "actor": row["actor"],
                "tool": row["tool"],
                "action_resolved": row["action_resolved"],
                "action_hash": row["action_hash"],
                "risk_level": row["risk_level"],
                "status": row["status"],
                "rejection_reason": row["rejection_reason"],
                "previous_hash": row["previous_hash"]
            }
            serialized = json.dumps(hash_payload, sort_keys=True, default=str)
            recomputed_hash = hashlib.sha256(serialized.encode('utf-8')).hexdigest()
            
            # Verify block self-hash
            if recomputed_hash != row["ledger_hash"]:
                return False
                
            # Verify chain link
            if row["previous_hash"] != expected_prev_hash:
                return False
                
            expected_prev_hash = row["ledger_hash"]
            
        # Verify against external anchor head to prevent database rewrite attacks
        from backend.core.ledger_anchor import LedgerAnchor
        anchored_hash = LedgerAnchor.read_anchor()
        if not rows:
            return anchored_hash == "GENESIS"
        if rows[-1]["ledger_hash"] != anchored_hash:
            return False
            
        return True

    def request_execution_authorization(self, session_id: str, tool: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Assess risk and route execution requests through policy, budget, or human gate.
        """
        risk_level, action_hash = self.classifier.assess_risk(session_id, tool, payload)
        
        # Ensure session exists in the security_sessions table
        self.set_session_taint(session_id, 0, "initialization")
        
        action_str = json.dumps(payload, sort_keys=True, default=str)
        
        if risk_level == 5:
            reason = "Blocked by Architecture: Prohibited dangerous action, traversal, or core mutation. Access is strictly prohibited. Path traversal outside the allowed workspace is prohibited."
            self.log_to_ledger(session_id, "agent", tool, action_str, action_hash, risk_level, "BLOCKED_BY_POLICY", reason)
            return {"status": "BLOCKED_BY_POLICY", "reason": reason}

        # Level 0 & 1: Immediate Safety Pass
        if risk_level <= 1:
            self.log_to_ledger(session_id, "agent", tool, action_str, action_hash, risk_level, "ALLOWED")
            return {"status": "AUTHORIZED", "ticket_id": None, "action_hash": action_hash, "risk_level": risk_level}

        # Check if there is an approved (unexpired) ticket for this action hash
        now_str = datetime.datetime.utcnow().isoformat()
        cursor = self.db.cursor()
        cursor.execute(
            "SELECT ticket_id FROM approval_tickets WHERE action_hash = ? AND status = 'APPROVED' AND expires_at > ? LIMIT 1",
            (action_hash, now_str)
        )
        row = cursor.fetchone()
        if row:
            ticket_id = row[0]
            # Consume ticket
            cursor.execute("UPDATE approval_tickets SET status = 'APPROVED_CONSUMED', resolved_at = ? WHERE ticket_id = ?", (now_str, ticket_id))
            self.db.commit()
            self.log_to_ledger(session_id, "system", tool, action_str, action_hash, risk_level, "ALLOWED", f"Consumed approved ticket {ticket_id}")
            return {"status": "AUTHORIZED", "ticket_id": ticket_id, "action_hash": action_hash, "risk_level": risk_level}

        # Validate human attention budget
        if not self.check_and_increment_budget(risk_level):
            reason = "Exceeded daily human attention budget. Execution halted to prevent fatigue coercion."
            self.log_to_ledger(session_id, "agent", tool, action_str, action_hash, risk_level, "BLOCKED_BY_POLICY", reason)
            return {"status": "BLOCKED_BY_POLICY", "reason": reason}

        # Generate ticket for Level 2, 3, 4
        ticket_id = f"TKT-{action_hash[:8].upper()}-{str(uuid.uuid4())[:4].upper()}"
        expires_at = (datetime.datetime.utcnow() + datetime.timedelta(minutes=10)).isoformat()
        
        cursor.execute(
            """
            INSERT INTO approval_tickets (
                ticket_id, session_id, action_hash, tool, risk_level, serialized_payload, status, expires_at
            ) VALUES (?, ?, ?, ?, ?, ?, 'PENDING', ?)
            """,
            (ticket_id, session_id, action_hash, tool, risk_level, action_str, expires_at)
        )
        self.db.commit()
        
        self.log_to_ledger(session_id, "agent", tool, action_str, action_hash, risk_level, "PENDING_APPROVAL")
        
        return {
            "status": "REQUIRES_HUMAN_APPROVAL",
            "ticket_id": ticket_id,
            "action_hash": action_hash,
            "risk_level": risk_level,
            "display_payload": payload
        }

    def clear_ticket(self, ticket_id: str, user_response: str, validation_payload: Dict[str, Any], context: Dict[str, Any]) -> bool:
        """
        Validates cryptographic hash consistency (TOCTOU Defense) upon explicit user clearance.
        """
        cursor = self.db.cursor()
        cursor.execute(
            "SELECT action_hash, serialized_payload, status, expires_at, tool, session_id, risk_level FROM approval_tickets WHERE ticket_id = ?",
            (ticket_id,)
        )
        ticket = cursor.fetchone()
        
        if not ticket:
            return False
            
        action_hash, serialized_payload, status, expires_at, tool, session_id, risk_level = ticket
        
        if status != 'PENDING':
            return False
            
        now_str = datetime.datetime.utcnow().isoformat()
        if now_str > expires_at:
            cursor.execute("UPDATE approval_tickets SET status = 'EXPIRED' WHERE ticket_id = ?", (ticket_id,))
            self.db.commit()
            self.log_to_ledger(session_id, "system", tool, serialized_payload, action_hash, risk_level, "EXPIRED", "Ticket expired before user action")
            return False

        # TOCTOU Proofing: Recompute the hash from the validation payload
        recomputed_hash = self.classifier.calculate_action_hash(tool, validation_payload, context)
        if recomputed_hash != action_hash:
            cursor.execute("UPDATE approval_tickets SET status = 'REVOKED' WHERE ticket_id = ?", (ticket_id,))
            self.db.commit()
            self.log_to_ledger(session_id, "system", tool, serialized_payload, action_hash, risk_level, "REVOKED", f"TOCTOU mismatch: execution params changed. Recomputed: {recomputed_hash}")
            return False

        if user_response == "APPROVE":
            cursor.execute(
                "UPDATE approval_tickets SET status = 'APPROVED', resolved_at = ? WHERE ticket_id = ?",
                (now_str, ticket_id)
            )
            self.db.commit()
            self.log_to_ledger(session_id, "human", tool, serialized_payload, action_hash, risk_level, "ALLOWED")
            return True
        else:
            cursor.execute(
                "UPDATE approval_tickets SET status = 'DENIED', resolved_at = ? WHERE ticket_id = ?",
                (now_str, ticket_id)
            )
            self.db.commit()
            self.log_to_ledger(session_id, "human", tool, serialized_payload, action_hash, risk_level, "DENIED", "Denied by user")
            return False
