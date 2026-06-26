"""
Pattern Miner — analyses mistakes + learning records to find weaknesses.

Inputs:
  - List[Reflection]   from MistakeLog
  - List[LearningRecord] from LearningStore (SKILL_GAP records)
  - SkillMemory         for attempt/success_rate data

Algorithm per domain:
  1. Count failures and partials
  2. Pull success_rate from SkillMemory (authoritative)
  3. Collect top 3 lessons (by frequency in mistakes)
  4. Collect knowledge gaps from LearningStore
  5. Compute weakness_score:
       w = 0.5 * failure_rate
         + 0.3 * gap_density       (gaps / attempts)
         + 0.2 * recency_weight    (recent failures count more)
     clamp to [0.0, 1.0]
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Dict, List, Optional, TYPE_CHECKING

from kattappa_runtime.reflection.schema    import Reflection, OutcomeLabel
from kattappa_runtime.learning.schema      import LearningRecord, RecordType
from kattappa_runtime.self_improvement.schema import DomainWeakness

if TYPE_CHECKING:
    from kattappa_runtime.skill_memory.store import SkillMemory

# Minimum failures before a domain is considered for weakness detection
MIN_FAILURES = 2

# How many hours back is considered "recent" for recency weighting
RECENT_HOURS = 48


class PatternMiner:
    """
    Mines mistake patterns across domains to produce DomainWeakness objects.

    Parameters
    ----------
    skill_memory : SkillMemory | None
        If provided, actual attempt counts and success rates are pulled
        from SkillMemory for more accurate failure_rate computation.
    """

    def __init__(self, skill_memory: Optional["SkillMemory"] = None):
        self.skill_mem = skill_memory

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def mine(
        self,
        mistakes:        List[Reflection],
        learning_gaps:   List[LearningRecord],
    ) -> List[DomainWeakness]:
        """
        Produce a sorted list of DomainWeakness objects (weakest first).

        Parameters
        ----------
        mistakes : List[Reflection]
            All is_mistake=True reflections from MistakeLog.
        learning_gaps : List[LearningRecord]
            SKILL_GAP records from LearningStore.

        Returns
        -------
        List[DomainWeakness]
            Sorted by weakness_score descending (weakest domain first).
        """
        # Group mistakes by domain
        by_domain: Dict[str, List[Reflection]] = defaultdict(list)
        for m in mistakes:
            by_domain[m.domain].append(m)

        # Build gap index
        gaps_by_domain: Dict[str, List[str]] = defaultdict(list)
        for gap in learning_gaps:
            if gap.record_type == RecordType.SKILL_GAP:
                gaps_by_domain[gap.domain].append(gap.knowledge)

        weaknesses = []
        for domain, domain_mistakes in by_domain.items():
            if len(domain_mistakes) < MIN_FAILURES:
                continue
            weakness = self._analyse_domain(domain, domain_mistakes, gaps_by_domain.get(domain, []))
            weaknesses.append(weakness)

        # Sort: most critical first
        return sorted(weaknesses, key=lambda w: w.weakness_score, reverse=True)

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    def _analyse_domain(
        self,
        domain:          str,
        mistakes:        List[Reflection],
        knowledge_gaps:  List[str],
    ) -> DomainWeakness:
        failures = [m for m in mistakes if m.outcome == OutcomeLabel.FAILURE]
        partials = [m for m in mistakes if m.outcome == OutcomeLabel.PARTIAL]

        # Pull authoritative stats from SkillMemory if available
        total_attempts = len(mistakes)
        if self.skill_mem:
            profile = self.skill_mem.get(domain)
            if profile and profile.attempts > 0:
                total_attempts = profile.attempts

        failure_rate = len(failures) / max(total_attempts, 1)

        # Top lessons from mistake texts (most common keywords)
        lesson_texts = [m.lesson for m in mistakes if m.lesson]
        top_lessons  = self._top_phrases(lesson_texts, n=3)

        # Knowledge gaps (deduplicated)
        unique_gaps = list(dict.fromkeys(knowledge_gaps))[:5]

        # Gap density
        gap_density = len(unique_gaps) / max(total_attempts, 1)

        # Recency weight: fraction of mistakes in last RECENT_HOURS
        recency_weight = self._recency_weight(mistakes)

        # Composite weakness score
        score = (
            0.50 * min(1.0, failure_rate)
            + 0.30 * min(1.0, gap_density * 3)   # scale: 1 gap per 3 attempts = max
            + 0.20 * recency_weight
        )
        score = round(min(1.0, score), 4)

        return DomainWeakness(
            domain             = domain,
            failure_count      = len(failures),
            partial_count      = len(partials),
            total_attempts     = total_attempts,
            failure_rate       = round(failure_rate, 4),
            top_lessons        = top_lessons,
            top_knowledge_gaps = unique_gaps,
            weakness_score     = score,
        )

    @staticmethod
    def _top_phrases(texts: List[str], n: int = 3) -> List[str]:
        """
        Extract the n most-mentioned meaningful 2–3 word phrases across texts.
        Falls back to returning the first n lesson strings if phrase extraction
        yields nothing meaningful.
        """
        stop = {"the", "a", "an", "in", "of", "for", "on", "and", "to",
                "was", "is", "it", "at", "be", "by", "or", "as"}
        all_words: List[str] = []
        for text in texts:
            words = [w.lower() for w in re.findall(r"\b[a-zA-Z]{4,}\b", text)
                     if w.lower() not in stop]
            all_words.extend(words)

        if not all_words:
            return texts[:n]

        counts = Counter(all_words)
        top    = [word for word, _ in counts.most_common(n * 3)]

        # Build bigrams from top words
        bigrams = []
        for text in texts:
            words = text.lower().split()
            for i in range(len(words) - 1):
                if words[i] in top and words[i+1] in top:
                    bigrams.append(f"{words[i]} {words[i+1]}")

        if bigrams:
            bigram_counts = Counter(bigrams)
            return [b for b, _ in bigram_counts.most_common(n)]

        # Fallback: just top single words
        return top[:n]

    @staticmethod
    def _recency_weight(mistakes: List[Reflection]) -> float:
        """
        Fraction of mistakes that occurred within RECENT_HOURS.
        Returns 0.0 if timestamps can't be parsed.
        """
        if not mistakes:
            return 0.0
        now = datetime.now(timezone.utc)
        recent = 0
        for m in mistakes:
            try:
                ts = datetime.fromisoformat(m.timestamp)
                if (now - ts).total_seconds() <= RECENT_HOURS * 3600:
                    recent += 1
            except (ValueError, TypeError):
                continue
        return recent / len(mistakes)
