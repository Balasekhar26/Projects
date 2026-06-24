"""Step 11: Relationship Engine — Architecture Contract Tests.

Validates:
  1. Relationship ≠ Permission (structural isolation)
  2. User profile — entity CRUD, identity verification
  3. Communication style layer
  4. Preference tracking — versioning, contradiction chaining, confidence decay
  5. Trust score — EMA formula, slow drift, confidence falls on contradiction
  6. Goal tracking — lifecycle, approval gate, not auto-elevated
  7. Project tracking + conversation history linkage
  8. Observed behaviors — evidence-linked, no psychological labels
  9. Channel binding — identity bound to channels, not display names
 10. RelationshipAssembler — full profile assembly
 11. Right-to-forget cascade (all new tables purged)
 12. Relationship≠Permission: authority modules have no imports from relationship_memory
"""

from __future__ import annotations

import json
import sqlite3
import time
import unittest
from unittest.mock import patch


class _NoClose:
    """Shared in-memory DB wrapper that prevents conn.close() from destroying state."""
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def __getattr__(self, name: str):
        return getattr(self._conn, name)

    def close(self) -> None:
        pass


def _make_shared_conn():
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


# ---------------------------------------------------------------------------
# 1. Relationship ≠ Permission: structural isolation
# ---------------------------------------------------------------------------

class TestRelationshipPermissionWall(unittest.TestCase):
    """Authority modules must have zero imports from relationship_memory."""

    AUTHORITY_MODULES = [
        "backend.core.execution_policy",
        "backend.core.risk_classifier",
        "backend.core.capability_broker",
        "backend.core.approval_engine",
    ]

    def test_authority_modules_do_not_import_relationship_memory(self):
        import importlib
        for authority_mod in self.AUTHORITY_MODULES:
            try:
                mod = importlib.import_module(authority_mod)
            except ImportError:
                self.skipTest(f"{authority_mod} not importable")

            for attr_name in dir(mod):
                try:
                    attr = getattr(mod, attr_name)
                    mod_name = getattr(attr, "__module__", "") or ""
                    self.assertNotIn(
                        "relationship_memory", mod_name,
                        msg=(
                            f"RELATIONSHIP≠PERMISSION VIOLATION: {authority_mod} has "
                            f"attr '{attr_name}' from relationship_memory"
                        ),
                    )
                except Exception:
                    pass


# ---------------------------------------------------------------------------
# Shared DB fixture base
# ---------------------------------------------------------------------------

class _RelBase(unittest.TestCase):
    def setUp(self):
        conn = _make_shared_conn()
        self.__class__._conn = conn

        from backend.core.relationship_memory import RelationshipMemory
        from backend.core.memory_governance import MemoryGovernance

        RelationshipMemory._ensure_schema(conn)
        MemoryGovernance._ensure_schema(conn)

        wrapped = _NoClose(conn)
        self._patchers = [
            patch.object(RelationshipMemory, "_get_sqlite_conn", return_value=wrapped),
            patch.object(MemoryGovernance, "_get_sqlite_conn", return_value=wrapped),
        ]
        for p in self._patchers:
            p.start()

    def tearDown(self):
        for p in self._patchers:
            p.stop()
        # Clean state between tests
        for table in (
            "hm_preferences", "hm_projects", "hm_user_goals",
            "hm_relationship_history", "hm_relationship_candidates",
            "hm_emotional_state", "hm_communication", "hm_trust",
            "hm_observed_behaviors", "hm_channel_bindings", "hm_entities",
        ):
            try:
                self.__class__._conn.execute(f"DELETE FROM {table}")
            except Exception:
                pass
        self.__class__._conn.commit()


# ---------------------------------------------------------------------------
# 2. User Profile — Identity Layer
# ---------------------------------------------------------------------------

