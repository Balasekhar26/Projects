"""Deduplicator (Program 27.0 / Phase 27A).

Two-stage deduplication for training corpus quality:

Stage 1 — Exact dedup:
    SHA-256 hash of (instruction, actions_tuple). Drops bitwise-identical records.

Stage 2 — Near-dedup via SimHash:
    64-bit SimHash fingerprint over instruction tokens. Records whose fingerprints
    differ by Hamming distance ≤ HAMMING_THRESHOLD are considered near-duplicates;
    only the first encountered is kept. This removes augmented paraphrases that are
    semantically identical despite surface variation.
"""
from __future__ import annotations

import hashlib
import re
from typing import Any, Dict, List, Tuple

# Empirically calibrated: augmented paraphrases of 6–10 word instructions
# typically differ by 4–8 bits in a 64-bit SimHash over word tokens.
HAMMING_THRESHOLD = 8
_SIMHASH_BITS = 64
_WORD_RE = re.compile(r"[a-zA-Z0-9\u0C00-\u0C7F]+")  # Latin + Telugu Unicode block


# ── SimHash ────────────────────────────────────────────────────────────────────

def _token_hash(token: str) -> int:
    """Returns a 64-bit integer hash for a single token."""
    digest = hashlib.md5(token.encode("utf-8")).digest()  # noqa: S324
    return int.from_bytes(digest[:8], "big")


def _simhash(text: str) -> int:
    """Computes a 64-bit SimHash fingerprint for the given text."""
    tokens = _WORD_RE.findall(text.lower())
    if not tokens:
        return 0

    v = [0] * _SIMHASH_BITS
    for token in tokens:
        h = _token_hash(token)
        for i in range(_SIMHASH_BITS):
            if (h >> i) & 1:
                v[i] += 1
            else:
                v[i] -= 1

    fingerprint = 0
    for i in range(_SIMHASH_BITS):
        if v[i] > 0:
            fingerprint |= 1 << i
    return fingerprint


def _hamming_distance(a: int, b: int) -> int:
    """Counts differing bits between two 64-bit integers."""
    xor = a ^ b
    count = 0
    while xor:
        count += xor & 1
        xor >>= 1
    return count


# ── Exact hash ────────────────────────────────────────────────────────────────

def _exact_key(record: Dict[str, Any]) -> str:
    """Returns a stable SHA-256 hex digest for a record's canonical content."""
    instruction = record.get("instruction", "")
    actions = tuple(record.get("actions", []))
    raw = f"{instruction}||{actions}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


# ── Public API ────────────────────────────────────────────────────────────────

class Deduplicator:
    """Removes exact and near-duplicate records from an extraction corpus."""

    @classmethod
    def deduplicate(
        cls,
        records: List[Dict[str, Any]],
        hamming_threshold: int = HAMMING_THRESHOLD,
    ) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
        """Filters duplicates in two passes.

        Args:
            records:           Extraction records from TraceExtractor / QualityFilter.
            hamming_threshold: Maximum bit-distance to consider two records
                               near-duplicates (default 8).

        Returns:
            (unique_records, stats) where stats contains:
                - total_input
                - exact_removed
                - near_removed
                - total_output
        """
        stats = {
            "total_input": len(records),
            "exact_removed": 0,
            "near_removed": 0,
            "total_output": 0,
        }

        # ── Pass 1: exact dedup ───────────────────────────────────────────────
        seen_exact: set[str] = set()
        after_exact: List[Dict[str, Any]] = []
        for rec in records:
            key = _exact_key(rec)
            if key in seen_exact:
                stats["exact_removed"] += 1
            else:
                seen_exact.add(key)
                after_exact.append(rec)

        # ── Pass 2: SimHash near-dedup ────────────────────────────────────────
        seen_fingerprints: List[int] = []
        unique: List[Dict[str, Any]] = []

        for rec in after_exact:
            fp = _simhash(rec.get("instruction", ""))
            is_near_dup = any(
                _hamming_distance(fp, existing) <= hamming_threshold
                for existing in seen_fingerprints
            )
            if is_near_dup:
                stats["near_removed"] += 1
            else:
                seen_fingerprints.append(fp)
                unique.append(rec)

        stats["total_output"] = len(unique)
        return unique, stats
