"""
Step 9.0 — Daily Research Loop Integration Test Suite.
Verifies reading, summarizing, idea extraction, proposal checks, and strict governance rules.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.core.research_reader import ResearchReader
from backend.core.research_summarizer import ResearchSummarizer
from backend.core.idea_extractor import IdeaExtractor
from backend.core.research_scheduler import ResearchScheduler
from backend.core.proposal_engine import ProposalEngine
from backend.core.approval_workflow import ApprovalWorkflow
from backend.core.burn_in_governance import BurnInGovernance
from backend.core.proposal_governance import ProposalStatus


@pytest.fixture(autouse=True)
def clean_research_stores(tmp_path):
    """Fixture to isolate all database and JSON stores during test runs."""
    temp_docs = tmp_path / "research_documents.json"
    temp_summaries = tmp_path / "research_summaries.json"
    temp_ideas = tmp_path / "research_ideas.json"
    temp_history = tmp_path / "research_loop_history.json"
    temp_state = tmp_path / "burn_in_state.json"
    temp_proposals = tmp_path / "proposals.json"
    temp_approvals = tmp_path / "approvals.json"
    temp_reputations = tmp_path / "source_reputation.json"
    temp_memory = tmp_path / "research_memory.json"

    # Write empty initial files
    temp_docs.write_text("[]", encoding="utf-8")
    temp_summaries.write_text("[]", encoding="utf-8")
    temp_ideas.write_text("[]", encoding="utf-8")
    temp_history.write_text("[]", encoding="utf-8")
    temp_state.write_text(json.dumps({"state": "NORMAL", "active_freezes": []}), encoding="utf-8")
    temp_proposals.write_text("[]", encoding="utf-8")
    temp_approvals.write_text("[]", encoding="utf-8")
    temp_reputations.write_text("{}", encoding="utf-8")
    temp_memory.write_text(json.dumps({
        "already_read": [],
        "already_summarized": [],
        "already_proposed": [],
        "already_rejected": []
    }), encoding="utf-8")

    with patch("backend.core.research_reader._documents_path", return_value=temp_docs), \
         patch("backend.core.research_summarizer._summaries_path", return_value=temp_summaries), \
         patch("backend.core.idea_extractor._ideas_path", return_value=temp_ideas), \
         patch("backend.core.research_scheduler._history_path", return_value=temp_history), \
         patch("backend.core.burn_in_governance._state_path", return_value=temp_state), \
         patch("backend.core.proposal_engine._proposals_path", return_value=temp_proposals), \
         patch("backend.core.approval_workflow._approval_store_path", return_value=temp_approvals), \
         patch("backend.core.source_trust_engine._reputation_path", return_value=temp_reputations), \
         patch("backend.core.research_memory._memory_path", return_value=temp_memory):
        yield


# ---------------------------------------------------------------------------
# 1. Source Reading Tests
# ---------------------------------------------------------------------------

class TestResearchReader:
    def test_read_sources_successful(self):
        custom = [
            {"source": "src1", "title": "Paper A", "content": "Desc A", "source_type": "peer_reviewed"},
            {"source": "src2", "title": "Paper B", "content": "Desc B", "source_type": "preprint"},
        ]
        new_docs = ResearchReader.read_sources(custom_sources=custom)
        assert len(new_docs) == 2
        assert new_docs[0]["title"] == "Paper A"
        assert new_docs[0]["trust_level"] == "High"
        assert new_docs[1]["trust_level"] == "Medium"

    def test_read_sources_deduplication(self):
        custom = [{"source": "src1", "title": "Paper A", "content": "Desc A", "source_type": "peer_reviewed"}]
        # First read
        new_docs_1 = ResearchReader.read_sources(custom_sources=custom)
        assert len(new_docs_1) == 1

        # Second read of duplicate should skip
        new_docs_2 = ResearchReader.read_sources(custom_sources=custom)
        assert len(new_docs_2) == 0

        # Different title should read
        custom_diff = [{"source": "src1", "title": "Paper B", "content": "Desc A", "source_type": "peer_reviewed"}]
        new_docs_3 = ResearchReader.read_sources(custom_sources=custom_diff)
        assert len(new_docs_3) == 1


# ---------------------------------------------------------------------------
# 2. Summarization Tests
# ---------------------------------------------------------------------------

class TestResearchSummarizer:
    def test_summarization_heuristics_fallback(self):
        # We test with ask_model patched to raise an exception to verify fallback heuristics
        doc = {
            "id": "doc_123",
            "title": "Consolidation Engine",
            "content": "This paper outlines custom consolidation filters.",
            "trust_level": "High"
        }
        with patch("backend.core.research_summarizer.ask_model", side_effect=RuntimeError("LLM Offline")):
            summary = ResearchSummarizer.summarize_document(doc)
            assert summary["doc_id"] == "doc_123"
            assert "Consolidation Engine" in summary["title"]
            assert len(summary["key_findings"]) > 0
            assert summary["confidence"] == 0.90  # trust level High Maps to 0.90


# ---------------------------------------------------------------------------
# 3. Idea Extraction Tests
# ---------------------------------------------------------------------------

class TestIdeaExtractor:
    def test_idea_extraction_heuristics_fallback(self):
        summary = {
            "id": "sum_123",
            "title": "Optimizing memory structures",
            "summary": "This outlines memory consolidations.",
            "key_findings": ["Consolidate memory pools"],
            "confidence": 0.85
        }
        with patch("backend.core.idea_extractor.ask_model", side_effect=RuntimeError("LLM Offline")):
            ideas = IdeaExtractor.extract_ideas(summary)
            assert len(ideas) == 1
            idea = ideas[0]
            assert idea["summary_id"] == "sum_123"
            assert "memory" in idea["problem"].lower()
            assert "expected_benefit" in idea
            assert len(idea["evidence"]) > 0


# ---------------------------------------------------------------------------
# 4. Proposal Generation & AUDIT Mode Blocking Tests
# ---------------------------------------------------------------------------

class TestProposalGenerationAndAuditMode:
    def test_proposal_created_as_pending(self):
        # NORMAL mode
        custom = [{"source": "src1", "title": "Skepticism Filters", "content": "Skepticism checks prevent failures.", "source_type": "peer_reviewed"}]
        run_record = ResearchScheduler.trigger_run(custom_sources=custom)
        assert run_record["documents_read"] == 1
        assert run_record["proposals_created"] == 1
        assert run_record["proposals_rejected"] == 0

        # Verify created proposal status is pending
        proposals = ProposalEngine.list_proposals()
        assert len(proposals) == 1
        assert proposals[0]["status"] == ProposalStatus.PENDING.value

    def test_proposal_blocked_in_audit_mode(self):
        # Freeze system in AUDIT mode
        BurnInGovernance._save_state("AUDIT", ["Economic failure trigger"])
        assert BurnInGovernance.is_frozen() is True

        custom = [{"source": "src1", "title": "Memory Optimization", "content": "Details.", "source_type": "peer_reviewed"}]
        run_record = ResearchScheduler.trigger_run(custom_sources=custom)
        
        # Verify read, summary and idea extraction succeed, but proposal creation is rejected (blocked)
        assert run_record["documents_read"] == 1
        assert run_record["proposals_created"] == 0
        assert run_record["proposals_rejected"] == 1


# ---------------------------------------------------------------------------
# 5. Governance Hard-Fail Invariant Tests
# ---------------------------------------------------------------------------

class TestResearchLoopGovernance:
    def test_no_auto_approvals_deployments_or_sandbox_runs(self):
        """Governance check: Verify proposal loop doesn't trigger auto-evals/runs."""
        custom = [
            {"source": "src1", "title": "Memory Sweeper", "content": "Sweep memory.", "source_type": "peer_reviewed"},
            {"source": "src2", "title": "Query Consolidation", "content": "Consolidate queries.", "source_type": "preprint"}
        ]
        run_record = ResearchScheduler.trigger_run(custom_sources=custom)
        assert run_record["proposals_created"] == 2

        # 1. Verify no proposals automatically promoted past PENDING
        proposals = ProposalEngine.list_proposals()
        assert len(proposals) == 2
        for prop in proposals:
            assert prop["status"] == ProposalStatus.PENDING.value

        # 2. Verify no active approval workflow requests are automatically approved or deployed
        workflow_requests = ApprovalWorkflow.list_all()
        # They shouldn't even have workflow records yet, as they are just proposal drafts/pending lists,
        # but if any workflow record existed, it must not be approved/testing/deployed.
        for req in workflow_requests:
            assert req["state"] not in {"APPROVED", "TESTING", "DEPLOYED"}


# ---------------------------------------------------------------------------
# 6. REST API Tests
# ---------------------------------------------------------------------------

class TestResearchLoopAPI:
    def test_get_status_api(self):
        client = TestClient(app)
        resp = client.get("/dashboard/research-loop/status")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"
        data = resp.json()["data"]
        assert "documents_read_today" in data
        assert "summaries_generated_today" in data
        assert "ideas_extracted_today" in data
        assert "proposals_created_today" in data
        assert "pending_approvals" in data
        assert "last_run_time" in data

    def test_post_trigger_api(self):
        client = TestClient(app)
        # Verify trigger endpoint runs pipeline synchronously and returns stats
        resp = client.post("/dashboard/research-loop/trigger")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"
        data = resp.json()["data"]
        assert data["documents_read"] > 0
        assert data["summaries_generated"] > 0