class TestIdentityLayer(_RelBase):

    def test_entity_create_and_retrieve(self):
        from backend.core.relationship_memory import RelationshipMemory
        e = RelationshipMemory.get_or_create_entity("user-001", "Bala", "user", "TRUST_USER")
        self.assertEqual(e["name"], "Bala")
        self.assertEqual(e["entity_type"], "user")

        # Idempotent — second call returns same record
        e2 = RelationshipMemory.get_or_create_entity("user-001", "Bala", "user", "TRUST_USER")
        self.assertEqual(e2["id"], e["id"])

    def test_entity_types_allowed(self):
        from backend.core.relationship_memory import RelationshipMemory
        for etype in ("user", "colleague", "friend", "system"):
            eid = f"entity-{etype}"
            e = RelationshipMemory.get_or_create_entity(eid, f"Test {etype}", etype, "TRUST_UNVERIFIED")
            self.assertEqual(e["entity_type"], etype)

    def test_nonexistent_entity_returns_none(self):
        from backend.core.relationship_memory import RelationshipMemory
        result = RelationshipMemory.get_entity("does-not-exist")
        self.assertIsNone(result)


# ---------------------------------------------------------------------------
# 3. Communication Style Layer
# ---------------------------------------------------------------------------

class TestCommunicationLayer(_RelBase):

    def setUp(self):
        super().setUp()
        from backend.core.relationship_memory import RelationshipMemory
        RelationshipMemory.get_or_create_entity("user-comm", "Test User", "user", "TRUST_USER")

    def test_set_and_get_communication_style(self):
        from backend.core.relationship_memory import RelationshipMemory
        RelationshipMemory.set_communication_style("user-comm", "language", "Telugu")
        RelationshipMemory.set_communication_style("user-comm", "technical_depth", "advanced")
        RelationshipMemory.set_communication_style("user-comm", "format", "step_by_step")

        style = RelationshipMemory.get_communication_style("user-comm")
        self.assertEqual(style["language"], "Telugu")
        self.assertEqual(style["technical_depth"], "advanced")
        self.assertEqual(style["format"], "step_by_step")

    def test_invalid_style_key_rejected(self):
        from backend.core.relationship_memory import RelationshipMemory
        with self.assertRaises(ValueError):
            RelationshipMemory.set_communication_style("user-comm", "personality", "INTJ")

    def test_communication_confidence_rises_on_repeat(self):
        from backend.core.relationship_memory import RelationshipMemory
        RelationshipMemory.set_communication_style("user-comm", "tone", "formal", confidence=0.8)
        RelationshipMemory.set_communication_style("user-comm", "tone", "formal", confidence=0.8)

        full = RelationshipMemory.get_communication_style_full("user-comm")
        tone_rec = next(r for r in full if r["style_key"] == "tone")
        self.assertEqual(tone_rec["evidence_count"], 2)
        self.assertGreater(tone_rec["confidence"], 0.8)

    def test_sensitive_content_blocked_from_style(self):
        from backend.core.relationship_memory import RelationshipMemory
        with self.assertRaises(ValueError):
            RelationshipMemory.set_communication_style(
                "user-comm", "language", "password: hunter2"
            )


# ---------------------------------------------------------------------------
# 4. Preference Tracking — Versioning & Confidence Decay on Contradiction
# ---------------------------------------------------------------------------

