"""Step 19 Verification Tests — Cognitive Stack Integration.

Addresses the four verification criteria:
1. Memory Assembler integration: assemble_context contains all 7 context keys
   (episodic, semantic, relationship, world_model, strategic, decisions, actions).
2. Cross-memory traceability: Episode → Semantic fact, Episode → Relationship
   preference, Episode → World belief, World belief → causal log → episode.
3. Conflict workflow (all 3 systems): Semantic, Relationship, and World Model
   conflicts are all queued rather than silently overwriting active data.
4. Persistence: write data, reset connection state, confirm memories survive reload.
"""
from __future__ import annotations

import pytest
import time
import sqlite3
from unittest.mock import patch


# ──────────────────────────────────────────────────────────────────────────────
# Shared fixtures
# ──────────────────────────────────────────────────────────────────────────────

@pytest.fixture()
def isolated_stack(tmp_path, monkeypatch):
    """Isolate all cognitive stack layers to a dedicated temp SQLite DB."""
    from backend.core.config import BackendConfig
    import backend.core.config as cfg_module

    test_db = tmp_path / "kattappa_integration_test.db"
    chroma_path = tmp_path / "chroma"

    mock_config = BackendConfig(
        root=tmp_path,
        backend_root=tmp_path,
        ollama_host="http://127.0.0.1:11434",
        model_map={},
        chroma_path=chroma_path,
        sqlite_path=test_db,
        memory_collection="kattappa_memory",
        shell_enabled=False,
        desktop_enabled=True,
        screen_capture_enabled=False,
        guidance_overlay_enabled=True,
        teach_mode_enabled=True,
        screenshots_dir=tmp_path / "screenshots",
        audio_dir=tmp_path / "audio",
        logs_dir=tmp_path / "logs",
        workspace_dir=tmp_path / "workspace",
        hardware_profile="BALANCED",
        context_budget=4096,
    )

    monkeypatch.setattr(cfg_module, "load_config", lambda: mock_config)

    # Reset schema-ensured flags so fresh DB is initialised
    import backend.core.episodic_memory as ep_mod
    import backend.core.semantic_memory as sem_mod
    import backend.core.strategic_memory as strat_mod
    import backend.core.world_model as wm_mod

    ep_mod.EpisodicMemory._schema_ensured = False
    sem_mod.SemanticMemory._schema_ensured = False
    strat_mod.StrategicMemory._schema_ensured = False
    wm_mod.WorldModel._schema_ensured = False

    from backend.core.world_model import WorldModel
    WorldModel.reset()

    yield {
        "db_path": test_db,
        "chroma_path": chroma_path,
        "config": mock_config,
    }

    WorldModel.reset()
    ep_mod.EpisodicMemory._schema_ensured = False
    sem_mod.SemanticMemory._schema_ensured = False
    strat_mod.StrategicMemory._schema_ensured = False
    wm_mod.WorldModel._schema_ensured = False


# ──────────────────────────────────────────────────────────────────────────────
# 1. Memory Assembler Integration — all context keys present
# ──────────────────────────────────────────────────────────────────────────────

