"""
Research Engine — Step 24 Core Implementation
==============================================

The Research Engine is Kattappa's "scientist brain." It:

  1. Accepts a research topic + domain
  2. Queries multiple sources in parallel-safe order (Wikipedia, Arxiv, Local)
  3. Synthesizes findings into a ResearchReport
  4. Promotes key facts into Semantic Memory (one fact per key_fact)
  5. Creates a Reflection on the research session
  6. Feeds the Reflection through the Learning Engine (if attached)
  7. Updates Skill Memory for the research domain
  8. Persists the full ResearchReport

This is the first engine that consumes ALL three previous engines:
  - Memory (writer.store_fact / store_episode)
  - ReflectionEngine (reflect on the research session itself)
  - LearningEngine (learn from what was found / not found)

Public API
----------
    from kattappa_runtime.research import ResearchEngine

    engine = ResearchEngine(
        memory=memory_provider,
        reflection_engine=reflection_engine,  # optional
        learning_engine=learning_engine,       # optional
    )
    report = engine.research("impedance matching RF circuits", domain="rf_systems")
    print(report.summary)
    print(report.key_facts)
"""

from __future__ import annotations

import concurrent.futures
from typing import Callable, List, Optional, TYPE_CHECKING

from kattappa_runtime.research.schema import (
    ResearchQuery, ResearchFinding, ResearchReport, SourceType
)
from kattappa_runtime.research.store       import ResearchStore
from kattappa_runtime.research.synthesizer import ResearchSynthesizer
from kattappa_runtime.research.sources     import get_adapter

if TYPE_CHECKING:
    from kattappa_runtime.memory            import MemoryProvider
    from kattappa_runtime.reflection.engine import ReflectionEngine
    from kattappa_runtime.learning.engine   import LearningEngine

# Sources queried when none are explicitly specified
_DEFAULT_SOURCES = [SourceType.WIKIPEDIA, SourceType.ARXIV, SourceType.LOCAL]

# Semantic memory subject prefix for research facts
_MEMORY_SUBJECT_PREFIX = "research"


