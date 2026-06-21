"""Tests for MemoryAssembler — cross-layer retrieval orchestrator.

Verifies:
- assemble_context() compiles facts, episodes, and actions in one call.
- Facts and episodes are each re-ranked by RRF assembler_score.
- Procedural triggers with SYSTEM_TRUST / USER_APPROVED are surfaced.
- Untrusted / revoked procedures are filtered out of actions.
- Layer failures are gracefully handled (returns empty sections).
- limit parameter correctly bounds result counts.
"""

import json
import unittest
from unittest.mock import MagicMock, patch

from backend.core.memory_assembler import MemoryAssembler


# ---------- Fake layer data ----------

def _make_fact(idx: int, rrf: float = 0.02) -> dict:
    return {
        "id": f"sem-{idx:03d}",
        "concept": f"Concept {idx}",
        "description": f"Description of concept {idx}.",
        "confidence": 0.75,
        "evidence_count": 2,
        "source_episode_ids": [f"ep-{idx}"],
        "rrf_score": rrf,
    }


def _make_episode(idx: int, rrf: float = 0.015) -> dict:
    return {
        "id": f"ep-{idx:03d}",
        "content": f"Episode content {idx}.",
        "importance": 0.6,
        "decay_score": 0.55,
        "rrf_score": rrf,
    }


def _make_procedure(idx: int, trust: str = "SYSTEM_TRUST", revoked: int = 0) -> dict:
    return {
        "id": f"proc-{idx:03d}",
        "skill_name": f"skill_{idx}",
        "trigger_phrase": f"phrase_{idx}",
        "steps_json": json.dumps([f"step_{idx}"]),
        "trust_level": trust,
        "revoked": revoked,
    }


