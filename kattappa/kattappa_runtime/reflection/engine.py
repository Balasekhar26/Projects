"""
Reflection Engine — Step 21 Core Implementation
================================================

This engine takes a completed action cycle and produces a structured
Reflection, then persists it into memory and confidence state.

Algorithm
---------
1.  Determine OutcomeLabel from the `succeeded` flag and optional
    `partial` hint.
2.  Compute confidence_delta:
      SUCCESS  → +0.05  (small reward, prevents runaway overconfidence)
      PARTIAL  → -0.02  (soft penalty)
      FAILURE  → -0.10  (strong signal something went wrong)
3.  Generate a one-sentence lesson using a template approach
    (rule-based, no LLM dependency; an LLM-augmented version can be
    plugged in later via the `lesson_generator` hook).
4.  Build the Reflection object.
5.  Write the Reflection into episodic memory (always).
6.  If outcome == SUCCESS and the lesson is substantive, also promote
    it as a semantic fact so it survives consolidation.
7.  Log mistake to MistakeLog if is_mistake=True.
8.  Update ConfidenceTracker for the domain.
9.  Return the Reflection to the caller.
"""

from __future__ import annotations

import re
from typing import Callable, Optional, TYPE_CHECKING

from kattappa_runtime.reflection.schema import Reflection, OutcomeLabel
from kattappa_runtime.reflection.confidence import ConfidenceTracker
from kattappa_runtime.reflection.mistake_log import MistakeLog

if TYPE_CHECKING:
    # Avoid circular imports; we only need the type at annotation time.
    from kattappa_runtime.memory import MemoryProvider

# Confidence deltas per outcome (tunable)
_DELTA: dict[OutcomeLabel, float] = {
    OutcomeLabel.SUCCESS: +0.05,
    OutcomeLabel.PARTIAL: -0.02,
    OutcomeLabel.FAILURE: -0.10,
}

# Maximum characters to store in episodic memory from long result strings
_MAX_RESULT_CHARS = 300


