"""
Learning Engine — Step 22 Core Implementation
==============================================

The Learning Engine converts Reflections into durable LearningRecords
and updates Skill Memory. It sits directly downstream of the Reflection
Engine in the cognitive pipeline:

    Experience
        ↓ ReflectionEngine
    Reflection (what happened + lesson)
        ↓ LearningEngine.learn_from()
    LearningRecord (distilled knowledge)
        ↓
    LearningStore  ←→  Semantic Memory
    SkillMemory         (long-term facts)

Algorithm
---------
1.  Receive a Reflection.
2.  Run the LessonExtractor to determine RecordType and priority.
3.  Distil a `knowledge` statement from the lesson.
4.  Build a LearningRecord.
5.  Save to LearningStore (deduplication + reinforcement merging handled there).
6.  Promote the knowledge into semantic memory.
7.  If a SkillMemory is attached, apply the skill update.
8.  Return the LearningRecord.

Public API
----------
    from kattappa_runtime.learning import LearningEngine

    engine = LearningEngine(memory_provider, skill_memory)
    record = engine.learn_from(reflection)
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional, TYPE_CHECKING

from kattappa_runtime.reflection.schema import Reflection, OutcomeLabel
from kattappa_runtime.learning.schema import (
    LearningRecord,
    LearningPriority,
    RecordType,
)
from kattappa_runtime.learning.store import LearningStore

if TYPE_CHECKING:
    from kattappa_runtime.memory import MemoryProvider
    from kattappa_runtime.skill_memory.store import SkillMemory


# -------------------------------------------------------------------------
# Priority mapping from outcome → default priority
# -------------------------------------------------------------------------
_OUTCOME_PRIORITY: dict[OutcomeLabel, LearningPriority] = {
    OutcomeLabel.SUCCESS: LearningPriority.LOW,
    OutcomeLabel.PARTIAL: LearningPriority.MEDIUM,
    OutcomeLabel.FAILURE: LearningPriority.HIGH,
}

# Importance weights per outcome
_OUTCOME_IMPORTANCE: dict[OutcomeLabel, float] = {
    OutcomeLabel.SUCCESS: 0.4,
    OutcomeLabel.PARTIAL: 0.6,
    OutcomeLabel.FAILURE: 0.85,
}

# Next review interval per priority (days from now)
_REVIEW_DAYS: dict[LearningPriority, int] = {
    LearningPriority.CRITICAL: 1,
    LearningPriority.HIGH:     3,
    LearningPriority.MEDIUM:   7,
    LearningPriority.LOW:      30,
}


class LearningEngine:
    """
    Converts Reflections into durable LearningRecords and updates Skill Memory.

    Parameters
    ----------
    memory : MemoryProvider
        The runtime memory system (for semantic memory promotion).
    skill_memory : SkillMemory | None
        Optional Skill Memory store (Step 23). If provided, every learning
        event will update the corresponding skill's stats.
    store : LearningStore | None
        Optional pre-built store (useful for testing). A default one is
        created if not provided.
    knowledge_distiller : Callable[[Reflection], str] | None
        Optional LLM-backed hook to produce a distilled `knowledge` string
        from a Reflection. Falls back to rule-based if not provided.
    """

    def __init__(
        self,
        memory: "MemoryProvider",
        skill_memory: Optional["SkillMemory"] = None,
        store: Optional[LearningStore] = None,
        knowledge_distiller: Optional[Callable[[Reflection], str]] = None,
    ):
        self.memory     = memory
        self.skill_mem  = skill_memory
        self.store      = store or LearningStore()
        self._distiller = knowledge_distiller

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def learn_from_reflection(self, reflection: Reflection) -> LearningRecord:
        """
        Wire reflection outcomes back into long-term memory.
        """
        return self.learn_from(reflection)

    def learn_from(self, reflection: Reflection) -> LearningRecord:
        """
        Derive a LearningRecord from a completed Reflection.

        Parameters
        ----------
        reflection : Reflection
            A fully built Reflection from the ReflectionEngine.

        Returns
        -------
        LearningRecord
            The saved (possibly reinforced) learning record.
        """
        # 1. Classify record type
        record_type = self._classify_type(reflection)

        # 2. Determine priority and importance
        priority   = self._determine_priority(reflection, record_type)
        importance = _OUTCOME_IMPORTANCE[reflection.outcome]

        # 3. Distil knowledge statement
        knowledge = self._distil_knowledge(reflection)

        # 4. Compute next review timestamp
        next_review = self._next_review(priority)

        # 5. Build record
        record = LearningRecord(
            source_reflection_id = reflection.reflection_id,
            domain               = reflection.domain,
            record_type          = record_type,
            lesson               = reflection.lesson,
            knowledge            = knowledge,
            priority             = priority,
            confidence           = max(0.0, min(1.0, reflection.confidence_delta + 0.6)),
            importance           = importance,
            next_review          = next_review,
            notes                = reflection.notes,
        )

        # 6. Save (deduplication + reinforcement handled in store)
        record = self.store.save(record)

        # 7. Promote to semantic memory
        self._promote_to_memory(record)

        # 8. Update Skill Memory (Step 23 integration)
        if self.skill_mem is not None:
            self._update_skill_memory(reflection, record)

        return record

    def get_knowledge_gaps(self, domain: Optional[str] = None):
        """Return current skill gaps, optionally filtered by domain."""
        return self.store.get_skill_gaps(domain=domain)

    def get_domain_knowledge(self, domain: str):
        """Return all learning records for a domain."""
        return self.store.get_by_domain(domain)

    def record_application(self, record_id: str, succeeded: bool) -> None:
        """
        Notify the engine that a learning record was applied and whether
        it succeeded. Updates the record's success_rate.
        """
        self.store.update_success_rate(record_id, succeeded)

    # ------------------------------------------------------------------
    # Private — classification & distillation
    # ------------------------------------------------------------------

    @staticmethod
    def _classify_type(r: Reflection) -> RecordType:
        """
        Classify what type of learning record this reflection produces.

        Rules (in priority order):
          SKILL_GAP  → failure whose lesson mentions "understanding", "insufficient",
                        "missing", "gap", "don't know", "unknown"
          SKILL_WIN  → success with high-confidence lesson
          RULE       → lesson contains "always", "never", "must", "should", "avoid"
          PATTERN    → partial with a recurring-sounding lesson
          KNOWLEDGE  → default catch-all
        """
        lesson_lower = r.lesson.lower()

        gap_keywords  = {"understanding", "insufficient", "missing", "gap",
                         "don't know", "unknown", "lack", "unfamiliar"}
        rule_keywords = {"always", "never", "must", "should", "avoid",
                         "do not", "require", "ensure", "first"}

        if r.outcome == OutcomeLabel.FAILURE:
            if any(kw in lesson_lower for kw in gap_keywords):
                return RecordType.SKILL_GAP
            return RecordType.RULE  # Failure → learn a rule about what NOT to do

        if r.outcome == OutcomeLabel.SUCCESS:
            if any(kw in lesson_lower for kw in rule_keywords):
                return RecordType.RULE
            return RecordType.SKILL_WIN

        if r.outcome == OutcomeLabel.PARTIAL:
            if any(kw in lesson_lower for kw in rule_keywords):
                return RecordType.RULE
            return RecordType.PATTERN

        return RecordType.KNOWLEDGE

    @staticmethod
    def _determine_priority(r: Reflection, record_type: RecordType) -> LearningPriority:
        """Determine priority. Skill gaps are always at least HIGH."""
        base = _OUTCOME_PRIORITY[r.outcome]
        if record_type == RecordType.SKILL_GAP:
            # Upgrade to at least HIGH
            rank = {"low": 0, "medium": 1, "high": 2, "critical": 3}
            if rank[base.value] < rank[LearningPriority.HIGH.value]:
                return LearningPriority.HIGH
        return base

    def _distil_knowledge(self, r: Reflection) -> str:
        """
        Produce a concise, durable knowledge statement.
        Delegates to LLM hook if available; falls back to rule-based.
        """
        if self._distiller:
            try:
                result = self._distiller(r)
                if result and isinstance(result, str):
                    return result.strip()
            except Exception:
                pass

        return self._rule_based_distil(r)

    @staticmethod
    def _rule_based_distil(r: Reflection) -> str:
        """
        Rule-based knowledge distillation.

        Turns a lesson string into a terse, imperative knowledge statement.
        """
        lesson = r.lesson.strip()
        # Strip leading "In domain 'X'," boilerplate from the ReflectionEngine
        lesson = re.sub(r"^In domain '[^']+',\s*", "", lesson)

        if r.outcome == OutcomeLabel.FAILURE:
            return f"[{r.domain.upper()} GAP] {lesson}"
        if r.outcome == OutcomeLabel.PARTIAL:
            return f"[{r.domain.upper()} PATTERN] {lesson}"
        return f"[{r.domain.upper()}] {lesson}"

    # ------------------------------------------------------------------
    # Private — persistence
    # ------------------------------------------------------------------

    def _promote_to_memory(self, record: LearningRecord) -> None:
        """Write the knowledge into semantic memory for long-term retention."""
        subject  = f"learning:{record.domain}:{record.record_type.value}"
        relation = f"record_{record.record_id[:8]}"
        self.memory.writer.store_fact(
            subject    = subject,
            relation   = relation,
            fact       = record.knowledge,
            confidence = record.confidence,
        )

    def _update_skill_memory(self, r: Reflection, record: LearningRecord) -> None:
        """Update Skill Memory with the outcome of this learning event."""
        succeeded = (r.outcome == OutcomeLabel.SUCCESS)
        self.skill_mem.record_attempt(
            domain    = r.domain,
            succeeded = succeeded,
            confidence_delta = r.confidence_delta,
        )
        if record.record_type == RecordType.SKILL_GAP:
            self.skill_mem.add_weakness(r.domain, record.knowledge)

    # ------------------------------------------------------------------
    # Private — utilities
    # ------------------------------------------------------------------

    @staticmethod
    def _next_review(priority: LearningPriority) -> str:
        days   = _REVIEW_DAYS[priority]
        review = datetime.now(timezone.utc) + timedelta(days=days)
        return review.isoformat()
