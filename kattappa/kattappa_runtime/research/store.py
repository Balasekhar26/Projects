"""
Research Store — JSONL persistence for ResearchReports.

Indexes reports by:
  - report_id
  - domain
  - topic (fuzzy: lowercased, stripped)

Findings are stored inline within each report record.
"""

from __future__ import annotations

import json
import os
from threading import Lock
from typing import Dict, List, Optional

from kattappa_runtime.research.schema import ResearchReport

_DEFAULT_PATH = os.path.join(os.path.dirname(__file__), "research_reports.jsonl")


class ResearchStore:
    """Append-only JSONL store for ResearchReports with in-memory index."""

    def __init__(self, path: str = _DEFAULT_PATH):
        self._path  = path
        self._lock  = Lock()
        self._index: Dict[str, ResearchReport] = {}
        self._load()

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def save(self, report: ResearchReport) -> None:
        with self._lock:
            self._index[report.report_id] = report
            self._append(report)

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def get_by_id(self, report_id: str) -> Optional[ResearchReport]:
        with self._lock:
            return self._index.get(report_id)

    def get_by_domain(self, domain: str) -> List[ResearchReport]:
        with self._lock:
            return [r for r in self._index.values() if r.domain == domain]

    def get_by_topic(self, topic: str) -> List[ResearchReport]:
        """Case-insensitive topic substring search."""
        topic_lower = topic.lower()
        with self._lock:
            return [
                r for r in self._index.values()
                if topic_lower in r.topic.lower()
            ]

    def get_all(self) -> List[ResearchReport]:
        with self._lock:
            return list(self._index.values())

    def count(self) -> int:
        with self._lock:
            return len(self._index)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _append(self, report: ResearchReport) -> None:
        with open(self._path, "a", encoding="utf-8") as f:
            f.write(json.dumps(report.to_dict(), ensure_ascii=False) + "\n")

    def _load(self) -> None:
        if not os.path.exists(self._path):
            return
        with open(self._path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    r = ResearchReport.from_dict(json.loads(line))
                    self._index[r.report_id] = r
                except (json.JSONDecodeError, TypeError, KeyError):
                    continue
