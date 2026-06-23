"""
Step 10.0 — Research Quality & Source Trust System Test Suite.
Verifies source trust classifications, claims consensus checks, deduplication memory, PVS filtering, and dynamic reputation shifts.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from backend.core.source_trust_engine import SourceTrustEngine, TrustLevel
from backend.core.research_memory import ResearchMemory
from backend.core.proposal_engine import ProposalEngine
from backend.core.research_reader import ResearchReader
from backend.core.research_scheduler import ResearchScheduler
from backend.core.burn_in_governance import BurnInGovernance
from backend.core.proposal_governance import ProposalStatus


@pytest.fixture(autouse=True)
def clean_research_stores(tmp_path):
    """Fixture to isolate all database and JSON stores during test runs."""
    temp_docs = tmp_path / "research_documents.json"
    temp_summaries = tmp_path / "research_summaries.json"
    temp_ideas = tmp_path / "research_ideas.json"
    temp_history = tmp_path / "research_loop_history.json"
    temp_reputations = tmp_path / "source_reputation.json"
    temp_memory = tmp_path / "research_memory.json"
    temp_proposals = tmp_path / "proposals.json"
    temp_state = tmp_path / "burn_in_state.json"

    # Write empty initial files
    temp_docs.write_text("[]", encoding="utf-8")
    temp_summaries.write_text("[]", encoding="utf-8")
    temp_ideas.write_text("[]", encoding="utf-8")
    temp_history.write_text("[]", encoding="utf-8")
    temp_reputations.write_text("{}", encoding="utf-8")
    temp_memory.write_text(json.dumps({
        "already_read": [],
        "already_summarized": [],
        "already_proposed": [],
        "already_rejected": []
    }), encoding="utf-8")
    temp_proposals.write_text("[]", encoding="utf-8")
    temp_state.write_text(json.dumps({"state": "NORMAL", "active_freezes": []}), encoding="utf-8")

    with patch("backend.core.research_reader._documents_path", return_value=temp_docs), \
         patch("backend.core.research_summarizer._summaries_path", return_value=temp_summaries), \
         patch("backend.core.idea_extractor._ideas_path", return_value=temp_ideas), \
         patch("backend.core.research_scheduler._history_path", return_value=temp_history), \
         patch("backend.core.source_trust_engine._reputation_path", return_value=temp_reputations), \
         patch("backend.core.research_memory._memory_path", return_value=temp_memory), \
         patch("backend.core.burn_in_governance._state_path", return_value=temp_state), \
         patch("backend.core.proposal_engine._proposals_path", return_value=temp_proposals):
        yield


# ---------------------------------------------------------------------------
# 1. Source Trust Engine Tests
# ---------------------------------------------------------------------------

class TestSourceTrustEngine:
    def test_trust_level_classifications(self):
        # Peer reviewed -> VERIFIED
        rep = SourceTrustEngine.get_source_reputation("arXiv:123", "peer_reviewed")
        assert rep["trust_level"] == TrustLevel.VERIFIED.value
        assert rep["reputation_score"] == 1.0

        # Blog -> LOW
        rep2 = SourceTrustEngine.get_source_reputation("Blog: Eng", "blog")
        assert rep2["trust_level"] == TrustLevel.LOW.value
        assert rep2["reputation_score"] == 0.3

        # Default -> LOW
        rep3 = SourceTrustEngine.get_source_reputation("UnknownSource")
        assert rep3["trust_level"] == TrustLevel.LOW.value
        assert rep3["reputation_score"] == 0.3

    def test_consensus_score_calculation(self):
        # Setup source reputations
        SourceTrustEngine.get_source_reputation("SourceA", "peer_reviewed")  # 1.0
        SourceTrustEngine.get_source_reputation("SourceB", "preprint")       # 0.6
        SourceTrustEngine.get_source_reputation("SourceC", "blog")           # 0.3

        # Single source consensus
        assert SourceTrustEngine.calculate_consensus(["SourceB"]) == 0.6

        # Multi source consensus: 1 - (1-1.0)*(1-0.6)*(1-0.3) = 1.0
        assert SourceTrustEngine.calculate_consensus(["SourceA", "SourceB", "SourceC"]) == 1.0

        # Combined consensus of B and C: 1 - (1-0.6)*(1-0.3) = 1 - 0.4*0.7 = 1 - 0.28 = 0.72
        assert SourceTrustEngine.calculate_consensus(["SourceB", "SourceC"]) == 0.72

    def test_reputation_updates_deployed_success(self):
        # Pre-register SourceA as High trust so PVS passes threshold
        SourceTrustEngine.get_source_reputation("SourceA", "peer_reviewed")

        # Create mock proposal in proposal engine
        prop = ProposalEngine.create_proposal(
            title="Consolidation Optimization",
            problem="Lookup bottleneck",
            evidence="Evidence",
            proposal="Proposed fix code",
            expected_gain=2.5,
            complexity=1,
            confidence=85,
            source_name="SourceA"
        )
        assert prop["status"] != "rejected"

        # Update reputation for DEPLOYED_SUCCESSFUL
        SourceTrustEngine.update_reputation(prop["id"], "DEPLOYED_SUCCESSFUL")
        rep = SourceTrustEngine.get_source_reputation("SourceA")
        assert rep["correct_predictions"] == 1
        assert rep["useful_ideas"] == 1
        # reputation score should increase from 1.0
        assert rep["reputation_score"] == 1.0  # Clamped to 1.0 max

    def test_reputation_updates_rollback(self):
        # Pre-register SourceB as High trust so PVS passes threshold
        SourceTrustEngine.get_source_reputation("SourceB", "peer_reviewed")

        # Create mock proposal
        prop = ProposalEngine.create_proposal(
            title="Consolidation Optimization 2",
            problem="Lookup bottleneck 2",
            evidence="Evidence",
            proposal="Proposed fix code 2",
            expected_gain=2.5,
            complexity=1,
            confidence=85,
            source_name="SourceB"
        )

        # Update reputation for ROLLBACK (failure)
        SourceTrustEngine.update_reputation(prop["id"], "ROLLBACK")
        rep = SourceTrustEngine.get_source_reputation("SourceB")
        assert rep["incorrect_predictions"] == 1
        # reputation score should decrease (base 1.0 - 0.10 = 0.90)
        assert rep["reputation_score"] == 0.90
        assert rep["trust_level"] == TrustLevel.VERIFIED.value

        # Multiple failures should degrade it further
        SourceTrustEngine.update_reputation(prop["id"], "ROLLBACK")
        SourceTrustEngine.update_reputation(prop["id"], "ROLLBACK")
        SourceTrustEngine.update_reputation(prop["id"], "ROLLBACK")
        SourceTrustEngine.update_reputation(prop["id"], "ROLLBACK")
        SourceTrustEngine.update_reputation(prop["id"], "ROLLBACK")
        SourceTrustEngine.update_reputation(prop["id"], "ROLLBACK")
        SourceTrustEngine.update_reputation(prop["id"], "ROLLBACK")
        SourceTrustEngine.update_reputation(prop["id"], "ROLLBACK")

        rep = SourceTrustEngine.get_source_reputation("SourceB")
        assert rep["reputation_score"] < 0.20
        assert rep["trust_level"] == TrustLevel.REJECTED.value


# ---------------------------------------------------------------------------
# 2. Research Memory Tests
# ---------------------------------------------------------------------------

class TestResearchMemory:
    def test_deduplication_tracking(self):
        title = "Novel Caching Strategies"
        
        # Initially not duplicate
        assert ResearchMemory.is_duplicate_document(title) is False
        assert ResearchMemory.is_duplicate_proposal(title) is False

        # Record and check document read
        ResearchMemory.record_read(title)
        assert ResearchMemory.is_duplicate_document(title) is True

        # Record and check proposal created
        ResearchMemory.record_proposed(title)
        assert ResearchMemory.is_duplicate_proposal(title) is True

        # Check case insensitivity
        assert ResearchMemory.is_duplicate_document("novel caching strategies") is True
        assert ResearchMemory.is_duplicate_proposal("NOVEL CACHING STRATEGIES") is True


# ---------------------------------------------------------------------------
# 3. Proposal Value Score (PVS) Filtering Tests
# ---------------------------------------------------------------------------

class TestProposalValueScore:
    def test_pvs_calculation_and_filtering(self):
        # Set Source trust to VERIFIED (reputation 1.0)
        SourceTrustEngine.get_source_reputation("SourceHigh", "peer_reviewed")

        # Create proposal with high expected gain (PVS = 3.5 * 0.85 * 1.0 / 1.0 = 2.975 >= 1.0) -> PENDING
        prop1 = ProposalEngine.create_proposal(
            title="Consolidation High PVS",
            problem="Bottleneck A",
            evidence="Evidence",
            proposal="Apply adjustments",
            expected_gain=3.5,
            complexity=1,
            confidence=85,
            source_name="SourceHigh"
        )
        assert prop1["status"] == ProposalStatus.PENDING.value
        assert prop1["pvs"] == 2.975

        # Create proposal with low expected gain (PVS = 0.5 * 0.80 * 1.0 / 1.0 = 0.40 < 1.0) -> Filtered/REJECTED
        prop2 = ProposalEngine.create_proposal(
            title="Consolidation Low PVS",
            problem="Bottleneck B",
            evidence="Evidence",
            proposal="Apply minimal adjustments",
            expected_gain=0.5,
            complexity=1,
            confidence=80,
            source_name="SourceHigh"
        )
        assert prop2["status"] == ProposalStatus.REJECTED.value
        assert "Proposal Value Score" in prop2["reasons"][0]


# ---------------------------------------------------------------------------
# 4. Multi-Source Consensus Verification Tests
# ---------------------------------------------------------------------------

class TestMultiSourceConsensus:
    def test_consensus_score_blocking_low_consensus(self):
        # Setup two low reputation sources (each blog -> 0.3)
        SourceTrustEngine.get_source_reputation("SourceX", "blog")
        SourceTrustEngine.get_source_reputation("SourceY", "blog")

        # Combine two blogs consensus = 1 - 0.7 * 0.7 = 0.51 >= 0.50 (passes consensus)
        # Single blog consensus = 0.3 < 0.50 (fails consensus)
        
        # Test case: single source fail
        custom = [
            {"source": "SourceX", "title": "Orphan Embeddings Optimization", "content": "Sweep orphan embeddings.", "source_type": "blog"}
        ]
        run_record = ResearchScheduler.trigger_run(custom_sources=custom)
        assert run_record["documents_read"] == 1
        assert run_record["proposals_created"] == 0  # blocked by consensus!
        assert run_record["proposals_rejected"] == 1

        # Test case: multi-source success (two sources claim the same title area)
        # We use a substring title match so both get read and group under consensus
        custom_multi = [
            {"source": "SourceX", "title": "Memory Compression sweeps", "content": "Sweep memory.", "source_type": "blog"},
            {"source": "SourceY", "title": "Memory Compression sweeps version 2", "content": "Sweep memory.", "source_type": "blog"}
        ]
        
        # Override fallback ideas' benefit to verify consensus works.
        with patch("backend.core.idea_extractor.IdeaExtractor.extract_ideas", return_value=[{
            "title": "Memory Compression sweeps",
            "problem": "Bottleneck",
            "proposed_solution": "Fix",
            "expected_benefit": 4.5,
            "evidence": ["Ev"]
        }]):
            # Let's clear read memory first so it reads them
            ResearchMemory.save_memory({
                "already_read": [],
                "already_summarized": [],
                "already_proposed": [],
                "already_rejected": []
            })
            run_record_multi2 = ResearchScheduler.trigger_run(custom_sources=custom_multi)
            assert run_record_multi2["proposals_created"] >= 1
