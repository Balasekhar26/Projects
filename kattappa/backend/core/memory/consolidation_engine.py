"""
backend/core/memory/consolidation_engine.py

Phase 1D: ConsolidationEngine — promotes transient working memories to episodic store.

Performs deduplication, Jaccard similarity clustering, promotion scoring, and purging
of working memory cache records.
"""

from __future__ import annotations

import json
import re
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

from .schemas import MemoryRecord, MemoryType
from .memory_manager import MemoryManager
from .working_memory_store import WorkingMemoryStore
from .episodic_memory_store import EpisodicMemoryStore


@dataclass
class ConsolidationReport:
    """Audit trail and statistics for a single consolidation run."""
    cycle_id: str = ""
    session_id: Optional[str] = None
    started_at: float = 0.0
    completed_at: float = 0.0
    duration_sec: float = 0.0
    scanned_count: int = 0
    promoted_count: int = 0
    discarded_count: int = 0
    merged_count: int = 0
    success: bool = True
    error: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "cycle_id": self.cycle_id,
            "session_id": self.session_id,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "duration_sec": round(self.duration_sec, 3),
            "scanned_count": self.scanned_count,
            "promoted_count": self.promoted_count,
            "discarded_count": self.discarded_count,
            "merged_count": self.merged_count,
            "success": self.success,
            "error": self.error,
        }


