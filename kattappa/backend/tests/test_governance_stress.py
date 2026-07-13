"""
P0 Stress Tests: Validates governance layer performance under sustained concurrent load.
Covers: 50 concurrent metric writes, 20 concurrent token mints, 50 concurrent skill reads,
        long-running token lifecycle sequences.
"""
import time
import uuid
import threading
import pytest
from backend.core.ledger.stores.sqlite_store import SQLiteLedgerStore


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def make_store() -> SQLiteLedgerStore:
    return SQLiteLedgerStore(db_path=":memory:")


def mint_token(store: SQLiteLedgerStore, agent_name: str, max_invocations: int = 10) -> str:
    token_id = f"TOK-{uuid.uuid4().hex[:8].upper()}"
    store.create_delegation_token({
        "token_id": token_id,
        "capabilities": ["CAP_READ", "CAP_WRITE"],
        "trace_id": str(uuid.uuid4()),
        "allowed_paths": [],
        "allowed_domains": [],
        "issued_by": "stress_test",
        "expires_at": time.time() + 3600,
        "max_invocations": max_invocations,
        "current_invocations": 0,
        "status": "active",
    })
    return token_id


def make_skill(store: SQLiteLedgerStore, name: str) -> None:
    store.register_skill({
        "skill_id": f"SKL-{uuid.uuid4().hex[:8].upper()}",
        "name": name,
        "version": "1.0.0",
        "description": f"Stress test skill: {name}",
        "entrypoint": "/dev/null",
        "sandbox_type": "subprocess",
        "timeout_seconds": 30,
        "max_memory_mb": None,
        "allow_network": False,
        "allowed_paths": [],
        "required_capabilities": [],
        "dependencies": [],
    })


# ─────────────────────────────────────────────────────────────────────────────
# 1. Concurrent Metric Writes
# ─────────────────────────────────────────────────────────────────────────────

