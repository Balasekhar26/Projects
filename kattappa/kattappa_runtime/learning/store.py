"""
Learning Store — append + query JSONL persistence for LearningRecords.

All records are kept in a flat JSONL file. On read, we index them by:
  - domain
  - record_type
  - source_reflection_id

Deduplication: if the same (domain, knowledge) pair arrives again,
the existing record's frequency counter is incremented and confidence
is nudged upward — rather than creating a duplicate.
"""

from __future__ import annotations

import json
import os
from threading import Lock
from typing import Dict, List, Optional

from kattappa_runtime.learning.schema import LearningRecord, RecordType, LearningPriority

_DEFAULT_PATH = os.path.join(os.path.dirname(__file__), "learning_records.jsonl")

# Confidence bump when a duplicate lesson is reinforced
_REINFORCE_DELTA = 0.03
_MAX_CONFIDENCE  = 1.0


class LearningStore:
    """
    Append-only JSONL store for LearningRecords with in-memory index.

    Thread-safe. All writes go to disk immediately.
    """

    def __init__(self, path: str = _DEFAULT_PATH):
        self._path  = path
        self._lock  = Lock()
        # In-memory index: record_id → LearningRecord
        self._index: Dict[str, LearningRecord] = {}
        self._load()

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def save(self, record: LearningRecord) -> LearningRecord:
        """
        Persist a LearningRecord.

        If a record with the same (domain, knowledge) fingerprint already
        exists, the duplicate is merged: frequency++ and confidence nudged.
        Otherwise the record is appended as new.

        Returns the saved (possibly merged) record.
        """
        with self._lock:
            existing = self._find_duplicate(record)
            if existing:
                existing.frequency  += 1
                existing.confidence  = min(
                    _MAX_CONFIDENCE,
                    existing.confidence + _REINFORCE_DELTA
                )
                # Upgrade priority if the new record demands it
                if self._priority_rank(record.priority) > self._priority_rank(existing.priority):
                    existing.priority = record.priority
                self._rewrite_all()
                return existing
            else:
                self._index[record.record_id] = record
                self._append(record)
                return record

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def get_by_domain(self, domain: str) -> List[LearningRecord]:
        """Return all records for a given domain, sorted by importance desc."""
        with self._lock:
            results = [r for r in self._index.values() if r.domain == domain]
        return sorted(results, key=lambda r: r.importance, reverse=True)

    def get_by_type(self, record_type: RecordType) -> List[LearningRecord]:
        """Return all records of a given type."""
        with self._lock:
            return [r for r in self._index.values() if r.record_type == record_type]

    def get_skill_gaps(self, domain: Optional[str] = None) -> List[LearningRecord]:
        """Return skill gap records, optionally filtered by domain."""
        gaps = self.get_by_type(RecordType.SKILL_GAP)
        if domain:
            gaps = [r for r in gaps if r.domain == domain]
        return sorted(gaps, key=lambda r: r.importance, reverse=True)

    def get_all(self) -> List[LearningRecord]:
        """Return all records."""
        with self._lock:
            return list(self._index.values())

    def count(self) -> int:
        with self._lock:
            return len(self._index)

    def update_success_rate(self, record_id: str, observed_success: bool) -> Optional[LearningRecord]:
        """
        Update the success_rate for a record based on an observed application.

        Uses exponential moving average: new_rate = 0.8*old + 0.2*observation
        """
        with self._lock:
            record = self._index.get(record_id)
            if not record:
                return None
            observation = 1.0 if observed_success else 0.0
            if record.success_rate < 0:
                record.success_rate = observation
            else:
                record.success_rate = 0.8 * record.success_rate + 0.2 * observation
            self._rewrite_all()
            return record

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _find_duplicate(self, record: LearningRecord) -> Optional[LearningRecord]:
        """Check if a record with the same (domain, knowledge) already exists."""
        fingerprint = (record.domain.lower(), record.knowledge.lower().strip())
        for r in self._index.values():
            if (r.domain.lower(), r.knowledge.lower().strip()) == fingerprint:
                return r
        return None

    def _append(self, record: LearningRecord) -> None:
        with open(self._path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record.to_dict(), ensure_ascii=False) + "\n")

    def _rewrite_all(self) -> None:
        """Rewrite the entire file (used after in-place updates)."""
        with open(self._path, "w", encoding="utf-8") as f:
            for r in self._index.values():
                f.write(json.dumps(r.to_dict(), ensure_ascii=False) + "\n")

    def _load(self) -> None:
        if not os.path.exists(self._path):
            return
        with open(self._path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    r = LearningRecord.from_dict(json.loads(line))
                    self._index[r.record_id] = r
                except (json.JSONDecodeError, TypeError, KeyError):
                    continue

    @staticmethod
    def _priority_rank(p: LearningPriority) -> int:
        return {"low": 0, "medium": 1, "high": 2, "critical": 3}[p.value]
