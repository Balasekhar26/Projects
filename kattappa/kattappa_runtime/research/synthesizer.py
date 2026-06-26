"""
Research Synthesizer
====================
Turns a list of raw ResearchFindings into a structured ResearchReport.

The synthesizer:
  1. Filters findings by quality (drops LOW quality if better exist)
  2. Deduplicates near-identical excerpts
  3. Generates a summary sentence
  4. Extracts key_facts (one per finding, terse)
  5. Computes aggregate confidence from finding quality + relevance scores

No LLM required — uses rule-based extraction. An LLM hook is available
to upgrade summary and key_facts quality when a model is online.
"""

from __future__ import annotations

import re
from typing import Callable, List, Optional

from kattappa_runtime.research.schema import (
    ResearchFinding, ResearchQuery, ResearchReport, FindingQuality
)

# Quality rank for filtering
_QUALITY_RANK = {
    FindingQuality.HIGH:   2,
    FindingQuality.MEDIUM: 1,
    FindingQuality.LOW:    0,
}

_MAX_FACT_LEN   = 200   # chars per key fact
_MAX_KEY_FACTS  = 6


class ResearchSynthesizer:
    """
    Synthesizes raw findings into a structured ResearchReport.

    Parameters
    ----------
    summarizer : Callable[[List[ResearchFinding], str], str] | None
        Optional LLM-backed hook. Receives findings + topic, returns summary.
    fact_extractor : Callable[[ResearchFinding], str] | None
        Optional LLM-backed hook. Receives one finding, returns a key fact.
    """

    def __init__(
        self,
        summarizer:     Optional[Callable[[List[ResearchFinding], str], str]] = None,
        fact_extractor: Optional[Callable[[ResearchFinding], str]]            = None,
    ):
        self._summarizer     = summarizer
        self._fact_extractor = fact_extractor

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def synthesize(
        self,
        query:    ResearchQuery,
        findings: List[ResearchFinding],
    ) -> ResearchReport:
        """
        Produce a ResearchReport from a query and its collected findings.
        """
        # 1. Filter & rank findings
        ranked = self._filter_and_rank(findings)

        # 2. Deduplicate
        deduped = self._deduplicate(ranked)

        # 3. Generate summary
        summary = self._make_summary(query.topic, deduped)

        # 4. Extract key facts
        key_facts = self._extract_facts(deduped)

        # 5. Compute confidence
        confidence = self._compute_confidence(deduped)

        return ResearchReport(
            query_id   = query.query_id,
            topic      = query.topic,
            domain     = query.domain,
            summary    = summary,
            key_facts  = key_facts,
            findings   = deduped,
            confidence = confidence,
        )

    # ------------------------------------------------------------------
    # Private — filtering
    # ------------------------------------------------------------------

    @staticmethod
    def _filter_and_rank(findings: List[ResearchFinding]) -> List[ResearchFinding]:
        """
        If any HIGH-quality findings exist, drop LOW-quality ones.
        Sort by relevance_score descending.
        """
        if not findings:
            return []
        best_quality = max(_QUALITY_RANK[f.quality] for f in findings)
        if best_quality >= _QUALITY_RANK[FindingQuality.MEDIUM]:
            findings = [f for f in findings if _QUALITY_RANK[f.quality] >= 1]
        return sorted(findings, key=lambda f: f.relevance_score, reverse=True)

    @staticmethod
    def _deduplicate(findings: List[ResearchFinding]) -> List[ResearchFinding]:
        """Remove findings whose excerpts are >80% similar (first-100-word Jaccard)."""
        seen_sets: List[set] = []
        deduped:  List[ResearchFinding] = []
        for f in findings:
            words = set(f.excerpt.lower().split()[:100])
            if any(_jaccard(words, s) > 0.80 for s in seen_sets):
                continue
            seen_sets.append(words)
            deduped.append(f)
        return deduped

    # ------------------------------------------------------------------
    # Private — synthesis
    # ------------------------------------------------------------------

    def _make_summary(self, topic: str, findings: List[ResearchFinding]) -> str:
        """Generate a 1–2 sentence summary."""
        if not findings:
            return f"No relevant information found for '{topic}'."

        # Try LLM hook
        if self._summarizer:
            try:
                result = self._summarizer(findings, topic)
                if result and isinstance(result, str):
                    return result.strip()
            except Exception:
                pass

        # Rule-based fallback: stitch first sentence of top-2 excerpts
        parts = []
        for f in findings[:2]:
            first_sent = _first_sentence(f.excerpt)
            if first_sent:
                parts.append(f"[{f.source.value.capitalize()}] {first_sent}")

        if parts:
            return " | ".join(parts)
        return f"Research on '{topic}' returned {len(findings)} finding(s) from multiple sources."

    def _extract_facts(self, findings: List[ResearchFinding]) -> List[str]:
        """Extract one terse key fact per finding (up to _MAX_KEY_FACTS)."""
        facts = []
        for f in findings[:_MAX_KEY_FACTS]:
            # Try LLM hook
            if self._fact_extractor:
                try:
                    fact = self._fact_extractor(f)
                    if fact and isinstance(fact, str):
                        facts.append(fact.strip()[:_MAX_FACT_LEN])
                        continue
                except Exception:
                    pass

            # Rule-based: first meaningful sentence from excerpt
            fact = _first_sentence(f.excerpt)
            if not fact:
                fact = f.excerpt[:_MAX_FACT_LEN]
            label = f.source.value.upper()
            facts.append(f"[{label}] {fact[:_MAX_FACT_LEN]}")

        return facts

    @staticmethod
    def _compute_confidence(findings: List[ResearchFinding]) -> float:
        """Weighted average relevance, boosted by quality."""
        if not findings:
            return 0.0
        total = sum(
            f.relevance_score * (_QUALITY_RANK[f.quality] + 1)
            for f in findings
        )
        weight = sum(_QUALITY_RANK[f.quality] + 1 for f in findings)
        return round(total / weight, 3)


# ------------------------------------------------------------------
# Utilities
# ------------------------------------------------------------------

def _jaccard(a: set, b: set) -> float:
    if not a and not b:
        return 1.0
    return len(a & b) / len(a | b)


def _first_sentence(text: str) -> str:
    """Extract the first complete sentence from text."""
    text = re.sub(r"\s+", " ", text).strip()
    # Match end of a sentence: . ! ? followed by space or end-of-string
    match = re.search(r"[^.!?]*[.!?](?=\s|$)", text)
    if match:
        return match.group(0).strip()
    # Fallback: first 150 chars
    return text[:150].strip()