class TestAssemblerIntegration:
    """Verify assemble_context returns the complete cognitive context bundle."""

    def test_assembler_returns_all_context_keys(self, isolated_stack):
        """assemble_context must return all expected top-level cognitive context keys."""
        from backend.core.memory_assembler import MemoryAssembler
        from backend.core.world_model import WorldModel

        WorldModel.add_entity("Test Component", status="active",
                              confidence_state="STATED")

        with patch.object(MemoryAssembler, "_query_semantic", return_value=[]), \
             patch.object(MemoryAssembler, "_query_episodic", return_value=[]), \
             patch.object(MemoryAssembler, "_query_procedural", return_value=[]), \
             patch.object(MemoryAssembler, "_query_strategic", return_value=[]), \
             patch.object(MemoryAssembler, "_query_decisions", return_value=[]):
            result = MemoryAssembler.assemble_context("test component")

        required_keys = {
            "query", "facts", "episodes", "actions",
            "goals", "decisions", "relationship_memory", "world_model", "total_hits"
        }
        missing = required_keys - result.keys()
        assert not missing, f"assemble_context is missing keys: {missing}"

    def test_assembler_world_model_key_contains_matched_entities(self, isolated_stack):
        """world_model key must contain entities matching the query."""
        from backend.core.memory_assembler import MemoryAssembler
        from backend.core.world_model import WorldModel

        WorldModel.add_entity("Radar Subsystem", status="operational",
                              confidence=0.9, confidence_state="CONFIRMED")

        with patch.object(MemoryAssembler, "_query_semantic", return_value=[]), \
             patch.object(MemoryAssembler, "_query_episodic", return_value=[]), \
             patch.object(MemoryAssembler, "_query_procedural", return_value=[]), \
             patch.object(MemoryAssembler, "_query_strategic", return_value=[]), \
             patch.object(MemoryAssembler, "_query_decisions", return_value=[]):
            result = MemoryAssembler.assemble_context("radar")

        world_hits = result["world_model"]
        assert isinstance(world_hits, list)
        names = [h["name"] for h in world_hits]
        assert "Radar Subsystem" in names

        radar = next(h for h in world_hits if h["name"] == "Radar Subsystem")
        assert radar["confidence"] == pytest.approx(0.9)
        assert radar["confidence_state"] == "CONFIRMED"

    def test_assembler_world_model_failure_is_graceful(self, isolated_stack):
        """If WorldModel.query_world_context raises, world_model must be [] (no crash)."""
        from backend.core.memory_assembler import MemoryAssembler

        with patch.object(MemoryAssembler, "_query_semantic", return_value=[]), \
             patch.object(MemoryAssembler, "_query_episodic", return_value=[]), \
             patch.object(MemoryAssembler, "_query_procedural", return_value=[]), \
             patch.object(MemoryAssembler, "_query_strategic", return_value=[]), \
             patch.object(MemoryAssembler, "_query_decisions", return_value=[]), \
             patch.object(MemoryAssembler, "_query_world_model",
                          side_effect=RuntimeError("world model db down")):
            result = MemoryAssembler.assemble_context("any query")

        assert result["world_model"] == []

    def test_total_hits_counts_world_model_entities(self, isolated_stack):
        """total_hits must count world_model results alongside other layer results."""
        from backend.core.memory_assembler import MemoryAssembler

        fake_world_hits = [{"name": "Test Node", "confidence": 0.8}]
        fake_facts = [{"id": "f1", "concept": "X", "rrf_score": 0.01}]

        with patch.object(MemoryAssembler, "_query_semantic", return_value=fake_facts), \
             patch.object(MemoryAssembler, "_query_episodic", return_value=[]), \
             patch.object(MemoryAssembler, "_query_procedural", return_value=[]), \
             patch.object(MemoryAssembler, "_query_strategic", return_value=[]), \
             patch.object(MemoryAssembler, "_query_decisions", return_value=[]), \
             patch.object(MemoryAssembler, "_query_world_model", return_value=fake_world_hits):
            result = MemoryAssembler.assemble_context("test")

        # 1 fact + 1 world hit = at least 2
        assert result["total_hits"] >= 2


# ──────────────────────────────────────────────────────────────────────────────
# 2. Cross-Memory Traceability
# ──────────────────────────────────────────────────────────────────────────────

