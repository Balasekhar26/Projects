"""
Local Corpus Adapter
====================
Searches Kattappa's own training corpus files for relevant passages.

This is important because:
  1. Works fully offline (no network required)
  2. Searches philosophy/ethics texts (Bhagavad Gita, etc.) once added
  3. Provides a feedback loop: training data informs the runtime agent

Search strategy:
  - Scans JSONL corpus files in the deduped/ directory
  - Each record has a "text" field
  - Keyword matching (case-insensitive, word-boundary aware)
  - Returns the top-scored passages as findings
"""

from __future__ import annotations

import json
import os
import re
from typing import List, Optional

from kattappa_runtime.research.schema import (
    ResearchQuery, ResearchFinding, SourceType, FindingQuality
)
from kattappa_runtime.research.sources.base import BaseSourceAdapter

# Default corpus directory (relative to project root; override via env)
_CORPUS_DIR = os.environ.get(
    "KATTAPPA_CORPUS_DIR",
    os.path.join(
        os.path.dirname(__file__),
        "..", "..", "..", "kattappa_native", "corpus", "deduped"
    )
)

_EXCERPT_LEN   = 800    # chars to extract around a match
_CONTEXT_PAD   = 150    # chars of context before/after the match
_MAX_SCAN_LINES = 5000  # don't scan entire corpus on every query (performance guard)


class LocalCorpusAdapter(BaseSourceAdapter):
    """Searches Kattappa's training corpus for relevant passages."""

    source_name = "local_corpus"

    def __init__(self, corpus_dir: Optional[str] = None):
        self._corpus_dir = os.path.abspath(corpus_dir or _CORPUS_DIR)

    def _fetch(self, query: ResearchQuery) -> List[ResearchFinding]:
        topic = query.topic.strip()
        if not topic or not os.path.isdir(self._corpus_dir):
            return []

        keywords = self._extract_keywords(topic)
        if not keywords:
            return []

        # Compile a single regex for any keyword
        pattern = re.compile(
            r"(" + "|".join(re.escape(kw) for kw in keywords) + r")",
            re.IGNORECASE
        )

        candidates: List[tuple[float, ResearchFinding]] = []
        scanned = 0

        for fname in sorted(os.listdir(self._corpus_dir)):
            if not fname.endswith(".jsonl"):
                continue
            fpath = os.path.join(self._corpus_dir, fname)
            try:
                with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                    for line in f:
                        if scanned >= _MAX_SCAN_LINES:
                            break
                        scanned += 1
                        try:
                            record = json.loads(line)
                        except json.JSONDecodeError:
                            continue

                        text = record.get("text", "") or record.get("content", "")
                        if not text:
                            continue

                        matches = list(pattern.finditer(text))
                        if not matches:
                            continue

                        score  = self._score(keywords, text)
                        excerpt = self._extract_excerpt(text, matches[0].start())

                        source_tag = record.get("source", fname.replace(".jsonl", ""))

                        candidates.append((score, ResearchFinding(
                            query_id        = query.query_id,
                            source          = SourceType.LOCAL,
                            title           = f"[Local] {source_tag}",
                            url             = f"file://{fpath}",
                            excerpt         = excerpt,
                            quality         = FindingQuality.MEDIUM,
                            relevance_score = score,
                        )))
            except OSError:
                continue

        # Sort by score desc, return top N
        candidates.sort(key=lambda x: x[0], reverse=True)
        return [f for _, f in candidates[: query.max_findings]]

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_keywords(topic: str) -> List[str]:
        """Extract meaningful keywords (length ≥ 4) from the topic string."""
        stop = {"what", "when", "where", "which", "with", "this", "that",
                "from", "have", "been", "will", "does", "about", "into"}
        words = re.findall(r"\b\w{4,}\b", topic.lower())
        return [w for w in words if w not in stop]

    @staticmethod
    def _score(keywords: List[str], text: str) -> float:
        """Keyword density score."""
        text_lower  = text.lower()
        word_count  = max(len(text.split()), 1)
        hit_count   = sum(text_lower.count(kw) for kw in keywords)
        raw_density = hit_count / word_count
        return round(min(1.0, raw_density * 20), 3)  # scale to [0,1]

    @staticmethod
    def _extract_excerpt(text: str, match_start: int) -> str:
        """Extract a window of text around the first match."""
        start = max(0, match_start - _CONTEXT_PAD)
        end   = min(len(text), match_start + _EXCERPT_LEN)
        excerpt = text[start:end].strip()
        if start > 0:
            excerpt = "…" + excerpt
        if end < len(text):
            excerpt = excerpt + "…"
        return excerpt