class ReflectionEngine:
    """
    Produces structured Reflection records from completed action cycles.

    Parameters
    ----------
    memory : MemoryProvider
        The runtime's memory system. Must expose `.writer.store_episode()`
        and `.writer.store_fact()`.
    confidence_tracker : ConfidenceTracker | None
        Optional shared tracker. A new one is created if not provided.
    mistake_log : MistakeLog | None
        Optional shared mistake log. A new one is created if not provided.
    lesson_generator : Callable[[Reflection], str] | None
        Optional hook to replace the built-in rule-based lesson generator
        with an LLM-backed generator. Receives the partially built
        Reflection (lesson field is empty at call time) and returns a
        one-sentence lesson string.
    """

    def __init__(
        self,
        memory: "MemoryProvider",
        confidence_tracker: Optional[ConfidenceTracker] = None,
        mistake_log: Optional[MistakeLog] = None,
        lesson_generator: Optional[Callable[["Reflection"], str]] = None,
    ):
        self.memory = memory
        self.confidence = confidence_tracker or ConfidenceTracker()
        self.mistakes = mistake_log or MistakeLog()
        self._lesson_generator = lesson_generator

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def reflect(
        self,
        input_text: str,
        action_taken: str,
        result: str,
        domain: str = "general",
        succeeded: bool = True,
        partial: bool = False,
        notes: str = "",
    ) -> Reflection:
        """
        Analyse one completed action cycle and return a persisted Reflection.

        Parameters
        ----------
        input_text : str
            The original user request or goal description.
        action_taken : str
            What Kattappa actually did (tool call, reasoning step, etc.).
        result : str
            The observable output or outcome of the action.
        domain : str
            Skill domain involved (e.g. "translation", "code", "reasoning").
        succeeded : bool
            True if the action fully achieved its goal.
        partial : bool
            True if the action partially achieved its goal (overrides
            `succeeded=True` → marks as PARTIAL, not SUCCESS).
        notes : str
            Optional extra context (e.g. error messages, timing info).

        Returns
        -------
        Reflection
            The fully built and persisted reflection record.
        """
        # 1. Classify outcome
        outcome = self._classify_outcome(succeeded, partial)

        # 2. Compute confidence delta
        delta = _DELTA[outcome]

        # 3. Build partial Reflection (lesson empty for now)
        reflection = Reflection(
            domain=domain,
            input_text=input_text,
            action_taken=action_taken,
            result=result[:_MAX_RESULT_CHARS],
            outcome=outcome,
            confidence_delta=delta,
            is_mistake=(outcome != OutcomeLabel.SUCCESS),
            notes=notes,
        )

        # 4. Generate lesson (fills reflection.lesson)
        reflection.lesson = self._generate_lesson(reflection)

        # 5. Persist to episodic memory
        self._write_to_episodic(reflection)

        # 6. Promote lesson to semantic memory if worth keeping
        if outcome == OutcomeLabel.SUCCESS and reflection.lesson:
            self._promote_lesson(reflection)

        # 7. Log mistakes
        self.mistakes.record(reflection)

        # 8. Update confidence
        self.confidence.update(domain, delta)

        return reflection

    def get_confidence(self, domain: str) -> float:
        """Query current confidence score for a domain."""
        return self.confidence.get(domain)

    def recent_mistakes(self, limit: int = 10):
        """Return the most recent `limit` mistakes."""
        all_mistakes = self.mistakes.load_all()
        return all_mistakes[-limit:]

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _classify_outcome(succeeded: bool, partial: bool) -> OutcomeLabel:
        if succeeded and not partial:
            return OutcomeLabel.SUCCESS
        if partial or (succeeded and partial):
            return OutcomeLabel.PARTIAL
        return OutcomeLabel.FAILURE

    def _generate_lesson(self, r: Reflection) -> str:
        """
        Generate a one-sentence lesson from the reflection.
        Delegates to the optional LLM hook if provided; otherwise uses
        rule-based templates.
        """
        if self._lesson_generator:
            try:
                lesson = self._lesson_generator(r)
                if lesson and isinstance(lesson, str):
                    return lesson.strip()
            except Exception:
                pass  # Fallback to rule-based on error

        return self._rule_based_lesson(r)

    @staticmethod
    def _rule_based_lesson(r: Reflection) -> str:
        """
        Derive a simple lesson string using pattern templates.

        Templates are intentionally terse — they capture the essence
        of what happened without over-fitting to exact phrasing.
        """
        domain = r.domain
        action_short = _shorten(r.action_taken, 60)
        result_short  = _shorten(r.result, 80)

        if r.outcome == OutcomeLabel.SUCCESS:
            return (
                f"In domain '{domain}', '{action_short}' successfully "
                f"produced '{result_short}'."
            )
        if r.outcome == OutcomeLabel.PARTIAL:
            return (
                f"In domain '{domain}', '{action_short}' only partially "
                f"achieved the goal; result was '{result_short}'."
            )
        # FAILURE
        return (
            f"In domain '{domain}', '{action_short}' failed; "
            f"result was '{result_short}'. Avoid or revise this approach."
        )

    def _write_to_episodic(self, r: Reflection) -> None:
        """Persist the reflection as a structured episode."""
        importance = {
            OutcomeLabel.SUCCESS: 0.6,
            OutcomeLabel.PARTIAL: 0.7,
            OutcomeLabel.FAILURE: 0.9,  # Failures are more important to remember
        }[r.outcome]

        event_text = (
            f"[Reflection:{r.outcome.value.upper()}] "
            f"domain={r.domain} | "
            f"action={_shorten(r.action_taken, 80)} | "
            f"lesson={r.lesson}"
        )

        self.memory.writer.store_episode(
            event=event_text,
            importance=importance,
            confidence=self.confidence.get(r.domain),
        )

    def _promote_lesson(self, r: Reflection) -> None:
        """Promote a successful lesson as a long-term semantic fact."""
        subject = f"lesson:{r.domain}"
        relation = "learned_from_success"
        self.memory.writer.store_fact(
            subject=subject,
            relation=relation,
            fact=r.lesson,
            confidence=self.confidence.get(r.domain),
        )


# ------------------------------------------------------------------
# Utility
# ------------------------------------------------------------------

def _shorten(text: str, max_chars: int) -> str:
    """Trim a string to max_chars, appending '…' if truncated."""
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= max_chars:
        return text
    return text[:max_chars - 1] + "…"
