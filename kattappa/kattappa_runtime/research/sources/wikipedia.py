"""
Wikipedia Source Adapter
========================
Uses the Wikipedia REST API (no API key required):
    https://en.wikipedia.org/api/rest_v1/page/summary/{title}
    https://en.wikipedia.org/w/api.php?action=opensearch (for topic → title)

Two-stage retrieval:
  1. OpenSearch → find the best matching article title
  2. REST summary → fetch the extract (first ~2000 chars of article)

Falls back gracefully if network unavailable.
"""

from __future__ import annotations

import urllib.parse
import urllib.request
import json
from typing import List

from kattappa_runtime.research.schema import (
    ResearchQuery, ResearchFinding, SourceType, FindingQuality
)
from kattappa_runtime.research.sources.base import BaseSourceAdapter, DEFAULT_TIMEOUT

_SEARCH_URL  = "https://en.wikipedia.org/w/api.php"
_SUMMARY_URL = "https://en.wikipedia.org/api/rest_v1/page/summary/{title}"
_MAX_EXCERPT = 1200   # chars to keep from the Wikipedia extract


class WikipediaAdapter(BaseSourceAdapter):
    """Retrieves a Wikipedia summary for the best-matching article."""

    source_name = "wikipedia"

    def _fetch(self, query: ResearchQuery) -> List[ResearchFinding]:
        topic = query.topic.strip()
        if not topic:
            return []

        # --- Step 1: OpenSearch for best title ---
        params = urllib.parse.urlencode({
            "action":  "opensearch",
            "search":  topic,
            "limit":   3,
            "format":  "json",
            "redirects": "resolve",
        })
        search_req = urllib.request.Request(
            f"{_SEARCH_URL}?{params}",
            headers={"User-Agent": "KattappaResearchEngine/1.0"},
        )
        with urllib.request.urlopen(search_req, timeout=DEFAULT_TIMEOUT) as resp:
            search_data = json.loads(resp.read().decode("utf-8"))

        titles = search_data[1] if len(search_data) > 1 else []
        if not titles:
            return []

        findings: List[ResearchFinding] = []

        # --- Step 2: Fetch summary for each title (up to max_findings) ---
        for title in titles[: query.max_findings]:
            try:
                encoded_title = urllib.parse.quote(title.replace(" ", "_"))
                summary_req = urllib.request.Request(
                    _SUMMARY_URL.format(title=encoded_title),
                    headers={"User-Agent": "KattappaResearchEngine/1.0"},
                )
                with urllib.request.urlopen(summary_req, timeout=DEFAULT_TIMEOUT) as resp:
                    article = json.loads(resp.read().decode("utf-8"))

                extract = article.get("extract", "").strip()
                if not extract:
                    continue

                # Trim excerpt
                excerpt = extract[:_MAX_EXCERPT]
                if len(extract) > _MAX_EXCERPT:
                    excerpt += "…"

                url   = article.get("content_urls", {}).get("desktop", {}).get("page", "")
                score = self._relevance(topic, title, extract)

                findings.append(ResearchFinding(
                    query_id        = query.query_id,
                    source          = SourceType.WIKIPEDIA,
                    title           = title,
                    url             = url,
                    excerpt         = excerpt,
                    quality         = FindingQuality.HIGH,
                    relevance_score = score,
                ))
            except Exception:
                continue  # Skip failed individual article, try next

        return findings

    @staticmethod
    def _relevance(topic: str, title: str, extract: str) -> float:
        """Simple keyword overlap relevance score."""
        topic_words = set(topic.lower().split())
        title_words = set(title.lower().split())
        text_words  = set(extract.lower().split()[:200])

        title_overlap = len(topic_words & title_words) / max(len(topic_words), 1)
        text_overlap  = len(topic_words & text_words)  / max(len(topic_words), 1)

        return round(min(1.0, 0.6 * title_overlap + 0.4 * text_overlap), 3)
