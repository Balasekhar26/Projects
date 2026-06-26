"""
Tests for Step 24 — Research Engine
=====================================

Network calls are fully mocked — no internet required.

Covers:
  Schema
    - ResearchQuery / ResearchFinding / ResearchReport to_dict / from_dict
  ResearchStore
    - save, get_by_domain, get_by_topic, count, persistence
  ResearchSynthesizer
    - Filters LOW quality when MEDIUM/HIGH available
    - Deduplicates near-identical excerpts
    - Generates non-empty summary and key_facts
    - Custom summarizer and fact_extractor hooks
    - Confidence is in [0,1]
  Source Adapters
    - WikipediaAdapter: mocked urllib, returns correct FindingQuality
    - ArxivAdapter: mocked urllib, parses Atom XML, returns findings
    - LocalCorpusAdapter: uses tmp JSONL file, keyword match
  ResearchEngine (integration, fully mocked)
    - research() returns ResearchReport
    - Promotes key facts to memory (store_fact called)
    - Logs research episode to memory (store_episode called)
    - Calls ReflectionEngine.reflect() when attached
    - Calls LearningEngine.learn_from() when attached
    - Parallel source fetch: one failing source doesn't abort session
    - Empty results from all sources still produces a valid report
"""

import json
import os
import pytest
from unittest.mock import MagicMock, patch, call
from io import BytesIO

from kattappa_runtime.research.schema import (
    ResearchQuery, ResearchFinding, ResearchReport,
    SourceType, FindingQuality
)
from kattappa_runtime.research.store       import ResearchStore
from kattappa_runtime.research.synthesizer import ResearchSynthesizer, _jaccard, _first_sentence
from kattappa_runtime.research.sources.wikipedia    import WikipediaAdapter
from kattappa_runtime.research.sources.arxiv        import ArxivAdapter
from kattappa_runtime.research.sources.local_corpus import LocalCorpusAdapter
from kattappa_runtime.research.engine      import ResearchEngine


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture
def mock_memory():
    mem = MagicMock()
    mem.writer = MagicMock()
    mem.writer.store_fact    = MagicMock()
    mem.writer.store_episode = MagicMock()
    return mem


@pytest.fixture
def mock_reflection_engine():
    eng = MagicMock()
    from kattappa_runtime.reflection.schema import Reflection, OutcomeLabel
    eng.reflect.return_value = Reflection(
        domain="test", outcome=OutcomeLabel.SUCCESS,
        lesson="test lesson", confidence_delta=0.05,
    )
    return eng


@pytest.fixture
def mock_learning_engine():
    from kattappa_runtime.learning.schema import LearningRecord
    eng = MagicMock()
    eng.learn_from.return_value = LearningRecord(domain="test")
    return eng


@pytest.fixture
def tmp_store(tmp_path):
    return ResearchStore(path=str(tmp_path / "reports.jsonl"))


@pytest.fixture
def sample_findings(tmp_store):
    q = ResearchQuery(topic="neural network", domain="ml")
    return [
        ResearchFinding(
            query_id        = q.query_id,
            source          = SourceType.WIKIPEDIA,
            title           = "Neural network",
            url             = "https://en.wikipedia.org/wiki/Neural_network",
            excerpt         = "A neural network is a series of algorithms that recognize patterns.",
            quality         = FindingQuality.HIGH,
            relevance_score = 0.85,
        ),
        ResearchFinding(
            query_id        = q.query_id,
            source          = SourceType.ARXIV,
            title           = "Attention Is All You Need",
            url             = "https://arxiv.org/abs/1706.03762",
            excerpt         = "The Transformer model relies entirely on self-attention mechanisms.",
            quality         = FindingQuality.HIGH,
            relevance_score = 0.90,
        ),
    ]


@pytest.fixture
def research_engine(mock_memory, tmp_store, mock_reflection_engine, mock_learning_engine):
    return ResearchEngine(
        memory            = mock_memory,
        reflection_engine = mock_reflection_engine,
        learning_engine   = mock_learning_engine,
        store             = tmp_store,
        max_workers       = 1,
    )


# ============================================================
# Schema
# ============================================================