class ConsolidationEngine:
    """Evaluates working memories, merges duplicates, and promotes to episodic storage."""

    def __init__(
        self,
        memory_manager: Optional[MemoryManager] = None,
        working_store: Optional[WorkingMemoryStore] = None,
        episodic_store: Optional[EpisodicMemoryStore] = None,
    ) -> None:
        """
        Args:
            memory_manager: Registered MemoryManager (optional)
            working_store: WorkingMemoryStore instance (optional)
            episodic_store: EpisodicMemoryStore instance (optional)
        """
        self._working_store = working_store
        self._episodic_store = episodic_store

        if memory_manager is not None:
            if self._working_store is None:
                self._working_store = memory_manager.get_store(MemoryType.WORKING)
            if self._episodic_store is None:
                self._episodic_store = memory_manager.get_store(MemoryType.EPISODIC)

    def _get_stores(self) -> Tuple[WorkingMemoryStore, EpisodicMemoryStore]:
        if self._working_store is None or self._episodic_store is None:
            raise ValueError("ConsolidationEngine: both working and episodic stores must be registered.")
        return self._working_store, self._episodic_store

    @staticmethod
    def _token_jaccard(text1: str, text2: str) -> float:
        words1 = set(re.findall(r"\w+", text1.lower()))
        words2 = set(re.findall(r"\w+", text2.lower()))
        if not words1 or not words2:
            return 1.0 if text1.strip() == text2.strip() else 0.0
        return len(words1.intersection(words2)) / len(words1.union(words2))

    def _cluster_records(self, records: List[MemoryRecord], jaccard_threshold: float = 0.85) -> List[List[MemoryRecord]]:
        """Groups working memory records into similar clusters for duplicate merging."""
        clusters: List[List[MemoryRecord]] = []
        for r in records:
            # Check key match or content similarity Jaccard threshold
            placed = False
            for cluster in clusters:
                lead = cluster[0]
                # Match same session and goal
                lead_sess = lead.payload.get("session_id", "default")
                lead_goal = lead.payload.get("goal_id", "")
                r_sess = r.payload.get("session_id", "default")
                r_goal = r.payload.get("goal_id", "")

                if lead_sess != r_sess or lead_goal != r_goal:
                    continue

                lead_key = lead.payload.get("key") or ""
                r_key = r.payload.get("key") or ""
                lead_content = lead.payload.get("content") or lead.payload.get("text") or lead_key
                r_content = r.payload.get("content") or r.payload.get("text") or r_key

                # Key exact match OR fuzzy jaccard match on content
                if (lead_key and lead_key == r_key) or self._token_jaccard(lead_content, r_content) >= jaccard_threshold:
                    cluster.append(r)
                    placed = True
                    break
            if not placed:
                clusters.append([r])
        return clusters

    def consolidate(
        self,
        session_id: Optional[str] = None,
        promotion_threshold: float = 0.5,
        jaccard_threshold: float = 0.85,
    ) -> ConsolidationReport:
        """Runs a single consolidation cycle, moving eligible records to episodic storage."""
        now = time.time()
        report = ConsolidationReport(
            cycle_id=f"cycle_{uuid.uuid4().hex[:8]}",
            session_id=session_id,
            started_at=now,
        )

        try:
            working, episodic = self._get_stores()

            # 1. Retrieve candidate working records (including expired)
            query: Dict[str, Any] = {"include_expired": True}
            if session_id is not None:
                query["session_id"] = session_id
            candidates = working.retrieve(query, limit=1000)
            report.scanned_count = len(candidates)

            if not candidates:
                report.completed_at = time.time()
                report.duration_sec = report.completed_at - report.started_at
                return report

            # 2. Cluster for deduplication
            clusters = self._cluster_records(candidates, jaccard_threshold)

            for cluster in clusters:
                # Calculate aggregated metrics for the cluster
                lead = cluster[0]
                merged_count = len(cluster)
                if merged_count > 1:
                    report.merged_count += (merged_count - 1)

                importance = max(r.importance_score for r in cluster)
                confidence = max(r.confidence for r in cluster)
                access_count = sum(r.payload.get("access_count", 0) for r in cluster)
                # Keep the oldest created_at for proper recency math
                created_at = min(r.timestamp for r in cluster)
                
                # Combine tags
                all_tags: Set[str] = set()
                for r in cluster:
                    all_tags.update(r.tags)

                # Combine content summaries if multiple items exist
                lead_key = lead.payload.get("key") or ""
                lead_content = lead.payload.get("content") or lead.payload.get("text") or lead_key
                if merged_count > 1:
                    contents = []
                    for r in cluster:
                        c = r.payload.get("content") or r.payload.get("text") or r.payload.get("key") or ""
                        if c and c not in contents:
                            contents.append(c)
                    content = "\n".join(contents)
                else:
                    content = lead_content

                # Check if pinned (importance == 1.0 or explicit payload tag)
                is_pinned = any(
                    r.importance_score == 1.0 or 
                    r.payload.get("pinned") is True or 
                    r.payload.get("pinned") == "True"
                    for r in cluster
                )

                # Recency score calculation: decays based on time elapsed relative to 3h working TTL
                time_elapsed = max(0.0, now - created_at)
                recency_score = max(0.0, 1.0 - (time_elapsed / (3.0 * 3600.0)))
                access_frequency_score = min(1.0, access_count / 5.0)

                # Heuristic promotion formula
                promotion_score = (importance * 0.40) + (access_frequency_score * 0.25) + (recency_score * 0.15) + (confidence * 0.20)

                # Absolute promotion gates: score threshold OR pinned OR high interaction frequency
                should_promote = (
                    promotion_score >= promotion_threshold or
                    is_pinned or
                    access_count >= 5
                )

                if should_promote:
                    # Map to Episodic Memory Record
                    # Strip working-specific payload keys
                    clean_payload = {}
                    for r in cluster:
                        for k, v in r.payload.items():
                            if k not in ("key", "priority", "access_count", "expires_at"):
                                clean_payload[k] = v

                    clean_payload.update({
                        "title": lead_key or lead.payload.get("title") or "Consolidated Episode",
                        "content": content,
                        "consolidation_state": "ACTIVE",
                    })

                    episodic_record = MemoryRecord(
                        memory_id=lead.memory_id,
                        memory_type=MemoryType.EPISODIC,
                        timestamp=now,
                        source_agent=lead.source_agent,
                        confidence=confidence,
                        importance_score=importance,
                        tags=list(all_tags),
                        payload=clean_payload,
                    )

                    # Save to Episodic Store
                    episodic.save(episodic_record)
                    report.promoted_count += 1
                else:
                    report.discarded_count += 1

                # Clean working cache: delete all items in cluster
                for r in cluster:
                    working.delete(r.memory_id)

        except Exception as e:
            report.success = False
            report.error = str(e)

        report.completed_at = time.time()
        report.duration_sec = report.completed_at - report.started_at
        return report
