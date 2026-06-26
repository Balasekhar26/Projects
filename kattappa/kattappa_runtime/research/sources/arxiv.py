"""
Arxiv Source Adapter
====================
Uses the Arxiv public API (no key required):
    http://export.arxiv.org/api/query?search_query=...

Retrieves paper abstracts — ideal for research and reasoning topics.
Parses the Atom XML response with only stdlib (xml.etree.ElementTree).

Returns up to max_findings findings, ordered by relevance (Arxiv's default).
"""

from __future__ import annotations

import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from typing import List

from kattappa_runtime.research.schema import (
    ResearchQuery, ResearchFinding, SourceType, FindingQuality
)
from kattappa_runtime.research.sources.base import BaseSourceAdapter, DEFAULT_TIMEOUT

_ARXIV_BASE  = "http://export.arxiv.org/api/query"
_ATOM_NS     = "http://www.w3.org/2005/Atom"
_MAX_RESULTS = 5
_MAX_EXCERPT = 1000


class ArxivAdapter(BaseSourceAdapter):
    """Retrieves paper abstracts from Arxiv matching the research topic."""

    source_name = "arxiv"

    def _fetch(self, query: ResearchQuery) -> List[ResearchFinding]:
        topic = query.topic.strip()
        if not topic:
            return []

        max_results = min(query.max_findings, _MAX_RESULTS)

        params = urllib.parse.urlencode({
            "search_query": f"all:{topic}",
            "start":        0,
            "max_results":  max_results,
        })

        req = urllib.request.Request(
            f"{_ARXIV_BASE}?{params}",
            headers={"User-Agent": "KattappaResearchEngine/1.0"},
        )
        with urllib.request.urlopen(req, timeout=DEFAULT_TIMEOUT) as resp:
            xml_bytes = resp.read()

        root = ET.fromstring(xml_bytes)
        findings: List[ResearchFinding] = []

        for entry in root.findall(f"{{{_ATOM_NS}}}entry"):
            try:
                title_el   = entry.find(f"{{{_ATOM_NS}}}title")
                summary_el = entry.find(f"{{{_ATOM_NS}}}summary")
                id_el      = entry.find(f"{{{_ATOM_NS}}}id")

                title   = title_el.text.strip()   if title_el   is not None else ""
                summary = summary_el.text.strip()  if summary_el is not None else ""
                url     = id_el.text.strip()       if id_el      is not None else ""

                if not summary:
                    continue

                excerpt = summary[:_MAX_EXCERPT]
                if len(summary) > _MAX_EXCERPT:
                    excerpt += "…"

                score = self._relevance(topic, title, summary)

                findings.append(ResearchFinding(
                    query_id        = query.query_id,
                    source          = SourceType.ARXIV,
                    title           = title,
                    url             = url,
                    excerpt         = excerpt,
                    quality         = FindingQuality.HIGH,
                    relevance_score = score,
                ))
            except Exception:
                continue

        return findings

    @staticmethod
    def _relevance(topic: str, title: str, summary: str) -> float:
        """Keyword overlap relevance: title carries more weight than abstract."""
        topic_words  = set(topic.lower().split())
        title_words  = set(title.lower().split())
        summary_words = set(summary.lower().split()[:150])

        title_overlap   = len(topic_words & title_words)   / max(len(topic_words), 1)
        summary_overlap = len(topic_words & summary_words) / max(len(topic_words), 1)

        return round(min(1.0, 0.7 * title_overlap + 0.3 * summary_overlap), 3)
