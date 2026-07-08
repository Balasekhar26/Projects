"""Dataset Metrics (Program 26.0).

Measures diversity, balance, token estimates, and quality scores for a
generated dataset corpus.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List

_WORD_RE = re.compile(r"[a-zA-Z0-9]+")
_TOKENS_PER_WORD = 1.3  # rough BPE approximation


def _word_count(text: str) -> int:
    return len(_WORD_RE.findall(text))


class DatasetMetrics:
    """Computes corpus-level quality and coverage metrics."""

    @classmethod
    def compute(cls, records: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Returns a metrics report dict for the provided record list.

        Fields:
            total_samples         : int
            success_count         : int
            failure_count         : int
            recovered_count       : int
            balance_ratio         : float  (success / total, ideally > 0.6)
            avg_action_count      : float
            avg_token_estimate    : float  (words × 1.3)
            vocabulary_diversity  : float  (unique tokens / total tokens)
            augmented_ratio       : float  (augmented samples / total)
        """
        if not records:
            return {
                "total_samples": 0,
                "success_count": 0,
                "failure_count": 0,
                "recovered_count": 0,
                "balance_ratio": 0.0,
                "avg_action_count": 0.0,
                "avg_token_estimate": 0.0,
                "vocabulary_diversity": 0.0,
                "augmented_ratio": 0.0,
            }

        total = len(records)
        success = sum(1 for r in records if r.get("result") == "success")
        failure = sum(1 for r in records if r.get("result") == "failure")
        recovered = sum(1 for r in records if r.get("result") == "recovered")
        augmented = sum(1 for r in records if r.get("augmented", False))

        all_words: List[str] = []
        total_actions = 0
        total_words = 0

        for rec in records:
            instr_words = _WORD_RE.findall(rec.get("instruction", ""))
            trace_words = _WORD_RE.findall(rec.get("reasoning_trace", ""))
            words = instr_words + trace_words
            all_words.extend(w.lower() for w in words)
            total_words += len(words)
            total_actions += len(rec.get("actions", []))

        avg_tokens = round((total_words / total) * _TOKENS_PER_WORD, 2) if total else 0.0
        vocab_diversity = round(len(set(all_words)) / total_words, 4) if total_words else 0.0

        return {
            "total_samples": total,
            "success_count": success,
            "failure_count": failure,
            "recovered_count": recovered,
            "balance_ratio": round(success / total, 3) if total else 0.0,
            "avg_action_count": round(total_actions / total, 2) if total else 0.0,
            "avg_token_estimate": avg_tokens,
            "vocabulary_diversity": vocab_diversity,
            "augmented_ratio": round(augmented / total, 3) if total else 0.0,
        }
