"""Integration and unit tests for Program 5A: Evidence & Provenance Engine.
"""
from __future__ import annotations

import os
import tempfile
import time
from unittest.mock import MagicMock, patch

import pytest

from backend.core.knowledge_graph import KnowledgeGraph, EntityType, RelationType
from backend.core.provenance.coordinator import ProvenanceCoordinator
from backend.core.provenance.models import ProvenanceEvidenceItem, Source, VerificationState
from backend.core.trust_evidence import EvidenceLevel


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def provenance_test_env():
    """Provides an isolated database-backed ProvenanceCoordinator."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = tmp.name

    prov = ProvenanceCoordinator.reset_instance(db_path=db_path)

    yield prov

    # Clean up test database
    if os.path.exists(db_path):
        try:
            os.remove(db_path)
        except OSError:
            pass


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_source_registry_registration_and_sync(provenance_test_env):
    """Verifies that sources can be registered, retrieved, and synced with SourceTrustEngine."""
    prov = provenance_test_env

    # 1. Register a web source
    src = prov.sources.register_source(
        source_id="src_arx_01",
        name="arXiv Preprint Server",
        source_type="preprint",
        base_reputation=0.7,
        metadata={"domain": "AI/ML"},
    )
    assert src.source_id == "src_arx_01"
    assert src.name == "arXiv Preprint Server"
    assert src.source_type == "preprint"
    assert src.base_reputation == 0.7
    assert src.current_reputation == 0.6  # Default fallback score for preprints in SourceTrustEngine
    assert src.trust_level == "MEDIUM"

    # 2. Get registered source
    retrieved = prov.sources.get_source("src_arx_01")
    assert retrieved is not None
    assert retrieved.name == "arXiv Preprint Server"

    # 3. Simulate outcome that boosts reputation in SourceTrustEngine
    prov.sources.update_reputation("arXiv Preprint Server", "DEPLOYED_SUCCESSFUL")

    # 4. Sync source and check that local reputation is updated
    synced = prov.sources.get_source("src_arx_01")
    assert synced.current_reputation > 0.6
    assert synced.trust_level in ("MEDIUM", "HIGH", "VERIFIED")


def test_evidence_persistence_and_retrieval(provenance_test_env):
    """Tests creating and persisting EvidenceItems to the ProvenanceStore."""
    prov = provenance_test_env

    # Register a source
    prov.sources.register_source("src_user", "User Feedback", "user", 0.5)

    # Save evidence
    ev = ProvenanceEvidenceItem.create(
        source_id="src_user",
        evidence_level=EvidenceLevel.OPINION,
        confidence=0.8,
        verification_state=VerificationState.UNVERIFIED,
        context_citation="msg_10928_chat",
        supports=True,
        metadata={"session": "sess_01"},
    )
    prov.store.save_evidence(ev)

    # Retrieve and verify fields
    retrieved = prov.store.get_evidence(ev.evidence_id)
    assert retrieved is not None
    assert retrieved.evidence_id == ev.evidence_id
    assert retrieved.source_id == "src_user"
    assert retrieved.confidence == 0.8
    assert retrieved.evidence_level == EvidenceLevel.OPINION
    assert retrieved.verification_state == VerificationState.UNVERIFIED
    assert retrieved.context_citation == "msg_10928_chat"
    assert retrieved.supports is True
    assert retrieved.metadata == {"session": "sess_01"}


def test_provenance_kg_integration(provenance_test_env):
    """Tests writing nodes and edges with attached evidence to the KG and linking them back."""
    prov = provenance_test_env

    # Setup source and evidence
    prov.sources.register_source("src_tester", "Unit Tester", "tool", 0.9)
    evidence = ProvenanceEvidenceItem.create(
        source_id="src_tester",
        evidence_level=EvidenceLevel.TEST_RESULT,
        confidence=1.0,
        verification_state=VerificationState.CORROBORATED,
        context_citation="tests/test_provenance.py",
        supports=True,
    )

    # Add a subject node
    node = prov.kg.add_node_with_provenance(
        node_id="test_node_p5a",
        name="Kattappa OS",
        entity_type=EntityType.CONCEPT,
        evidence=evidence,
        properties={"version": "10.0"},
    )
    assert node is not None

    # Retrieve and verify links
    record = prov.kg.get_provenance_record("test_node_p5a")
    assert evidence.evidence_id in record.evidence_ids

    ev_list = prov.kg.get_evidence_for_target("test_node_p5a")
    assert len(ev_list) == 1
    assert ev_list[0].source_id == "src_tester"
    assert ev_list[0].context_citation == "tests/test_provenance.py"


def test_citation_formatting(provenance_test_env):
    """Verifies that CitationEngine formats items and chains correctly."""
    prov = provenance_test_env

    prov.sources.register_source("src_agent", "Executive Agent", "agent", 0.8)
    ev = ProvenanceEvidenceItem.create(
        source_id="src_agent",
        evidence_level=EvidenceLevel.LLM_REASONING,
        confidence=0.85,
        verification_state=VerificationState.CORROBORATED,
        context_citation="ecl_plan_abc",
        supports=True,
    )
    prov.store.save_evidence(ev)
    prov.store.link_target_to_evidence("claim_01", ev.evidence_id)

    formatted = prov.citations.format_evidence_item(ev)
    assert "Executive Agent" in formatted
    assert "LLM_REASONING" in formatted
    assert "supports" in formatted
    assert "conf: 0.85" in formatted
    assert "CORROBORATED" in formatted
    assert "ref: ecl_plan_abc" in formatted

    chain = prov.citations.generate_markdown_citation_chain("claim_01")
    assert "### Provenance Chain for `claim_01`" in chain
    assert "Executive Agent" in chain


def test_mce_graph_integrator_provenance():
    """Verifies that MCE consolidation records provenance back to episodic source rows."""
    from backend.core.mce.semantic_extractor import KnowledgeTriple
    from backend.core.mce.graph_integrator import MCEGraphIntegrator

    # Prepare some simulated triples
    triples = [
        KnowledgeTriple(
            subject="FastAPI",
            relation="USES",
            obj="Uvicorn",
            confidence=0.9,
            source_episode_id="ep_dummy_999",
        )
    ]

    # Initialize / reset isolated test coordinator
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = tmp.name

    prov = ProvenanceCoordinator.reset_instance(db_path=db_path)

    try:
        # Mock actual KG calls so we don't pollute the dev database
        mock_node = MagicMock()
        mock_edge = MagicMock()
        mock_edge.id = "edge_fastapi_uvicorn_uses"
        
        with patch.object(prov.kg, "add_node_with_provenance", return_value=mock_node) as mock_add_node, \
             patch.object(prov.kg, "add_edge_with_provenance", return_value=mock_edge) as mock_add_edge:
            
            MCEGraphIntegrator.integrate(triples)

            # Verify that add_node and add_edge were called with episodic context
            assert mock_add_node.call_count == 2
            assert mock_add_edge.call_count == 1

            # Get the evidence items passed
            node_ev = mock_add_node.call_args_list[0][1]["evidence"]
            edge_ev = mock_add_edge.call_args_list[0][1]["evidence"]

            assert node_ev.source_id == "mce_consolidator"
            assert node_ev.context_citation == "hm_episodes:ep_dummy_999"
            assert edge_ev.source_id == "mce_consolidator"
            assert edge_ev.context_citation == "hm_episodes:ep_dummy_999"

    finally:
        if os.path.exists(db_path):
            os.remove(db_path)