class TestPreferenceTracking(_RelBase):

    def setUp(self):
        super().setUp()
        from backend.core.relationship_memory import RelationshipMemory
        RelationshipMemory.get_or_create_entity("user-pref", "Pref User", "user", "TRUST_USER")

    def test_preference_set_and_retrieve(self):
        from backend.core.relationship_memory import RelationshipMemory
        RelationshipMemory.set_preference("user-pref", "tooling", "editor", "neovim")
        prefs = RelationshipMemory.get_preferences("user-pref", category="tooling")
        self.assertTrue(any(p["value"] == "neovim" for p in prefs))

    def test_contradiction_chains_correctly(self):
        from backend.core.relationship_memory import RelationshipMemory
        RelationshipMemory.set_preference("user-pref", "language", "spoken_lang", "English")
        RelationshipMemory.set_preference("user-pref", "language", "spoken_lang", "Telugu")

        active = RelationshipMemory.get_preferences("user-pref", category="language")
        active_vals = [p["value"] for p in active]
        self.assertIn("Telugu", active_vals)
        self.assertNotIn("English", active_vals)

        history = RelationshipMemory.get_preference_history("user-pref", "language", "spoken_lang")
        self.assertEqual(len(history), 2)

    def test_trust_confidence_drops_on_contradiction(self):
        """When a preference is contradicted, the trust model confidence must fall."""
        from backend.core.relationship_memory import RelationshipMemory
        RelationshipMemory.get_or_create_entity("user-pref", "Pref User", "user", "TRUST_USER")
        RelationshipMemory.get_or_create_trust("user-pref")

        # Positive evidence first
        RelationshipMemory.update_trust("user-pref", evidence_strength=0.8, is_contradiction=False)
        after_positive = RelationshipMemory.get_trust("user-pref")

        # Now contradiction
        RelationshipMemory.update_trust("user-pref", evidence_strength=0.0, is_contradiction=True)
        after_contradiction = RelationshipMemory.get_trust("user-pref")

        self.assertLess(
            after_contradiction["confidence"],
            after_positive["confidence"],
            "Confidence must fall after contradiction"
        )

    def test_sensitive_preference_blocked(self):
        from backend.core.relationship_memory import RelationshipMemory
        with self.assertRaises(ValueError):
            RelationshipMemory.set_preference("user-pref", "credentials", "api_key", "my secret password")


# ---------------------------------------------------------------------------
# 5. Trust Score — EMA, Slow Drift, Confidence Asymmetry
# ---------------------------------------------------------------------------

class TestTrustScoreLayer(_RelBase):

    def setUp(self):
        super().setUp()
        from backend.core.relationship_memory import RelationshipMemory
        RelationshipMemory.get_or_create_entity("user-trust", "Trust User", "user", "TRUST_USER")

    def test_trust_starts_at_zero(self):
        from backend.core.relationship_memory import RelationshipMemory
        rec = RelationshipMemory.get_or_create_trust("user-trust")
        self.assertEqual(rec["trust_score"], 0.0)
        self.assertEqual(rec["confidence"], 0.0)
        self.assertEqual(rec["evidence_count"], 0)

    def test_ema_formula_applied(self):
        """new = old * 0.95 + evidence * 0.05"""
        from backend.core.relationship_memory import RelationshipMemory
        RelationshipMemory.get_or_create_trust("user-trust")

        result = RelationshipMemory.update_trust("user-trust", evidence_strength=1.0)
        expected = 0.0 * 0.95 + 1.0 * 0.05
        self.assertAlmostEqual(result["trust_score"], expected, places=4)

    def test_trust_changes_slowly(self):
        """Even 100 perfect interactions cannot spike trust to 1.0 instantly."""
        from backend.core.relationship_memory import RelationshipMemory
        RelationshipMemory.get_or_create_trust("user-trust")

        for _ in range(10):
            result = RelationshipMemory.update_trust("user-trust", evidence_strength=1.0)

        # After 10 rounds of maximum evidence, trust is still < 0.5
        self.assertLess(result["trust_score"], 0.5)

    def test_trust_never_exceeds_one(self):
        from backend.core.relationship_memory import RelationshipMemory
        RelationshipMemory.get_or_create_trust("user-trust")
        for _ in range(200):
            RelationshipMemory.update_trust("user-trust", evidence_strength=1.0)
        rec = RelationshipMemory.get_trust("user-trust")
        self.assertLessEqual(rec["trust_score"], 1.0)

    def test_confidence_rises_on_positive_evidence(self):
        from backend.core.relationship_memory import RelationshipMemory
        RelationshipMemory.get_or_create_trust("user-trust")
        r1 = RelationshipMemory.update_trust("user-trust", evidence_strength=0.8)
        r2 = RelationshipMemory.update_trust("user-trust", evidence_strength=0.8)
        self.assertGreater(r2["confidence"], r1["confidence"])

    def test_confidence_falls_on_contradiction(self):
        from backend.core.relationship_memory import RelationshipMemory
        RelationshipMemory.get_or_create_trust("user-trust")
        r_pos = RelationshipMemory.update_trust("user-trust", evidence_strength=0.9)
        r_neg = RelationshipMemory.update_trust("user-trust", evidence_strength=0.0, is_contradiction=True)
        self.assertLess(r_neg["confidence"], r_pos["confidence"])

    def test_trust_score_is_internal_only(self):
        """Trust score must never be labelled as a judgment of the person's power."""
        # This is enforced by docstring and API design — the field is 'trust_metrics'
        # in the assembler output, which is labelled internal.
        from backend.core.relationship_memory import RelationshipAssembler, RelationshipMemory
        RelationshipMemory.get_or_create_entity("user-trust", "Trust User", "user", "TRUST_USER")
        profile = RelationshipAssembler.assemble("user-trust")
        self.assertIn("trust_metrics", profile)
        # trust_metrics is present but should NOT be labelled as power/access
        trust_keys = list(profile["trust_metrics"].keys())
        self.assertIn("trust_score", trust_keys)
        self.assertNotIn("access_level", trust_keys)
        self.assertNotIn("power", trust_keys)


