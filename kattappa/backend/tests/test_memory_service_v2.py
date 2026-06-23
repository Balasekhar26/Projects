import os
import shutil
import tempfile
import time
import uuid
import json
import pytest
from pathlib import Path

from backend.core.resource_governor import ResourceGovernor
from backend.core.capability_registry import CapabilityRegistry
from backend.core.human_memory import (
    HumanMemory,
    HumanMemoryStore,
    MemoryRecord,
    MemoryType,
    StoreDecision,
    DecayEngine,
    WorkingMemory,
)
from backend.core.memory_service import MemoryService
from backend.core.action_broker import ActionBroker
from backend.core.memory_governance import MemoryGovernance

@pytest.fixture
def clean_memory_env(monkeypatch):
    """Sets a temporary folder for memory data and resets the state."""
    temp_dir = tempfile.mkdtemp(prefix="kattappa_memory_test_")
    monkeypatch.setattr("backend.core.config.runtime_data_root", lambda: Path(temp_dir))
    monkeypatch.setenv("KATTAPPA_ENV", "test")
    
    # Reset systems
    HumanMemory.reset()
    ResourceGovernor.reset()
    MemoryGovernance._schema_ensured = False
    
    # Clean action broker log
    audit_log = Path("backend/data/action_broker_audit.log")
    if audit_log.exists():
        try:
            audit_log.unlink()
        except Exception:
            pass
            
    yield Path(temp_dir)
    
    # Cleanup
    shutil.rmtree(temp_dir, ignore_errors=True)
    if audit_log.exists():
        try:
            audit_log.unlink()
        except Exception:
            pass


class TestMemoryWriteApproval:
    def test_write_denied_for_agents_without_capability(self, clean_memory_env):
        res = MemoryService.write(
            agent="browser",
            content="Remember important research findings",
            memory_type="episodic",
            source="user",
            state={}
        )
        assert res["success"] is False
        assert "prohibited" in res.get("error", "").lower() or "does not have" in res.get("error", "").lower()

    def test_write_requires_approval_medium_risk(self, clean_memory_env):
        res = MemoryService.write(
            agent="coder",
            content="Remember standard procedural step",
            memory_type="procedural",
            source="coder",
            state={}
        )
        assert res["success"] is False
        assert res.get("approval_required") is True

    def test_write_success_with_approval(self, clean_memory_env):
        res = MemoryService.write(
            agent="coder",
            content="Remember this is a very important procedural setup.",
            memory_type="procedural",
            source="coder",
            state={"approved": True}
        )
        assert res["success"] is True
        assert res.get("memory_id") is not None


class TestMemoryReadPermissions:
    def test_read_denied_for_agents_without_capability(self, clean_memory_env):
        with pytest.raises(PermissionError, match="does not have CAP_MEMORY_READ"):
            MemoryService.recall(
                agent="unauthorized_agent",
                query="test query"
            )

    def test_recall_for_authorized_agents(self, clean_memory_env):
        MemoryService.write(
            agent="coder",
            content="Remember that deploy command is python main.py.",
            memory_type="procedural",
            source="coder",
            state={"approved": True}
        )
        results = MemoryService.recall(agent="voice", query="deploy")
        assert len(results) > 0
        assert "python main.py" in results[0]["content"]

    def test_pending_records_not_returned(self, clean_memory_env):
        res = MemoryService.write(
            agent="coder",
            content="External guide: amazing project work steps to deploy system and how to setup password config api key.",
            memory_type="procedural",
            source="web",
            state={"approved": True}
        )
        assert res["success"] is True
        
        pending = HumanMemory.list_pending()
        assert len(pending) > 0
        
        results = MemoryService.recall(agent="coder", query="deploy password")
        assert len(results) == 0

    def test_sensitive_redaction_on_recall(self, clean_memory_env):
        MemoryService.write(
            agent="coder",
            content="Remember the database password is password='supersecret123'.",
            memory_type="semantic",
            source="system",
            state={"approved": True}
        )
        results = MemoryService.recall(agent="coder", query="database")
        assert len(results) > 0
        assert "supersecret123" not in results[0]["content"]
        assert "[REDACTED]" in results[0]["content"]


