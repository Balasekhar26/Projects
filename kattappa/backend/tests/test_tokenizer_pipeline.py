"""Unit tests for Program 27.0 / Phase 27B: Tokenizer Training Pipeline.

All tests use the MockTokenizer fallback so they run cleanly in CI without
the sentencepiece native wheel installed.
"""
from __future__ import annotations

import pytest

from backend.core.dataset.tokenizer_trainer import TokenizerTrainer, _MockTokenizer, _SP_AVAILABLE
from backend.core.dataset.tokenizer_registry import TokenizerRegistry
from backend.core.dataset.vocabulary_analyzer import VocabularyAnalyzer, _DOMAIN_TERMS
from backend.core.dataset.tokenizer_benchmark import TokenizerBenchmark, _DOMAIN_TOKENS


@pytest.fixture(autouse=True)
def clean_registry():
    TokenizerRegistry.reset()
    yield
    TokenizerRegistry.reset()


# ── Sample data ───────────────────────────────────────────────────────────────

_SAMPLE_TEXTS = [
    "deploy the docker sandbox now",
    "train a neural network on the GPU cluster",
    "run automated integration tests for the api",
    "create a distributed task dispatcher",
    "Please build the corpus preparation pipeline",
    "Your task is to launch the experience store",
    "analyze the combined_score for planner_version HTN-v2",
    "execute the skill_former and trajectory analyzer",
]

_TELUGU_TEXTS = [
    "సాండ్‌బాక్స్ ఎగ్జిక్యూటర్‌ను అమలు చేయండి",  # "run the sandbox executor"
    "నెట్‌వర్క్ పాలసీని తనిఖీ చేయండి",            # "check network policy"
]


# ── 1. MockTokenizer ──────────────────────────────────────────────────────────

class TestMockTokenizer:
    def test_encode_returns_list(self):
        tok = _MockTokenizer()
        result = tok.encode("deploy docker sandbox", out_type=str)
        assert isinstance(result, list)
        assert len(result) > 0

    def test_encode_int_returns_ints(self):
        tok = _MockTokenizer()
        result = tok.encode("deploy docker sandbox", out_type=int)
        assert all(isinstance(x, int) for x in result)

    def test_decode_not_empty(self):
        tok = _MockTokenizer()
        ids = tok.encode("run tests", out_type=int)
        decoded = tok.decode(ids)
        assert isinstance(decoded, str)
        assert len(decoded) > 0

    def test_vocab_size_stored(self):
        tok = _MockTokenizer(vocab_size=8000)
        assert tok.get_piece_size() == 8000


# ── 2. Tokenizer Trainer ──────────────────────────────────────────────────────

class TestTokenizerTrainer:
    def test_train_produces_model_and_vocab_files(self):
        report = TokenizerTrainer.train_from_texts(
            texts=_SAMPLE_TEXTS,
            version_id="test_tok_v1",
            vocab_size=200,
        )
        from pathlib import Path
        assert Path(report["model_path"]).exists()
        assert Path(report["vocab_path"]).exists()

    def test_report_contains_expected_keys(self):
        report = TokenizerTrainer.train_from_texts(
            texts=_SAMPLE_TEXTS,
            version_id="test_tok_v2",
            vocab_size=200,
        )
        for key in ("version_id", "vocab_size", "algorithm", "model_path", "vocab_path", "mock"):
            assert key in report, f"Missing key: {key}"

    def test_text_count_in_report(self):
        report = TokenizerTrainer.train_from_texts(
            texts=_SAMPLE_TEXTS,
            version_id="test_tok_v3",
            vocab_size=200,
        )
        assert report["text_count"] == len(_SAMPLE_TEXTS)

    def test_registered_in_registry(self):
        TokenizerTrainer.train_from_texts(
            texts=_SAMPLE_TEXTS,
            version_id="test_tok_v4",
            vocab_size=200,
        )
        entries = TokenizerRegistry.load()
        version_ids = [e["version_id"] for e in entries]
        assert "test_tok_v4" in version_ids

    def test_load_returns_tokenizer(self):
        TokenizerTrainer.train_from_texts(
            texts=_SAMPLE_TEXTS,
            version_id="test_tok_v5",
            vocab_size=200,
        )
        tok = TokenizerTrainer.load("test_tok_v5")
        assert hasattr(tok, "encode")
        assert hasattr(tok, "decode")


# ── 3. Tokenizer Registry ─────────────────────────────────────────────────────

