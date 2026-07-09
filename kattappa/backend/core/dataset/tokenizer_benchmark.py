"""Tokenizer Benchmark (Program 27.0 / Phase 27B).

Quality and performance benchmark suite for a trained tokenizer:

1. Round-trip fidelity   — decode(encode(text)) ≈ text
2. Fertility benchmark   — tokens/word across Latin, Telugu, mixed
3. Special token check   — all 5 domain tokens encode/decode correctly
4. Throughput estimate   — tokens/second (from a timed batch)
"""
from __future__ import annotations

import time
from typing import Any, Dict, List

_DOMAIN_TOKENS = ["<|plan|>", "<|action|>", "<|tool|>", "<|result|>", "<|eot|>"]

# Normalisation helper: collapse whitespace for round-trip comparison
def _normalise(text: str) -> str:
    return " ".join(text.split())


class TokenizerBenchmark:
    """Runs a standardised quality and performance benchmark on a tokenizer."""

    @classmethod
    def run(
        cls,
        tokenizer: Any,
        texts: List[str],
        max_samples: int = 200,
    ) -> Dict[str, Any]:
        """Executes all benchmark passes.

        Args:
            tokenizer:   A SentencePieceProcessor or MockTokenizer.
            texts:       Held-out text samples (val or test split).
            max_samples: Cap to keep runtime bounded.

        Returns:
            Dict with: fidelity_rate, avg_fertility, special_tokens_ok,
                       tokens_per_second, samples_tested.
        """
        sample = texts[:max_samples]
        if not sample:
            return cls._empty_report()

        # ── 1. Round-trip fidelity ────────────────────────────────────────────
        fidelity_hits = 0
        total_tokens = 0
        t0 = time.perf_counter()

        for text in sample:
            ids = tokenizer.encode(text, out_type=int)
            reconstructed = tokenizer.decode(ids)
            total_tokens += len(ids)
            if _normalise(reconstructed) == _normalise(text):
                fidelity_hits += 1

        elapsed = time.perf_counter() - t0
        fidelity_rate = round(fidelity_hits / len(sample), 4)

        # ── 2. Fertility ──────────────────────────────────────────────────────
        total_words = sum(len(t.split()) for t in sample)
        avg_fertility = round(total_tokens / total_words, 4) if total_words else 0.0

        # ── 3. Special token verification ─────────────────────────────────────
        special_ok = True
        special_results = {}
        for tok in _DOMAIN_TOKENS:
            encoded = tokenizer.encode(tok, out_type=str)
            decoded = tokenizer.decode(tokenizer.encode(tok, out_type=int))
            # Accept if encoded as a single piece or decode recovers the token
            ok = (len(encoded) >= 1) and (tok in decoded or decoded.strip() == tok.strip())
            special_results[tok] = ok
            if not ok:
                special_ok = False

        # ── 4. Throughput ─────────────────────────────────────────────────────
        tokens_per_second = round(total_tokens / elapsed, 1) if elapsed > 0 else 0.0

        return {
            "fidelity_rate": fidelity_rate,
            "avg_fertility": avg_fertility,
            "special_tokens_ok": special_ok,
            "special_token_results": special_results,
            "tokens_per_second": tokens_per_second,
            "samples_tested": len(sample),
            "total_tokens": total_tokens,
        }

    @classmethod
    def _empty_report(cls) -> Dict[str, Any]:
        return {
            "fidelity_rate": 0.0,
            "avg_fertility": 0.0,
            "special_tokens_ok": False,
            "special_token_results": {},
            "tokens_per_second": 0.0,
            "samples_tested": 0,
            "total_tokens": 0,
        }