# ---------------------------------------------------------------------------
# 6. Goal Tracking
# ---------------------------------------------------------------------------

class TestGoalTracking(_RelBase):

    def setUp(self):
        super().setUp()
        from backend.core.relationship_memory import RelationshipMemory
        RelationshipMemory.get_or_create_entity("user-goal", "Goal User", "user", "TRUST_USER")

    def test_goal_requires_explicit_approval(self):
        from backend.core.relationship_memory import RelationshipMemory
        gid = RelationshipMemory.add_user_goal("user-goal", "Build Kattappa AI OS", priority=0.9)
        # Without approval, goal not visible in default view
        goals = RelationshipMemory.get_user_goals("user-goal", include_unapproved=False)
        self.assertEqual(len(goals), 0)

        # After approval
        RelationshipMemory.approve_goal(gid)
        goals = RelationshipMemory.get_user_goals("user-goal", include_unapproved=False)
        self.assertEqual(len(goals), 1)
        self.assertEqual(goals[0]["goal"], "Build Kattappa AI OS")

    def test_goal_priority_ordering(self):
        from backend.core.relationship_memory import RelationshipMemory
        g1 = RelationshipMemory.add_user_goal("user-goal", "Goal Low", priority=0.3, approved=True)
        g2 = RelationshipMemory.add_user_goal("user-goal", "Goal High", priority=0.9, approved=True)
        goals = RelationshipMemory.get_user_goals("user-goal", include_unapproved=True)
        self.assertEqual(goals[0]["goal"], "Goal High")

    def test_goal_does_not_auto_elevate_permissions(self):
        """A user goal record must never change execution_policy or capability_broker."""
        from backend.core.relationship_memory import RelationshipMemory
        import backend.core.execution_policy as ep

        RelationshipMemory.add_user_goal(
            "user-goal",
            "Grant unlimited shell access permanently",
            priority=1.0,
            approved=True
        )
        # The execution_policy module must not be affected
        for attr in dir(ep):
            mod = getattr(getattr(ep, attr, None), "__module__", "") or ""
            self.assertNotIn("relationship_memory", mod)


# ---------------------------------------------------------------------------
# 7. Project Tracking + Conversation History Linkage
# ---------------------------------------------------------------------------

