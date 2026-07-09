"""Vocabulary Analyzer (Program 27.0 / Phase 27B).

Loads a trained tokenizer and measures its coverage, fertility, and
domain-specific token representation on a held-out text corpus.

Works with both real SentencePiece processors and the MockTokenizer fallback.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List

# Domain-specific terms that should ideally be single tokens
_DOMAIN_TERMS = [
    "planner_version",
    "combined_score",
    "sandbox",
    "trajectory",
    "htn",
    "replanning",
    "skill_former",
    "experience_store",
    "distributed",
    "heartbeat",
]

_TELUGU_RE = re.compile(r"[\u0C00-\u0C7F]+")
_LATIN_RE = re.compile(r"[a-zA-Z0-9_\-]+")


def _word_count(text: str) -> int:
    return len(_LATIN_RE.findall(text)) + len(_TELUGU_RE.findall(text))


class VocabularyAnalyzer:
    """Analyses a tokenizer's quality metrics on a sample text corpus."""

    @classmethod
    def analyze(
        cls,
        tokenizer: Any,
        texts: List[str],
    ) -> Dict[str, Any]:
        """Computes OOV rate, token fertility, and domain coverage.

        Args:
            tokenizer: A SentencePieceProcessor or MockTokenizer instance.
            texts:     List of raw text strings (typically from the val/test split).

        Returns:
            Dict with:
                oov_rate            : float  (fraction of <unk> tokens)
                avg_fertility       : float  (avg tokens per word)
                latin_fertility     : float
                telugu_fertility    : float
                domain_coverage     : float  (fraction of domain terms as single token)
                total_texts         : int
                total_tokens        : int
        """
        if not texts:
            return cls._empty_report()

        total_tokens = 0
        total_unk = 0
        total_words = 0
        latin_tokens = 0
        latin_words = 0
        telugu_tokens = 0
        telugu_words = 0

        for text in texts:
            encoded = tokenizer.encode(text, out_type=str)
            total_tokens += len(encoded)
            total_unk += sum(1 for t in encoded if t == "<unk>")
            words = _word_count(text)
            total_words += words

            # Per-script fertility
            latin_w = len(_LATIN_RE.findall(text))
            telugu_w = len(_TELUGU_RE.findall(text))
            if latin_w:
                # Rough share of tokens belonging to latin words
                latin_share = latin_w / max(words, 1)
                latin_tokens += int(len(encoded) * latin_share)
                latin_words += latin_w
            if telugu_w:
                telugu_share = telugu_w / max(words, 1)
                telugu_tokens += int(len(encoded) * telugu_share)
                telugu_words += telugu_w

        oov_rate = round(total_unk / total_tokens, 4) if total_tokens else 0.0
        avg_fertility = round(total_tokens / total_words, 4) if total_words else 0.0
        latin_fertility = round(latin_tokens / latin_words, 4) if latin_words else 0.0
        telugu_fertility = round(telugu_tokens / telugu_words, 4) if telugu_words else 0.0

        # Domain coverage: count how many domain terms encode as a single token
        domain_hits = 0
        for term in _DOMAIN_TERMS:
            encoded_term = tokenizer.encode(term, out_type=str)
            if len(encoded_term) == 1 and encoded_term[0] != "<unk>":
                domain_hits += 1
        domain_coverage = round(domain_hits / len(_DOMAIN_TERMS), 4)

        return {
            "oov_rate": oov_rate,
            "avg_fertility": avg_fertility,
            "latin_fertility": latin_fertility,
            "telugu_fertility": telugu_fertility,
            "domain_coverage": domain_coverage,
            "domain_terms_checked": len(_DOMAIN_TERMS),
            "total_texts": len(texts),
            "total_tokens": total_tokens,
            "total_words": total_words,
        }

    @classmethod
    def _empty_report(cls) -> Dict[str, Any]:
        return {
            "oov_rate": 0.0,
            "avg_fertility": 0.0,
            "latin_fertility": 0.0,
            "telugu_fertility": 0.0,
            "domain_coverage": 0.0,
            "domain_terms_checked": len(_DOMAIN_TERMS),
            "total_texts": 0,
            "total_tokens": 0,
            "total_words": 0,
        }