class TestResearchSchema:
    def test_query_to_dict(self):
        q = ResearchQuery(topic="test topic", domain="ml")
        d = q.to_dict()
        assert d["topic"] == "test topic"
        assert d["domain"] == "ml"
        assert "wikipedia" in d["sources"]

    def test_finding_roundtrip(self):
        f = ResearchFinding(
            source=SourceType.WIKIPEDIA, title="T", url="U",
            excerpt="E", quality=FindingQuality.HIGH, relevance_score=0.8
        )
        d = f.to_dict()
        f2 = ResearchFinding.from_dict(d)
        assert f2.source == SourceType.WIKIPEDIA
        assert f2.quality == FindingQuality.HIGH
        assert f2.relevance_score == pytest.approx(0.8)

    def test_report_roundtrip(self, sample_findings):
        q = ResearchQuery(topic="neural network", domain="ml")
        r = ResearchReport(
            query_id  = q.query_id,
            topic     = "neural network",
            domain    = "ml",
            summary   = "Test summary.",
            key_facts = ["fact1", "fact2"],
            findings  = sample_findings,
            confidence= 0.75,
        )
        d = r.to_dict()
        r2 = ResearchReport.from_dict(d)
        assert r2.topic == "neural network"
        assert len(r2.findings) == 2
        assert r2.findings[0].source == SourceType.WIKIPEDIA

    def test_report_from_dict_empty_findings(self):
        r = ResearchReport(topic="t", domain="d", summary="s")
        d = r.to_dict()
        r2 = ResearchReport.from_dict(d)
        assert r2.findings == []


# ============================================================
# ResearchStore
# ============================================================

class TestResearchStore:
    def test_save_and_count(self, tmp_store, sample_findings):
        r = ResearchReport(topic="t", domain="ml", findings=sample_findings)
        tmp_store.save(r)
        assert tmp_store.count() == 1

    def test_get_by_domain(self, tmp_store):
        tmp_store.save(ResearchReport(topic="a", domain="ml"))
        tmp_store.save(ResearchReport(topic="b", domain="code"))
        results = tmp_store.get_by_domain("ml")
        assert len(results) == 1
        assert results[0].topic == "a"

    def test_get_by_topic_substring(self, tmp_store):
        tmp_store.save(ResearchReport(topic="neural networks and attention", domain="ml"))
        tmp_store.save(ResearchReport(topic="quantum computing", domain="physics"))
        results = tmp_store.get_by_topic("neural")
        assert len(results) == 1

    def test_persistence_across_instances(self, tmp_path, sample_findings):
        path = str(tmp_path / "r.jsonl")
        s1 = ResearchStore(path=path)
        s1.save(ResearchReport(topic="t", domain="d", findings=sample_findings))

        s2 = ResearchStore(path=path)
        assert s2.count() == 1
        rpts = s2.get_all()
        assert len(rpts[0].findings) == 2

    def test_get_by_id(self, tmp_store):
        r = ResearchReport(topic="t", domain="d")
        tmp_store.save(r)
        found = tmp_store.get_by_id(r.report_id)
        assert found is not None
        assert found.report_id == r.report_id


# ============================================================
# ResearchSynthesizer
# ============================================================