class TestTokenizerRegistry:
    def test_register_and_load(self):
        entry = TokenizerRegistry.register(
            version_id="reg_v1",
            vocab_size=16000,
            algorithm="sentencepiece_unigram",
            corpus_version="corpus_v1",
            model_path="/tmp/reg_v1.model",
            vocab_path="/tmp/reg_v1.vocab",
        )
        assert entry["version_id"] == "reg_v1"
        entries = TokenizerRegistry.load()
        assert any(e["version_id"] == "reg_v1" for e in entries)

    def test_promote_marks_active(self):
        TokenizerRegistry.register(
            version_id="promo_v1",
            vocab_size=8000,
            algorithm="mock",
            corpus_version="c1",
            model_path="/tmp/p.model",
            vocab_path="/tmp/p.vocab",
        )
        result = TokenizerRegistry.promote("promo_v1")
        assert result is True
        active = TokenizerRegistry.get_active()
        assert active["version_id"] == "promo_v1"
        assert active["active"] is True

    def test_promote_unknown_returns_false(self):
        assert TokenizerRegistry.promote("nonexistent_id") is False

    def test_get_active_returns_none_on_empty(self):
        assert TokenizerRegistry.get_active() is None

    def test_get_active_falls_back_to_latest(self):
        TokenizerRegistry.register(
            version_id="latest_v1",
            vocab_size=8000,
            algorithm="mock",
            corpus_version="c1",
            model_path="/tmp/l.model",
            vocab_path="/tmp/l.vocab",
        )
        active = TokenizerRegistry.get_active()
        assert active["version_id"] == "latest_v1"


# ── 4. Vocabulary Analyzer ────────────────────────────────────────────────────

class TestVocabularyAnalyzer:
    def test_analysis_keys_present(self):
        tok = _MockTokenizer()
        report = VocabularyAnalyzer.analyze(tok, _SAMPLE_TEXTS)
        for key in ("oov_rate", "avg_fertility", "domain_coverage", "total_tokens", "total_texts"):
            assert key in report, f"Missing key: {key}"

    def test_total_texts_matches_input(self):
        tok = _MockTokenizer()
        report = VocabularyAnalyzer.analyze(tok, _SAMPLE_TEXTS)
        assert report["total_texts"] == len(_SAMPLE_TEXTS)

    def test_oov_rate_between_zero_and_one(self):
        tok = _MockTokenizer()
        report = VocabularyAnalyzer.analyze(tok, _SAMPLE_TEXTS)
        assert 0.0 <= report["oov_rate"] <= 1.0

    def test_domain_coverage_between_zero_and_one(self):
        tok = _MockTokenizer()
        report = VocabularyAnalyzer.analyze(tok, _SAMPLE_TEXTS)
        assert 0.0 <= report["domain_coverage"] <= 1.0

    def test_empty_texts_returns_empty_report(self):
        tok = _MockTokenizer()
        report = VocabularyAnalyzer.analyze(tok, [])
        assert report["total_texts"] == 0
        assert report["total_tokens"] == 0


# ── 5. Tokenizer Benchmark ────────────────────────────────────────────────────

class TestTokenizerBenchmark:
    def test_benchmark_report_keys(self):
        tok = _MockTokenizer()
        report = TokenizerBenchmark.run(tok, _SAMPLE_TEXTS)
        for key in ("fidelity_rate", "avg_fertility", "special_tokens_ok",
                    "tokens_per_second", "samples_tested", "total_tokens"):
            assert key in report, f"Missing key: {key}"

    def test_samples_tested_capped(self):
        tok = _MockTokenizer()
        report = TokenizerBenchmark.run(tok, _SAMPLE_TEXTS * 100, max_samples=10)
        assert report["samples_tested"] == 10

    def test_tokens_per_second_positive(self):
        tok = _MockTokenizer()
        report = TokenizerBenchmark.run(tok, _SAMPLE_TEXTS)
        assert report["tokens_per_second"] >= 0.0

    def test_special_token_results_has_all_domain_tokens(self):
        tok = _MockTokenizer()
        report = TokenizerBenchmark.run(tok, _SAMPLE_TEXTS)
        for tok_str in _DOMAIN_TOKENS:
            assert tok_str in report["special_token_results"]

    def test_empty_texts_returns_empty_report(self):
        tok = _MockTokenizer()
        report = TokenizerBenchmark.run(tok, [])
        assert report["samples_tested"] == 0
        assert report["fidelity_rate"] == 0.0