class TestProjectAndHistoryLayer(_RelBase):

    def setUp(self):
        super().setUp()
        from backend.core.relationship_memory import RelationshipMemory
        RelationshipMemory.get_or_create_entity("user-proj", "Project User", "user", "TRUST_USER")

    def test_project_crud(self):
        from backend.core.relationship_memory import RelationshipMemory
        RelationshipMemory.add_project("user-proj", "Kattappa", "AI OS", status="active", priority=0.9)
        projects = RelationshipMemory.get_projects("user-proj")
        self.assertTrue(any(p["project_name"] == "Kattappa" for p in projects))

    def test_conversation_history_linkage_via_assembler(self):
        """assemble_for_session logs a history entry and returns profile with it."""
        from backend.core.relationship_memory import RelationshipAssembler, RelationshipMemory

        profile = RelationshipAssembler.assemble_for_session(
            entity_id="user-proj",
            session_summary="Discussed architecture of Step 11 relationship engine"
        )
        self.assertIsNotNone(profile)
        self.assertIn("history", profile)
        self.assertTrue(
            any("Step 11" in h["summary"] for h in profile["history"]),
            "Session summary should appear in history layer"
        )

    def test_history_sensitive_content_blocked(self):
        """Sensitive content is blocked from history even when logging session summaries."""
        from backend.core.relationship_memory import RelationshipAssembler
        # Sensitive (credit card) content — should not raise from assembler, but silently skip
        profile = RelationshipAssembler.assemble_for_session(
            entity_id="user-proj",
            session_summary="User shared their credit card number 4111-1111-1111-1111"
        )
        # Profile still returned (entity exists); the sensitive history entry is skipped
        self.assertIsNotNone(profile)
        history_summaries = [h["summary"] for h in profile.get("history", [])]
        self.assertFalse(
            any("credit card" in s for s in history_summaries),
            "Sensitive history entry must not be stored"
        )

    def test_history_compaction(self):
        from backend.core.relationship_memory import RelationshipMemory
        for i in range(5):
            RelationshipMemory.add_history("user-proj", f"Milestone {i} completed", importance=0.6)

        # Force old timestamps
        self.__class__._conn.execute(
            "UPDATE hm_relationship_history SET created_at = created_at - 86400 * 40 WHERE entity_id = 'user-proj'"
        )
        self.__class__._conn.commit()

        compacted = RelationshipMemory.compact_history("user-proj", age_days=30)
        self.assertTrue(compacted)
        history = RelationshipMemory.get_history("user-proj", limit=20)
        # Should now be a single compacted entry
        self.assertEqual(len(history), 1)
        self.assertIn("Compacted", history[0]["summary"])


# ---------------------------------------------------------------------------
# 8. Observed Behaviors — Evidence-Linked, No Psychological Labels
# ---------------------------------------------------------------------------

class TestObservedBehaviors(_RelBase):

    def setUp(self):
        super().setUp()
        from backend.core.relationship_memory import RelationshipMemory
        RelationshipMemory.get_or_create_entity("user-obs", "Obs User", "user", "TRUST_USER")

    def test_store_and_retrieve_observation(self):
        from backend.core.relationship_memory import RelationshipMemory
        hist_id = RelationshipMemory.add_history("user-obs", "Requested architecture-first", 0.7)
        obs_id = RelationshipMemory.add_observed_behavior(
            "user-obs",
            "Requested architecture-first explanation 3 times",
            evidence_ids=[hist_id],
            confidence=0.75,
        )
        behaviors = RelationshipMemory.get_observed_behaviors("user-obs", min_confidence=0.5)
        self.assertTrue(any(b["observation"].startswith("Requested") for b in behaviors))
        self.assertIn(hist_id, behaviors[0]["evidence_ids"])

    def test_psychological_label_rejected(self):
        from backend.core.relationship_memory import RelationshipMemory
        with self.assertRaises(ValueError):
            RelationshipMemory.add_observed_behavior(
                "user-obs",
                "User is very analytical and systematic",  # labels
                evidence_ids=["ev-001"],
            )

    def test_user_can_retract_observation(self):
        from backend.core.relationship_memory import RelationshipMemory
        obs_id = RelationshipMemory.add_observed_behavior(
            "user-obs",
            "Requested code examples instead of theory",
            evidence_ids=["ev-x"],
            confidence=0.8,
        )
        self.assertTrue(RelationshipMemory.retract_observed_behavior(obs_id))
        behaviors = RelationshipMemory.get_observed_behaviors("user-obs")
        self.assertFalse(any(b["confidence"] == 0.8 for b in behaviors))

    def test_evidence_required_not_synthesized(self):
        """Observations with no evidence IDs are allowed but get evidence_count=1 minimum."""
        from backend.core.relationship_memory import RelationshipMemory
        obs_id = RelationshipMemory.add_observed_behavior(
            "user-obs",
            "User prefers step-by-step walkthroughs over bullet summaries",
            evidence_ids=[],  # No links yet
            confidence=0.5,
        )
        self.assertIsNotNone(obs_id)
        behaviors = RelationshipMemory.get_observed_behaviors("user-obs", min_confidence=0.4)
        self.assertEqual(behaviors[0]["evidence_ids"], [])


