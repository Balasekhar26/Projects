"""MCE Component 1: Duplicate Detector.

Uses SHA-256 for exact-duplicate fingerprinting and a lightweight
128-permutation MinHash for near-duplicate clustering with configurable
Jaccard similarity threshold.
"""
from __future__ import annotations

import hashlib
import logging
import re
import sqlite3
from dataclasses import dataclass, field
from typing import Any, Dict, List, Set, Tuple

from backend.core.config import load_config
from backend.core.logger import log_event

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# MinHash implementation (no external dependency)
# ---------------------------------------------------------------------------

def _shingles(text: str, k: int = 3) -> Set[str]:
    """Returns k-shingling set for the given text."""
    tokens = re.sub(r"\s+", " ", text.lower().strip()).split()
    return {" ".join(tokens[i : i + k]) for i in range(max(1, len(tokens) - k + 1))}


def _minhash_signature(shingles: Set[str], n_perm: int = 128) -> List[int]:
    """Computes a MinHash signature vector of length n_perm."""
    sig: List[int] = []
    for seed in range(n_perm):
        min_val = float("inf")
        for s in shingles:
            h = int(hashlib.md5(f"{seed}:{s}".encode()).hexdigest(), 16)
            if h < min_val:
                min_val = h
        sig.append(int(min_val))
    return sig


def _jaccard_from_minhash(sig_a: List[int], sig_b: List[int]) -> float:
    """Estimates Jaccard similarity from two MinHash signatures."""
    if not sig_a or not sig_b or len(sig_a) != len(sig_b):
        return 0.0
    matches = sum(1 for a, b in zip(sig_a, sig_b) if a == b)
    return matches / len(sig_a)


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class DuplicationReport:
    exact_duplicate_ids: List[str] = field(default_factory=list)
    near_duplicate_clusters: List[List[str]] = field(default_factory=list)
    unique_ids: List[str] = field(default_factory=list)
    exact_dupe_count: int = 0
    near_dupe_count: int = 0
    unique_count: int = 0


# ---------------------------------------------------------------------------
# Detector
# ---------------------------------------------------------------------------

class MCEDuplicateDetector:
    """Detects exact and near-duplicate episodes in EpisodicMemory."""

    @classmethod
    def _get_episodic_conn(cls) -> sqlite3.Connection:
        config = load_config()
        conn = sqlite3.connect(str(config.sqlite_path), check_same_thread=False, timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    @classmethod
    def detect(
        cls,
        jaccard_threshold: float = 0.85,
        n_perm: int = 128,
        limit: int = 2000,
    ) -> DuplicationReport:
        """Scans recent episodic records and clusters near-duplicates."""
        report = DuplicationReport()

        conn = cls._get_episodic_conn()
        try:
            rows = conn.execute(
                """
                SELECT id, content FROM hm_episodes
                WHERE pinned = 0
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        except Exception as exc:
            logger.warning("DuplicateDetector: could not read hm_episodes: %s", exc)
            return report
        finally:
            conn.close()

        if not rows:
            return report

        # 1. Exact-duplicate fingerprinting
        seen_hashes: Dict[str, str] = {}  # sha256 -> first_id
        exact_dupes: Set[str] = set()

        for row in rows:
            sha = hashlib.sha256(row["content"].encode()).hexdigest()
            if sha in seen_hashes:
                exact_dupes.add(row["id"])
            else:
                seen_hashes[sha] = row["id"]

        report.exact_duplicate_ids = list(exact_dupes)
        report.exact_dupe_count = len(exact_dupes)

        # 2. MinHash near-duplicate clustering on non-exact-dupes
        candidates = [r for r in rows if r["id"] not in exact_dupes]
        sigs: List[Tuple[str, List[int]]] = []
        for row in candidates:
            sh = _shingles(row["content"])
            sig = _minhash_signature(sh, n_perm=n_perm)
            sigs.append((row["id"], sig))

        visited: Set[str] = set()
        clusters: List[List[str]] = []

        for i, (id_a, sig_a) in enumerate(sigs):
            if id_a in visited:
                continue
            cluster = [id_a]
            for j, (id_b, sig_b) in enumerate(sigs):
                if i == j or id_b in visited:
                    continue
                if _jaccard_from_minhash(sig_a, sig_b) >= jaccard_threshold:
                    cluster.append(id_b)
                    visited.add(id_b)
            if len(cluster) > 1:
                visited.add(id_a)
                clusters.append(cluster)
                report.near_dupe_count += len(cluster) - 1  # all but first are dupes

        report.near_duplicate_clusters = clusters
        all_dupe_ids = set(exact_dupes)
        for cluster in clusters:
            for ep_id in cluster[1:]:  # keep first, mark rest as near-dupes
                all_dupe_ids.add(ep_id)

        report.unique_ids = [r["id"] for r in rows if r["id"] not in all_dupe_ids]
        report.unique_count = len(report.unique_ids)

        log_event(
            "mce_duplicate_detect",
            f"Scanned {len(rows)} episodes — exact={report.exact_dupe_count}, "
            f"near={report.near_dupe_count}, unique={report.unique_count}",
        )
        return report
