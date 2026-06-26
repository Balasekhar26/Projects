"""
Research Engine Schema — Step 24
=================================
Data structures for the Research Engine's input/output pipeline.

ResearchQuery   → what to search for
ResearchFinding → one piece of retrieved evidence from one source
ResearchReport  → synthesized final output from all findings on a query
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional


class SourceType(str, Enum):
    """Where a research finding came from."""
    WIKIPEDIA   = "wikipedia"
    ARXIV       = "arxiv"
    LOCAL       = "local_corpus"
    WEB         = "web"
    MANUAL      = "manual"   # user-injected finding


class FindingQuality(str, Enum):
    """Assessed quality of a retrieved finding."""
    HIGH    = "high"      # authoritative, well-structured
    MEDIUM  = "medium"    # useful but may need verification
    LOW     = "low"       # noisy, partial, or uncertain


@dataclass
class ResearchQuery:
    """
    A research request submitted to the Research Engine.

    Fields
    ------
    query_id : str
        UUID4 identifier.
    topic : str
        The subject to research (e.g. "impedance matching RF circuits").
    domain : str
        Skill domain this research should update (e.g. "rf_systems").
    max_findings : int
        Maximum number of findings to retrieve across all sources.
    sources : List[SourceType]
        Which sources to query. Default: all available.
    timestamp : str
        ISO-8601 UTC creation timestamp.
    notes : str
        Optional context about why this research is being done.
    """
    query_id:     str              = field(default_factory=lambda: str(uuid.uuid4()))
    topic:        str              = ""
    domain:       str              = "general"
    max_findings: int              = 5
    sources:      List[SourceType] = field(
        default_factory=lambda: [SourceType.WIKIPEDIA, SourceType.ARXIV]
    )
    timestamp:    str              = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    notes:        str              = ""

    def to_dict(self) -> dict:
        return {
            "query_id":     self.query_id,
            "topic":        self.topic,
            "domain":       self.domain,
            "max_findings": self.max_findings,
            "sources":      [s.value for s in self.sources],
            "timestamp":    self.timestamp,
            "notes":        self.notes,
        }


@dataclass
class ResearchFinding:
    """
    One retrieved piece of evidence from one source.

    Fields
    ------
    finding_id : str
        UUID4 identifier.
    query_id : str
        The query that triggered this finding.
    source : SourceType
        Where this came from.
    title : str
        Title of the source document/article.
    url : str
        URL or reference path for the source.
    excerpt : str
        Relevant extracted text (trimmed to max ~1000 chars).
    quality : FindingQuality
        Assessed quality of this finding.
    relevance_score : float
        Estimated relevance to the query topic. [0.0 – 1.0]
    timestamp : str
        ISO-8601 UTC timestamp of retrieval.
    """
    finding_id:      str            = field(default_factory=lambda: str(uuid.uuid4()))
    query_id:        str            = ""
    source:          SourceType     = SourceType.MANUAL
    title:           str            = ""
    url:             str            = ""
    excerpt:         str            = ""
    quality:         FindingQuality = FindingQuality.MEDIUM
    relevance_score: float          = 0.5
    timestamp:       str            = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict:
        return {
            "finding_id":      self.finding_id,
            "query_id":        self.query_id,
            "source":          self.source.value,
            "title":           self.title,
            "url":             self.url,
            "excerpt":         self.excerpt,
            "quality":         self.quality.value,
            "relevance_score": self.relevance_score,
            "timestamp":       self.timestamp,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ResearchFinding":
        d = dict(d)
        d["source"]  = SourceType(d.get("source", "manual"))
        d["quality"] = FindingQuality(d.get("quality", "medium"))
        return cls(**d)


@dataclass
class ResearchReport:
    """
    Synthesized output from all findings collected for a query.

    Fields
    ------
    report_id : str
        UUID4 identifier.
    query_id : str
        The query this report answers.
    topic : str
        The original research topic.
    domain : str
        Skill domain being researched.
    summary : str
        Synthesized 1–3 sentence summary of findings.
    key_facts : List[str]
        Bullet-point distilled facts ready for memory promotion.
    findings : List[ResearchFinding]
        All raw findings that fed this report.
    confidence : float
        Aggregate confidence in the report's accuracy. [0.0 – 1.0]
    timestamp : str
        ISO-8601 UTC creation timestamp.
    """
    report_id:  str                    = field(default_factory=lambda: str(uuid.uuid4()))
    query_id:   str                    = ""
    topic:      str                    = ""
    domain:     str                    = "general"
    summary:    str                    = ""
    key_facts:  List[str]              = field(default_factory=list)
    findings:   List[ResearchFinding]  = field(default_factory=list)
    confidence: float                  = 0.5
    timestamp:  str                    = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict:
        return {
            "report_id":  self.report_id,
            "query_id":   self.query_id,
            "topic":      self.topic,
            "domain":     self.domain,
            "summary":    self.summary,
            "key_facts":  self.key_facts,
            "findings":   [f.to_dict() for f in self.findings],
            "confidence": self.confidence,
            "timestamp":  self.timestamp,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ResearchReport":
        d = dict(d)
        findings_raw = d.pop("findings", [])
        report = cls(**d)
        report.findings = [ResearchFinding.from_dict(f) for f in findings_raw]
        return report
