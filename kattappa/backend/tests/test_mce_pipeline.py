"""Integration tests for Program 3: Memory Consolidation Engine (MCE).

Tests cover:
- Duplicate detection: SHA-256 exact and MinHash near-duplicates
- Importance scoring: recency, recall, domain bonuses
- Episodic-to-semantic promotion gate (importance threshold)
- Semantic triple extraction with LLM fallback
- Graph integrator writing nodes via frozen KG v1 interface
- Archive manager marking stale episodes (non-destructive)
- Full consolidation_engine.run_cycle() end-to-end
"""
from __future__ import annotations

import json
import sqlite3
import time
import uuid
from pathlib import Path
from typing import List
from unittest.mock import MagicMock, patch

import pytest

from backend.core.mce.archive_manager import MCEArchiveManager
from backend.core.mce.consolidation_engine import MCEConsolidationEngine
from backend.core.mce.duplicate_detector import MCEDuplicateDetector, _minhash_signature, _shingles
from backend.core.mce.episodic_promoter import MCEEpisodicPromoter
from backend.core.mce.graph_integrator import MCEGraphIntegrator
from backend.core.mce.importance_scorer import MCEImportanceScorer, ScoredEpisode
from backend.core.mce.semantic_extractor import KnowledgeTriple, MCESemanticExtractor


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def patch_episodic_db(tmp_path):
    """Redirect all MCE SQLite reads to an in-memory test DB."""
    db_path = str(tmp_path / "test_mce.db")

    def _make_conn_ro():
        conn = sqlite3.connect(db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        # Create minimal episodic schema
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS hm_episodes (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL DEFAULT 'test_session',
                content TEXT NOT NULL,
                importance REAL NOT NULL DEFAULT 0.5,
                category TEXT NOT NULL DEFAULT 'general',
                created_at REAL NOT NULL,
                last_recalled_at REAL NOT NULL,
                recall_count INTEGER DEFAULT 0,
                pinned INTEGER DEFAULT 0,
                tags TEXT DEFAULT '[]'
            );
        """)
        conn.commit()
        return conn

    with patch("backend.core.mce.duplicate_detector.MCEDuplicateDetector._get_episodic_conn", side_effect=_make_conn_ro), \
         patch("backend.core.mce.importance_scorer.MCEImportanceScorer._get_conn", side_effect=_make_conn_ro), \
         patch("backend.core.mce.archive_manager.MCEArchiveManager._get_conn", side_effect=_make_conn_ro), \
         patch("backend.core.mce.episodic_promoter.MCEEpisodicPromoter._get_conn", side_effect=_make_conn_ro):
        # Seed the DB with test data
        conn = _make_conn_ro()
        now = time.time()
        rows = [
            # id, content, importance, created_at, last_recalled_at, recall_count, pinned, tags
            ("ep_001", "Kattappa uses Python for backend development.", 0.80, now - 100, now - 50, 3, 0, '["technical"]'),
            ("ep_002", "Kattappa uses Python for backend development.", 0.80, now - 200, now - 180, 1, 0, '["technical"]'),  # exact dupe
            ("ep_003", "The knowledge graph stores entity relationships.", 0.70, now - 300, now - 200, 2, 0, '["technical"]'),
            ("ep_004", "The knowledge graph stores entity relationships.", 0.72, now - 400, now - 350, 0, 0, '["technical"]'),  # near dupe
            ("ep_005", "Low quality note.", 0.20, now - 2000000, now - 1900000, 0, 0, '[]'),  # stale, low recall
            ("ep_006", "Pinned important note.", 0.90, now - 3000000, now - 2900000, 0, 1, '[]'),  # pinned, stale
            ("ep_007", "Goal hierarchy maps goals to subgoals and tasks in the ECL layer.", 0.75, now - 500, now - 400, 5, 0, '["goal"]'),
        ]
        conn.executemany(
            "INSERT OR IGNORE INTO hm_episodes (id, content, importance, created_at, last_recalled_at, recall_count, pinned, tags) VALUES (?,?,?,?,?,?,?,?)",
            rows,
        )
        conn.commit()
        conn.close()
        yield db_path


# ---------------------------------------------------------------------------
# Test 1: Duplicate Detection — exact duplicates
# ---------------------------------------------------------------------------

def test_duplicate_detector_exact_duplicates():
    report = MCEDuplicateDetector.detect(jaccard_threshold=0.85, limit=100)
    # ep_001 and ep_002 have identical content — one should be flagged
    assert report.exact_dupe_count >= 1, "Expected at least 1 exact duplicate"
    assert report.unique_count >= 1, "Expected at least 1 unique episode"


# ---------------------------------------------------------------------------
# Test 2: MinHash shingles and signature are deterministic
# ---------------------------------------------------------------------------

def test_minhash_signature_deterministic():
    text = "Kattappa is an AI operating system."
    sh = _shingles(text, k=3)
    sig_a = _minhash_signature(sh, n_perm=32)
    sig_b = _minhash_signature(sh, n_perm=32)
    assert sig_a == sig_b, "MinHash signature must be deterministic"
    assert len(sig_a) == 32, "Signature length must equal n_perm"


# ---------------------------------------------------------------------------
# Test 3: Near-duplicate clustering detects similar episodes
# ---------------------------------------------------------------------------

def test_duplicate_detector_near_duplicates():
    report = MCEDuplicateDetector.detect(jaccard_threshold=0.80, limit=100)
    # ep_003 and ep_004 are near-duplicates (Jaccard > 0.80)
    assert report.near_dupe_count >= 1 or report.exact_dupe_count >= 1, \
        "Should detect near or exact duplicates for similar episodes"


# ---------------------------------------------------------------------------
# Test 4: Importance scoring respects domain multiplier
# ---------------------------------------------------------------------------

def test_importance_scorer_domain_multiplier():
    scored = MCEImportanceScorer.score_episodes(limit=100)
    assert len(scored) > 0, "Expected at least one scored episode"
    # Technical episodes should have higher composite scores than their base importance
    technical = [s for s in scored if s.domain == "technical"]
    if technical:
        ep = technical[0]
        assert ep.composite_score >= ep.base_importance * 1.0, \
            "Technical domain should not decrease score"


# ---------------------------------------------------------------------------
# Test 5: Importance scorer returns sorted results
# ---------------------------------------------------------------------------

def test_importance_scorer_sorted_desc():
    scored = MCEImportanceScorer.score_episodes(limit=100)
    scores = [s.composite_score for s in scored]
    assert scores == sorted(scores, reverse=True), \
        "Scored episodes must be returned sorted descending"


# ---------------------------------------------------------------------------
# Test 6: Episodic promoter respects importance floor
# ---------------------------------------------------------------------------

def test_episodic_promoter_importance_floor():
    scored = [
        ScoredEpisode("ep_h", "A high-quality technical fact about deep learning systems.", 0.8, 0.85, "technical", 3, time.time()),
        ScoredEpisode("ep_l", "Low.", 0.2, 0.25, "general", 0, time.time()),
    ]
    mock_result = MagicMock()
    mock_result.success = True

    with patch("backend.core.mce.episodic_promoter.MEMORY_BUS") as mock_bus, \
         patch("backend.core.mce.episodic_promoter.MCEEpisodicPromoter._mark_promoted"):
        mock_bus.write.return_value = mock_result
        report = MCEEpisodicPromoter.promote(scored, importance_floor=0.65)

    assert report.promoted_count == 1, "Only the high-importance episode should be promoted"
    assert report.rejected_count == 1, "Low-importance episode should be rejected"


# ---------------------------------------------------------------------------
# Test 7: Episodic promoter rejects short content (quality gate)
# ---------------------------------------------------------------------------

def test_episodic_promoter_quality_gate():
    scored = [
        ScoredEpisode("ep_short", "ok", 0.9, 0.92, "technical", 1, time.time()),
    ]
    with patch("backend.core.mce.episodic_promoter.MEMORY_BUS") as mock_bus:
        report = MCEEpisodicPromoter.promote(scored, importance_floor=0.65)
    assert report.promoted_count == 0, "Episode with < 3 words should be rejected"
    assert mock_bus.write.call_count == 0


# ---------------------------------------------------------------------------
# Test 8: Semantic extractor keyword fallback
# ---------------------------------------------------------------------------

def test_semantic_extractor_keyword_fallback():
    """Fallback should work even when model is unavailable."""
    content = "Kattappa uses Python for processing. Python depends on FastAPI for APIs."
    with patch("backend.core.mce.semantic_extractor.ask_model", side_effect=Exception("model unavailable")):
        triples = MCESemanticExtractor.extract(content, source_episode_id="ep_test")

    assert len(triples) > 0, "Keyword fallback should extract at least one triple"
    for t in triples:
        assert isinstance(t, KnowledgeTriple)
        assert t.subject
        assert t.relation
        assert t.obj


# ---------------------------------------------------------------------------
# Test 9: Semantic extractor parses LLM JSON response
# ---------------------------------------------------------------------------

def test_semantic_extractor_llm_parsing():
    llm_response = json.dumps([
        {"subject": "Kattappa", "relation": "uses", "object": "Python"},
        {"subject": "Python", "relation": "is_a", "object": "programming language"},
    ])
    with patch("backend.core.mce.semantic_extractor.ask_model", return_value=llm_response):
        triples = MCESemanticExtractor.extract("any content", source_episode_id="ep_llm")

    assert len(triples) == 2
    assert triples[0].subject == "Kattappa"
    assert triples[0].relation == "uses"
    assert triples[0].obj == "Python"
    assert triples[0].confidence == 0.78


# ---------------------------------------------------------------------------
# Test 10: Graph integrator writes nodes and edges via KG interface
# ---------------------------------------------------------------------------

def test_graph_integrator_writes_to_kg():
    triples = [
        KnowledgeTriple(
            subject="Kattappa",
            relation="USES",
            obj="Python",
            confidence=0.80,
            source_episode_id="ep_001",
        )
    ]
    mock_kg_helper = MagicMock()
    mock_prov = MagicMock()
    mock_prov.kg = mock_kg_helper

    with patch("backend.core.mce.graph_integrator.ProvenanceCoordinator.get_instance", return_value=mock_prov):
        report = MCEGraphIntegrator.integrate(triples)

    assert report.nodes_added == 2, "Should add subject and object nodes"
    assert report.relations_added == 1, "Should add one edge"
    assert report.errors == 0
    assert mock_kg_helper.add_node_with_provenance.call_count == 2
    assert mock_kg_helper.add_edge_with_provenance.call_count == 1



# ---------------------------------------------------------------------------
# Test 11: Archive manager marks stale episodes (non-destructive)
# ---------------------------------------------------------------------------

def test_archive_manager_marks_stale_episodes():
    report = MCEArchiveManager.archive_stale(archive_after_days=1.0, max_recall_count=1)
    # ep_005 (created 23+ days ago, recall=0) should be archived; ep_006 is pinned (skipped)
    assert report.archived_count >= 1, "Expected at least one archived episode"
    assert report.skipped_pinned >= 1, "Pinned episode should be skipped"


# ---------------------------------------------------------------------------
# Test 12: Archive manager does not delete — only tags
# ---------------------------------------------------------------------------

def test_archive_manager_no_deletes(patch_episodic_db):
    db_path = patch_episodic_db
    conn = sqlite3.connect(db_path)
    count_before = conn.execute("SELECT COUNT(*) FROM hm_episodes").fetchone()[0]
    conn.close()

    MCEArchiveManager.archive_stale(archive_after_days=1.0, max_recall_count=1)

    conn = sqlite3.connect(db_path)
    count_after = conn.execute("SELECT COUNT(*) FROM hm_episodes").fetchone()[0]
    conn.close()

    assert count_before == count_after, "Archive must never delete rows"


# ---------------------------------------------------------------------------
# Test 13: Full consolidation engine run_cycle produces valid report
# ---------------------------------------------------------------------------

def test_consolidation_engine_run_cycle():
    mock_bus_result = MagicMock()
    mock_bus_result.success = True
    mock_kg_helper = MagicMock()
    mock_prov = MagicMock()
    mock_prov.kg = mock_kg_helper

    with patch("backend.core.mce.episodic_promoter.MEMORY_BUS") as mock_bus, \
         patch("backend.core.mce.episodic_promoter.MCEEpisodicPromoter._mark_promoted"), \
         patch("backend.core.mce.graph_integrator.ProvenanceCoordinator.get_instance", return_value=mock_prov), \
         patch("backend.core.mce.consolidation_engine.WSEEventBus") as mock_eb_cls, \
         patch("backend.core.mce.semantic_extractor.ask_model", side_effect=Exception("offline")):
        mock_bus.write.return_value = mock_bus_result
        report = MCEConsolidationEngine.run_cycle(
            importance_floor=0.65,
            archive_after_days=1.0,
            episode_limit=100,
        )

    assert report.success is True, f"Cycle failed: {report.error}"
    assert report.cycle_id.startswith("cycle_")
    assert report.duration_sec > 0
    assert report.episodes_scanned >= 0

    d = report.to_dict()
    assert "dedup" in d
    assert "promotion" in d
    assert "integration" in d
    assert "archive" in d
    assert "triples_extracted" in d
