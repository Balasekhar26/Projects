import json
import sqlite3
import time
import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient

from backend.main import app
from backend.core.human_conversation_engine import (
    HumanConversationEngine,
    HCEConstitution,
    HCEStore,
    RelationshipState,
    PersonalityPosture,
    MemoryTier,
    IntentStatus,
    GovernanceStatus,
    ContradictionResolution,
    ReflectionSummary,
    MemoryCandidate,
    ProposedIntent,
    ConversationContext,
    HCEResponse,
    AcknowledgementEngine,
    AttentionBudget,
    CuriosityEngine,
    MemoryCandidateProducer,
    IntentCandidateProducer,
    ContradictionDetector,
    PersonalityConsistencyEngine,
    IntellectualIntegrityMonitor,
    RelationshipContinuityEngine,
    ReflectionEngine,
    NarrativeEngine,
    NarrativeContinuityEngine,
    ConversationHealthMonitor,
    TrustRecoveryEngine,
)
from backend.core.episodic_memory import EpisodicMemory
from backend.core.human_memory import HumanMemoryStore, MemoryRecord, MemoryType
from backend.core.goal_memory import GoalMemory
from backend.core.project_memory import ProjectMemory
from backend.core.personal_project_manager import PersonalProjectManager
from backend.core.relationship_memory import RelationshipMemory
from backend.core.memory_governance import MemoryGovernance


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