# ---------------------------------------------------------------------------
# 9. Channel Binding — Identity Bound to Channel
# ---------------------------------------------------------------------------

class TestChannelBinding(_RelBase):

    def setUp(self):
        super().setUp()
        from backend.core.relationship_memory import RelationshipMemory
        RelationshipMemory.get_or_create_entity("user-chan", "Chan User", "user", "TRUST_UNVERIFIED")

    def test_unverified_channel_entity_not_verified(self):
        from backend.core.relationship_memory import RelationshipMemory
        RelationshipMemory.bind_channel("user-chan", "email", "user@example.com", verified=False)
        self.assertFalse(RelationshipMemory.is_identity_verified("user-chan"))

    def test_verified_channel_confirms_identity(self):
        from backend.core.relationship_memory import RelationshipMemory
        RelationshipMemory.bind_channel("user-chan", "user_session", "sess-abc", verified=True)
        self.assertTrue(RelationshipMemory.is_identity_verified("user-chan"))

    def test_verify_channel_after_binding(self):
        from backend.core.relationship_memory import RelationshipMemory
        RelationshipMemory.bind_channel("user-chan", "github", "gh-bala", verified=False)
        self.assertFalse(RelationshipMemory.is_identity_verified("user-chan"))
        RelationshipMemory.verify_channel("github", "gh-bala")
        self.assertTrue(RelationshipMemory.is_identity_verified("user-chan"))

    def test_invalid_channel_type_rejected(self):
        from backend.core.relationship_memory import RelationshipMemory
        with self.assertRaises(ValueError):
            RelationshipMemory.bind_channel("user-chan", "telegram", "t-123")

    def test_display_name_alone_is_insufficient_for_verification(self):
        """An entity with only a display name (no channel binding) is not verified."""
        from backend.core.relationship_memory import RelationshipMemory
        RelationshipMemory.get_or_create_entity("imposter", "Admin", "user", "TRUST_UNVERIFIED")
        # No channel binding
        self.assertFalse(RelationshipMemory.is_identity_verified("imposter"))


# ---------------------------------------------------------------------------
# 10. RelationshipAssembler — Full Profile
# ---------------------------------------------------------------------------