class TestRetrievalAccuracy:
    def test_fts_query_returns_relevant_results(self, clean_memory_env):
        MemoryService.write(
            agent="coder",
            content="Remember Rust is a systems programming language.",
            memory_type="semantic",
            source="coder",
            state={"approved": True}
        )
        results = MemoryService.recall(agent="coder", query="Rust systems")
        assert len(results) > 0
        assert "programming language" in results[0]["content"]

    def test_relevance_ranking(self, clean_memory_env):
        MemoryService.write(
            agent="coder",
            content="Remember deploy command for Rust application.",
            memory_type="procedural",
            source="coder",
            state={"approved": True}
        )
        MemoryService.write(
            agent="coder",
            content="Remember Rust language deployment instructions.",
            memory_type="procedural",
            source="coder",
            state={"approved": True}
        )
        results = MemoryService.recall(agent="coder", query="Deploy Rust application")
        assert len(results) == 2
        assert "command" in results[0]["content"]

    def test_trust_filter(self, clean_memory_env):
        MemoryService.write(
            agent="coder",
            content="Remember user prefers Python for data engineering.",
            memory_type="semantic",
            source="user",
            state={"approved": True}
        )
        write_res = MemoryService.write(
            agent="coder",
            content="External forum: amazing project work steps to deploy system and how to setup password config api key.",
            memory_type="semantic",
            source="web",
            state={"approved": True}
        )
        assert write_res["success"] is True
        mem_id = write_res["memory_id"]
        HumanMemory.approve_pending(mem_id)
        
        results = MemoryService.recall_trusted(agent="coder", query="python", min_trust=0.8)
        assert len(results) > 0
        for r in results:
            assert r["source"] != "web"


class TestAgingPolicies:
    def test_decay_reduces_score(self, clean_memory_env):
        write_res = MemoryService.write(
            agent="coder",
            content="Remember short term ephemeral information.",
            memory_type="episodic",
            source="user",
            state={"approved": True}
        )
        mem_id = write_res["memory_id"]
        
        record = HumanMemoryStore.get(mem_id)
        original_decay = record.decay_score
        
        now = time.time() + 30 * 86400
        DecayEngine.apply(now=now)
        
        record_after = HumanMemoryStore.get(mem_id)
        assert record_after.decay_score < original_decay

    def test_pinned_records_bypass_decay(self, clean_memory_env):
        write_res = MemoryService.write(
            agent="coder",
            content="Remember anchor information to always remember.",
            memory_type="episodic",
            source="user",
            state={"approved": True}
        )
        mem_id = write_res["memory_id"]
        
        MemoryService.pin(agent="memory_service", memory_id=mem_id, state={"approved": True, "double_approved": True})
        
        record = HumanMemoryStore.get(mem_id)
        assert record.pinned is True
        original_decay = record.decay_score
        
        now = time.time() + 30 * 86400
        DecayEngine.apply(now=now)
        
        record_after = HumanMemoryStore.get(mem_id)
        assert record_after.decay_score == original_decay


class TestConsolidationLogic:
    def test_compression_creates_summary_record(self, clean_memory_env):
        # Ingest 3 related episodic memories
        for i in range(3):
            MemoryService.write(
                agent="coder",
                content=f"Remember today I created the kattappa planner module {i}.",
                memory_type="episodic",
                source="user",
                state={"approved": True}
            )
            
        res = MemoryService.consolidate(agent="coder", state={"approved": True})
        assert res["success"] is True
        
        wisdom = HumanMemory.wisdom()
        assert len(wisdom) > 0