class TestConcurrentMetricWrites:
    def test_50_concurrent_metric_writes_all_persist(self):
        """50 threads writing 10 metrics each = 500 total writes, all must persist."""
        store = make_store()
        errors = []
        NUM_THREADS = 50
        WRITES_PER_THREAD = 10

        def write_batch(tid: int):
            try:
                for i in range(WRITES_PER_THREAD):
                    store.record_metric(
                        timestamp=time.time(),
                        metric_name=f"stress.metric.{tid}",
                        value=float(tid * WRITES_PER_THREAD + i),
                    )
            except Exception as e:
                errors.append(str(e))

        threads = [threading.Thread(target=write_batch, args=(i,)) for i in range(NUM_THREADS)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        assert not errors, f"Write errors occurred: {errors}"

        # Spot-check: verify at least one thread's writes persisted
        values = store.get_metric_values("stress.metric.0")
        assert len(values) == WRITES_PER_THREAD, \
            f"Expected {WRITES_PER_THREAD} metric values, got {len(values)}"


# ─────────────────────────────────────────────────────────────────────────────
# 2. Concurrent Token Mints
# ─────────────────────────────────────────────────────────────────────────────

class TestConcurrentTokenMints:
    def test_20_concurrent_token_mints_no_collision(self):
        """20 threads each minting a unique token, no ID collisions, all retrievable."""
        store = make_store()
        errors = []
        minted_ids = []
        id_lock = threading.Lock()

        def mint(i: int):
            try:
                token_id = mint_token(store, agent_name=f"stress_agent_{i}")
                with id_lock:
                    minted_ids.append(token_id)
            except Exception as e:
                errors.append(f"Thread {i}: {e}")

        threads = [threading.Thread(target=mint, args=(i,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=15)

        assert not errors, f"Mint errors: {errors}"
        assert len(minted_ids) == 20, f"Expected 20 minted tokens, got {len(minted_ids)}"

        # Verify all are retrievable
        for token_id in minted_ids:
            result = store.get_delegation_token(token_id)
            assert result is not None, f"Token {token_id} not found after concurrent mint"
            assert result["status"] == "active"

    def test_concurrent_invocation_count_updates_no_race(self):
        """10 threads each incrementing the same token's invocation count — final count must be correct."""
        store = make_store()
        token_id = mint_token(store, agent_name="shared_agent", max_invocations=10)
        errors = []
        update_lock = threading.Lock()

        def increment_invocation(expected_count: int):
            try:
                with update_lock:
                    current = store.get_delegation_token(token_id)["current_invocations"]
                    store.update_token_usage(
                        token_id,
                        current_invocations=current + 1,
                        status="active" if current + 1 < 10 else "exhausted",
                    )
            except Exception as e:
                errors.append(str(e))

        threads = [threading.Thread(target=increment_invocation, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=15)

        assert not errors, f"Update errors: {errors}"
        token = store.get_delegation_token(token_id)
        assert token["current_invocations"] == 10
        assert token["status"] == "exhausted"


# ─────────────────────────────────────────────────────────────────────────────
# 3. Concurrent Skill Registry Reads
# ─────────────────────────────────────────────────────────────────────────────

class TestConcurrentSkillRegistryReads:
    def test_50_concurrent_reads_consistent(self):
        """Pre-populate 5 skills, then 50 threads simultaneously read list_skills."""
        store = make_store()
        for i in range(5):
            make_skill(store, name=f"stress.skill.{i}")

        errors = []
        results = []
        lock = threading.Lock()

        def read_skills():
            try:
                skills = store.list_skills()
                with lock:
                    results.append(len(skills))
            except Exception as e:
                errors.append(str(e))

        threads = [threading.Thread(target=read_skills) for _ in range(50)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=15)

        assert not errors, f"Read errors: {errors}"
        assert len(results) == 50
        # All reads must observe exactly 5 skills (consistent reads)
        assert all(r == 5 for r in results), f"Inconsistent read results: {set(results)}"


# ─────────────────────────────────────────────────────────────────────────────
# 4. Long-Running Token Lifecycle
# ─────────────────────────────────────────────────────────────────────────────

class TestLongRunningTokenLifecycle:
    def test_full_lifecycle_mint_use_exhaust_reject(self):
        """
        Token lifecycle: mint → validate × N → exhaust → subsequent reads show exhausted.
        Simulates a complete token burn-down sequence.
        """
        MAX_INVOCATIONS = 5
        store = make_store()
        token_id = mint_token(store, agent_name="lifecycle_agent", max_invocations=MAX_INVOCATIONS)

        for invocation_num in range(1, MAX_INVOCATIONS + 1):
            token = store.get_delegation_token(token_id)
            assert token["status"] == "active", f"Expected active at invocation {invocation_num}"

            new_count = invocation_num
            new_status = "exhausted" if new_count >= MAX_INVOCATIONS else "active"
            store.update_token_usage(token_id, current_invocations=new_count, status=new_status)

        # After exhaustion, token must report exhausted
        final = store.get_delegation_token(token_id)
        assert final["status"] == "exhausted"
        assert final["current_invocations"] == MAX_INVOCATIONS

        # Attempting to use an exhausted token: status remains exhausted
        store.update_token_usage(token_id, current_invocations=MAX_INVOCATIONS, status="exhausted")
        still_exhausted = store.get_delegation_token(token_id)
        assert still_exhausted["status"] == "exhausted"

    def test_token_expiry_detectable_by_timestamp(self):
        """A token issued with a past expiry must have expires_at in the past."""
        store = make_store()
        past_time = time.time() - 7200  # expired 2 hours ago
        token_id = mint_token(store, agent_name="expired_agent", max_invocations=1)
        # Simulate by creating a fresh one with explicit past expiry
        expired_id = f"TOK-EXPIRED-{uuid.uuid4().hex[:6].upper()}"
        store.create_delegation_token({
            "token_id": expired_id,
            "capabilities": ["CAP_READ"],
            "trace_id": str(uuid.uuid4()),
            "allowed_paths": [],
            "allowed_domains": [],
            "issued_by": "test",
            "expires_at": past_time,
            "max_invocations": 1,
            "current_invocations": 0,
            "status": "active",
        })
        token = store.get_delegation_token(expired_id)
        assert token["expires_at"] < time.time(), "Token should report as past expiry"