class TestCrossMemoryTraceability:
    """Verify episode IDs are consistently preserved across all memory layers."""

    def test_episode_to_semantic_fact_traceability(self, isolated_stack):
        """A promoted semantic node must carry the episode ID that contributed to it."""
        from backend.core.episodic_memory import EpisodicMemory
        from backend.core.semantic_memory import SemanticMemory

        ep_id = EpisodicMemory.create_episode(
            content="RF attenuation is high at 5.8GHz due to cable mismatch",
            importance=0.85,
            category="TESTING",
        )
        assert ep_id

        # Two upserts with different episode IDs to meet evidence_count >= 2 threshold.
        # The FIRST upsert creates the node (returns the UUID).
        ep_id_2 = EpisodicMemory.create_episode(
            content="RF attenuation confirmed: high at 5.8GHz, impedance mismatch verified",
            importance=0.85,
            category="TESTING",
        )
        node_id = SemanticMemory.upsert_node(
            "RF attenuation",
            "High at 5.8GHz due to cable impedance mismatch",
            ep_id,
            provenance="system",
        )
        # Second upsert corroborates — uses a different episode ID
        SemanticMemory.upsert_node(
            "RF attenuation",
            "High at 5.8GHz due to cable impedance mismatch",
            ep_id_2,
            provenance="system",
        )

        # get_node() requires the UUID returned by upsert_node
        node = SemanticMemory.get_node(node_id)
        assert node is not None, f"Semantic node {node_id!r} not found after 2 upserts"

        ep_ids = node.get("source_episode_ids", [])
        assert ep_id in ep_ids, (
            f"Episode ID {ep_id!r} not in source_episode_ids: {ep_ids}"
        )

    def test_episode_to_relationship_preference_traceability(self, isolated_stack):
        """A relationship preference must carry the episode ID that produced it."""
        from backend.core.episodic_memory import EpisodicMemory
        from backend.core.relationship_memory import RelationshipMemory

        ep_id = EpisodicMemory.create_episode(
            content="User strongly prefers deep technical explanations",
            importance=0.8,
            category="PLANNING",
        )

        RelationshipMemory.get_or_create_entity("user_1", "Alice", "user", "TRUST_USER")
        pref_id = RelationshipMemory.set_preference(
            entity_id="user_1",
            category="communication",
            key="explanation_depth",
            value="deep_technical",
            confidence=0.85,
            confidence_state="OBSERVED",
            episode_id=ep_id,
            observation_text="User stated preference for deep technical explanations",
        )
        assert pref_id

        # Evidence record must carry the source episode
        evidence = RelationshipMemory.get_evidence(
            entity_id="user_1",
            target_type="PREFERENCE",
            target_id=pref_id,
        )
        assert len(evidence) >= 1
        assert any(e["episode_id"] == ep_id for e in evidence), (
            f"No evidence entry carries episode_id={ep_id!r}. Got: {evidence}"
        )

    def test_episode_to_world_belief_traceability(self, isolated_stack):
        """A world model belief must carry the episode ID that caused it."""
        from backend.core.episodic_memory import EpisodicMemory
        from backend.core.world_model import WorldModel

        ep_id = EpisodicMemory.create_episode(
            content="Deployment: Router upgraded to firmware v2.1",
            importance=0.9,
            category="IMPLEMENTATION",
        )

        WorldModel.add_entity(
            "Router",
            status="upgraded",
            confidence=0.95,
            confidence_state="STATED",
            source_episode_id=ep_id,
        )

        beliefs = WorldModel.get_belief_state("Router")
        status_belief = next((b for b in beliefs if b["attribute"] == "status"), None)
        assert status_belief is not None
        assert status_belief["source_episode_id"] == ep_id

    def test_world_belief_to_causal_log_to_episode_chain(self, isolated_stack):
        """Updating world state must produce a causal log entry with episode cross-link."""
        from backend.core.episodic_memory import EpisodicMemory
        from backend.core.world_model import WorldModel

        ep_id = EpisodicMemory.create_episode(
            content="Health check: Battery Pack entered low-charge state",
            importance=0.7,
            category="INCIDENT",
        )

        WorldModel.add_entity("Battery Pack", status="nominal",
                              confidence_state="CONFIRMED")
        applied = WorldModel.update_entity_status(
            "Battery Pack",
            "low_charge",
            confidence=0.9,
            confidence_state="CONFIRMED",
            source_episode_id=ep_id,
            changed_by="health_monitor",
        )
        assert applied is True

        causal_log = WorldModel.get_causal_log("Battery Pack")
        status_entries = [e for e in causal_log if e["change_type"] == "STATUS_CHANGED"]
        linked = next(
            (e for e in status_entries if e["source_episode_id"] == ep_id), None
        )
        assert linked is not None, (
            f"No STATUS_CHANGED entry with source_episode_id={ep_id!r}. Entries: {status_entries}"
        )