class TestResearchSynthesizer:
    def test_empty_findings_returns_no_info_summary(self):
        synth = ResearchSynthesizer()
        q = ResearchQuery(topic="black holes", domain="physics")
        report = synth.synthesize(q, [])
        assert "No relevant" in report.summary
        assert report.confidence == 0.0
        assert report.key_facts == []

    def test_normal_synthesis_produces_facts(self, sample_findings):
        synth = ResearchSynthesizer()
        q = ResearchQuery(topic="neural network", domain="ml")
        report = synth.synthesize(q, sample_findings)
        assert len(report.key_facts) >= 1
        assert report.confidence > 0.0
        assert len(report.summary) > 5

    def test_low_quality_filtered_when_high_exists(self):
        synth = ResearchSynthesizer()
        q = ResearchQuery(topic="t", domain="d")
        findings = [
            ResearchFinding(query_id=q.query_id, source=SourceType.WIKIPEDIA,
                            excerpt="High quality result.", quality=FindingQuality.HIGH,
                            relevance_score=0.9),
            ResearchFinding(query_id=q.query_id, source=SourceType.LOCAL,
                            excerpt="Low quality noise.", quality=FindingQuality.LOW,
                            relevance_score=0.1),
        ]
        report = synth.synthesize(q, findings)
        assert all(f.quality != FindingQuality.LOW for f in report.findings)

    def test_deduplication_removes_near_identical(self):
        synth = ResearchSynthesizer()
        q = ResearchQuery(topic="t", domain="d")
        same_text = "The quick brown fox jumps over the lazy dog. " * 10
        findings = [
            ResearchFinding(query_id=q.query_id, source=SourceType.WIKIPEDIA,
                            excerpt=same_text, quality=FindingQuality.HIGH,
                            relevance_score=0.8),
            ResearchFinding(query_id=q.query_id, source=SourceType.ARXIV,
                            excerpt=same_text, quality=FindingQuality.HIGH,
                            relevance_score=0.7),
        ]
        report = synth.synthesize(q, findings)
        assert len(report.findings) == 1

    def test_custom_summarizer_hook(self, sample_findings):
        def my_summary(findings, topic):
            return "Custom summary!"

        synth = ResearchSynthesizer(summarizer=my_summary)
        q = ResearchQuery(topic="neural network", domain="ml")
        report = synth.synthesize(q, sample_findings)
        assert report.summary == "Custom summary!"

    def test_custom_summarizer_fallback_on_error(self, sample_findings):
        def bad_summary(findings, topic):
            raise RuntimeError("LLM down")

        synth = ResearchSynthesizer(summarizer=bad_summary)
        q = ResearchQuery(topic="neural network", domain="ml")
        report = synth.synthesize(q, sample_findings)
        assert len(report.summary) > 5  # fell back to rule-based

    def test_custom_fact_extractor(self, sample_findings):
        def my_extractor(f):
            return f"Custom fact from {f.source.value}"

        synth = ResearchSynthesizer(fact_extractor=my_extractor)
        q = ResearchQuery(topic="neural network", domain="ml")
        report = synth.synthesize(q, sample_findings)
        assert all("Custom fact" in f for f in report.key_facts)

    def test_confidence_in_range(self, sample_findings):
        synth = ResearchSynthesizer()
        q = ResearchQuery(topic="neural network", domain="ml")
        report = synth.synthesize(q, sample_findings)
        assert 0.0 <= report.confidence <= 1.0


class TestSynthesizerUtils:
    def test_jaccard_identical(self):
        s = {"a", "b", "c"}
        assert _jaccard(s, s) == pytest.approx(1.0)

    def test_jaccard_disjoint(self):
        assert _jaccard({"a"}, {"b"}) == pytest.approx(0.0)

    def test_jaccard_partial(self):
        assert _jaccard({"a", "b"}, {"b", "c"}) == pytest.approx(1/3)

    def test_first_sentence_period(self):
        s = _first_sentence("Hello world. This is second.")
        assert s == "Hello world."

    def test_first_sentence_no_period(self):
        s = _first_sentence("No ending here")
        assert len(s) <= 150


# ============================================================
# Wikipedia Adapter (mocked)
# ============================================================

WIKI_SEARCH_RESPONSE = json.dumps(
    ["neural network", ["Neural network", "Artificial neural network"], [], []]
).encode()

WIKI_SUMMARY_RESPONSE = json.dumps({
    "title":   "Neural network",
    "extract": "A neural network is a method in AI that teaches computers to process data. " * 20,
    "content_urls": {"desktop": {"page": "https://en.wikipedia.org/wiki/Neural_network"}},
}).encode()


class TestWikipediaAdapter:
    def test_returns_findings_on_success(self):
        adapter = WikipediaAdapter()
        q = ResearchQuery(topic="neural network", domain="ml", max_findings=2)

        call_count = [0]
        def mock_urlopen(req, timeout=None):
            call_count[0] += 1
            resp = MagicMock()
            if call_count[0] == 1:
                resp.read.return_value = WIKI_SEARCH_RESPONSE
            else:
                resp.read.return_value = WIKI_SUMMARY_RESPONSE
            resp.__enter__ = lambda s: s
            resp.__exit__  = MagicMock(return_value=False)
            return resp

        with patch("urllib.request.urlopen", side_effect=mock_urlopen):
            findings = adapter.fetch(q)

        assert len(findings) >= 1
        assert findings[0].source == SourceType.WIKIPEDIA
        assert findings[0].quality == FindingQuality.HIGH
        assert len(findings[0].excerpt) > 10

    def test_returns_empty_on_network_error(self):
        adapter = WikipediaAdapter()
        q = ResearchQuery(topic="anything", domain="x")
        with patch("urllib.request.urlopen", side_effect=OSError("no network")):
            findings = adapter.fetch(q)
        assert findings == []

    def test_returns_empty_for_blank_topic(self):
        adapter = WikipediaAdapter()
        q = ResearchQuery(topic="", domain="x")
        findings = adapter.fetch(q)
        assert findings == []


