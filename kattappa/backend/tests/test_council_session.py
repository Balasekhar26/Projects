"""Tests for Council of Perspectives (council_session.py)."""

from __future__ import annotations

import json
import time
import uuid
import pytest
from unittest.mock import patch, MagicMock

from backend.core.council_session import (
    COUNCIL_ROSTER,
    VOTING_ROSTER,
    ROSTER_BY_ROLE,
    CONTEXT_WEIGHT_AMPLIFIERS,
    ALL_QUESTION_TYPES,
    CouncilPerspective,
    CouncilSession,
    CouncilPerformanceReport,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    import backend.core.council_session as cs_module
    monkeypatch.setenv("KATTAPPA_DATA_DIR", str(tmp_path))
    cs_module._schema_ensured.clear()
    yield


# ── Roster completeness ───────────────────────────────────────────────────────

class TestRosterCompleteness:

    def test_roster_has_12_members(self):
        assert len(COUNCIL_ROSTER) == 12

    def test_exactly_one_auditor(self):
        auditors = [p for p in COUNCIL_ROSTER if p.is_auditor]
        assert len(auditors) == 1
        assert auditors[0].role == "Auditor"

    def test_auditor_not_in_voting_roster(self):
        roles = [p.role for p in VOTING_ROSTER]
        assert "Auditor" not in roles

    def test_voting_roster_has_11_members(self):
        assert len(VOTING_ROSTER) == 11

    def test_all_required_roles_present(self):
        roles = {p.role for p in COUNCIL_ROSTER}
        required = {
            "Rama", "Krishna", "Shiva", "Brahma", "Hanuman",
            "Kattappa", "Scientist", "Engineer", "Teacher",
            "Security", "MemoryKeeper", "Auditor",
        }
        assert roles == required

    def test_all_perspectives_have_function(self):
        for p in COUNCIL_ROSTER:
            assert p.function, f"{p.role} has empty function"

    def test_auditor_base_weight_is_zero(self):
        """Auditor has no vote weight — adversarial meta-role only."""
        auditor = ROSTER_BY_ROLE["Auditor"]
        assert auditor.base_weight == 0.0

    def test_high_weight_roles(self):
        """Security, Scientist, Kattappa should have base_weight >= 1.4."""
        for role in ["Security", "Scientist", "Kattappa"]:
            p = ROSTER_BY_ROLE[role]
            assert p.base_weight >= 1.4, f"{role} weight too low: {p.base_weight}"


# ── Context-adaptive weights ──────────────────────────────────────────────────

class TestContextAdaptiveWeights:

    def test_all_question_types_covered(self):
        assert ALL_QUESTION_TYPES == {"safety", "research", "user_impact", "architecture", "general"}

    def test_safety_amplifies_security(self):
        security = ROSTER_BY_ROLE["Security"]
        base = security.base_weight
        amplified = security.amplified_weight("safety")
        assert amplified > base

    def test_research_amplifies_scientist(self):
        scientist = ROSTER_BY_ROLE["Scientist"]
        amplified = scientist.amplified_weight("research")
        assert amplified > scientist.amplified_weight("general")

    def test_user_impact_amplifies_kattappa(self):
        kattappa = ROSTER_BY_ROLE["Kattappa"]
        assert kattappa.amplified_weight("user_impact") > kattappa.amplified_weight("general")

    def test_architecture_amplifies_shiva(self):
        shiva = ROSTER_BY_ROLE["Shiva"]
        assert shiva.amplified_weight("architecture") > shiva.amplified_weight("general")

    def test_general_uses_base_weight(self):
        """No amplifiers for 'general' — amplified weight == base weight."""
        for p in VOTING_ROSTER:
            assert p.amplified_weight("general") == p.base_weight

    def test_unknown_question_type_falls_back_to_base(self):
        rama = ROSTER_BY_ROLE["Rama"]
        assert rama.amplified_weight("unknown_xyz") == rama.base_weight


# ── quick_deliberate selection ────────────────────────────────────────────────

class TestQuickDeliberateSelection:

    def _make_mock_elicit(self, vote="APPROVE"):
        """Return a mock that produces a valid (AgentOutput, vote_record) tuple."""
        from backend.core.consensus_engine import AgentOutput, Decision, EvidenceType
        ao = AgentOutput(
            agent="Mock",
            decision=Decision.APPROVE,
            confidence=0.8,
            evidence=(EvidenceType.REASONING,),
            source_id="mock_source",
        )
        vote_rec = {
            "perspective": "Mock",
            "vote": vote,
            "confidence": 0.8,
            "evidence_type": "reasoning",
            "rationale": "mock rationale",
            "risks": [],
            "benefits": [],
            "vote_weight": 1.0,
        }
        return ao, vote_rec

    def test_quick_deliberate_selects_n_perspectives(self):
        """quick_deliberate with n=3 should call _elicit_perspective exactly 3 times."""
        call_count = {"count": 0}

        def fake_elicit(cls, perspective, question, question_type, context, *args, **kwargs):
            call_count["count"] += 1
            return self._make_mock_elicit()

        def fake_auditor(cls, question, outputs):
            return [], []

        with patch.object(CouncilSession, "_elicit_perspective", classmethod(fake_elicit)), \
             patch.object(CouncilSession, "_run_auditor", classmethod(fake_auditor)), \
             patch.object(CouncilSession, "_maybe_submit_governance", return_value=None), \
             patch.object(CouncilSession, "_record_to_strategic_memory", return_value=None):
            CouncilSession.quick_deliberate("Test question", "general", n=3)

        assert call_count["count"] == 3

    def test_safety_question_always_includes_security(self):
        """For safety questions, Security must be in the selected perspectives."""
        selected_roles = {"count": [], "perspectives": []}

        def fake_run(cls, question, question_type, context, perspectives, *args, **kwargs):
            selected_roles["perspectives"] = [p.role for p in perspectives]
            # Return a minimal CouncilResult
            from backend.core.council_session import CouncilResult
            return CouncilResult(
                decision_id=str(uuid.uuid4()),
                question=question,
                question_type=question_type,
                consensus_status="rejected",
                requires_human_approval=False,
                selected_recommendation=None,
                approve_mass=0.0,
                reject_mass=0.0,
                margin=None,
                votes=[],
                audit_findings=[],
                reasons=[],
                created_at=time.time(),
            )

        with patch.object(CouncilSession, "_run", classmethod(fake_run)):
            CouncilSession.quick_deliberate("Is memory safe?", "safety", n=3)

        assert "Security" in selected_roles["perspectives"]

    def test_full_deliberate_uses_all_11_voting_perspectives(self):
        """deliberate() should call _elicit_perspective exactly 11 times."""
        call_count = {"count": 0}

        def fake_elicit(cls, perspective, question, question_type, context, *args, **kwargs):
            call_count["count"] += 1
            return self._make_mock_elicit()

        def fake_auditor(cls, question, outputs):
            return [], []

        with patch.object(CouncilSession, "_elicit_perspective", classmethod(fake_elicit)), \
             patch.object(CouncilSession, "_run_auditor", classmethod(fake_auditor)), \
             patch.object(CouncilSession, "_maybe_submit_governance", return_value=None), \
             patch.object(CouncilSession, "_record_to_strategic_memory", return_value=None):
            CouncilSession.deliberate("Should we add a cache?", "architecture")

        assert call_count["count"] == 11


# ── Auditor meta-role ─────────────────────────────────────────────────────────

class TestAuditorMetaRole:

    def test_auditor_never_votes(self):
        """The Auditor perspective must never cast APPROVE or REJECT."""
        auditor = ROSTER_BY_ROLE["Auditor"]
        assert auditor.is_auditor is True
        assert auditor.base_weight == 0.0

    def test_auditor_not_in_voting_roster(self):
        for p in VOTING_ROSTER:
            assert not p.is_auditor

    def test_auditor_findings_injected_as_critic_findings(self):
        """When _run_auditor returns findings, they appear as CriticFindings in outputs."""
        from backend.core.consensus_engine import CriticFinding, FindingCategory

        mock_findings = [
            CriticFinding(
                source="Auditor",
                category=FindingCategory.ADVISORY,
                description="Assumption about memory safety not validated.",
            )
        ]
        mock_ledger = [
            {"finding_category": "advisory", "description": "Assumption about memory safety not validated."}
        ]

        def fake_auditor(cls, question, outputs):
            return mock_findings, mock_ledger

        def fake_elicit(cls, perspective, question, question_type, context, *args, **kwargs):
            from backend.core.consensus_engine import AgentOutput, Decision, EvidenceType
            ao = AgentOutput(
                agent=perspective.role,
                decision=Decision.ABSTAIN,
                confidence=0.5,
                evidence=(EvidenceType.REASONING,),
                source_id="mock_src",
            )
            vr = {"perspective": perspective.role, "vote": "ABSTAIN", "confidence": 0.5,
                  "evidence_type": "reasoning", "rationale": "", "risks": [], "benefits": [],
                  "vote_weight": 1.0}
            return ao, vr

        with patch.object(CouncilSession, "_elicit_perspective", classmethod(fake_elicit)), \
             patch.object(CouncilSession, "_run_auditor", classmethod(fake_auditor)), \
             patch.object(CouncilSession, "_maybe_submit_governance", return_value=None), \
             patch.object(CouncilSession, "_record_to_strategic_memory", return_value=None):
            result = CouncilSession.quick_deliberate("Test", "safety", n=2)

        assert len(result.audit_findings) == 1
        assert result.audit_findings[0]["finding_category"] == "advisory"


# ── Decision ledger persistence ───────────────────────────────────────────────

class TestLedgerPersistence:

    def _run_with_mocked_llm(self, question="Test question", qt="general", n=2):
        from backend.core.consensus_engine import AgentOutput, Decision, EvidenceType

        def fake_elicit(cls, perspective, question, question_type, context, *args, **kwargs):
            ao = AgentOutput(
                agent=perspective.role,
                decision=Decision.APPROVE,
                confidence=0.75,
                evidence=(EvidenceType.REASONING,),
                source_id=f"src_{perspective.role.lower()}",
                rationale="Mock rationale",
            )
            vr = {"perspective": perspective.role, "vote": "APPROVE", "confidence": 0.75,
                  "evidence_type": "reasoning", "rationale": "Mock rationale",
                  "risks": ["mock risk"], "benefits": ["mock benefit"], "vote_weight": 1.2}
            return ao, vr

        def fake_auditor(cls, question, outputs):
            return [], []

        with patch.object(CouncilSession, "_elicit_perspective", classmethod(fake_elicit)), \
             patch.object(CouncilSession, "_run_auditor", classmethod(fake_auditor)), \
             patch.object(CouncilSession, "_maybe_submit_governance", return_value=None), \
             patch.object(CouncilSession, "_record_to_strategic_memory", return_value=None):
            return CouncilSession.quick_deliberate(question, qt, n=n)

    def test_decision_persisted_to_ledger(self):
        result = self._run_with_mocked_llm()
        decision = CouncilSession.get_decision(result.decision_id)
        assert decision is not None
        assert decision["id"] == result.decision_id

    def test_votes_persisted_to_ledger(self):
        result = self._run_with_mocked_llm(n=3)
        decision = CouncilSession.get_decision(result.decision_id)
        assert len(decision["votes"]) == 3

    def test_vote_fields_present(self):
        result = self._run_with_mocked_llm(n=2)
        decision = CouncilSession.get_decision(result.decision_id)
        vote = decision["votes"][0]
        for field in ["perspective", "vote", "confidence", "evidence_type", "rationale", "risks", "benefits"]:
            assert field in vote, f"Missing field: {field}"

    def test_list_decisions_returns_results(self):
        self._run_with_mocked_llm()
        self._run_with_mocked_llm("Second question")
        decisions = CouncilSession.list_decisions(limit=10)
        assert len(decisions) >= 2

    def test_question_stored_correctly(self):
        result = self._run_with_mocked_llm(question="Should we refactor the planner?")
        decision = CouncilSession.get_decision(result.decision_id)
        assert decision["question"] == "Should we refactor the planner?"

    def test_question_type_stored_correctly(self):
        result = self._run_with_mocked_llm(qt="architecture")
        decision = CouncilSession.get_decision(result.decision_id)
        assert decision["question_type"] == "architecture"


# ── Governance submission trigger ─────────────────────────────────────────────

class TestGovernanceSubmission:

    def test_approved_requires_human_triggers_governance(self):
        """When ConsensusEngine returns APPROVED + requires_human=True, _maybe_submit_governance is called."""
        from backend.core.consensus_engine import (
            AgentOutput, ConsensusDecision, ConsensusStatus, Decision, Recommendation
        )

        mock_decision = ConsensusDecision(
            status=ConsensusStatus.APPROVED,
            selected=Recommendation(source="Security", message="Approve the change", weight=1.5),
            requires_human_approval=True,
            approve_mass=5.0,
            reject_mass=0.0,
        )

        submit_calls = {"count": 0, "proposal_id": None}

        def fake_submit_gov(decision, question, question_type, context):
            submit_calls["count"] += 1
            if decision.requires_human_approval and decision.status == ConsensusStatus.APPROVED:
                submit_calls["proposal_id"] = str(uuid.uuid4())
                return submit_calls["proposal_id"]
            return None

        def fake_elicit(cls, perspective, question, question_type, context, *args, **kwargs):
            ao = AgentOutput(
                agent=perspective.role,
                decision=Decision.APPROVE,
                confidence=0.9,
                source_id=f"src_{perspective.role.lower()}",
            )
            vr = {"perspective": perspective.role, "vote": "APPROVE", "confidence": 0.9,
                  "evidence_type": "reasoning", "rationale": "", "risks": [], "benefits": [],
                  "vote_weight": 1.5}
            return ao, vr

        with patch("backend.core.consensus_engine.ConsensusEngine.decide", return_value=mock_decision), \
             patch.object(CouncilSession, "_elicit_perspective", classmethod(fake_elicit)), \
             patch.object(CouncilSession, "_run_auditor", return_value=([], [])), \
             patch.object(CouncilSession, "_maybe_submit_governance",
                          staticmethod(fake_submit_gov)), \
             patch.object(CouncilSession, "_record_to_strategic_memory", return_value=None):
            result = CouncilSession.quick_deliberate("Is this safe?", "safety", n=1)

        assert result.consensus_status == "approved"
        assert result.requires_human_approval is True
        assert submit_calls["count"] == 1
        assert result.governance_proposal_id is not None


# ── Performance report ────────────────────────────────────────────────────────

class TestPerformanceReport:

    def test_empty_report_returns_valid_structure(self):
        report = CouncilPerformanceReport.generate()
        assert isinstance(report, dict)
        assert "total_deliberations" in report
        assert "approved" in report
        assert "rejected" in report
        assert "escalated" in report
        assert "benchmarked_outcomes" in report
        assert "by_question_type" in report

    def test_empty_report_has_zero_totals(self):
        report = CouncilPerformanceReport.generate()
        assert report["total_deliberations"] == 0
        assert report["benchmarked_outcomes"] == 0
        assert report["accuracy"] is None

    def test_record_outcome_persisted(self):
        # Insert a fake decision row directly
        from backend.core.council_session import _ensure_schema, _connect, _WRITE_LOCK
        _ensure_schema()
        fake_id = str(uuid.uuid4())
        import time as _time
        with _WRITE_LOCK:
            conn = _connect()
            try:
                conn.execute(
                    "INSERT INTO council_decisions "
                    "(id, question, question_type, context_json, created_at, consensus_status, requires_human, reasons_json) "
                    "VALUES (?, ?, ?, '{}', ?, 'approved', 0, '[]')",
                    (fake_id, "Test?", "general", _time.time())
                )
                conn.commit()
            finally:
                conn.close()

        CouncilSession.record_outcome(fake_id, "correct", 0.92)
        report = CouncilPerformanceReport.generate()
        assert report["benchmarked_outcomes"] == 1
        assert report["correct_outcomes"] == 1
        assert report["accuracy"] == 1.0


# ── CouncilResult serialisation ───────────────────────────────────────────────

class TestCouncilResultSerialization:

    def test_to_dict_has_all_fields(self):
        from backend.core.council_session import CouncilResult
        result = CouncilResult(
            decision_id="test-id",
            question="Test?",
            question_type="general",
            consensus_status="approved",
            requires_human_approval=True,
            selected_recommendation="Do the thing",
            approve_mass=5.0,
            reject_mass=1.0,
            margin=0.67,
            votes=[],
            audit_findings=[],
            reasons=["reason1"],
            created_at=time.time(),
        )
        d = result.to_dict()
        assert d["decision_id"] == "test-id"
        assert d["consensus_status"] == "approved"
        assert d["requires_human_approval"] is True
        assert d["approve_mass"] == 5.0
        assert d["reasons"] == ["reason1"]


# ── Council Hardening (Step 20) Tests ─────────────────────────────────────────

class TestCouncilHardening:

    def test_hanuman_weight_positive_in_all_profiles(self):
        """Verify Hanuman has positive default influence in all mode profiles."""
        from backend.core.council_session import MODE_PROFILES
        for profile_name, profile_weights in MODE_PROFILES.items():
            hanuman_weight = profile_weights.get("Hanuman", 0.0)
            assert hanuman_weight > 0.0, f"Hanuman weight in {profile_name} is not positive: {hanuman_weight}"

    def test_select_mode_profile_auto_detection(self):
        """Verify select_mode_profile auto-detection logic for different prompt keywords."""
        from backend.core.council_session import select_mode_profile

        # Safety keywords/types -> critical_fix
        assert select_mode_profile("Need to rotate credentials immediately", "general", {}) == "critical_fix"
        assert select_mode_profile("Is this safe?", "safety", {}) == "critical_fix"
        assert select_mode_profile("Some prompt", "general", {"production": True}) == "critical_fix"
        assert select_mode_profile("Truncate the table", "general", {}) == "critical_fix"

        # Engineering / Code keywords/types -> engineering_standard
        assert select_mode_profile("Refactor the scheduler component", "general", {}) == "engineering_standard"
        assert select_mode_profile("Implementation of the new user api", "general", {}) == "engineering_standard"
        assert select_mode_profile("Code change request", "general", {"code_change": True}) == "engineering_standard"

        # Innovation keywords/types -> innovation
        assert select_mode_profile("Brainstorm ideas for Q3 features", "general", {}) == "innovation"
        assert select_mode_profile("Research potential storage alternatives", "general", {}) == "innovation"

        # Default -> system_default
        assert select_mode_profile("Explain standard operations", "general", {}) == "system_default"

    def test_calibration_factor_adjustments(self, isolated_db):
        """Verify calibration factor computation: cold-start, low accuracy, high accuracy."""
        from backend.core.council_session import CouncilCalibration, _connect, _WRITE_LOCK, _ensure_schema
        import time

        _ensure_schema()
        agent = "Scientist"

        # 1. Cold-start (< 3 judged votes)
        assert CouncilCalibration.get_calibration_factor(agent) == 1.0

        # Insert 2 correct votes - still cold start
        with _WRITE_LOCK:
            conn = _connect()
            for i in range(2):
                conn.execute(
                    "INSERT INTO agent_accuracy_history (history_id, agent_name, prediction_correct, created_at) "
                    "VALUES (?, ?, 1, ?)",
                    (str(uuid.uuid4()), agent, time.time())
                )
            conn.commit()
            conn.close()

        assert CouncilCalibration.get_calibration_factor(agent) == 1.0

        # Insert a 3rd correct vote -> should be 3/3 = 1.0
        with _WRITE_LOCK:
            conn = _connect()
            conn.execute(
                "INSERT INTO agent_accuracy_history (history_id, agent_name, prediction_correct, created_at) "
                "VALUES (?, ?, 1, ?)",
                (str(uuid.uuid4()), agent, time.time())
            )
            conn.commit()
            conn.close()

        assert CouncilCalibration.get_calibration_factor(agent) == 1.0

        # Insert 3 incorrect votes -> 3 correct, 3 incorrect = 3/6 = 0.5
        with _WRITE_LOCK:
            conn = _connect()
            for i in range(3):
                conn.execute(
                    "INSERT INTO agent_accuracy_history (history_id, agent_name, prediction_correct, created_at) "
                    "VALUES (?, ?, 0, ?)",
                    (str(uuid.uuid4()), agent, time.time())
                )
            conn.commit()
            conn.close()

        assert CouncilCalibration.get_calibration_factor(agent) == 0.5

        # Insert 5 more incorrect votes -> 3 correct, 8 incorrect = 3/11 = 0.2727
        with _WRITE_LOCK:
            conn = _connect()
            for i in range(5):
                conn.execute(
                    "INSERT INTO agent_accuracy_history (history_id, agent_name, prediction_correct, created_at) "
                    "VALUES (?, ?, 0, ?)",
                    (str(uuid.uuid4()), agent, time.time())
                )
            conn.commit()
            conn.close()

        assert abs(CouncilCalibration.get_calibration_factor(agent) - 3.0/11.0) < 1e-4

        # Insert 10 more incorrect votes -> should clamp to 0.25 minimum
        with _WRITE_LOCK:
            conn = _connect()
            for i in range(10):
                conn.execute(
                    "INSERT INTO agent_accuracy_history (history_id, agent_name, prediction_correct, created_at) "
                    "VALUES (?, ?, 0, ?)",
                    (str(uuid.uuid4()), agent, time.time())
                )
            conn.commit()
            conn.close()

        assert CouncilCalibration.get_calibration_factor(agent) == 0.25

    def test_traceability_evidence_refs_filtering(self):
        """Verify that cited references are filtered against available refs."""
        from backend.core.consensus_engine import AgentOutput, Decision, EvidenceType
        
        available_refs = {"ref_1", "ref_2"}
        available_refs_str = "ref_1, ref_2"
        active_weights = {"Security": 1.5}
        perspective = ROSTER_BY_ROLE["Security"]

        # Mock ask_model to return JSON with valid and invalid references
        mock_response = json.dumps({
            "decision": "APPROVE",
            "confidence": 0.9,
            "evidence_type": "reasoning",
            "risks": [],
            "benefits": [],
            "rationale": "Mock reasoning",
            "evidence_refs": ["ref_1", "ref_invalid_3"]
        })

        with patch("backend.core.model_router.ask_model", return_value=mock_response):
            ao, vote_rec = CouncilSession._elicit_perspective(
                perspective=perspective,
                question="Is this secure?",
                question_type="safety",
                context={},
                available_refs_str=available_refs_str,
                available_refs=available_refs,
                active_weights=active_weights
            )

        # "ref_invalid_3" should be filtered out
        assert vote_rec["evidence_refs"] == ["ref_1"]

    def test_arbiter_blocking_and_advisory_findings(self):
        """Verify Arbiter evaluate checks and how blocking finding forces escalation."""
        from backend.core.council_session import CouncilArbiter

        # Mock vote records
        votes_clean = [
            {
                "perspective": "Security",
                "vote": "APPROVE",
                "confidence": 0.8,
                "historical_judged": 4,
                "evidence_type": "reasoning",
                "rationale": "Clear logical layout.",
                "evidence_refs": ["ref_1"],
                "risks": []
            }
        ]

        # 1. No warnings / clean run
        findings = CouncilArbiter.evaluate(
            question="Clean?",
            votes=votes_clean,
            available_refs={"ref_1"},
            consensus_status="approved",
            consensus_strength=1.0,
            requires_human_approval=False
        )
        assert len([f for f in findings if f["severity"] == "blocking"]) == 0

        # 2. Unverified evidence (blocking)
        votes_unverified = [
            {
                "perspective": "Security",
                "vote": "APPROVE",
                "confidence": 0.8,
                "historical_judged": 4,
                "evidence_type": "reasoning",
                "rationale": "Logical analysis.",
                "evidence_refs": ["ref_unverified"],
                "risks": []
            }
        ]
        findings = CouncilArbiter.evaluate(
            question="Unverified?",
            votes=votes_unverified,
            available_refs={"ref_1"},
            consensus_status="approved",
            consensus_strength=1.0,
            requires_human_approval=False
        )
        assert any(f["rule"] == "unverified_evidence" and f["severity"] == "blocking" for f in findings)

        # 3. Unsupported high confidence (blocking)
        votes_high_conf = [
            {
                "perspective": "Security",
                "vote": "APPROVE",
                "confidence": 0.99,
                "historical_judged": 1,  # < 3
                "evidence_type": "reasoning",
                "rationale": "Logical analysis.",
                "evidence_refs": ["ref_1"],
                "risks": []
            }
        ]
        findings = CouncilArbiter.evaluate(
            question="High confidence?",
            votes=votes_high_conf,
            available_refs={"ref_1"},
            consensus_status="approved",
            consensus_strength=1.0,
            requires_human_approval=False
        )
        assert any(f["rule"] == "unsupported_high_confidence" and f["severity"] == "blocking" for f in findings)

        # 4. Missing traceability (advisory)
        votes_no_trace = [
            {
                "perspective": "Security",
                "vote": "APPROVE",
                "confidence": 0.8,
                "historical_judged": 4,
                "evidence_type": "reasoning",
                "rationale": "Logical analysis.",
                "evidence_refs": [],  # Empty refs
                "risks": []
            }
        ]
        findings = CouncilArbiter.evaluate(
            question="No trace?",
            votes=votes_no_trace,
            available_refs={"ref_1"},
            consensus_status="approved",
            consensus_strength=1.0,
            requires_human_approval=False
        )
        assert any(f["rule"] == "missing_traceability" and f["severity"] == "advisory" for f in findings)

    def test_dissent_preservation_during_session(self):
        """Verify that dissenting votes are archived and returned in decision details."""
        from backend.core.consensus_engine import AgentOutput, ConsensusDecision, ConsensusStatus, Decision, Recommendation
        
        mock_decision = ConsensusDecision(
            status=ConsensusStatus.APPROVED,
            selected=Recommendation(source="Security", message="Approve", weight=1.5),
            requires_human_approval=False,
            approve_mass=5.0,
            reject_mass=1.0,
        )

        # Mock elicitation to return Kattappa voting APPROVE and Scientist voting REJECT (dissenting)
        def fake_elicit(cls, perspective, question, question_type, context, *args, **kwargs):
            vote = "APPROVE" if perspective.role == "Kattappa" else "REJECT"
            ao = AgentOutput(
                agent=perspective.role,
                decision=Decision.APPROVE if vote == "APPROVE" else Decision.REJECT,
                confidence=0.8,
                source_id=f"src_{perspective.role.lower()}"
            )
            vr = {
                "perspective": perspective.role,
                "vote": vote,
                "confidence": 0.8,
                "evidence_type": "reasoning",
                "rationale": "Mock reasoning",
                "risks": ["mock risk"] if vote == "REJECT" else [],
                "benefits": [],
                "vote_weight": 1.0,
                "calibration_factor": 1.0,
                "evidence_refs": ["ref_1"]
            }
            return ao, vr

        with patch("backend.core.consensus_engine.ConsensusEngine.decide", return_value=mock_decision), \
             patch.object(CouncilSession, "_elicit_perspective", classmethod(fake_elicit)), \
             patch.object(CouncilSession, "_run_auditor", return_value=([], [])), \
             patch.object(CouncilSession, "_maybe_submit_governance", return_value=None), \
             patch.object(CouncilSession, "_record_to_strategic_memory", return_value=None):
            
            result = CouncilSession.quick_deliberate("Should we run?", "general", context={"episodic_ids": ["ref_1"]}, n=2)

        # result should contain the dissent record for Scientist
        assert len(result.dissent) == 1
        assert result.dissent[0]["perspective"] == "Scientist"
        assert result.dissent[0]["vote"] == "REJECT"

        # retrieve from DB and verify
        db_record = CouncilSession.get_decision(result.decision_id)
        assert db_record is not None
        assert len(db_record["dissent"]) == 1
        assert db_record["dissent"][0]["perspective"] == "Scientist"

    def test_dissent_preservation_and_outcome_learning_loop(self, isolated_db):
        """Verify minority dissent votes are preserved, and outcome learning updates accuracy."""
        from backend.core.consensus_engine import AgentOutput, ConsensusDecision, ConsensusStatus, Decision
        
        decision_id = str(uuid.uuid4())
        
        # Mock elicitation to return a consensus where Shiva dissents (REJECTS when approved)
        vote_records = [
            {
                "perspective": "Security",
                "vote": "APPROVE",
                "confidence": 0.9,
                "evidence_type": "reasoning",
                "rationale": "Looks good",
                "risks": [],
                "benefits": [],
                "vote_weight": 1.5,
                "calibration_factor": 1.0,
                "historical_judged": 4,
                "historical_correct": 3
            },
            {
                "perspective": "Shiva",
                "vote": "REJECT",
                "confidence": 0.8,
                "evidence_type": "reasoning",
                "rationale": "Too complex",
                "risks": ["high complexity"],
                "benefits": [],
                "vote_weight": 1.2,
                "calibration_factor": 1.0,
                "historical_judged": 4,
                "historical_correct": 2
            }
        ]

        # Call record_outcome for the decision and verify SQLite records
        from backend.core.council_session import _ensure_schema, _connect, _WRITE_LOCK
        _ensure_schema()

        # Insert the decision directly
        import time
        with _WRITE_LOCK:
            conn = _connect()
            conn.execute(
                """
                INSERT INTO council_decisions
                (id, question, question_type, context_json, created_at, consensus_status, requires_human, approve_mass, reject_mass, reasons_json)
                VALUES (?, ?, 'general', '{}', ?, 'approved', 0, 1.5, 1.2, '[]')
                """,
                (decision_id, "Test Question?", time.time())
            )
            # Insert votes
            for vr in vote_records:
                conn.execute(
                    """
                    INSERT INTO council_votes
                    (decision_id, perspective, vote, confidence, evidence_type, rationale, risks_json, benefits_json, vote_weight, logged_at, calibration_factor)
                    VALUES (?, ?, ?, ?, ?, ?, '[]', '[]', ?, ?, ?)
                    """,
                    (decision_id, vr["perspective"], vr["vote"], vr["confidence"], vr["evidence_type"], vr["rationale"], vr["vote_weight"], time.time(), vr["calibration_factor"])
                )
            conn.commit()
            conn.close()

        # Call record_outcome (actual outcome is correct / APPROVED was correct)
        CouncilSession.record_outcome(decision_id, "correct", 1.0)

        # Check accuracy history was updated correctly
        conn = _connect()
        history = conn.execute("SELECT * FROM agent_accuracy_history WHERE session_id = ?", (decision_id,)).fetchall()
        assert len(history) == 2
        
        sec_hist = [h for h in history if h["agent_name"] == "Security"][0]
        shiva_hist = [h for h in history if h["agent_name"] == "Shiva"][0]

        # Security voted APPROVE, consensus was approved, actual outcome is correct -> Security prediction is correct (1)
        assert sec_hist["prediction_correct"] == 1
        # Shiva voted REJECT, consensus was approved, actual outcome is correct -> Shiva prediction is incorrect (0)
        assert shiva_hist["prediction_correct"] == 0
        conn.close()
