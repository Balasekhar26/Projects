from __future__ import annotations

import json
import re
import time
import uuid
from typing import Any, Optional

from backend.core.capability_registry import (
    CapabilityRegistry,
    CAP_MEMORY_READ,
    CAP_MEMORY_WRITE,
    CAP_MEMORY_PIN,
    CAP_MEMORY_DELETE,
    CAP_MEMORY_ROLLBACK,
)
from backend.core.human_memory import (
    HumanMemory,
    HumanMemoryStore,
    MemoryRecord,
    MemoryType,
    StoreDecision,
    ImportanceScorer,
    WorkingMemory,
    RecallEngine,
)
from backend.core.memory_governance import MemoryGovernance
from backend.core.action_broker import ActionBroker

_REDACT_PATTERNS = [
    re.compile(r"-----BEGIN [A-Z ]+ PRIVATE KEY-----[\s\S]+?-----END [A-Z ]+ PRIVATE KEY-----"),
    re.compile(r"(?i)(?:api_key|password|secret|token|credential|auth_token|github_token|openai_key|session_key|private_key)\s*[:=]\s*['\"][^'\"]+['\"]"),
    re.compile(r"\bsk-[a-zA-Z0-9]{48}\b"),   # openai keys
    re.compile(r"\bghp_[a-zA-Z0-9]{36,40}\b"), # github token
]