# ============================================================
# Arxiv Adapter (mocked)
# ============================================================

ARXIV_ATOM_RESPONSE = b"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/abs/1706.03762v5</id>
    <title>Attention Is All You Need</title>
    <summary>We propose a new simple network architecture, the Transformer, based solely on attention mechanisms. The dominant sequence transduction models are based on complex recurrent or convolutional neural networks.</summary>
  </entry>
  <entry>
    <id>http://arxiv.org/abs/1810.04805v2</id>
    <title>BERT: Pre-training of Deep Bidirectional Transformers</title>
    <summary>We introduce BERT, which stands for Bidirectional Encoder Representations from Transformers. Unlike recent language representation models, BERT is designed to pre-train deep bidirectional representations from unlabeled text.</summary>
  </entry>
</feed>"""


class TestArxivAdapter:
    def test_returns_findings_on_success(self):
        adapter = ArxivAdapter()
        q = ResearchQuery(topic="attention transformer", domain="ml", max_findings=2)

        mock_resp = MagicMock()
        mock_resp.read.return_value = ARXIV_ATOM_RESPONSE
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__  = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_resp):
            findings = adapter.fetch(q)

        assert len(findings) == 2
        assert findings[0].source == SourceType.ARXIV
        assert "Attention" in findings[0].title
        assert len(findings[0].excerpt) > 10

    def test_returns_empty_on_network_error(self):
        adapter = ArxivAdapter()
        q = ResearchQuery(topic="transformer", domain="ml")
        with patch("urllib.request.urlopen", side_effect=OSError("timeout")):
            findings = adapter.fetch(q)
        assert findings == []

    def test_empty_topic_returns_empty(self):
        adapter = ArxivAdapter()
        q = ResearchQuery(topic="", domain="ml")
        findings = adapter.fetch(q)
        assert findings == []


# ============================================================
# Local Corpus Adapter
# ============================================================

class TestLocalCorpusAdapter:
    def test_returns_matching_findings(self, tmp_path):
        corpus_dir = tmp_path / "corpus"
        corpus_dir.mkdir()

        # Write a JSONL corpus file with matching content
        with open(corpus_dir / "philosophy.jsonl", "w") as f:
            f.write(json.dumps({
                "text": "The Bhagavad Gita teaches us about dharma and duty in times of conflict. Arjuna faces a moral dilemma and Krishna provides guidance.",
                "source": "bhagavad_gita"
            }) + "\n")
            f.write(json.dumps({
                "text": "Quantum mechanics describes the behavior of particles at subatomic scales.",
                "source": "physics"
            }) + "\n")

        adapter = LocalCorpusAdapter(corpus_dir=str(corpus_dir))
        q = ResearchQuery(topic="dharma duty", domain="philosophy", max_findings=3)
        findings = adapter.fetch(q)

        assert len(findings) >= 1
        assert findings[0].source == SourceType.LOCAL
        assert "dharma" in findings[0].excerpt.lower() or "duty" in findings[0].excerpt.lower()

    def test_returns_empty_for_no_match(self, tmp_path):
        corpus_dir = tmp_path / "corpus"
        corpus_dir.mkdir()
        with open(corpus_dir / "c.jsonl", "w") as f:
            f.write(json.dumps({"text": "The weather is nice today.", "source": "x"}) + "\n")

        adapter = LocalCorpusAdapter(corpus_dir=str(corpus_dir))
        q = ResearchQuery(topic="quantum entanglement superposition", domain="physics")
        findings = adapter.fetch(q)
        assert findings == []

    def test_returns_empty_for_missing_corpus_dir(self, tmp_path):
        adapter = LocalCorpusAdapter(corpus_dir=str(tmp_path / "nonexistent"))
        q = ResearchQuery(topic="anything", domain="x")
        findings = adapter.fetch(q)
        assert findings == []


# ============================================================
# ResearchEngine — Integration (fully mocked sources)
# ============================================================

class TestResearchEngineIntegration:
    def _make_engine(self, mock_memory, tmp_store,
                     mock_reflection_engine, mock_learning_engine,
                     mock_findings):
        """Build engine with all sources mocked to return mock_findings."""
        eng = ResearchEngine(
            memory            = mock_memory,
            reflection_engine = mock_reflection_engine,
            learning_engine   = mock_learning_engine,
            store             = tmp_store,
            max_workers       = 1,
        )
        # Patch the internal _fetch_all to return controlled findings
        eng._fetch_all = lambda q: mock_findings
        return eng

    def test_returns_research_report(self, mock_memory, tmp_store,
                                     mock_reflection_engine, mock_learning_engine,
                                     sample_findings):
        eng = self._make_engine(mock_memory, tmp_store, mock_reflection_engine,
                                mock_learning_engine, sample_findings)
        report = eng.research("neural network", domain="ml")
        assert isinstance(report, ResearchReport)
        assert report.topic == "neural network"

    def test_key_facts_promoted_to_memory(self, mock_memory, tmp_store,
                                          mock_reflection_engine, mock_learning_engine,
                                          sample_findings):
        eng = self._make_engine(mock_memory, tmp_store, mock_reflection_engine,
                                mock_learning_engine, sample_findings)
        eng.research("neural network", domain="ml")
        assert mock_memory.writer.store_fact.call_count >= 1

    def test_episode_logged_to_memory(self, mock_memory, tmp_store,
                                      mock_reflection_engine, mock_learning_engine,
                                      sample_findings):
        eng = self._make_engine(mock_memory, tmp_store, mock_reflection_engine,
                                mock_learning_engine, sample_findings)
        eng.research("neural network", domain="ml")
        mock_memory.writer.store_episode.assert_called_once()

    def test_reflection_engine_called(self, mock_memory, tmp_store,
                                      mock_reflection_engine, mock_learning_engine,
                                      sample_findings):
        eng = self._make_engine(mock_memory, tmp_store, mock_reflection_engine,
                                mock_learning_engine, sample_findings)
        eng.research("neural network", domain="ml")
        mock_reflection_engine.reflect.assert_called_once()

    def test_learning_engine_called(self, mock_memory, tmp_store,
                                    mock_reflection_engine, mock_learning_engine,
                                    sample_findings):
        eng = self._make_engine(mock_memory, tmp_store, mock_reflection_engine,
                                mock_learning_engine, sample_findings)
        eng.research("neural network", domain="ml")
        mock_learning_engine.learn_from.assert_called_once()

    def test_report_persisted_to_store(self, mock_memory, tmp_store,
                                       mock_reflection_engine, mock_learning_engine,
                                       sample_findings):
        eng = self._make_engine(mock_memory, tmp_store, mock_reflection_engine,
                                mock_learning_engine, sample_findings)
        eng.research("neural network", domain="ml")
        assert tmp_store.count() == 1

    def test_empty_findings_still_returns_report(self, mock_memory, tmp_store,
                                                  mock_reflection_engine, mock_learning_engine):
        eng = self._make_engine(mock_memory, tmp_store, mock_reflection_engine,
                                mock_learning_engine, [])
        report = eng.research("obscure topic xyz", domain="unknown")
        assert isinstance(report, ResearchReport)
        assert "No relevant" in report.summary

    def test_works_without_reflection_engine(self, mock_memory, tmp_store, sample_findings):
        eng = ResearchEngine(memory=mock_memory, store=tmp_store, max_workers=1)
        eng._fetch_all = lambda q: sample_findings
        report = eng.research("neural network", domain="ml")
        assert isinstance(report, ResearchReport)  # no crash

    def test_get_reports_for_domain(self, mock_memory, tmp_store,
                                    mock_reflection_engine, mock_learning_engine,
                                    sample_findings):
        eng = self._make_engine(mock_memory, tmp_store, mock_reflection_engine,
                                mock_learning_engine, sample_findings)
        eng.research("neural network", domain="ml")
        eng.research("backprop",       domain="ml")
        reports = eng.get_reports_for_domain("ml")
        assert len(reports) == 2
