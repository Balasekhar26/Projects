"""Token Estimator (Program 27.0 / Phase 27A).

Estimates token counts and training FLOPs without loading a real tokenizer.
Uses word-count heuristics calibrated against BPE tokenizers:

    Latin (English):  words × 1.30   (GPT-2 / LLaMA BPE approximation)
    Telugu script:    words × 1.60   (higher due to morphological richness)

Training FLOPs estimate follows the Chinchilla scaling law:
    C ≈ 6 × N × D
    where N = number of model parameters, D = number of training tokens.

Reference: Hoffmann et al. 2022 "Training Compute-Optimal Large Language Models"
"""
from __future__ import annotations

import re
from typing import Any, Dict, List

# Unicode ranges
_TELUGU_RE = re.compile(r"[\u0C00-\u0C7F]+")
_LATIN_RE = re.compile(r"[a-zA-Z0-9_\-]+")

# BPE calibration multipliers
_LATIN_TOKENS_PER_WORD = 1.30
_TELUGU_TOKENS_PER_WORD = 1.60

# Chinchilla constant
_CHINCHILLA_CONSTANT = 6.0


def _estimate_tokens_text(text: str) -> float:
    """Returns approximate token count for a raw text string."""
    latin_words = len(_LATIN_RE.findall(text))
    telugu_words = len(_TELUGU_RE.findall(text))
    return (latin_words * _LATIN_TOKENS_PER_WORD) + (telugu_words * _TELUGU_TOKENS_PER_WORD)


def _record_text(record: Dict[str, Any]) -> str:
    """Concatenates all textual fields of a record for token estimation."""
    parts = [
        record.get("instruction", ""),
        record.get("reasoning_trace", ""),
        record.get("result", ""),
        " ".join(record.get("actions", [])),
    ]
    return " ".join(parts)


class TokenEstimator:
    """Estimates token budget and training compute requirements for a corpus."""

    @classmethod
    def estimate(
        cls,
        records: List[Dict[str, Any]],
        model_params: int | None = None,
    ) -> Dict[str, Any]:
        """Computes corpus-level token estimates and optional FLOPs budget.

        Args:
            records:      Training records (any split or the full corpus).
            model_params: Number of model parameters (e.g. 135_000_000 for 135M).
                          If provided, returns estimated training FLOPs.

        Returns:
            Dict with:
                total_records       : int
                total_tokens        : int   (rounded)
                avg_tokens_per_record: float
                latin_token_share   : float
                telugu_token_share  : float
                training_flops      : int | None  (if model_params given)
                recommended_scale   : str
        """
        total_latin = 0.0
        total_telugu = 0.0

        for rec in records:
            text = _record_text(rec)
            total_latin += len(_LATIN_RE.findall(text)) * _LATIN_TOKENS_PER_WORD
            total_telugu += len(_TELUGU_RE.findall(text)) * _TELUGU_TOKENS_PER_WORD

        total_tokens = total_latin + total_telugu
        n = len(records)

        flops = None
        if model_params is not None and total_tokens > 0:
            flops = int(_CHINCHILLA_CONSTANT * model_params * total_tokens)

        # Recommend a model scale based on corpus token count
        if total_tokens < 500_000:
            recommended = "135M (proof-of-concept)"
        elif total_tokens < 5_000_000:
            recommended = "360M–1.3B (small assistant)"
        elif total_tokens < 50_000_000:
            recommended = "3B–7B (personal AI OS)"
        else:
            recommended = "13B+ (production)"

        return {
            "total_records": n,
            "total_tokens": round(total_tokens),
            "avg_tokens_per_record": round(total_tokens / n, 2) if n else 0.0,
            "latin_token_share": round(total_latin / total_tokens, 4) if total_tokens else 0.0,
            "telugu_token_share": round(total_telugu / total_tokens, 4) if total_tokens else 0.0,
            "training_flops": flops,
            "recommended_scale": recommended,
        }