class TestMemoryAssembler(unittest.TestCase):

    def setUp(self):
        self.strategic_patcher = patch.object(MemoryAssembler, "_query_strategic", return_value=[])
        self.strategic_patcher.start()

    def tearDown(self):
        self.strategic_patcher.stop()

    # ---------- assemble_context: basic structure ----------

    def test_assemble_context_returns_required_keys(self):
        """assemble_context must always return the four top-level keys."""
        with (
            patch.object(MemoryAssembler, "_query_semantic", return_value=[]),
            patch.object(MemoryAssembler, "_query_episodic", return_value=[]),
            patch.object(MemoryAssembler, "_query_procedural", return_value=[]),
        ):
            result = MemoryAssembler.assemble_context("test query")

        self.assertIn("query", result)
        self.assertIn("facts", result)
        self.assertIn("episodes", result)
        self.assertIn("actions", result)
        self.assertIn("total_hits", result)
        self.assertEqual(result["query"], "test query")

    def test_assemble_context_empty_layers(self):
        """All sections must be empty lists when all layers return nothing."""
        with (
            patch.object(MemoryAssembler, "_query_semantic", return_value=[]),
            patch.object(MemoryAssembler, "_query_episodic", return_value=[]),
            patch.object(MemoryAssembler, "_query_procedural", return_value=[]),
        ):
            result = MemoryAssembler.assemble_context("no data here")

        self.assertEqual(result["facts"], [])
        self.assertEqual(result["episodes"], [])
        self.assertEqual(result["actions"], [])
        self.assertEqual(result["total_hits"], 0)

    # ---------- assemble_context: data flows through ----------

    def test_assemble_context_facts_present(self):
        """Semantic facts should appear in the 'facts' section."""
        facts = [_make_fact(i) for i in range(3)]
        with (
            patch.object(MemoryAssembler, "_query_semantic", return_value=facts),
            patch.object(MemoryAssembler, "_query_episodic", return_value=[]),
            patch.object(MemoryAssembler, "_query_procedural", return_value=[]),
        ):
            result = MemoryAssembler.assemble_context("query", limit=5)

        self.assertEqual(len(result["facts"]), 3)
        # assembler_score must be set on each fact
        for fact in result["facts"]:
            self.assertIn("assembler_score", fact)

    def test_assemble_context_episodes_present(self):
        """Episodic memories should appear in the 'episodes' section."""
        episodes = [_make_episode(i) for i in range(4)]
        with (
            patch.object(MemoryAssembler, "_query_semantic", return_value=[]),
            patch.object(MemoryAssembler, "_query_episodic", return_value=episodes),
            patch.object(MemoryAssembler, "_query_procedural", return_value=[]),
        ):
            result = MemoryAssembler.assemble_context("RF testing last month", limit=5)

        self.assertEqual(len(result["episodes"]), 4)

    def test_assemble_context_actions_present(self):
        """Matching procedures should appear in the 'actions' section."""
        procs = [_make_procedure(1, "SYSTEM_TRUST"), _make_procedure(2, "USER_APPROVED")]
        with (
            patch.object(MemoryAssembler, "_query_semantic", return_value=[]),
            patch.object(MemoryAssembler, "_query_episodic", return_value=[]),
            patch.object(MemoryAssembler, "_query_procedural", return_value=procs),
        ):
            result = MemoryAssembler.assemble_context("do something")

        self.assertEqual(len(result["actions"]), 2)

    def test_assemble_context_total_hits(self):
        """total_hits must count combined raw results from all three layers."""
        facts = [_make_fact(i) for i in range(2)]
        episodes = [_make_episode(i) for i in range(3)]
        procs = [_make_procedure(1)]
        with (
            patch.object(MemoryAssembler, "_query_semantic", return_value=facts),
            patch.object(MemoryAssembler, "_query_episodic", return_value=episodes),
            patch.object(MemoryAssembler, "_query_procedural", return_value=procs),
        ):
            result = MemoryAssembler.assemble_context("query")

        self.assertEqual(result["total_hits"], 6)  # 2 + 3 + 1

    # ---------- RRF ranking ----------

    def test_facts_ranked_by_assembler_score_descending(self):
        """Facts must be sorted descending by assembler_score after fusion."""
        # Feed in reverse-priority order to verify the sort flips them.
        facts = [_make_fact(i, rrf=0.001 * i) for i in range(5)]
        facts_reversed = list(reversed(facts))
        with (
            patch.object(MemoryAssembler, "_query_semantic", return_value=facts_reversed),
            patch.object(MemoryAssembler, "_query_episodic", return_value=[]),
            patch.object(MemoryAssembler, "_query_procedural", return_value=[]),
        ):
            result = MemoryAssembler.assemble_context("query", limit=10)

        scores = [f["assembler_score"] for f in result["facts"]]
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_episodes_ranked_by_assembler_score_descending(self):
        """Episodes must be sorted descending by assembler_score after fusion."""
        episodes = [_make_episode(i, rrf=0.001 * i) for i in range(5)]
        episodes_reversed = list(reversed(episodes))
        with (
            patch.object(MemoryAssembler, "_query_semantic", return_value=[]),
            patch.object(MemoryAssembler, "_query_episodic", return_value=episodes_reversed),
            patch.object(MemoryAssembler, "_query_procedural", return_value=[]),
        ):
            result = MemoryAssembler.assemble_context("query", limit=10)

        scores = [e["assembler_score"] for e in result["episodes"]]
        self.assertEqual(scores, sorted(scores, reverse=True))

    # ---------- limit enforcement ----------

    def test_limit_bounds_facts(self):
        """Facts section must be capped at the requested limit."""
        facts = [_make_fact(i) for i in range(10)]
        with (
            patch.object(MemoryAssembler, "_query_semantic", return_value=facts),
            patch.object(MemoryAssembler, "_query_episodic", return_value=[]),
            patch.object(MemoryAssembler, "_query_procedural", return_value=[]),
        ):
            result = MemoryAssembler.assemble_context("query", limit=3)

        self.assertLessEqual(len(result["facts"]), 3)

    def test_limit_bounds_episodes(self):
        """Episodes section must be capped at the requested limit."""
        episodes = [_make_episode(i) for i in range(10)]
        with (
            patch.object(MemoryAssembler, "_query_semantic", return_value=[]),
            patch.object(MemoryAssembler, "_query_episodic", return_value=episodes),
            patch.object(MemoryAssembler, "_query_procedural", return_value=[]),
        ):
            result = MemoryAssembler.assemble_context("query", limit=4)

        self.assertLessEqual(len(result["episodes"]), 4)

    # ---------- Procedural trust filtering ----------

    def test_untrusted_procedures_filtered(self):
        """Procedures with DRAFT or UNTRUSTED trust must not appear in actions."""
        trusted = _make_procedure(1, "SYSTEM_TRUST")
        untrusted = _make_procedure(2, "UNTRUSTED")
        draft = _make_procedure(3, "DRAFT")
        with (
            patch.object(MemoryAssembler, "_query_semantic", return_value=[]),
            patch.object(MemoryAssembler, "_query_episodic", return_value=[]),
            patch("backend.core.procedural_memory.ProceduralMemory.match_trigger",
                  return_value=[trusted, untrusted, draft]),
        ):
            result = MemoryAssembler.assemble_context("do something")

        action_ids = [a["id"] for a in result["actions"]]
        self.assertIn("proc-001", action_ids)
        self.assertNotIn("proc-002", action_ids)
        self.assertNotIn("proc-003", action_ids)

    def test_revoked_procedures_filtered(self):
        """Revoked procedures (revoked=1) must not appear in actions."""
        active = _make_procedure(1, "SYSTEM_TRUST", revoked=0)
        revoked = _make_procedure(2, "SYSTEM_TRUST", revoked=1)
        with (
            patch.object(MemoryAssembler, "_query_semantic", return_value=[]),
            patch.object(MemoryAssembler, "_query_episodic", return_value=[]),
            patch("backend.core.procedural_memory.ProceduralMemory.match_trigger",
                  return_value=[active, revoked]),
        ):
            result = MemoryAssembler.assemble_context("run action")

        action_ids = [a["id"] for a in result["actions"]]
        self.assertIn("proc-001", action_ids)
        self.assertNotIn("proc-002", action_ids)

    # ---------- include_actions=False ----------

    def test_include_actions_false_skips_procedural_query(self):
        """When include_actions=False, procedural layer must not be queried."""
        with (
            patch.object(MemoryAssembler, "_query_semantic", return_value=[]),
            patch.object(MemoryAssembler, "_query_episodic", return_value=[]),
            patch.object(MemoryAssembler, "_query_procedural") as mock_proc,
        ):
            result = MemoryAssembler.assemble_context("query", include_actions=False)

        mock_proc.assert_not_called()
        self.assertEqual(result["actions"], [])

    # ---------- Layer failure resilience ----------

    def test_semantic_layer_failure_returns_empty_facts(self):
        """If SemanticMemory raises, facts must be empty (not crash)."""
        with (
            patch.object(MemoryAssembler, "_query_semantic", side_effect=RuntimeError("db down")),
            patch.object(MemoryAssembler, "_query_episodic", return_value=[]),
            patch.object(MemoryAssembler, "_query_procedural", return_value=[]),
        ):
            result = MemoryAssembler.assemble_context("query")

        self.assertEqual(result["facts"], [])

    def test_episodic_layer_failure_returns_empty_episodes(self):
        """If EpisodicMemory raises, episodes must be empty (not crash)."""
        with (
            patch.object(MemoryAssembler, "_query_semantic", return_value=[]),
            patch.object(MemoryAssembler, "_query_episodic", side_effect=RuntimeError("db down")),
            patch.object(MemoryAssembler, "_query_procedural", return_value=[]),
        ):
            result = MemoryAssembler.assemble_context("query")

        self.assertEqual(result["episodes"], [])

    def test_procedural_layer_failure_returns_empty_actions(self):
        """If ProceduralMemory raises, actions must be empty (not crash)."""
        with (
            patch.object(MemoryAssembler, "_query_semantic", return_value=[]),
            patch.object(MemoryAssembler, "_query_episodic", return_value=[]),
            patch.object(MemoryAssembler, "_query_procedural", side_effect=RuntimeError("db down")),
        ):
            result = MemoryAssembler.assemble_context("query")

        self.assertEqual(result["actions"], [])

    # ---------- assembler_score must not mutate originals ----------

    def test_assembler_does_not_mutate_original_dicts(self):
        """rrf_rerank must return copies, not mutate the caller's dicts."""
        original = _make_fact(99, rrf=0.01)
        original_id_before = id(original)
        with (
            patch.object(MemoryAssembler, "_query_semantic", return_value=[original]),
            patch.object(MemoryAssembler, "_query_episodic", return_value=[]),
            patch.object(MemoryAssembler, "_query_procedural", return_value=[]),
        ):
            result = MemoryAssembler.assemble_context("query")

        # The returned fact is a different object
        returned_fact = result["facts"][0]
        self.assertIsNot(returned_fact, original)
        # Original dict should not have assembler_score injected into it
        self.assertNotIn("assembler_score", original)

    def test_assemble_context_goals_present(self):
        """Strategic goals should appear in the 'goals' section."""
        goals = [{"id": "goal-001", "goal": "Find RF attenuation", "status": "active"}]
        # Temporarily stop our setup patcher so we can override it
        self.strategic_patcher.stop()
        try:
            with (
                patch.object(MemoryAssembler, "_query_semantic", return_value=[]),
                patch.object(MemoryAssembler, "_query_episodic", return_value=[]),
                patch.object(MemoryAssembler, "_query_procedural", return_value=[]),
                patch.object(MemoryAssembler, "_query_strategic", return_value=goals),
            ):
                result = MemoryAssembler.assemble_context("query")
            self.assertEqual(result["goals"], goals)
            self.assertIn("goals", result)
        finally:
            self.strategic_patcher.start()


if __name__ == "__main__":
    unittest.main()