class MemoryService:
    @classmethod
    def _ensure_versions_schema(cls) -> None:
        conn = HumanMemoryStore._connect()
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS hm_memory_versions (
            version_id   TEXT PRIMARY KEY,
            memory_id    TEXT NOT NULL,
            content      TEXT NOT NULL,
            importance   REAL NOT NULL,
            agent        TEXT NOT NULL,
            created_at   REAL NOT NULL,
            rollback_ref TEXT         -- previous version_id, for chain traversal
        );
        CREATE INDEX IF NOT EXISTS idx_hm_versions_memory ON hm_memory_versions(memory_id);
        """)
        conn.commit()

    @classmethod
    def redact_secrets(cls, text: str) -> str:
        redacted = text
        for pattern in _REDACT_PATTERNS:
            redacted = pattern.sub("[REDACTED]", redacted)
        return redacted

    # ----- Public APIs (route through Action Broker where required) -----

    @classmethod
    def write(
        cls,
        agent: str,
        content: str,
        memory_type: str = None,
        source: str = "user",
        session_id: str = "primary",
        state: dict = None
    ) -> dict:
        if state is None:
            state = {}
        cls._ensure_versions_schema()
        params = {
            "content": content,
            "memory_type": memory_type,
            "source": source,
            "session_id": session_id,
        }
        res = ActionBroker.intake_request(agent, "COMMIT_MEMORY_DELTA", params, state)
        if res.get("success") and "result" in res:
            return res["result"]
        return res

    @classmethod
    def recall(
        cls,
        agent: str,
        query: str,
        limit: int = 5,
        session_id: str = "primary",
        state: dict = None
    ) -> list[dict]:
        if state is None:
            state = {}
        # Every read capability check
        if not CapabilityRegistry.is_capability_allowed(agent, CAP_MEMORY_READ):
            raise PermissionError(f"Security Error: Agent '{agent}' does not have CAP_MEMORY_READ capability")

        # Log read audit
        ActionBroker.log_audit_trail(agent, "RECALL_MEMORY", "allowed", "auto_approved", f"Query: {query}")

        # Call recall engine
        hits = RecallEngine.recall(query, limit=limit, reinforce=True)
        
        results = []
        for hit in hits:
            record_dict = hit.record.to_dict()
            record_dict["content"] = cls.redact_secrets(record_dict["content"])
            record_dict["relevance"] = round(hit.relevance, 3)
            results.append(record_dict)
        return results

    @classmethod
    def recall_trusted(
        cls,
        agent: str,
        query: str,
        min_trust: float = 0.6,
        session_id: str = "primary",
        state: dict = None
    ) -> list[dict]:
        results = cls.recall(agent, query, limit=100, session_id=session_id, state=state)
        # Filters results by trust (trusted=True or confidence >= min_trust)
        return [r for r in results if r.get("trusted") or r.get("confidence", 0.0) >= min_trust]

    @classmethod
    def pin(cls, agent: str, memory_id: str, state: dict = None) -> dict:
        if state is None:
            state = {}
        res = ActionBroker.intake_request(agent, "PIN_MEMORY", {"memory_id": memory_id}, state)
        if res.get("success") and "result" in res:
            return res["result"]
        return res

    @classmethod
    def unpin(cls, agent: str, memory_id: str, state: dict = None) -> dict:
        if state is None:
            state = {}
        res = ActionBroker.intake_request(agent, "UNPIN_MEMORY", {"memory_id": memory_id}, state)
        if res.get("success") and "result" in res:
            return res["result"]
        return res

    @classmethod
    def delete(cls, agent: str, memory_id: str, state: dict = None) -> dict:
        if state is None:
            state = {}
        res = ActionBroker.intake_request(agent, "DELETE_MEMORY", {"memory_id": memory_id}, state)
        if res.get("success") and "result" in res:
            return res["result"]
        return res

    @classmethod
    def expire(cls, agent: str, memory_id: str, state: dict = None) -> dict:
        if state is None:
            state = {}
        res = ActionBroker.intake_request(agent, "EXPIRE_MEMORY", {"memory_id": memory_id}, state)
        if res.get("success") and "result" in res:
            return res["result"]
        return res

    @classmethod
    def consolidate(cls, agent: str, state: dict = None) -> dict:
        if state is None:
            state = {}
        res = ActionBroker.intake_request(agent, "CONSOLIDATE_MEMORY", {}, state)
        if res.get("success") and "result" in res:
            return res["result"]
        return res

    @classmethod
    def apply_aging(cls, agent: str, state: dict = None) -> dict:
        if state is None:
            state = {}
        res = ActionBroker.intake_request(agent, "AGING_MEMORY", {}, state)
        if res.get("success") and "result" in res:
            return res["result"]
        return res

    @classmethod
    def rollback(cls, agent: str, memory_id: str, version_id: str, state: dict = None) -> dict:
        if state is None:
            state = {}
        cls._ensure_versions_schema()
        params = {
            "memory_id": memory_id,
            "version_id": version_id,
        }
        res = ActionBroker.intake_request(agent, "ROLLBACK_MEMORY", params, state)
        if res.get("success") and "result" in res:
            return res["result"]
        return res

    @classmethod
    def score_importance(cls, content: str, trusted: bool = True) -> dict:
        score = ImportanceScorer.score(content, trusted=trusted)
        return score.as_dict()

    # ----- Broker Execution Handlers -----

    @classmethod
    def _execute_write(cls, agent: str, params: dict, state: dict) -> dict:
        if not CapabilityRegistry.is_capability_allowed(agent, CAP_MEMORY_WRITE):
            return {"success": False, "error": f"Security Error: Agent '{agent}' does not have CAP_MEMORY_WRITE"}

        content = params.get("content") or ""
        memory_type = params.get("memory_type")
        source = params.get("source") or "user"
        session_id = params.get("session_id") or "primary"

        trusted = source in {"user", "system", "voice", "coder"}
        if trusted is None:
            trusted = True

        from backend.core.human_memory import classify_memory_type
        mem_type = MemoryType(memory_type) if memory_type else classify_memory_type(content)

        pending_approval = False
        if not trusted:
            pending_approval = True

        repetition = WorkingMemory.repetition_count(session_id, content)
        score = ImportanceScorer.score(content, repetition_count=repetition, trusted=trusted)

        if score.decision == StoreDecision.FORGET:
            return {"success": False, "error": "Memory score below threshold, forgotten", "decision": "forget"}

        now = time.time()
        memory_id = uuid.uuid4().hex

        record = MemoryRecord(
            id=memory_id,
            type=mem_type,
            content=content,
            importance=score.total,
            confidence=0.8 if trusted else 0.4,
            decay_score=max(0.5, score.total),
            recall_count=0,
            created_at=now,
            last_recall_at=now,
            pinned=False,
            trusted=trusted,
            source=source,
            compression_level=0,
            tags=["pending_approval"] if pending_approval else [],
            metadata={"session_id": session_id},
            pending_approval=pending_approval
        )

        # Storage insert
        HumanMemoryStore.insert(record)

        # Create Version
        cls._create_version(memory_id, content, score.total, agent, now)

        # Governance
        MemoryGovernance.log_provenance(
            memory_id=memory_id,
            memory_type=mem_type.value,
            source=source,
            created_by=agent,
            confidence=record.confidence
        )

        trust_level = "TRUST_SYSTEM" if source == "system" else ("TRUST_USER" if source == "user" else "TRUST_UNVERIFIED")
        MemoryGovernance.set_trust(memory_id, "memory", trust_level)

        return {
            "success": True,
            "memory_id": memory_id,
            "record": record.to_dict(),
            "decision": score.decision.value
        }

    @classmethod
    def _execute_pin(cls, agent: str, params: dict, state: dict) -> dict:
        if not CapabilityRegistry.is_capability_allowed(agent, CAP_MEMORY_PIN):
            return {"success": False, "error": f"Security Error: Agent '{agent}' does not have CAP_MEMORY_PIN"}
        memory_id = params.get("memory_id")
        success = HumanMemory.pin(memory_id)
        return {"success": success}

    @classmethod
    def _execute_unpin(cls, agent: str, params: dict, state: dict) -> dict:
        if not CapabilityRegistry.is_capability_allowed(agent, CAP_MEMORY_PIN):
            return {"success": False, "error": f"Security Error: Agent '{agent}' does not have CAP_MEMORY_PIN"}
        memory_id = params.get("memory_id")
        success = HumanMemory.unpin(memory_id)
        return {"success": success}

    @classmethod
    def _execute_delete(cls, agent: str, params: dict, state: dict) -> dict:
        if not CapabilityRegistry.is_capability_allowed(agent, CAP_MEMORY_DELETE):
            return {"success": False, "error": f"Security Error: Agent '{agent}' does not have CAP_MEMORY_DELETE"}
        memory_id = params.get("memory_id")
        success = HumanMemoryStore.delete(memory_id)
        return {"success": success}

    @classmethod
    def _execute_expire(cls, agent: str, params: dict, state: dict) -> dict:
        if not CapabilityRegistry.is_capability_allowed(agent, CAP_MEMORY_WRITE):
            return {"success": False, "error": f"Security Error: Agent '{agent}' does not have CAP_MEMORY_WRITE"}
        memory_id = params.get("memory_id")
        record = HumanMemoryStore.get(memory_id)
        if record:
            record.decay_score = 0.0
            HumanMemoryStore.update(record)
            return {"success": True}
        return {"success": False, "error": "Memory not found"}

    @classmethod
    def _execute_consolidate(cls, agent: str, params: dict, state: dict) -> dict:
        if not CapabilityRegistry.is_capability_allowed(agent, CAP_MEMORY_WRITE):
            return {"success": False, "error": f"Security Error: Agent '{agent}' does not have CAP_MEMORY_WRITE"}
        res = HumanMemory.reflect()
        return {"success": True, "result": res}

    @classmethod
    def _execute_aging(cls, agent: str, params: dict, state: dict) -> dict:
        if not CapabilityRegistry.is_capability_allowed(agent, CAP_MEMORY_WRITE):
            return {"success": False, "error": f"Security Error: Agent '{agent}' does not have CAP_MEMORY_WRITE"}
        res = HumanMemory.run_decay()
        return {"success": True, "result": res}

    @classmethod
    def _execute_rollback(cls, agent: str, params: dict, state: dict) -> dict:
        if not CapabilityRegistry.is_capability_allowed(agent, CAP_MEMORY_ROLLBACK):
            return {"success": False, "error": f"Security Error: Agent '{agent}' does not have CAP_MEMORY_ROLLBACK"}

        memory_id = params.get("memory_id")
        version_id = params.get("version_id")

        conn = HumanMemoryStore._connect()
        row = conn.execute(
            "SELECT * FROM hm_memory_versions WHERE version_id = ? AND memory_id = ?",
            (version_id, memory_id)
        ).fetchone()
        if not row:
            return {"success": False, "error": f"Version '{version_id}' for memory '{memory_id}' not found"}

        record = HumanMemoryStore.get(memory_id)
        if not record:
            return {"success": False, "error": f"Memory '{memory_id}' not found"}

        record.content = row["content"]
        record.importance = row["importance"]
        HumanMemoryStore.update(record)

        now = time.time()
        cls._create_version(memory_id, record.content, record.importance, agent, now)

        return {
            "success": True,
            "memory_id": memory_id,
            "content": record.content,
            "importance": record.importance
        }

    # ----- Version Helper -----

    @classmethod
    def _create_version(cls, memory_id: str, content: str, importance: float, agent: str, now: float) -> str:
        version_id = uuid.uuid4().hex
        conn = HumanMemoryStore._connect()
        row = conn.execute(
            "SELECT version_id FROM hm_memory_versions WHERE memory_id = ? ORDER BY created_at DESC LIMIT 1",
            (memory_id,)
        ).fetchone()
        rollback_ref = row["version_id"] if row else None

        conn.execute(
            """INSERT INTO hm_memory_versions (version_id, memory_id, content, importance, agent, created_at, rollback_ref)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (version_id, memory_id, content, importance, agent, now, rollback_ref)
        )
        conn.commit()
        return version_id
