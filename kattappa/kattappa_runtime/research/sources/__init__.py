"""
Sources package — exposes all adapters and the adapter registry.
"""

from kattappa_runtime.research.sources.base         import BaseSourceAdapter
from kattappa_runtime.research.sources.wikipedia    import WikipediaAdapter
from kattappa_runtime.research.sources.arxiv        import ArxivAdapter
from kattappa_runtime.research.sources.local_corpus import LocalCorpusAdapter
from kattappa_runtime.research.schema               import SourceType

from typing import Dict

# Registry: SourceType → adapter class
_REGISTRY: Dict[SourceType, type] = {
    SourceType.WIKIPEDIA: WikipediaAdapter,
    SourceType.ARXIV:     ArxivAdapter,
    SourceType.LOCAL:     LocalCorpusAdapter,
}


def get_adapter(source_type: SourceType) -> BaseSourceAdapter:
    """Instantiate and return the adapter for a given SourceType."""
    cls = _REGISTRY.get(source_type)
    if cls is None:
        raise ValueError(f"No adapter registered for source type: {source_type}")
    return cls()


__all__ = [
    "BaseSourceAdapter",
    "WikipediaAdapter",
    "ArxivAdapter",
    "LocalCorpusAdapter",
    "get_adapter",
]
