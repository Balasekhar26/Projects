"""
Kattappa Research Engine — Step 24
====================================
Scientist brain: searches, collects, and synthesizes external knowledge.

Pipeline position:
    ResearchEngine → Memory + ReflectionEngine + LearningEngine

Public API:
    from kattappa_runtime.research import ResearchEngine

    engine = ResearchEngine(
        memory=memory_provider,
        reflection_engine=reflection_engine,
        learning_engine=learning_engine,
    )
    report = engine.research("neural network attention mechanisms", domain="ml")
    print(report.summary)
    for fact in report.key_facts:
        print(" •", fact)
"""

from kattappa_runtime.research.engine      import ResearchEngine
from kattappa_runtime.research.schema      import (
    ResearchQuery, ResearchFinding, ResearchReport,
    SourceType, FindingQuality
)
from kattappa_runtime.research.store       import ResearchStore
from kattappa_runtime.research.synthesizer import ResearchSynthesizer

__all__ = [
    "ResearchEngine",
    "ResearchQuery",
    "ResearchFinding",
    "ResearchReport",
    "ResearchStore",
    "ResearchSynthesizer",
    "SourceType",
    "FindingQuality",
]