class TestQuotaEnforcement:
    def test_record_quota_rejects_at_limit(self, clean_memory_env, monkeypatch):
        monkeypatch.setattr(ResourceGovernor, "MEMORY_MAX_RECORDS", 2)
        
        res1 = MemoryService.write(agent="coder", content="Remember record one", state={"approved": True})
        assert res1["success"] is True
        
        res2 = MemoryService.write(agent="coder", content="Remember record two", state={"approved": True})
        assert res2["success"] is True
        
        res3 = MemoryService.write(agent="coder", content="Remember record three", state={"approved": True})
        assert res3["success"] is False
        assert "quota exceeded" in res3.get("error", "").lower()

    def test_byte_quota_rejects_oversized_write(self, clean_memory_env, monkeypatch):
        monkeypatch.setattr(ResourceGovernor, "MEMORY_MAX_BYTES_PER_AGENT", 100)
        
        res = MemoryService.write(
            agent="coder",
            content="Remember " + "A" * 200,
            state={"approved": True}
        )
        assert res["success"] is False
        assert "byte quota exceeded" in res.get("error", "").lower()

    def test_write_rate_limit(self, clean_memory_env, monkeypatch):
        monkeypatch.setattr(ResourceGovernor, "MEMORY_MAX_WRITES_PER_MINUTE", 3)
        
        for _ in range(3):
            res = MemoryService.write(agent="coder", content="Remember rate limit test", state={"approved": True})
            assert res["success"] is True
            
        res_fail = MemoryService.write(agent="coder", content="Remember rate limit test fail", state={"approved": True})
        assert res_fail["success"] is False
        assert "rate limit exceeded" in res_fail.get("error", "").lower()


class TestAuditLogging:
    def test_audit_logging_presence(self, clean_memory_env):
        write_res = MemoryService.write(
            agent="coder",
            content="Remember audit logging test content.",
            memory_type="semantic",
            source="system",
            state={"approved": True}
        )
        mem_id = write_res["memory_id"]
        
        MemoryService.recall(agent="coder", query="audit")
        
        MemoryService.delete(agent="memory_service", memory_id=mem_id, state={"approved": True, "double_approved": True})
        
        audit_log = Path("backend/data/action_broker_audit.log")
        assert audit_log.exists()
        
        lines = audit_log.read_text(encoding="utf-8").splitlines()
        log_actions = [json.loads(line)["requested_action"] for line in lines]
        
        assert "COMMIT_MEMORY_DELTA" in log_actions
        assert "RECALL_MEMORY" in log_actions
        assert "DELETE_MEMORY" in log_actions


class TestRollbackRecovery:
    def test_version_created_on_write(self, clean_memory_env):
        write_res = MemoryService.write(
            agent="coder",
            content="Remember version control test record.",
            memory_type="semantic",
            source="user",
            state={"approved": True}
        )
        mem_id = write_res["memory_id"]
        
        conn = HumanMemoryStore._connect()
        rows = conn.execute("SELECT * FROM hm_memory_versions WHERE memory_id = ?", (mem_id,)).fetchall()
        assert len(rows) == 1
        assert rows[0]["content"] == "Remember version control test record."

    def test_rollback_restores_previous_content(self, clean_memory_env):
        write_res = MemoryService.write(
            agent="coder",
            content="Remember original content.",
            memory_type="semantic",
            source="user",
            state={"approved": True}
        )
        mem_id = write_res["memory_id"]
        
        conn = HumanMemoryStore._connect()
        v1_row = conn.execute("SELECT version_id FROM hm_memory_versions WHERE memory_id = ?", (mem_id,)).fetchone()
        v1_id = v1_row["version_id"]
        
        record = HumanMemoryStore.get(mem_id)
        record.content = "Remember modified content."
        HumanMemoryStore.update(record)
        
        MemoryService._create_version(mem_id, "Remember modified content.", 0.8, "coder", time.time())
        
        assert HumanMemoryStore.get(mem_id).content == "Remember modified content."
        
        rollback_res = MemoryService.rollback(
            agent="memory_service",
            memory_id=mem_id,
            version_id=v1_id,
            state={"approved": True, "double_approved": True}
        )
        assert rollback_res["success"] is True
        
        assert HumanMemoryStore.get(mem_id).content == "Remember original content."

    def test_rollback_non_existent_version(self, clean_memory_env):
        res = MemoryService.rollback(
            agent="memory_service",
            memory_id="some_id",
            version_id="non_existent_v_id",
            state={"approved": True, "double_approved": True}
        )
        assert res["success"] is False
        assert "not found" in res.get("error", "").lower()