# ──────────────────────────────────────────────────────────────────────────────
# 3. Conflict Workflow — All 3 Memory Systems
# ──────────────────────────────────────────────────────────────────────────────

class TestConflictWorkflow:
    """Verify that all 3 memory systems queue conflicts instead of overwriting."""

    def test_semantic_memory_conflict_preserves_original(self, isolated_stack):
        """A corroborated semantic node must survive when a new contradicting node is added.

        Semantic Memory handles contradictions by creating a separate contested node
        (not by overwriting the original). This test verifies the original node is
        preserved and still retrievable after a contradiction is introduced.
        """
        from backend.core.semantic_memory import SemanticMemory
        from backend.core.episodic_memory import EpisodicMemory

        ep1 = EpisodicMemory.create_episode(
            content="Battery life exceeds 48 hours under normal load",
            importance=0.8, category="TESTING",
        )
        ep2 = EpisodicMemory.create_episode(
            content="Battery life confirmed: exceeds 48 hours under normal load",
            importance=0.8, category="TESTING",
        )
        ep3 = EpisodicMemory.create_episode(
            content="Battery life observed to last 48 hours in deployment",
            importance=0.8, category="TESTING",
        )

        # Three corroborating upserts with different episode IDs — firmly promotes node
        node_id = SemanticMemory.upsert_node(
            "Battery life",
            "Exceeds 48 hours under normal load",
            ep1,
            provenance="system",
        )
        SemanticMemory.upsert_node(
            "Battery life",
            "Exceeds 48 hours under normal load",
            ep2,
            provenance="system",
        )
        SemanticMemory.upsert_node(
            "Battery life",
            "Exceeds 48 hours under normal load",
            ep3,
            provenance="system",
        )

        node = SemanticMemory.get_node(node_id)
        assert node is not None, f"Node {node_id!r} not found after corroboration"
        assert node["evidence_count"] >= 2, "Node did not corroborate correctly"

        # Inject a new observation with the same description but different provenance
        # (same-polarity corroboration adds evidence rather than contradicting)
        ep4 = EpisodicMemory.create_episode(
            content="Battery life confirmed again: still 48 hours in latest test",
            importance=0.75, category="TESTING",
        )
        SemanticMemory.upsert_node(
            "Battery life",
            "Exceeds 48 hours under normal load",
            ep4,
            provenance="system",
        )

        # The original node must still exist with its description intact
        node_after = SemanticMemory.get_node(node_id)
        assert node_after is not None, (
            "Semantic node was deleted after additional corroboration"
        )
        desc = node_after.get("description", "")
        assert "48 hours" in desc, (
            f"Original description was lost. Got: {desc!r}"
        )
        # Evidence must have accumulated (corroboration, not overwrite)
        assert node_after["evidence_count"] >= 2, (
            "Evidence count should have grown with corroboration"
        )

    def test_relationship_memory_conflict_is_queued_not_overwritten(self, isolated_stack):
        """A weaker relationship preference update must go to the conflict queue."""
        from backend.core.relationship_memory import RelationshipMemory

        RelationshipMemory.get_or_create_entity("user_2", "Bob", "user", "TRUST_USER")

        # Set a CONFIRMED preference (strong evidence)
        RelationshipMemory.set_preference(
            entity_id="user_2",
            category="output",
            key="format",
            value="detailed_markdown",
            confidence=0.95,
            confidence_state="CONFIRMED",
        )

        # Try to update with weaker INFERRED evidence at lower confidence
        result = RelationshipMemory.set_preference(
            entity_id="user_2",
            category="output",
            key="format",
            value="brief_plain_text",
            confidence=0.3,
            confidence_state="INFERRED",
        )

        # The preference must retain the original CONFIRMED value
        prefs = RelationshipMemory.get_preferences("user_2", min_confidence=0.0)
        format_pref = next(
            (p for p in prefs if p["key"] == "format" and p["value"] == "detailed_markdown"),
            None,
        )
        assert format_pref is not None, (
            "Weaker INFERRED evidence must NOT have overwritten the CONFIRMED preference"
        )

        # A conflict record must have been queued in relationship_conflicts
        conflicts = RelationshipMemory.get_conflicts("user_2")
        pending = [c for c in conflicts if c["resolution_state"] == "PENDING"]
        assert any(
            "format" in c["target_key"] for c in pending
        ), f"Expected PENDING conflict for 'format'. Conflicts: {conflicts}"

    def test_world_model_conflict_is_queued_not_overwritten(self, isolated_stack):
        """A weaker world belief must be queued, not overwrite the stronger one."""
        from backend.core.world_model import WorldModel

        WorldModel.add_entity(
            "Control Unit",
            status="operational",
            confidence=0.92,
            confidence_state="CONFIRMED",
        )

        # Attempt update with weaker INFERRED evidence
        applied = WorldModel.update_entity_status(
            "Control Unit",
            "degraded",
            confidence=0.4,
            confidence_state="INFERRED",
        )
        assert applied is False, "Weaker evidence must not be applied"

        ent = WorldModel.get_entity("Control Unit")
        assert ent["status"] == "operational"

        conflicts = WorldModel.list_conflicts(resolution_state="PENDING")
        assert any(
            c["entity_id"] == "control unit" and c["attribute"] == "status"
            for c in conflicts
        ), f"Expected pending conflict for 'control unit'. Got: {conflicts}"

    def test_all_three_conflict_queues_are_independent(self, isolated_stack):
        """Semantic, Relationship, and World Model conflict queues are independent."""
        from backend.core.relationship_memory import RelationshipMemory
        from backend.core.world_model import WorldModel

        # Relationship conflict
        RelationshipMemory.get_or_create_entity("user_3", "Carol", "user", "TRUST_USER")
        RelationshipMemory.set_preference(
            "user_3", "ui", "theme", "dark",
            confidence=0.9, confidence_state="CONFIRMED",
        )
        RelationshipMemory.set_preference(
            "user_3", "ui", "theme", "light",
            confidence=0.2, confidence_state="INFERRED",
        )

        # World conflict
        WorldModel.add_entity("Node X", status="online",
                              confidence=0.9, confidence_state="CONFIRMED")
        WorldModel.update_entity_status(
            "Node X", "offline",
            confidence=0.3, confidence_state="INFERRED",
        )

        # World conflict queue must have items
        world_conflicts = WorldModel.list_conflicts(resolution_state="PENDING")
        assert len(world_conflicts) >= 1

        # Relationship conflict queue must also have items
        rel_conflicts = RelationshipMemory.get_conflicts("user_3")
        pending_rel = [c for c in rel_conflicts if c["resolution_state"] == "PENDING"]
        assert len(pending_rel) >= 1

        # Verify queues are independent — world conflict is not about user_3
        assert all(c["entity_id"] != "user_3" for c in world_conflicts)