class ResearchEngine:
    """
    Orchestrates multi-source research and feeds findings into Kattappa's
    memory, reflection, and learning systems.

    Parameters
    ----------
    memory : MemoryProvider
        Runtime memory. Facts are promoted via memory.writer.store_fact().
    reflection_engine : ReflectionEngine | None
        If provided, a Reflection is created after each research session.
    learning_engine : LearningEngine | None
        If provided, the Reflection is immediately processed to produce
        a LearningRecord.
    store : ResearchStore | None
        Custom store for testing. Default store used if None.
    synthesizer : ResearchSynthesizer | None
        Custom synthesizer (e.g. LLM-backed). Default used if None.
    max_workers : int
        Number of parallel threads for source fetching. Default 3.
    """

    def __init__(
        self,
        memory:            "MemoryProvider",
        reflection_engine: Optional["ReflectionEngine"] = None,
        learning_engine:   Optional["LearningEngine"]   = None,
        store:             Optional[ResearchStore]      = None,
        synthesizer:       Optional[ResearchSynthesizer] = None,
        max_workers:       int = 3,
    ):
        self.memory     = memory
        self.reflection = reflection_engine
        self.learning   = learning_engine
        self.store      = store or ResearchStore()
        self.synth      = synthesizer or ResearchSynthesizer()
        self._workers   = max_workers

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def research(
        self,
        topic:        str,
        domain:       str = "general",
        max_findings: int = 5,
        sources:      Optional[List[SourceType]] = None,
        notes:        str = "",
    ) -> ResearchReport:
        """
        Execute a research session on a topic.

        Parameters
        ----------
        topic : str
            What to research (e.g. "impedance matching RF circuits").
        domain : str
            Skill domain this research should update.
        max_findings : int
            Max findings to collect across all sources.
        sources : List[SourceType] | None
            Which sources to query. Defaults to Wikipedia + Arxiv + Local.
        notes : str
            Optional context about why this research is happening.

        Returns
        -------
        ResearchReport
            Synthesized report with summary, key_facts, and raw findings.
        """
        sources = sources or _DEFAULT_SOURCES

        # 1. Build query
        query = ResearchQuery(
            topic        = topic,
            domain       = domain,
            max_findings = max(1, max_findings // len(sources)),
            sources      = sources,
            notes        = notes,
        )

        # 2. Fetch from all sources (parallel)
        all_findings = self._fetch_all(query)

        # 3. Synthesize into report
        report = self.synth.synthesize(query, all_findings)

        # 4. Persist the report
        self.store.save(report)

        # 5. Promote key facts to semantic memory
        self._promote_to_memory(report)

        # 6. Reflect on the research session
        if self.reflection is not None:
            self._reflect_on_research(report)

        return report

    def get_reports_for_domain(self, domain: str) -> List[ResearchReport]:
        """Return all persisted research reports for a domain."""
        return self.store.get_by_domain(domain)

    def get_reports_for_topic(self, topic: str) -> List[ResearchReport]:
        """Return reports matching a topic substring."""
        return self.store.get_by_topic(topic)

    # ------------------------------------------------------------------
    # Private — fetching
    # ------------------------------------------------------------------

    def _fetch_all(self, query: ResearchQuery) -> List[ResearchFinding]:
        """
        Query all requested sources, collect findings.
        Uses a thread pool for parallel fetching — each adapter is
        already wrapped in a try/except so failures are silent.
        """
        all_findings: List[ResearchFinding] = []

        def fetch_one(source_type: SourceType) -> List[ResearchFinding]:
            adapter = get_adapter(source_type)
            return adapter.fetch(query)

        with concurrent.futures.ThreadPoolExecutor(max_workers=self._workers) as ex:
            futures = {ex.submit(fetch_one, s): s for s in query.sources}
            for future in concurrent.futures.as_completed(futures):
                try:
                    all_findings.extend(future.result())
                except Exception:
                    pass  # Individual source failures are non-fatal

        return all_findings

    # ------------------------------------------------------------------
    # Private — memory promotion
    # ------------------------------------------------------------------

    def _promote_to_memory(self, report: ResearchReport) -> None:
        """Store each key fact as a semantic memory entry."""
        for i, fact in enumerate(report.key_facts):
            subject  = f"{_MEMORY_SUBJECT_PREFIX}:{report.domain}:{report.topic[:40]}"
            relation = f"fact_{i+1}"
            self.memory.writer.store_fact(
                subject    = subject,
                relation   = relation,
                fact       = fact,
                confidence = report.confidence,
            )

        # Also log as an episode
        self.memory.writer.store_episode(
            event=(
                f"[Research] topic='{report.topic}' domain={report.domain} "
                f"| findings={len(report.findings)} | summary: {report.summary[:120]}"
            ),
            importance = 0.7,
            confidence = report.confidence,
        )

    # ------------------------------------------------------------------
    # Private — reflection integration
    # ------------------------------------------------------------------

    def _reflect_on_research(self, report: ResearchReport) -> None:
        """
        Create a Reflection on the research session and feed it through
        the Learning Engine if one is attached.
        """
        succeeded = len(report.findings) > 0 and report.confidence > 0.2

        reflection = self.reflection.reflect(
            input_text   = f"Research: {report.topic}",
            action_taken = (
                f"Queried {len(set(f.source for f in report.findings))} source(s), "
                f"retrieved {len(report.findings)} finding(s)"
            ),
            result       = report.summary[:200],
            domain       = report.domain,
            succeeded    = succeeded,
            partial      = (not succeeded and len(report.findings) > 0),
            notes        = f"report_id={report.report_id}",
        )

        # Feed through Learning Engine
        if self.learning is not None:
            self.learning.learn_from(reflection)