class TestHumanConversationEngine(unittest.TestCase):

    def setUp(self):
        # Create a single shared in-memory DB connection to ensure schema isolation during tests
        if not hasattr(self.__class__, "_shared_conn"):
            self.__class__._shared_conn = sqlite3.connect(":memory:", check_same_thread=False)
            self.__class__._shared_conn.row_factory = sqlite3.Row
            HCEStore._ensure_schema(self.__class__._shared_conn)
            RelationshipMemory._ensure_schema(self.__class__._shared_conn)
            MemoryGovernance._ensure_schema(self.__class__._shared_conn)
            EpisodicMemory._ensure_schema(self.__class__._shared_conn)
            GoalMemory._ensure_schema(self.__class__._shared_conn)
            ProjectMemory._ensure_schema(self.__class__._shared_conn)
            HumanMemoryStore._ensure_schema(self.__class__._shared_conn)

        # Clear HCE tables and others between tests
        self.__class__._shared_conn.execute("DELETE FROM hce_relationships")
        self.__class__._shared_conn.execute("DELETE FROM hce_chapters")
        self.__class__._shared_conn.execute("DELETE FROM hce_utterances")
        self.__class__._shared_conn.execute("DELETE FROM hce_reflections")
        self.__class__._shared_conn.execute("DELETE FROM hce_memory_candidates")
        self.__class__._shared_conn.execute("DELETE FROM hce_proposed_intents")
        self.__class__._shared_conn.execute("DELETE FROM hce_relationship_metrics")
        self.__class__._shared_conn.execute("DELETE FROM hce_contradictions")
        self.__class__._shared_conn.execute("DELETE FROM hce_narrative_arcs")
        
        self.__class__._shared_conn.execute("DELETE FROM hm_entities")
        self.__class__._shared_conn.execute("DELETE FROM hm_preferences")
        self.__class__._shared_conn.execute("DELETE FROM hm_projects")
        self.__class__._shared_conn.execute("DELETE FROM hm_user_goals")
        self.__class__._shared_conn.execute("DELETE FROM hm_episodes")
        self.__class__._shared_conn.commit()

        # Reset HCEStore schema ensure check caching flag
        HCEStore._schema_ensured = True

        # Patch connection getters to return our shared in-memory connection
        self.conn_patchers = [
            patch.object(HCEStore, "_get_conn", return_value=NoCloseConnection(self.__class__._shared_conn)),
            patch.object(RelationshipMemory, "_get_sqlite_conn", return_value=NoCloseConnection(self.__class__._shared_conn)),
            patch.object(MemoryGovernance, "_get_sqlite_conn", return_value=NoCloseConnection(self.__class__._shared_conn)),
            patch.object(EpisodicMemory, "_get_sqlite_conn", return_value=NoCloseConnection(self.__class__._shared_conn)),
            patch.object(GoalMemory, "_get_sqlite_conn", return_value=NoCloseConnection(self.__class__._shared_conn)),
            patch.object(PersonalProjectManager, "_get_sqlite_conn", return_value=NoCloseConnection(self.__class__._shared_conn)),
            patch.object(HumanMemoryStore, "_connect", return_value=NoCloseConnection(self.__class__._shared_conn)),
        ]
        for p in self.conn_patchers:
            p.start()

        # Clean Chroma collections mock for tests that might use Vector recall
        try:
            EpisodicMemory._get_chroma_collection()
            EpisodicMemory._chroma_client.delete_collection("episodic_vectors")
            EpisodicMemory._collection = None
        except Exception:
            pass

    def tearDown(self):
        for p in self.conn_patchers:
            p.stop()

    def test_hce_constitution_safety_guarantees(self):
        """Verify the immutable safety rules of HCE are correctly reported and dictionary mapped."""
        rules = HCEConstitution.to_dict()
        self.assertTrue(rules["rule_1"]["enforced"])
        self.assertEqual(rules["rule_1"]["name"], "HCE_CANNOT_CREATE_GOALS")
        self.assertTrue(rules["rule_2"]["enforced"])
        self.assertEqual(rules["rule_2"]["name"], "HCE_CANNOT_WRITE_MEMORY")
        self.assertTrue(rules["rule_3"]["enforced"])
        self.assertEqual(rules["rule_3"]["name"], "HCE_EMPATHY_CANNOT_OVERRIDE_TRUTH")
        self.assertTrue(rules["rule_4"]["enforced"])
        self.assertEqual(rules["rule_4"]["name"], "HCE_PERSONALITY_CANNOT_OVERRIDE_SAFETY")
        self.assertTrue(rules["rule_5"]["enforced"])
        self.assertEqual(rules["rule_5"]["name"], "HCE_RELATIONSHIP_CANNOT_OVERRIDE_USER_INTENT")
        self.assertTrue(rules["rule_6"]["enforced"])
        self.assertEqual(rules["rule_6"]["name"], "HCE_NO_RELATIONSHIP_OPTIMIZATION")

        # Verify HCEResponse enforces these rules in output to_dict() contract
        ref = ReflectionSummary("Deduction", [], PersonalityPosture.TECHNICAL_EXECUTOR, RelationshipState.BUILDING_MODE, 0.0, 0.0, 0.0)
        ctx = ConversationContext()
        resp = HCEResponse(
            utterance_id="utt_1",
            chapter_id="chap_1",
            relationship_id="rel_1",
            reflection=ref,
            conversation_context=ctx,
        )
        data = resp.to_dict()
        self.assertFalse(data["authorized_to_create_goals"])
        self.assertFalse(data["authorized_to_write_memory"])
        self.assertTrue(data["constitution_enforced"])

    def test_hce_store_lifecycle_and_crud(self):
        """Verify relationship, chapter, utterance, metrics, and reflection record CRUD in HCEStore."""
        # 1. Create Relationship
        rel = HCEStore.create_relationship("user_456", "Kattappa User")
        self.assertIsNotNone(rel)
        self.assertEqual(rel["user_entity_id"], "user_456")
        self.assertEqual(rel["display_name"], "Kattappa User")

        rel_id = rel["relationship_id"]

        # 2. Get Relationship
        fetched_rel = HCEStore.get_relationship(rel_id)
        self.assertEqual(fetched_rel["relationship_id"], rel_id)

        # 3. Chapter Open/Close
        chapter = HCEStore.open_chapter(rel_id, RelationshipState.PLANNING_MODE)
        self.assertIsNotNone(chapter)
        chap_id = chapter["chapter_id"]

        active = HCEStore.get_active_chapter(rel_id)
        self.assertEqual(active["chapter_id"], chap_id)
        self.assertEqual(active["relationship_state"], RelationshipState.PLANNING_MODE.value)

        closed = HCEStore.close_chapter(chap_id, "Discussed the strategic long-term architecture.")
        self.assertTrue(closed)
        self.assertIsNone(HCEStore.get_active_chapter(rel_id))

        chap_details = HCEStore.get_chapter(chap_id)
        self.assertIsNotNone(chap_details["closed_at"])
        self.assertEqual(chap_details["chapter_summary_narrative"], "Discussed the strategic long-term architecture.")

        # 4. Utterance and Reflections
        new_chap = HCEStore.open_chapter(rel_id, RelationshipState.BUILDING_MODE)
        new_chap_id = new_chap["chapter_id"]
        utt_id = HCEStore.create_utterance(new_chap_id, "Let's build a parser.")
        self.assertIsNotNone(utt_id)

        # Reflection
        ref_summary = ReflectionSummary(
            intent_deduction="Build code component",
            recalled_context=[],
            personality_posture=PersonalityPosture.TECHNICAL_EXECUTOR,
            relationship_state=RelationshipState.BUILDING_MODE,
            friction_signal=0.25,
            ambiguity_score=0.1,
            blocker_density=0.0
        )
        HCEStore.log_reflection(utt_id, ref_summary, questions_asked=1)

        # Finalize Utterance
        HCEStore.finalize_utterance(utt_id, "I have set up the basic parser structure.", input_tokens=10, output_tokens=30)
        
        recent = HCEStore.get_recent_utterances(new_chap_id, limit=5)
        self.assertEqual(len(recent), 1)
        self.assertEqual(recent[0]["user_message"], "Let's build a parser.")
        self.assertEqual(recent[0]["system_response"], "I have set up the basic parser structure.")
        self.assertEqual(recent[0]["input_token_count"], 10)
        self.assertEqual(recent[0]["output_token_count"], 30)

        # Metrics
        metrics = HCEStore.get_metrics(rel_id)
        self.assertIsNotNone(metrics)
        self.assertEqual(metrics["trust_score"], 50.0) # default initial metrics
        HCEStore.update_metrics(rel_id, trust_score=85.0)
        metrics_updated = HCEStore.get_metrics(rel_id)
        self.assertEqual(metrics_updated["trust_score"], 85.0)

    def test_acknowledgement_engine(self):
        """Verify acknowledgement signals (friction, ambiguity, blockers) are computed properly from message content."""
        # Friction
        f1 = AcknowledgementEngine.compute("I am stuck on this compiler crash. Help!", [])
        self.assertGreater(f1[0], 0.0) # stuck, crash, help
        self.assertEqual(f1[2], 0.0) # no blockers in context

        # Ambiguity
        f2 = AcknowledgementEngine.compute("Maybe or perhaps we could do something like that.", [])
        self.assertGreater(f2[1], 0.3) # maybe, perhaps, something like

        # Blocker density
        context = [
            {"content": "Completed task 1"},
            {"content": "Failed to compile the firmware - blocker details"},
            {"content": "Active task in ready state"},
        ]
        f3 = AcknowledgementEngine.compute("Checking status", context)
        self.assertAlmostEqual(f3[2], 1.0 / 3.0) # blocker_density: 1/3 of the items contain blocker terms

    def test_attention_budget_gating(self):
        """Verify the per-utterance Attention Budget correctly gates curiosities."""
        budget = AttentionBudget()
        self.assertEqual(budget.remaining, 2)
        self.assertTrue(budget.can_ask())

        allowed1 = budget.consume(1)
        self.assertEqual(allowed1, 1)
        self.assertEqual(budget.remaining, 1)

        allowed2 = budget.consume(2) # request more than remaining
        self.assertEqual(allowed2, 1) # only gets 1
        self.assertEqual(budget.remaining, 0)
        self.assertFalse(budget.can_ask())

    def test_curiosity_engine(self):
        """Verify curiosity clarifies when ambiguity is high and respects budget limitations."""
        budget = AttentionBudget()
        # Case 1: Low ambiguity -> no question generated
        q1 = CuriosityEngine.generate("Build project", ambiguity_score=0.1, budget=budget)
        self.assertEqual(len(q1), 0)

        # Case 2: High ambiguity with active projects context -> project scope clarification
        active_projects = [{"project_name": "embedded_testing"}]
        q2 = CuriosityEngine.generate("How to test this?", ambiguity_score=0.4, budget=budget, active_projects=active_projects)
        self.assertEqual(len(q2), 1)
        self.assertIn("Which of your active projects does this relate to", q2[0])
        self.assertEqual(budget.remaining, 1)

        # Case 3: Extreme ambiguity -> general clarify question
        q3 = CuriosityEngine.generate("Maybe it failed?", ambiguity_score=0.6, budget=budget)
        self.assertEqual(len(q3), 1)
        self.assertIn("Can you clarify what outcome you're aiming for", q3[0])
        self.assertEqual(budget.remaining, 0)

        # Case 4: High ambiguity but exhausted budget
        q4 = CuriosityEngine.generate("Maybe it failed again?", ambiguity_score=0.6, budget=budget)
        self.assertEqual(len(q4), 0)

    def test_memory_candidate_producer(self):
        """Verify memory candidates (episodic, semantic, relationship) are properly produced from triggers."""
        # 1. Episodic
        c1 = MemoryCandidateProducer.extract("I designed the suit thruster yesterday.", "utt_1")
        self.assertEqual(len(c1), 1)
        self.assertEqual(c1[0].memory_tier, MemoryTier.EPISODIC)
        self.assertEqual(c1[0].extracted_fact, "I designed the suit thruster yesterday.")

        # 2. Semantic
        c2 = MemoryCandidateProducer.extract("I prefer compiler optimization on standard build routes.", "utt_2")
        self.assertEqual(len(c2), 1)
        self.assertEqual(c2[0].memory_tier, MemoryTier.SEMANTIC)

        # 3. Relationship
        c3 = MemoryCandidateProducer.extract("Please always explain things step by step.", "utt_3")
        self.assertEqual(len(c3), 1)
        self.assertEqual(c3[0].memory_tier, MemoryTier.RELATIONSHIP)

    def test_intent_candidate_producer(self):
        """Verify ProposedIntent objects are parsed without modifying GoalMemory directly."""
        intents = IntentCandidateProducer.extract("I want to establish a firmware validation rig.", "utt_5")
        self.assertEqual(len(intents), 1)
        self.assertEqual(intents[0].inferred_goal_structure["title"], "I want to establish a firmware validation rig.")
        self.assertEqual(intents[0].status, IntentStatus.PENDING_USER_CONFIRMATION)

    def test_contradiction_detection(self):
        """Verify simultaneous or time-bound contradictions are correctly detected."""
        recent_preferences = [
            {"category": "style_preference", "value": "Use simple guidelines."}
        ]
        
        # Conflicting preference expressed
        detected = ContradictionDetector.check(
            "I prefer detailed and complex explanations.", "user_456", recent_preferences
        )
        self.assertEqual(len(detected), 1)
        self.assertEqual(detected[0]["fact_a"], "Use simple guidelines.")
        self.assertEqual(detected[0]["fact_b"], "I prefer detailed and complex explanations.")
        self.assertEqual(detected[0]["category"], "style_preference")

    def test_intellectual_integrity_monitor(self):
        """Verify the Anti-Sycophancy flag fires under warning conditions."""
        # Under threshold: no concern
        self.assertFalse(IntellectualIntegrityMonitor.check({"total_utterances": 5, "correction_rate": 0.0}))

        # Over threshold, but healthy correction rate
        self.assertFalse(IntellectualIntegrityMonitor.check({"total_utterances": 25, "correction_rate": 0.05}))

        # Over threshold, extremely low/zero correction rate -> fires integrity flag (True)
        self.assertTrue(IntellectualIntegrityMonitor.check({"total_utterances": 25, "correction_rate": 0.00}))

    def test_personality_consistency_static_adaptations(self):
        """Verify PersonalityPosture derived dynamically from state without accumulation/ratchet."""
        p1 = PersonalityConsistencyEngine.derive_posture(RelationshipState.DEBUGGING_MODE)
        self.assertEqual(p1, PersonalityPosture.TECHNICAL_EXECUTOR)

        p2 = PersonalityConsistencyEngine.derive_posture(RelationshipState.PLANNING_MODE)
        self.assertEqual(p2, PersonalityPosture.STRATEGIC_COLLABORATOR)

    def test_narrative_arcs_creation_and_checks(self):
        """Verify narrative framing and auto-updating arcs from chapter summary."""
        rel = HCEStore.create_relationship("user_456", "Bala")
        rel_id = rel["relationship_id"]
        chapter = HCEStore.open_chapter(rel_id, RelationshipState.BUILDING_MODE)
        chap_id = chapter["chapter_id"]

        # Run arc detection triggers
        summary = "I finished embedded microcontroller spi tests and improved Kattappa architecture."
        updated = NarrativeContinuityEngine.update_arcs_from_chapter(rel_id, chap_id, summary)
        self.assertIn("Kattappa Arc", updated)
        self.assertIn("Embedded Systems Arc", updated)

        arcs = HCEStore.get_narrative_arcs(rel_id)
        self.assertEqual(len(arcs), 2)

    def test_conversation_health_and_repetition(self):
        """Verify health monitoring updates metrics correctly via alpha smoothing."""
        rel = HCEStore.create_relationship("user_456", "Bala")
        rel_id = rel["relationship_id"]

        recent = [
            {"user_message": "Build the firmware compiler."}
        ]
        
        # Verify repetition metric calculation
        rep_score = ConversationHealthMonitor.detect_repetition("Compile the firmware code.", recent)
        self.assertGreater(rep_score, 0.0)

        # Update health metrics
        ConversationHealthMonitor.update(rel_id, "Compile the firmware code.", recent, system_was_corrected=True)
        metrics = HCEStore.get_metrics(rel_id)
        self.assertGreater(metrics["correction_rate"], 0.0)

    def test_trust_recovery_scoring(self):
        """Verify trust penalty and acknowledgement recovery mechanics are applied."""
        rel = HCEStore.create_relationship("user_456", "Bala")
        rel_id = rel["relationship_id"]

        # Default trust = 50.0
        TrustRecoveryEngine.record_error(rel_id)
        metrics1 = HCEStore.get_metrics(rel_id)
        self.assertEqual(metrics1["trust_score"], 48.0) # 50.0 - 2.0 penalty

        TrustRecoveryEngine.record_correction(rel_id)
        metrics2 = HCEStore.get_metrics(rel_id)
        self.assertEqual(metrics2["trust_score"], 49.5) # 48.0 + 1.5 recovery

    def test_human_conversation_engine_process_pipeline(self):
        """Verify the full cognitive pipeline (HumanConversationEngine.process) end-to-end."""
        rel = HCEStore.create_relationship("user_456", "Bala")
        rel_id = rel["relationship_id"]

        response = HumanConversationEngine.process(
            "I always prefer to use Rust for RTOS tasks, and yesterday I designed a scheduler but I am stuck on compiler errors. I want to build a test suite to verify it.",
            relationship_id=rel_id
        )

        self.assertIsNotNone(response)
        self.assertEqual(response.relationship_id, rel_id)
        self.assertTrue(len(response.memory_candidates) > 0)
        self.assertTrue(len(response.proposed_intents) > 0)
        self.assertGreater(response.reflection.friction_signal, 0.0)

    def test_memory_candidate_and_intent_promotion_workflows(self):
        """Verify memory candidate validation & goal promotion gates actually write back to the respective databases."""
        rel = HCEStore.create_relationship("user_456", "Bala")
        rel_id = rel["relationship_id"]

        # Setup mock active chapter and utterance
        chapter = HCEStore.open_chapter(rel_id, RelationshipState.BUILDING_MODE)
        chap_id = chapter["chapter_id"]
        utt_id = HCEStore.create_utterance(chap_id, "I worked on STM32 compiler scripts today.")

        # Episodic Memory Candidate
        cand1 = MemoryCandidate("cand_1", utt_id, MemoryTier.EPISODIC, "Bala worked on STM32 compiler.", 0.8)
        HCEStore.store_memory_candidate(cand1)

        # Semantic Memory Candidate
        cand2 = MemoryCandidate("cand_2", utt_id, MemoryTier.SEMANTIC, "Bala prefers Rust programming.", 0.9)
        HCEStore.store_memory_candidate(cand2)

        # Proposed Goal Intent
        intent = ProposedIntent("prop_1", utt_id, {"title": "Rig Validation Goal", "description": "Rig validation details"})
        HCEStore.store_proposed_intent(intent)

        # 1. Commit Episodic Candidate -> writes to EpisodicMemory
        self.assertTrue(HumanConversationEngine.commit_memory_candidate("cand_1"))
        # Verify in EpisodicMemory
        conn = EpisodicMemory._get_sqlite_conn()
        ep = conn.execute("SELECT content FROM hm_episodes").fetchall()
        conn.close()
        self.assertTrue(any("STM32" in row["content"] for row in ep))

        # 2. Commit Semantic Candidate -> writes to HumanMemoryStore
        self.assertTrue(HumanConversationEngine.commit_memory_candidate("cand_2"))
        records = HumanMemoryStore.all_records()
        self.assertTrue(any("Rust" in r.content for r in records))

        # 3. Commit Intent -> writes to GoalMemory
        self.assertTrue(HumanConversationEngine.commit_proposed_intent("prop_1"))
        goals = GoalMemory.list_goals()
        self.assertTrue(any("Rig Validation Goal" in g["title"] for g in goals))

    def test_hce_api_endpoints_fastapi(self):
        """Verify FastAPI REST API endpoints /hce/* behave correctly with HTTP client requests."""
        client = TestClient(app)

        # 1. Constitution
        res_const = client.get("/hce/constitution")
        self.assertEqual(res_const.status_code, 200)
        self.assertTrue(res_const.json()["constitution"]["rule_1"]["enforced"])

        # 2. Relationship Create
        res_rel = client.post("/hce/relationship", json={"user_entity_id": "api_user_999", "display_name": "API Tester"})
        self.assertEqual(res_rel.status_code, 200)
        rel_id = res_rel.json()["relationship"]["relationship_id"]
        self.assertIsNotNone(rel_id)

        # 3. Chapter Open
        res_chap = client.post("/hce/chapter", json={"relationship_id": rel_id, "relationship_state": "learning_mode"})
        self.assertEqual(res_chap.status_code, 200)
        chap_id = res_chap.json()["chapter"]["chapter_id"]
        self.assertIsNotNone(chap_id)

        # 4. HCE Process
        res_proc = client.post("/hce/process", json={
            "relationship_id": rel_id,
            "chapter_id": chap_id,
            "user_message": "I prefer lightweight compiler optimizations and want to learn RTOS task switching."
        })
        self.assertEqual(res_proc.status_code, 200)
        proc_data = res_proc.json()
        self.assertEqual(proc_data["relationship_id"], rel_id)
        self.assertEqual(proc_data["chapter_id"], chap_id)
        self.assertFalse(proc_data["authorized_to_create_goals"])
        self.assertFalse(proc_data["authorized_to_write_memory"])

        # 5. Retrieve Context Snapshot
        res_ctx = client.get(f"/hce/relationship/{rel_id}/context")
        self.assertEqual(res_ctx.status_code, 200)
        self.assertEqual(res_ctx.json()["active_chapter"]["chapter_id"], chap_id)

        # 6. Retrieve health
        res_health = client.get(f"/hce/relationship/{rel_id}/health")
        self.assertEqual(res_health.status_code, 200)
        self.assertIn("trust_score", res_health.json()["health_metrics"])

        # 7. Chapter Close and auto-detect narrative arcs
        res_close = client.put(f"/hce/chapter/{chap_id}/close", json={"summary_narrative": "Studied embedded systems and improved Kattappa HCE."})
        self.assertEqual(res_close.status_code, 200)
        self.assertTrue(res_close.json()["closed"])

        # 8. Narrative arcs retrieval
        res_arcs = client.get(f"/hce/relationship/{rel_id}/narrative-arcs")
        self.assertEqual(res_arcs.status_code, 200)
        self.assertTrue(len(res_arcs.json()["narrative_arcs"]) > 0)