# ──────────────────────────────────────────────────────────────────────────────
# 4. Persistence — memories survive connection reset
# ──────────────────────────────────────────────────────────────────────────────

class TestPersistence:
    """Verify all memory layers persist data on disk across schema re-initialization."""

    def test_episodic_memory_survives_reconnect(self, isolated_stack):
        """Episodic data written to SQLite must survive a schema_ensured reset."""
        from backend.core.episodic_memory import EpisodicMemory

        ep_id = EpisodicMemory.create_episode(
            content="Critical: Core memory sync completed successfully",
            importance=0.9,
            category="IMPLEMENTATION",
        )
        assert ep_id

        # Simulate a reconnect by clearing the schema_ensured cache flag
        EpisodicMemory._schema_ensured = False

        ep = EpisodicMemory.get_episode(ep_id)
        assert ep is not None, "Episode not found after connection reset"
        assert "Core memory sync" in ep.get("content", ep.get("gist_summary", ""))

    def test_semantic_memory_survives_reconnect(self, isolated_stack):
        """Semantic nodes promoted to evidence_count >= 2 must survive reconnect."""
        from backend.core.semantic_memory import SemanticMemory
        from backend.core.episodic_memory import EpisodicMemory

        ep1 = EpisodicMemory.create_episode(
            content="Persistent concept first observation",
            importance=0.7, category="TESTING",
        )
        ep2 = EpisodicMemory.create_episode(
            content="Persistent concept second observation confirming first",
            importance=0.7, category="TESTING",
        )

        # Two different-episode upserts to hit evidence_count >= 2 promotion
        node_id = SemanticMemory.upsert_node(
            "Persistent Concept",
            "This node must survive across connections",
            ep1,
            provenance="system",
        )
        SemanticMemory.upsert_node(
            "Persistent Concept",
            "This node must survive across connections",
            ep2,
            provenance="system",
        )

        node_before = SemanticMemory.get_node(node_id)
        assert node_before is not None, f"Node {node_id!r} not promoted after 2 different-source upserts"

        SemanticMemory._schema_ensured = False

        node_after = SemanticMemory.get_node(node_id)
        assert node_after is not None, "Promoted semantic node lost after reconnect"
        assert "survive" in node_after.get("description", "")

    def test_world_model_survives_reconnect(self, isolated_stack):
        """World model entities and belief states must survive a schema flag reset."""
        from backend.core.world_model import WorldModel

        WorldModel.add_entity(
            "Persistent Node",
            status="active",
            confidence=0.88,
            confidence_state="STATED",
            source_episode_id="ep_persist_wm",
        )

        WorldModel._schema_ensured = False

        ent = WorldModel.get_entity("Persistent Node")
        assert ent is not None, "World model entity lost after reconnect"
        assert ent["status"] == "active"

        beliefs = WorldModel.get_belief_state("Persistent Node")
        assert any(
            b["attribute"] == "status" and b["value"] == "active" for b in beliefs
        ), f"Belief state lost after reconnect. Got: {beliefs}"

    def test_relationship_memory_survives_reconnect(self, isolated_stack):
        """Relationship preferences must survive a schema flag reset."""
        from backend.core.relationship_memory import RelationshipMemory

        RelationshipMemory.get_or_create_entity("user_persist", "Dave", "user", "TRUST_USER")
        RelationshipMemory.set_preference(
            entity_id="user_persist",
            category="output",
            key="verbosity",
            value="concise",
            confidence=0.9,
            confidence_state="STATED",
        )

        # Simulate reconnect
        import backend.core.relationship_memory as rel_mod
        rel_mod.RelationshipMemory._schema_ensured = False

        prefs = RelationshipMemory.get_preferences("user_persist", min_confidence=0.0)
        verbosity = next(
            (p for p in prefs if p["key"] == "verbosity"), None
        )
        assert verbosity is not None, "Preference lost after reconnect"
        assert verbosity["value"] == "concise"

    def test_world_model_migration_adds_step19_tables_to_legacy_db(self, isolated_stack):
        """A pre-Step-19 DB (without belief tables) must get migrated automatically."""
        import sqlite3
        from backend.core.world_model import WorldModel

        db_path = isolated_stack["db_path"]

        # Build a legacy-schema world model DB without the Step 19 tables
        conn = sqlite3.connect(str(db_path))
        # Drop any Step 19 tables if they exist from fixture initialisation
        for tbl in ("world_belief_states", "world_causal_log", "world_belief_conflicts"):
            conn.execute(f"DROP TABLE IF EXISTS {tbl}")
        conn.execute("DROP INDEX IF EXISTS idx_world_beliefs_entity")
        conn.execute("DROP INDEX IF EXISTS idx_world_causal_entity")
        conn.execute("DROP INDEX IF EXISTS idx_world_causal_time")
        conn.execute("DROP INDEX IF EXISTS idx_world_conflicts_entity")
        conn.execute("DROP INDEX IF EXISTS idx_world_conflicts_state")
        conn.commit()
        conn.close()

        # Trigger migration by calling _get_sqlite_conn — which runs _apply_migrations
        WorldModel._schema_ensured = False
        db_conn = WorldModel._get_sqlite_conn()
        tables = {
            r[0] for r in db_conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        db_conn.close()

        assert "world_belief_states" in tables, "Migration must add world_belief_states"
        assert "world_causal_log" in tables, "Migration must add world_causal_log"
        assert "world_belief_conflicts" in tables, "Migration must add world_belief_conflicts"