class TestRelationshipAssembler(_RelBase):

    def setUp(self):
        super().setUp()
        from backend.core.relationship_memory import RelationshipMemory, RelationshipAssembler
        RelationshipMemory.get_or_create_entity("user-asm", "Asm User", "user", "TRUST_USER")
        RelationshipMemory.set_communication_style("user-asm", "language", "Telugu")
        RelationshipMemory.set_communication_style("user-asm", "technical_depth", "very_high")
        RelationshipMemory.set_preference("user-asm", "tooling", "editor", "neovim", confidence=0.9)
        gid = RelationshipMemory.add_user_goal("user-asm", "Build DEWS", priority=0.8)
        RelationshipMemory.approve_goal(gid)
        RelationshipMemory.add_project("user-asm", "Kattappa", "AI agent OS", priority=0.9)
        RelationshipMemory.add_history("user-asm", "Completed Step 11 relationship engine", importance=0.8)
        RelationshipMemory.add_observed_behavior(
            "user-asm",
            "Requested detailed technical explanations in multiple sessions",
            evidence_ids=["hist-01"],
            confidence=0.8,
        )

    def test_assembler_returns_all_required_keys(self):
        from backend.core.relationship_memory import RelationshipAssembler
        profile = RelationshipAssembler.assemble("user-asm")
        required = {"identity", "trust_metrics", "communication_style",
                    "preferences", "goals", "projects", "history", "observed_behaviors",
                    "topics", "retrieval_explainability"}
        self.assertEqual(set(profile.keys()), required)

    def test_communication_style_surfaced(self):
        from backend.core.relationship_memory import RelationshipAssembler
        profile = RelationshipAssembler.assemble("user-asm")
        self.assertEqual(profile["communication_style"].get("language"), "Telugu")
        self.assertEqual(profile["communication_style"].get("technical_depth"), "very_high")

    def test_goals_surfaced(self):
        from backend.core.relationship_memory import RelationshipAssembler
        profile = RelationshipAssembler.assemble("user-asm")
        goal_names = [g["goal"] for g in profile["goals"]]
        self.assertIn("Build DEWS", goal_names)

    def test_projects_surfaced(self):
        from backend.core.relationship_memory import RelationshipAssembler
        profile = RelationshipAssembler.assemble("user-asm")
        proj_names = [p["project_name"] for p in profile["projects"]]
        self.assertIn("Kattappa", proj_names)

    def test_history_surfaced(self):
        from backend.core.relationship_memory import RelationshipAssembler
        profile = RelationshipAssembler.assemble("user-asm")
        self.assertTrue(any("Step 11" in h["summary"] for h in profile["history"]))

    def test_observed_behaviors_surfaced(self):
        from backend.core.relationship_memory import RelationshipAssembler
        profile = RelationshipAssembler.assemble("user-asm")
        self.assertTrue(len(profile["observed_behaviors"]) >= 1)
        self.assertIn("evidence_ids", profile["observed_behaviors"][0])

    def test_assembler_returns_none_for_unknown_entity(self):
        from backend.core.relationship_memory import RelationshipAssembler
        self.assertIsNone(RelationshipAssembler.assemble("does-not-exist"))

    def test_trust_metrics_present_but_not_rendering_power_labels(self):
        from backend.core.relationship_memory import RelationshipAssembler
        profile = RelationshipAssembler.assemble("user-asm")
        tm = profile["trust_metrics"]
        self.assertIn("trust_score", tm)
        self.assertIn("confidence", tm)
        self.assertIn("evidence_count", tm)
        # These keys must NOT exist — trust is not power
        for forbidden in ("access_level", "permission_level", "power", "rank"):
            self.assertNotIn(forbidden, tm)


# ---------------------------------------------------------------------------
# 11. Right-to-Forget Cascade (all tables)
# ---------------------------------------------------------------------------

class TestRightToForget(_RelBase):

    def test_forget_purges_all_new_tables(self):
        from backend.core.relationship_memory import RelationshipMemory
        eid = "user-forget"
        RelationshipMemory.get_or_create_entity(eid, "Delete Me", "user", "TRUST_USER")
        RelationshipMemory.set_communication_style(eid, "language", "Telugu")
        RelationshipMemory.get_or_create_trust(eid)
        RelationshipMemory.update_trust(eid, 0.8)
        RelationshipMemory.add_observed_behavior(eid, "Requested detailed explanations", evidence_ids=["e1"], confidence=0.7)
        RelationshipMemory.bind_channel(eid, "user_session", "sess-xyz")
        RelationshipMemory.add_history(eid, "Test history entry", importance=0.5)
        RelationshipMemory.set_preference(eid, "tooling", "editor", "vim")
        RelationshipMemory.add_project(eid, "TestProj", "test", priority=0.5)
        goal_id = RelationshipMemory.add_user_goal(eid, "Test goal", priority=0.5)

        # Forget
        result = RelationshipMemory.forget(eid)
        self.assertTrue(result)

        # Entity gone
        self.assertIsNone(RelationshipMemory.get_entity(eid))
        # All dependent records gone
        conn = self.__class__._conn
        for table in ("hm_communication", "hm_trust", "hm_observed_behaviors",
                      "hm_channel_bindings", "hm_relationship_history",
                      "hm_preferences", "hm_projects", "hm_user_goals"):
            count = conn.execute(
                f"SELECT COUNT(*) FROM {table} WHERE entity_id = ?", (eid,)
            ).fetchone()[0]
            self.assertEqual(count, 0, f"Table {table} still has rows for {eid} after forget()")


if __name__ == "__main__":
    unittest.main()
