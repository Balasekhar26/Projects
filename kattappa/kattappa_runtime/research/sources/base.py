"""
Base class for all Research Engine source adapters.

A source adapter:
  1. Accepts a ResearchQuery
  2. Fetches data from its specific source (Wikipedia, Arxiv, etc.)
  3. Returns a List[ResearchFinding]
  4. NEVER raises — errors are caught and returned as empty lists

All network calls use a configurable timeout to prevent blocking.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List

from kattappa_runtime.research.schema import ResearchQuery, ResearchFinding

# Default network timeout (seconds)
DEFAULT_TIMEOUT = 8


class BaseSourceAdapter(ABC):
    """Abstract base for all research source adapters."""

    source_name: str = "unknown"

    def fetch(self, query: ResearchQuery) -> List[ResearchFinding]:
        """
        Public entry point. Wraps _fetch() in a broad try/except so
        a broken adapter never crashes the Research Engine.
        """
        try:
            return self._fetch(query)
        except Exception:
            return []

    @abstractmethod
    def _fetch(self, query: ResearchQuery) -> List[ResearchFinding]:
        """Subclasses implement actual retrieval here."""
        ...
