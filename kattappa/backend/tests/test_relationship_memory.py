import json
import sqlite3
import time
import unittest
from unittest.mock import patch

from backend.core.relationship_memory import RelationshipMemory, redact_secrets, classify_sensitive_content
from backend.core.memory_governance import MemoryGovernance
from backend.core.memory_assembler import MemoryAssembler


class NoCloseConnection:
    def __init__(self, conn):
        self._conn = conn

    def __getattr__(self, name):
        return getattr(self._conn, name)

    def close(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass


class TestRelationshipMemory(unittest.TestCase):

    def setUp(self):
        # Create a single shared in-memory DB connection to ensure schema isolation during tests
        if not hasattr(self.__class__, "_shared_conn"):
            self.__class__._shared_conn = sqlite3.connect(":memory:", check_same_thread=False)
            self.__class__._shared_conn.row_factory = sqlite3.Row
            RelationshipMemory._ensure_schema(self.__class__._shared_conn)
            MemoryGovernance._ensure_schema(self.__class__._shared_conn)

            from backend.core.episodic_memory import EpisodicMemory
            EpisodicMemory._ensure_schema(self.__class__._shared_conn)

            from backend.core.semantic_memory import SemanticMemory
            SemanticMemory._ensure_schema(self.__class__._shared_conn)

        # Clear tables between tests
        self.__class__._shared_conn.execute("DELETE FROM hm_entities")
        self.__class__._shared_conn.execute("DELETE FROM hm_preferences")
        self.__class__._shared_conn.execute("DELETE FROM hm_projects")
        self.__class__._shared_conn.execute("DELETE FROM hm_user_goals")
        self.__class__._shared_conn.execute("DELETE FROM hm_relationship_history")
        self.__class__._shared_conn.execute("DELETE FROM hm_relationship_candidates")
        self.__class__._shared_conn.execute("DELETE FROM hm_emotional_state")
        self.__class__._shared_conn.execute("DELETE FROM hm_trust_registry")
        self.__class__._shared_conn.execute("DELETE FROM hm_provenance")
        self.__class__._shared_conn.commit()

        # Patch connection getters to return our shared in-memory connection
        from backend.core.episodic_memory import EpisodicMemory
        from backend.core.semantic_memory import SemanticMemory
        self.conn_patchers = [
            patch.object(RelationshipMemory, "_get_sqlite_conn", return_value=NoCloseConnection(self.__class__._shared_conn)),
            patch.object(MemoryGovernance, "_get_sqlite_conn", return_value=NoCloseConnection(self.__class__._shared_conn)),
            patch.object(EpisodicMemory, "_get_sqlite_conn", return_value=NoCloseConnection(self.__class__._shared_conn)),
            patch.object(SemanticMemory, "_get_sqlite_conn", return_value=NoCloseConnection(self.__class__._shared_conn)),
        ]
        for p in self.conn_patchers:
            p.start()

    def tearDown(self):
        for p in self.conn_patchers:
            p.stop()

    def test_entity_creation_and_trust(self):
        """Verify entities can be registered and updated in the trust registry."""
        entity = RelationshipMemory.get_or_create_entity("user_123", "Bala Sekhar", "user", "TRUST_USER")
        self.assertEqual(entity["id"], "user_123")
        self.assertEqual(entity["name"], "Bala Sekhar")
        self.assertEqual(entity["trust_level"], "TRUST_USER")

        # Verify default trust registration in memory governance
        self.assertEqual(MemoryGovernance.get_trust("user_123"), "TRUST_USER")

    def test_plaintext_storage(self):
        """Verify plaintext storage (no homemade crypto)."""
        entity_id = "user_123"
        RelationshipMemory.get_or_create_entity(entity_id, "Bala Sekhar")

        # Set preference
        RelationshipMemory.set_preference(entity_id, "tone", "verbosity", "concise")

        # Direct database query should yield plaintext
        row = self.__class__._shared_conn.execute("SELECT value FROM hm_preferences WHERE key = 'verbosity'").fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row["value"], "concise")

    def test_sensitive_category_blocker(self):
        """Verify blocked sensitive categories trigger ValueErrors prior to insertion/candidate creation."""
        entity_id = "user_123"
        RelationshipMemory.get_or_create_entity(entity_id, "Bala Sekhar")

        # Prohibited topics should raise ValueError
        with self.assertRaises(ValueError):
            RelationshipMemory.set_preference(entity_id, "religion", "belief", "I go to church")

        with self.assertRaises(ValueError):
            RelationshipMemory.add_candidate(entity_id, "preference", "health:condition", "taking cardio hospital drugs")

        with self.assertRaises(ValueError):
            RelationshipMemory.add_project(entity_id, "sensitive_proj", "politics and democratic senator debates")

        # Standard topics should pass
        pref_id = RelationshipMemory.set_preference(entity_id, "tone", "verbosity", "concise")
        self.assertIsNotNone(pref_id)

    def test_opt_in_emotional_logging(self):
        """Verify emotional logging is strictly gated by the opt-in privacy preference."""
        entity_id = "user_123"
        RelationshipMemory.get_or_create_entity(entity_id, "Bala Sekhar")

        # Disabled by default
        self.assertFalse(RelationshipMemory.is_emotional_logging_enabled(entity_id))
        self.assertIsNone(RelationshipMemory.set_emotional_state(entity_id, "frustrated", 0.9))

        # Enable opt-in
        RelationshipMemory.set_preference(entity_id, "privacy", "emotional_logging_enabled", "true")
        self.assertTrue(RelationshipMemory.is_emotional_logging_enabled(entity_id))

        # Should now succeed
        state_id = RelationshipMemory.set_emotional_state(entity_id, "frustrated", 0.9)
        self.assertIsNotNone(state_id)

    def test_right_to_forget_cascade(self):
        """Verify Right-To-Forget cascade explicitly deletes all entity data across tables."""
        entity_id = "user_123"
        RelationshipMemory.get_or_create_entity(entity_id, "Bala Sekhar")

        # Populate tables
        RelationshipMemory.set_preference(entity_id, "tone", "verbosity", "verbose")
        RelationshipMemory.add_project(entity_id, "Project X", "Description")
        RelationshipMemory.add_user_goal(entity_id, "Goal 1", priority=0.8, approved=True)
        RelationshipMemory.add_history(entity_id, "Interaction note")

        # Execute Cascade
        self.assertTrue(RelationshipMemory.forget(entity_id))

        # Verify deletion
        self.assertIsNone(RelationshipMemory.get_entity(entity_id))
        self.assertEqual(len(RelationshipMemory.get_preferences(entity_id)), 0)
        self.assertEqual(len(RelationshipMemory.get_projects(entity_id)), 0)
        self.assertEqual(len(RelationshipMemory.get_user_goals(entity_id)), 0)
        self.assertEqual(len(RelationshipMemory.get_history(entity_id)), 0)

    def test_candidate_promotion_workflow(self):
        """Verify candidates transition to pending_approval and require manual user confirmation to promote."""
        entity_id = "user_123"
        RelationshipMemory.get_or_create_entity(entity_id, "Bala Sekhar")

        # 1. Add candidate (evidence = 1) -> status: pending
        cand_id = RelationshipMemory.add_candidate(entity_id, "preference", "tone:verbosity", "brief")
        cands = RelationshipMemory.list_candidates(entity_id, "pending")
        self.assertEqual(len(cands), 1)
        self.assertEqual(cands[0]["evidence_count"], 1)

        # 2. Add again (evidence = 2) -> status: pending_approval (NOT auto-promoted)
        RelationshipMemory.add_candidate(entity_id, "preference", "tone:verbosity", "brief")
        self.assertEqual(len(RelationshipMemory.list_candidates(entity_id, "pending")), 0)
        cands_appr = RelationshipMemory.list_candidates(entity_id, "pending_approval")
        self.assertEqual(len(cands_appr), 1)
        self.assertEqual(cands_appr[0]["evidence_count"], 2)
        
        # Confirm no preference exists yet
        self.assertEqual(len(RelationshipMemory.get_preferences(entity_id)), 0)

        # 3. Promote manually with user confirmation
        self.assertTrue(RelationshipMemory.promote_candidate_manually(cand_id))
        
        # Candidate status should be promoted
        self.assertEqual(len(RelationshipMemory.list_candidates(entity_id, "pending_approval")), 0)
        
        # Preference should now exist and be active
        prefs = RelationshipMemory.get_preferences(entity_id, "tone")
        self.assertEqual(len(prefs), 1)
        self.assertEqual(prefs[0]["value"], "brief")
        self.assertEqual(prefs[0]["status"], "active")

        # Provenance should be recorded
        prov = MemoryGovernance.get_provenance(prefs[0]["id"])
        self.assertIsNotNone(prov)
        self.assertEqual(prov["memory_type"], "semantic")
        self.assertIn(cand_id, prov["derived_from"])

    def test_preference_lifecycle(self):
        """Verify preference changes mark preceding preferences as superseded instead of overwriting."""
        entity_id = "user_123"
        RelationshipMemory.get_or_create_entity(entity_id, "Bala Sekhar")

        # Set first preference
        pref_id1 = RelationshipMemory.set_preference(entity_id, "tone", "verbosity", "brief")
        
        # Set new preference
        pref_id2 = RelationshipMemory.set_preference(entity_id, "tone", "verbosity", "verbose")

        # Only the active preference should be retrieved
        prefs = RelationshipMemory.get_preferences(entity_id, "tone")
        self.assertEqual(len(prefs), 1)
        self.assertEqual(prefs[0]["value"], "verbose")
        self.assertEqual(prefs[0]["status"], "active")

        # Check full history contains both
        history = RelationshipMemory.get_preference_history(entity_id, "tone", "verbosity")
        self.assertEqual(len(history), 2)
        self.assertEqual(history[0]["value"], "verbose")
        self.assertEqual(history[0]["status"], "active")
        self.assertEqual(history[1]["value"], "brief")
        self.assertEqual(history[1]["status"], "superseded")
        self.assertEqual(history[1]["superseded_by"], pref_id2)

    def test_governance_gc_sweep_integration(self):
        """Verify expired candidates transition to 'expired' and emotional states are pruned."""
        entity_id = "user_123"
        RelationshipMemory.get_or_create_entity(entity_id, "Bala Sekhar")
        RelationshipMemory.set_preference(entity_id, "privacy", "emotional_logging_enabled", "true")

        # Create expired candidate
        with patch("time.time", return_value=time.time() - 1000):
            cand_id = RelationshipMemory.add_candidate(entity_id, "preference", "tone:verbosity", "brief", ttl_seconds=100)

        # Create expired emotional state
        with patch("time.time", return_value=time.time() - 1000):
            RelationshipMemory.set_emotional_state(entity_id, "happy", 0.9, ttl_seconds=100)

        # Verify they exist in DB
        self.assertEqual(len(RelationshipMemory.list_candidates(entity_id)), 1)
        row = self.__class__._shared_conn.execute("SELECT id FROM hm_emotional_state WHERE entity_id = ?", (entity_id,)).fetchone()
        self.assertIsNotNone(row)

        # Run centralized GC sweep via MemoryGovernance
        results = MemoryGovernance.run_global_gc()
        self.assertEqual(results["expired_candidates_pruned"], 1)
        self.assertEqual(results["expired_emotions_pruned"], 1)

        # Verify candidate transitioned to 'expired'
        self.assertEqual(len(RelationshipMemory.list_candidates(entity_id)), 0)
        cand_row = self.__class__._shared_conn.execute("SELECT status FROM hm_relationship_candidates WHERE id = ?", (cand_id,)).fetchone()
        self.assertIsNotNone(cand_row)
        self.assertEqual(cand_row["status"], "expired")

        # Verify emotional state is deleted
        row = self.__class__._shared_conn.execute("SELECT id FROM hm_emotional_state WHERE entity_id = ?", (entity_id,)).fetchone()
        self.assertIsNone(row)

    def test_memory_assembler_context_inclusion(self):
        """Verify the context assembler queries, respects skip_semantic, and includes Layer 7 Relationship Memory."""
        entity_id = "primary"
        RelationshipMemory.get_or_create_entity(entity_id, "User")
        RelationshipMemory.set_preference(entity_id, "tone", "verbosity", "brief")
        RelationshipMemory.add_project(entity_id, "Active Project", "desc", status="active")
        RelationshipMemory.add_user_goal(entity_id, "User Goal", priority=0.9, approved=True)
        RelationshipMemory.add_history(entity_id, "Last interaction summary note")

        # Test context assembly with skip_semantic = True
        with (
            patch.object(MemoryAssembler, "_query_semantic", return_value=[]) as mock_sem,
            patch.object(MemoryAssembler, "_query_episodic", return_value=[]) as mock_epi,
        ):
            context = MemoryAssembler.assemble_context("arbitrary query", skip_semantic=True)
            mock_sem.assert_not_called()
            mock_epi.assert_not_called()

        self.assertIn("relationship_memory", context)
        rel_mem = context["relationship_memory"]
        self.assertEqual(len(rel_mem["preferences"]), 1)
        self.assertEqual(rel_mem["preferences"][0]["key"], "verbosity")
        self.assertEqual(rel_mem["preferences"][0]["value"], "brief")
        
        self.assertEqual(len(rel_mem["active_goals"]), 1)
        self.assertEqual(rel_mem["active_goals"][0]["goal"], "User Goal")
        
        self.assertEqual(len(rel_mem["active_projects"]), 1)
        self.assertEqual(rel_mem["active_projects"][0]["project_name"], "Active Project")
        
        self.assertEqual(len(rel_mem["recent_history"]), 1)
        self.assertEqual(rel_mem["recent_history"][0]["summary"], "Last interaction summary note")

    def test_explicit_goal_approvals(self):
        """Verify that goals default to unapproved (approved=0) and require explicit approval."""
        entity_id = "user_123"
        RelationshipMemory.get_or_create_entity(entity_id, "Bala Sekhar")

        # 1. Add goal -> should default to approved=False (0)
        goal_id = RelationshipMemory.add_user_goal(entity_id, "Build a new robotic arm", priority=0.8)
        
        # 2. Get goals (include_unapproved=False) -> should NOT return it
        goals = RelationshipMemory.get_user_goals(entity_id, include_unapproved=False)
        self.assertEqual(len(goals), 0)

        # 3. Get goals (include_unapproved=True) -> should return it
        all_goals = RelationshipMemory.get_user_goals(entity_id, include_unapproved=True)
        self.assertEqual(len(all_goals), 1)
        self.assertEqual(all_goals[0]["goal"], "Build a new robotic arm")
        self.assertEqual(all_goals[0]["approved"], 0)

        # 4. Explicitly approve the goal
        success = RelationshipMemory.approve_goal(goal_id)
        self.assertTrue(success)

        # 5. Get goals (include_unapproved=False) -> should now return it
        approved_goals = RelationshipMemory.get_user_goals(entity_id, include_unapproved=False)
        self.assertEqual(len(approved_goals), 1)
        self.assertEqual(approved_goals[0]["approved"], 1)

    def test_relevance_floors(self):
        """Verify that relevance floors are successfully enforced at both database retrieval and assembler levels."""
        entity_id = "primary"
        RelationshipMemory.get_or_create_entity(entity_id, "User", "user", "TRUST_USER")

        # Create preferences with high and low confidence
        RelationshipMemory.set_preference(entity_id, "tone", "verbosity", "brief", confidence=0.8)
        RelationshipMemory.set_preference(entity_id, "tone", "speed", "fast", confidence=0.4) # Below 0.5 floor

        # Create goals with high and low priority
        g1 = RelationshipMemory.add_user_goal(entity_id, "Important Goal", priority=0.7)
        g2 = RelationshipMemory.add_user_goal(entity_id, "Low Priority Goal", priority=0.2) # Below 0.3 floor
        RelationshipMemory.approve_goal(g1)
        RelationshipMemory.approve_goal(g2)

        # Create projects with high and low priority
        RelationshipMemory.add_project(entity_id, "Project High", "desc", priority=0.6)
        RelationshipMemory.add_project(entity_id, "Project Low", "desc", priority=0.1) # Below 0.3 floor

        # Create history items with high and low importance
        RelationshipMemory.add_history(entity_id, "High importance interaction", importance=0.9)
        RelationshipMemory.add_history(entity_id, "Low importance interaction", importance=0.2) # Below 0.3 floor

        # Test DB level filtering defaults
        self.assertEqual(len(RelationshipMemory.get_preferences(entity_id)), 1)
        self.assertEqual(RelationshipMemory.get_preferences(entity_id)[0]["key"], "verbosity")

        self.assertEqual(len(RelationshipMemory.get_user_goals(entity_id)), 1)
        self.assertEqual(RelationshipMemory.get_user_goals(entity_id)[0]["goal"], "Important Goal")

        self.assertEqual(len(RelationshipMemory.get_projects(entity_id)), 1)
        self.assertEqual(RelationshipMemory.get_projects(entity_id)[0]["project_name"], "Project High")

        self.assertEqual(len(RelationshipMemory.get_history(entity_id)), 1)
        self.assertEqual(RelationshipMemory.get_history(entity_id)[0]["summary"], "High importance interaction")

        # Test Assembler context integration level filtering
        with (
            patch.object(MemoryAssembler, "_query_semantic", return_value=[]) as mock_sem,
            patch.object(MemoryAssembler, "_query_episodic", return_value=[]) as mock_epi,
        ):
            context = MemoryAssembler.assemble_context("dummy", skip_semantic=True)

        rel_mem = context["relationship_memory"]
        self.assertEqual(len(rel_mem["preferences"]), 1)
        self.assertEqual(rel_mem["preferences"][0]["key"], "verbosity")

        self.assertEqual(len(rel_mem["active_goals"]), 1)
        self.assertEqual(rel_mem["active_goals"][0]["goal"], "Important Goal")

        self.assertEqual(len(rel_mem["active_projects"]), 1)
        self.assertEqual(rel_mem["active_projects"][0]["project_name"], "Project High")

        self.assertEqual(len(rel_mem["recent_history"]), 1)
        self.assertEqual(rel_mem["recent_history"][0]["summary"], "High importance interaction")

    def test_history_compaction(self):
        """Verify that history compaction helper consolidates entries older than 30 days and logs provenance."""
        entity_id = "user_123"
        RelationshipMemory.get_or_create_entity(entity_id, "Bala Sekhar")

        now = time.time()
        # Insert 3 history entries: 2 older than 30 days, 1 recent
        with patch("time.time", return_value=now - 40 * 86400):
            h1 = RelationshipMemory.add_history(entity_id, "Older interaction 1", importance=0.4)
            h2 = RelationshipMemory.add_history(entity_id, "Older interaction 2", importance=0.6)

        h3 = RelationshipMemory.add_history(entity_id, "Recent interaction", importance=0.8)

        # Confirm 3 entries exist initially (using a low importance floor to get all of them)
        initial_history = RelationshipMemory.get_history(entity_id, limit=10, min_importance=0.1)
        self.assertEqual(len(initial_history), 3)

        # Run compaction
        success = RelationshipMemory.compact_history(entity_id, age_days=30)
        self.assertTrue(success)

        # Verify compacted structure
        # h1 and h2 should be deleted and replaced with a consolidated entry.
        # h3 (recent) should remain intact.
        remaining = RelationshipMemory.get_history(entity_id, limit=10, min_importance=0.1)
        self.assertEqual(len(remaining), 2)
        
        recent_entry = [r for r in remaining if r["id"] == h3][0]
        self.assertEqual(recent_entry["summary"], "Recent interaction")

        compacted_entry = [r for r in remaining if r["id"] != h3][0]
        self.assertIn("Compacted monthly summary (2 entries)", compacted_entry["summary"])
        self.assertIn("Older interaction 1", compacted_entry["summary"])
        self.assertIn("Older interaction 2", compacted_entry["summary"])
        
        # Max importance + 0.1: max(0.4, 0.6) + 0.1 = 0.7
        self.assertAlmostEqual(compacted_entry["importance"], 0.7)

        # Verify provenance was logged for the compacted entry
        prov = MemoryGovernance.get_provenance(compacted_entry["id"])
        self.assertIsNotNone(prov)
        self.assertEqual(prov["memory_type"], "semantic")
        self.assertEqual(prov["source"], "system")
        self.assertEqual(prov["created_by"], "broker")
        self.assertEqual(set(prov["derived_from"]), {h1, h2})
        self.assertEqual(prov["metadata"]["compaction_event"], "monthly")

        # Verify compacted entry has is_compacted = 1
        self.assertEqual(compacted_entry["is_compacted"], 1)

        # Verify that if we add another old entry, and run compaction again,
        # it does NOT select the already compacted entry (requires at least 2 uncompacted entries to run compaction).
        with patch("time.time", return_value=now - 40 * 86400):
            h4 = RelationshipMemory.add_history(entity_id, "Another old interaction", importance=0.5)

        # Only h4 is uncompacted and older than 30 days. compacted_entry is already compacted (is_compacted=1).
        # Running compaction should return False because there is only 1 uncompacted older entry.
        success_second = RelationshipMemory.compact_history(entity_id, age_days=30)
        self.assertFalse(success_second)

    def test_confidence_states(self):
        """Verify confidence prioritizing orders and consistency-frequency calculations."""
        import math
        entity_id = "user_conf"
        RelationshipMemory.get_or_create_entity(entity_id, "User Conf")
        
        # Inferred / Observed preferences with default confidence (1.0) will be calculated
        pref_id1 = RelationshipMemory.set_preference(entity_id, "category_1", "key_1", "value_1", confidence=1.0, confidence_state="INFERRED", evidence_count=1)
        # Check that it uses the formula: C = consistency * (1.0 - exp(-0.08 * N))
        # N = 1, consistency = 1.0 => C = 1.0 * (1 - e^-0.08) approx 0.0768
        prefs = RelationshipMemory.get_preferences(entity_id, "category_1", min_confidence=0.0)
        self.assertEqual(len(prefs), 1)
        self.assertAlmostEqual(prefs[0]["confidence"], 1.0 - math.exp(-0.08), places=4)
        self.assertEqual(prefs[0]["confidence_state"], "INFERRED")

        # Let's add it again to increase N and confidence
        pref_id2 = RelationshipMemory.set_preference(entity_id, "category_1", "key_1", "value_1", confidence=1.0, confidence_state="INFERRED", evidence_count=1)
        # N = 2, consistency = 1.0 => C = 1 - e^-0.16 approx 0.1478
        prefs = RelationshipMemory.get_preferences(entity_id, "category_1", min_confidence=0.0)
        self.assertEqual(len(prefs), 1)
        self.assertAlmostEqual(prefs[0]["confidence"], 1.0 - math.exp(-0.16), places=4)

        # STATED and CONFIRMED should keep confidence = 1.0 even if we set confidence_state
        pref_id3 = RelationshipMemory.set_preference(entity_id, "category_1", "key_stated", "value_stated", confidence=1.0, confidence_state="STATED")
        prefs = RelationshipMemory.get_preferences(entity_id, "category_1", min_confidence=0.5)
        stated_pref = [p for p in prefs if p["key"] == "key_stated"][0]
        self.assertEqual(stated_pref["confidence"], 1.0)
        self.assertEqual(stated_pref["confidence_state"], "STATED")

    def test_dunbar_layers(self):
        """Verify storage limits based on Dunbar Layers."""
        entity_id = "user_dunbar"
        RelationshipMemory.get_or_create_entity(entity_id, "User Dunbar")
        
        # Default layer is 1, which has a limit of 15 preferences
        # Let's set layer to 0 (limit 5)
        RelationshipMemory.update_entity_dunbar_layer(entity_id, 0)
        
        # Set 6 active preferences
        for i in range(6):
            RelationshipMemory.set_preference(entity_id, "test_cat", f"key_{i}", f"value_{i}", confidence=1.0)
            
        # Get active preferences - should be capped at 5
        prefs = RelationshipMemory.get_preferences(entity_id, min_confidence=0.0)
        self.assertEqual(len(prefs), 5)
        
        # Now change Dunbar layer to 2 (limit 50)
        RelationshipMemory.update_entity_dunbar_layer(entity_id, 2)
        # Set another 10 active preferences
        for i in range(6, 16):
            RelationshipMemory.set_preference(entity_id, "test_cat", f"key_{i}", f"value_{i}", confidence=1.0)
            
        # Should now have 15 active preferences (5 from before, and 10 new)
        prefs = RelationshipMemory.get_preferences(entity_id, min_confidence=0.0)
        self.assertEqual(len(prefs), 15)

    def test_relationship_conflict_queue(self):
        """Verify that setting a contradictory preference value does not overwrite the existing record but queues a conflict."""
        entity_id = "user_conflict"
        RelationshipMemory.get_or_create_entity(entity_id, "User Conflict")
        
        # Insert initial preference
        RelationshipMemory.set_preference(entity_id, "editor", "type", "vim", confidence=1.0)
        
        # Set a contradictory preference with confidence < 1.0 and state != CONFIRMED/STATED
        conflict_id = RelationshipMemory.set_preference(entity_id, "editor", "type", "emacs", confidence=0.8, confidence_state="OBSERVED")
        
        # Ensure preference is NOT overwritten
        prefs = RelationshipMemory.get_preferences(entity_id, "editor")
        self.assertEqual(len(prefs), 1)
        self.assertEqual(prefs[0]["value"], "vim")
        
        # Check conflict queue
        conflicts = RelationshipMemory.get_conflicts(entity_id)
        self.assertEqual(len(conflicts), 1)
        self.assertEqual(conflicts[0]["id"], conflict_id)
        self.assertEqual(conflicts[0]["old_value"], "vim")
        self.assertEqual(conflicts[0]["new_value"], "emacs")
        self.assertEqual(conflicts[0]["resolution_state"], "PENDING")

    def test_attention_budget_hot_cold(self):
        """Verify capping active prompting contexts to the top 100 hot records."""
        from backend.core.relationship_memory import RelationshipAssembler
        entity_id = "user_budget"
        RelationshipMemory.get_or_create_entity(entity_id, "User Budget")
        RelationshipMemory.update_entity_dunbar_layer(entity_id, 3)
        
        # Ingest 90 preferences with varying confidence scores
        for i in range(90):
            # Set confidence starting from 1.0 down to 0.55
            conf = 1.0 - (i * 0.005)
            RelationshipMemory.set_preference(entity_id, "cat", f"pref_{i}", f"value_{i}", confidence=conf, confidence_state="CONFIRMED")
            
        # Ingest 15 approved goals
        for i in range(15):
            gid = RelationshipMemory.add_user_goal(entity_id, f"Goal {i}", priority=0.8, approved=True)
            
        # Ingest 15 projects
        for i in range(15):
            RelationshipMemory.add_project(entity_id, f"Proj {i}", f"desc {i}", priority=0.7)
            
        profile = RelationshipAssembler.assemble(entity_id)
        self.assertIsNotNone(profile)
        
        # Total items = 90 + 15 + 15 = 120 items
        # The hot partition must be capped to 100 items
        total_hot = len(profile["preferences"]) + len(profile["goals"]) + len(profile["projects"])
        self.assertEqual(total_hot, 100)
        self.assertEqual(profile["retrieval_explainability"]["hot_items_count"], 100)
        self.assertEqual(profile["retrieval_explainability"]["cold_items_count"], 20)

    def test_retrieval_explainability(self):
        """Confirm explainability ranking payload formats."""
        from backend.core.relationship_memory import RelationshipAssembler
        entity_id = "user_exp"
        RelationshipMemory.get_or_create_entity(entity_id, "User Expl")
        RelationshipMemory.set_preference(entity_id, "tone", "verbosity", "concise", confidence=0.9, confidence_state="STATED")
        
        profile = RelationshipAssembler.assemble(entity_id)
        self.assertIn("retrieval_explainability", profile)
        expl = profile["retrieval_explainability"]
        self.assertEqual(expl["hot_items_count"], 1)
        self.assertEqual(len(expl["ranking"]), 1)
        
        rank_item = expl["ranking"][0]
        self.assertEqual(rank_item["type"], "preference")
        self.assertEqual(rank_item["identifier"], "tone:verbosity")
        self.assertEqual(rank_item["evidence_count"], 1)
        self.assertAlmostEqual(rank_item["score"], 0.20 * 0.9, places=4)

    def test_domain_trust_isolation(self):
        """Assert updates to specific trust domains do not leak to other spaces."""
        entity_id = "user_trust_iso"
        RelationshipMemory.get_or_create_entity(entity_id, "User Trust Iso")
        
        # Initial trust states for GLOBAL and CODE_EXECUTION
        t_global = RelationshipMemory.get_or_create_trust(entity_id, domain="GLOBAL")
        t_code = RelationshipMemory.get_or_create_trust(entity_id, domain="CODE_EXECUTION")
        self.assertEqual(t_global["trust_score"], 0.0)
        self.assertEqual(t_code["trust_score"], 0.0)
        
        # Update CODE_EXECUTION trust
        RelationshipMemory.update_trust(entity_id, evidence_strength=0.8, domain="CODE_EXECUTION")
        
        # GLOBAL trust should remain unchanged (0.0)
        t_global_new = RelationshipMemory.get_trust(entity_id, domain="GLOBAL")
        self.assertEqual(t_global_new["trust_score"], 0.0)
        
        # CODE_EXECUTION trust should be updated
        t_code_new = RelationshipMemory.get_trust(entity_id, domain="CODE_EXECUTION")
        self.assertGreater(t_code_new["trust_score"], 0.0)
        self.assertEqual(t_code_new["evidence_count"], 1)

    def test_relationship_evidence_graph(self):
        """Verify linking every relationship belief to episode_id and retrieving it."""
        from backend.core.relationship_memory import RelationshipAssembler
        entity_id = "user_evidence_test"
        RelationshipMemory.get_or_create_entity(entity_id, "Evidence User")

        # 1. Set preference with episode_id
        pref_id = RelationshipMemory.set_preference(
            entity_id, "tone", "format", "markdown",
            confidence=1.0, confidence_state="STATED",
            episode_id="conv_101", observation_text="User requests markdown formatting"
        )
        
        # Verify evidence is recorded
        ev_pref = RelationshipMemory.get_evidence(entity_id, "PREFERENCE", pref_id)
        self.assertEqual(len(ev_pref), 1)
        self.assertEqual(ev_pref[0]["episode_id"], "conv_101")
        self.assertEqual(ev_pref[0]["observation_text"], "User requests markdown formatting")

        # 2. Corroborate preference with a different episode_id
        RelationshipMemory.set_preference(
            entity_id, "tone", "format", "markdown",
            confidence=1.0, confidence_state="STATED",
            episode_id="conv_102", observation_text="User again requests markdown"
        )
        
        ev_pref_corroborated = RelationshipMemory.get_evidence(entity_id, "PREFERENCE", pref_id)
        self.assertEqual(len(ev_pref_corroborated), 2)
        # Ordered by timestamp desc, so conv_102 (newest) should be first
        self.assertEqual(ev_pref_corroborated[0]["episode_id"], "conv_102")
        self.assertEqual(ev_pref_corroborated[1]["episode_id"], "conv_101")

        # 3. Add goal with episode_id
        goal_id = RelationshipMemory.add_user_goal(
            entity_id, "Write a compiler in Rust", priority=0.9, approved=True,
            episode_id="conv_103", observation_text="User states their core goal"
        )
        ev_goal = RelationshipMemory.get_evidence(entity_id, "GOAL", goal_id)
        self.assertEqual(len(ev_goal), 1)
        self.assertEqual(ev_goal[0]["episode_id"], "conv_103")

        # 4. Add project with episode_id
        proj_id = RelationshipMemory.add_project(
            entity_id, "Rust Compiler", "Rust compiler project description", priority=0.8,
            episode_id="conv_104", observation_text="User initiates Rust compiler project"
        )
        ev_proj = RelationshipMemory.get_evidence(entity_id, "PROJECT", proj_id)
        self.assertEqual(len(ev_proj), 1)
        self.assertEqual(ev_proj[0]["episode_id"], "conv_104")

        # 5. Set style with episode_id
        style_id = RelationshipMemory.set_communication_style(
            entity_id, "tone", "concise", confidence=0.8, source="observed",
            episode_id="conv_105", observation_text="Observed short responses preference"
        )
        ev_style = RelationshipMemory.get_evidence(entity_id, "STYLE", style_id)
        self.assertEqual(len(ev_style), 1)
        self.assertEqual(ev_style[0]["episode_id"], "conv_105")

        # 6. Update trust with episode_id
        trust_res = RelationshipMemory.update_trust(
            entity_id, evidence_strength=0.9, domain="CODE_EXECUTION",
            episode_id="conv_106", observation_text="Accurate bash script compilation"
        )
        trust_rec = RelationshipMemory.get_trust(entity_id, domain="CODE_EXECUTION")
        ev_trust = RelationshipMemory.get_evidence(entity_id, "TRUST", trust_rec["id"])
        self.assertEqual(len(ev_trust), 1)
        self.assertEqual(ev_trust[0]["episode_id"], "conv_106")

        # 7. Assert that assembler payload embeds the evidence records correctly
        profile = RelationshipAssembler.assemble(entity_id)
        self.assertIsNotNone(profile)
        
        # Verify preferences evidence
        pref_item = [p for p in profile["preferences"] if p["key"] == "format"][0]
        self.assertEqual(len(pref_item["evidence"]), 2)
        self.assertEqual(pref_item["evidence"][0]["episode_id"], "conv_102")

        # Verify goals evidence
        goal_item = [g for g in profile["goals"] if g["goal"] == "Write a compiler in Rust"][0]
        self.assertEqual(len(goal_item["evidence"]), 1)
        self.assertEqual(goal_item["evidence"][0]["episode_id"], "conv_103")

        # Verify projects evidence
        proj_item = [p for p in profile["projects"] if p["project_name"] == "Rust Compiler"][0]
        self.assertEqual(len(proj_item["evidence"]), 1)
        self.assertEqual(proj_item["evidence"][0]["episode_id"], "conv_104")

        # Verify explainability ranking embeds evidence too
        ranking = profile["retrieval_explainability"]["ranking"]
        # Find project ranking item
        proj_rank = [r for r in ranking if r["type"] == "project" and r["identifier"] == "Rust Compiler"][0]
        self.assertEqual(len(proj_rank["evidence"]), 1)
        self.assertEqual(proj_rank["evidence"][0]["episode_id"], "conv_104")
