"""Lighthouse Attention Framework.

Attention comes before memory. The lighthouse constantly scans every incoming
event and decides what stays in darkness (noise), what is merely observed
(background), and what gets illuminated (focus / critical). Only events that win
attention are allowed to reach the memory system.

Pipeline:

    Environment -> Attention Engine -> {Ignore | Observe | Focus | Critical}
                                              -> Memory Evaluation

The framework is intentionally LLM-free at the hot path: scoring is a fast,
deterministic, fully typed computation so it can run on every sensory event
without taxing the CPU/GPU (see docs/architecture critique on the "Sensory
Tax"). Goals, relationships and the curiosity research queue persist to JSON
under the runtime data directory using the same resilient pattern as the rest
of ``backend/core``.

Public surface:

* :class:`LighthouseAttention` - facade orchestrator (``process_event`` etc.)
* :class:`AttentionScorer` - the six-factor attention score engine
* :class:`GoalRegistry` - goal-locked attention (goal resonance)
* :class:`RelationshipRegistry` - relationship attention layer
* :class:`CuriosityEngine` - knowledge-gap detection and research queue
* :class:`FocusGuardian` - attention drift prevention
"""

from __future__ import annotations

import json
import re
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Iterable

from backend.core.config import runtime_data_root


# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------

def _storage_dir() -> Path:
    """Runtime directory for attention state.

    Resolved lazily so tests that set ``KATTAPPA_DATA_DIR`` are isolated.
    """
    base = runtime_data_root()
    return base / "backend" / "data" / "attention"


def _read_json(path: Path, default: Any) -> Any:
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return default


def _write_json(path: Path, data: Any) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class AttentionRing(str, Enum):
    """Concentric attention rings around the user."""

    CRITICAL = "critical"      # Ring 1 - act now
    IMPORTANT = "important"    # Ring 2 - goals / important entities
    ACTIVE = "active"          # Ring 3 - current conversation focus
    BACKGROUND = "background"  # Ring 4 - observe, recall only if relevant
    NOISE = "noise"            # Ring 5 - discard, never reaches memory

    @property
    def index(self) -> int:
        return {
            AttentionRing.CRITICAL: 1,
            AttentionRing.IMPORTANT: 2,
            AttentionRing.ACTIVE: 3,
            AttentionRing.BACKGROUND: 4,
            AttentionRing.NOISE: 5,
        }[self]


class AttentionAction(str, Enum):
    """Score-band disposition for an event."""

    IGNORE = "ignore"      # 0-20
    OBSERVE = "observe"    # 20-50
    FOCUS = "focus"        # 50-80
    CRITICAL = "critical"  # 80-100


class MemoryDisposition(str, Enum):
    """What the memory evaluation engine should do with the event."""

    FORGET = "forget"
    COMPRESS = "compress"
    STORE = "store"


# ---------------------------------------------------------------------------
# Score model
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class AttentionFactors:
    """The six factors of the attention score engine, each in ``[0, 1]``."""

    user_importance: float = 0.0
    goal_relevance: float = 0.0
    urgency: float = 0.0
    novelty: float = 0.0
    emotional_weight: float = 0.0
    repetition: float = 0.0

    def as_dict(self) -> dict[str, float]:
        return {k: round(v, 3) for k, v in asdict(self).items()}


# Relative importance of each factor. They are normalised so the weighted mean
# stays in [0, 1] regardless of the absolute numbers below.
_FACTOR_WEIGHTS: dict[str, float] = {
    "user_importance": 0.30,
    "goal_relevance": 0.22,
    "urgency": 0.20,
    "novelty": 0.10,
    "emotional_weight": 0.08,
    "repetition": 0.10,
}


@dataclass(frozen=True)
class AttentionResult:
    """Outcome of scoring a single event."""

    event_id: str
    text: str
    source: str
    score: float
    ring: AttentionRing
    action: AttentionAction
    memory_disposition: MemoryDisposition
    factors: AttentionFactors
    reasons: list[str] = field(default_factory=list)
    matched_goals: list[str] = field(default_factory=list)
    matched_entities: list[str] = field(default_factory=list)
    curiosity_triggered: bool = False
    duplicate: bool = False

    @property
    def should_remember(self) -> bool:
        return self.memory_disposition is not MemoryDisposition.FORGET

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "text": self.text,
            "source": self.source,
            "score": round(self.score, 2),
            "ring": self.ring.value,
            "ring_index": self.ring.index,
            "action": self.action.value,
            "memory_disposition": self.memory_disposition.value,
            "should_remember": self.should_remember,
            "factors": self.factors.as_dict(),
            "reasons": list(self.reasons),
            "matched_goals": list(self.matched_goals),
            "matched_entities": list(self.matched_entities),
            "curiosity_triggered": self.curiosity_triggered,
            "duplicate": self.duplicate,
        }


# ---------------------------------------------------------------------------
# Tokenisation helpers
# ---------------------------------------------------------------------------

_STOPWORDS = frozenset(
    """a an the and or but if then is are was were be been being to of in on at for
    with from by as it its this that these those i you he she we they me my your our
    do does did can could should would will just now please""".split()
)

_WORD_RE = re.compile(r"[a-z0-9]+")


def _tokens(text: str) -> set[str]:
    return {
        tok
        for tok in _WORD_RE.findall(text.lower())
        if len(tok) > 2 and tok not in _STOPWORDS
    }


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


# ---------------------------------------------------------------------------
# Keyword signals
# ---------------------------------------------------------------------------

_URGENCY_TERMS = (
    "urgent", "asap", "immediately", "right now", "emergency", "critical",
    "deadline", "now", "failure", "failed", "error", "crash", "down", "alert",
    "broken", "stop", "halt",
)

_CRITICAL_TERMS = (
    "emergency", "security breach", "system failure", "data loss", "fire",
    "danger", "fatal", "corrupted", "ransom", "attack",
)

_EMOTION_TERMS = (
    "excited", "love", "hate", "amazing", "terrible", "awful", "frustrated",
    "angry", "worried", "stressed", "happy", "sad", "afraid", "thrilled",
    "annoyed", "proud", "anxious",
)

_EXPLICIT_SAVE_TERMS = (
    "remember", "store this", "never forget", "keep in mind", "note that",
    "don't forget", "save this",
)

_DIRECT_ADDRESS = ("kattappa", "mama", "kittu")

_CURIOSITY_TERMS = (
    "what is", "what's", "how do", "how does", "how to", "why does", "why is",
    "i wonder", "not sure", "unsure", "don't know", "unknown", "unfamiliar",
    "never heard of", "explain", "research",
)


def _contains_any(text: str, terms: Iterable[str]) -> list[str]:
    return [term for term in terms if term in text]


# ---------------------------------------------------------------------------
# Goal registry (Goal-Locked Attention / Goal Resonance)
# ---------------------------------------------------------------------------

class GoalRegistry:
    """Active user goals. Events resonating with a goal get an attention boost."""

    _lock = threading.Lock()
    _filename = "goals.json"

    @classmethod
    def _path(cls) -> Path:
        return _storage_dir() / cls._filename

    @classmethod
    def list_goals(cls) -> list[dict[str, Any]]:
        with cls._lock:
            data = _read_json(cls._path(), {"goals": []})
            return list(data.get("goals", []))

    @classmethod
    def add_goal(cls, title: str, keywords: Iterable[str] | None = None,
                 priority: str = "normal") -> dict[str, Any]:
        title = title.strip()
        if not title:
            raise ValueError("Goal title cannot be empty")
        derived = sorted(_tokens(title) | {k.strip().lower() for k in (keywords or []) if k.strip()})
        goal = {
            "id": uuid.uuid4().hex[:12],
            "title": title,
            "keywords": derived,
            "priority": priority,
            "active": True,
            "created_at": time.time(),
        }
        with cls._lock:
            data = _read_json(cls._path(), {"goals": []})
            goals = data.get("goals", [])
            goals.append(goal)
            data["goals"] = goals
            _write_json(cls._path(), data)
        return goal

    @classmethod
    def remove_goal(cls, goal_id: str) -> bool:
        with cls._lock:
            data = _read_json(cls._path(), {"goals": []})
            goals = data.get("goals", [])
            new_goals = [g for g in goals if g.get("id") != goal_id]
            if len(new_goals) == len(goals):
                return False
            data["goals"] = new_goals
            _write_json(cls._path(), data)
            return True

    @classmethod
    def resonance(cls, tokens: set[str]) -> tuple[float, list[str]]:
        """Return ``(score in [0,1], matched goal titles)`` for the event tokens."""
        matched: list[str] = []
        best = 0.0
        for goal in cls.list_goals():
            if not goal.get("active", True):
                continue
            goal_kw = set(goal.get("keywords", []))
            if not goal_kw:
                continue
            overlap = tokens & goal_kw
            if overlap:
                strength = min(1.0, len(overlap) / max(2, len(goal_kw)) + 0.34)
                weight = 1.15 if goal.get("priority") == "high" else 1.0
                strength = min(1.0, strength * weight)
                best = max(best, strength)
                matched.append(goal.get("title", ""))
        return best, matched


# ---------------------------------------------------------------------------
# Relationship registry (Relationship Attention Layer)
# ---------------------------------------------------------------------------

class RelationshipRegistry:
    """People important to the user. Events mentioning them get priority."""

    _lock = threading.Lock()
    _filename = "relationships.json"

    @classmethod
    def _path(cls) -> Path:
        return _storage_dir() / cls._filename

    @classmethod
    def list_entities(cls) -> list[dict[str, Any]]:
        with cls._lock:
            data = _read_json(cls._path(), {"entities": []})
            return list(data.get("entities", []))

    @classmethod
    def add_entity(cls, name: str, relation: str = "contact",
                   importance: float = 0.6) -> dict[str, Any]:
        name = name.strip()
        if not name:
            raise ValueError("Entity name cannot be empty")
        entity = {
            "id": uuid.uuid4().hex[:12],
            "name": name,
            "relation": relation,
            "importance": max(0.0, min(1.0, importance)),
            "created_at": time.time(),
        }
        with cls._lock:
            data = _read_json(cls._path(), {"entities": []})
            entities = data.get("entities", [])
            entities.append(entity)
            data["entities"] = entities
            _write_json(cls._path(), data)
        return entity

    @classmethod
    def remove_entity(cls, entity_id: str) -> bool:
        with cls._lock:
            data = _read_json(cls._path(), {"entities": []})
            entities = data.get("entities", [])
            new_entities = [e for e in entities if e.get("id") != entity_id]
            if len(new_entities) == len(entities):
                return False
            data["entities"] = new_entities
            _write_json(cls._path(), data)
            return True

    @classmethod
    def match(cls, text_lower: str) -> tuple[float, list[str]]:
        matched: list[str] = []
        best = 0.0
        for entity in cls.list_entities():
            name = str(entity.get("name", "")).lower()
            if name and re.search(rf"\b{re.escape(name)}\b", text_lower):
                best = max(best, float(entity.get("importance", 0.6)))
                matched.append(entity.get("name", ""))
        return best, matched


# ---------------------------------------------------------------------------
# Curiosity engine
# ---------------------------------------------------------------------------

class CuriosityEngine:
    """Detect knowledge gaps and queue them for later research."""

    _lock = threading.Lock()
    _filename = "curiosity_queue.json"

    @classmethod
    def _path(cls) -> Path:
        return _storage_dir() / cls._filename

    @classmethod
    def detect_gap(cls, text: str) -> str | None:
        lower = text.lower()
        if any(term in lower for term in _CURIOSITY_TERMS):
            return text.strip()
        return None

    @classmethod
    def enqueue(cls, topic: str, source: str = "attention") -> dict[str, Any]:
        topic = topic.strip()
        item = {
            "id": uuid.uuid4().hex[:12],
            "topic": topic,
            "source": source,
            "status": "pending",
            "created_at": time.time(),
        }
        with cls._lock:
            data = _read_json(cls._path(), {"queue": []})
            queue = data.get("queue", [])
            # Avoid near-duplicate curiosity entries.
            topic_tokens = _tokens(topic)
            for existing in queue:
                if existing.get("status") == "pending" and _jaccard(
                    topic_tokens, _tokens(str(existing.get("topic", "")))
                ) >= 0.8:
                    return existing
            queue.append(item)
            data["queue"] = queue
            _write_json(cls._path(), data)
        return item

    @classmethod
    def list_queue(cls, status: str | None = None) -> list[dict[str, Any]]:
        with cls._lock:
            data = _read_json(cls._path(), {"queue": []})
            queue = list(data.get("queue", []))
        if status:
            queue = [item for item in queue if item.get("status") == status]
        return queue

    @classmethod
    def resolve(cls, item_id: str, status: str = "done") -> bool:
        with cls._lock:
            data = _read_json(cls._path(), {"queue": []})
            queue = data.get("queue", [])
            hit = False
            for item in queue:
                if item.get("id") == item_id:
                    item["status"] = status
                    item["resolved_at"] = time.time()
                    hit = True
            if hit:
                data["queue"] = queue
                _write_json(cls._path(), data)
            return hit


# ---------------------------------------------------------------------------
# Focus guardian (Attention Drift Prevention)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class DriftCheck:
    drifted: bool
    similarity: float
    objective: str
    advice: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "drifted": self.drifted,
            "similarity": round(self.similarity, 3),
            "objective": self.objective,
            "advice": self.advice,
        }


class FocusGuardian:
    """Detect when the current event drifts away from the active objective."""

    drift_threshold: float = 0.12

    @classmethod
    def check(cls, objective: str, event_text: str) -> DriftCheck:
        objective = (objective or "").strip()
        if not objective:
            return DriftCheck(False, 1.0, objective, "No active objective set; nothing to drift from.")
        similarity = _jaccard(_tokens(objective), _tokens(event_text))
        drifted = similarity < cls.drift_threshold
        advice = (
            f"Possible drift from objective. Return to: {objective!r}."
            if drifted
            else "On track with the current objective."
        )
        return DriftCheck(drifted, similarity, objective, advice)


# ---------------------------------------------------------------------------
# Attention score engine
# ---------------------------------------------------------------------------

class AttentionScorer:
    """Compute the six-factor attention score for an event."""

    @staticmethod
    def _user_importance(text_lower: str, source: str) -> tuple[float, list[str]]:
        reasons: list[str] = []
        score = 0.0
        if source == "user":
            score = max(score, 0.55)
            reasons.append("direct user message")
        if _contains_any(text_lower, _DIRECT_ADDRESS):
            score = max(score, 0.9)
            reasons.append("addressed Kattappa directly")
        if _contains_any(text_lower, _EXPLICIT_SAVE_TERMS):
            score = max(score, 0.95)
            reasons.append("explicit save request")
        # Imperative / question signals.
        stripped = text_lower.strip()
        if stripped.endswith("?"):
            score = max(score, 0.6)
            reasons.append("direct question")
        if re.match(r"^(please\s+)?(do|make|build|create|run|open|fix|write|find|show|tell|set|stop|start)\b", stripped):
            score = max(score, 0.7)
            reasons.append("direct command")
        return min(1.0, score), reasons

    @staticmethod
    def _urgency(text_lower: str) -> tuple[float, list[str]]:
        hits = _contains_any(text_lower, _URGENCY_TERMS)
        if not hits:
            return 0.0, []
        score = min(1.0, 0.55 + 0.15 * len(hits))
        return score, [f"urgency cue: {', '.join(hits[:3])}"]

    @staticmethod
    def _emotional(text_lower: str) -> tuple[float, list[str]]:
        hits = _contains_any(text_lower, _EMOTION_TERMS)
        if not hits:
            return 0.0, []
        score = min(1.0, 0.5 + 0.2 * len(hits))
        bang = text_lower.count("!")
        if bang:
            score = min(1.0, score + 0.1 * min(bang, 3))
        return score, [f"emotional weight: {', '.join(hits[:3])}"]

    @classmethod
    def score(
        cls,
        text: str,
        tokens: set[str],
        source: str,
        recent: list[tuple[str, set[str]]],
    ) -> tuple[AttentionFactors, list[str], list[str], list[str]]:
        """Return ``(factors, reasons, matched_goals, matched_entities)``."""
        text_lower = text.lower()
        reasons: list[str] = []

        user_importance, ui_reasons = cls._user_importance(text_lower, source)
        reasons.extend(ui_reasons)

        urgency, urg_reasons = cls._urgency(text_lower)
        reasons.extend(urg_reasons)

        emotional, emo_reasons = cls._emotional(text_lower)
        reasons.extend(emo_reasons)

        goal_relevance, matched_goals = GoalRegistry.resonance(tokens)
        if matched_goals:
            reasons.append(f"goal resonance: {', '.join(m for m in matched_goals if m)}")

        entity_importance, matched_entities = RelationshipRegistry.match(text_lower)
        if matched_entities:
            reasons.append(f"relationship match: {', '.join(matched_entities)}")
            # Important people lift personal importance.
            user_importance = max(user_importance, entity_importance)

        # Novelty / repetition from the recent window.
        max_sim = max((_jaccard(tokens, prev_tokens) for _, prev_tokens in recent), default=0.0)
        novelty = 1.0 - max_sim
        # Topical repetition (mentioned often but not an exact dup) boosts salience.
        related = sum(1 for _, prev_tokens in recent if 0.2 <= _jaccard(tokens, prev_tokens) < 0.85)
        repetition = min(1.0, related / 4.0)
        if repetition > 0:
            reasons.append("recurring topic")

        factors = AttentionFactors(
            user_importance=user_importance,
            goal_relevance=goal_relevance,
            urgency=urgency,
            novelty=novelty,
            emotional_weight=emotional,
            repetition=repetition,
        )
        return factors, reasons, [m for m in matched_goals if m], matched_entities

    @staticmethod
    def aggregate(factors: AttentionFactors) -> float:
        """Aggregate factors into a 0-100 attention score.

        A pure weighted mean would let a single dominant beacon (a direct
        command, an emergency) be diluted by the quiet dimensions. The
        lighthouse should illuminate strongly when *any* salient signal is high,
        so the final score blends the weighted mean with the strongest salience
        signal (``dominance``).
        """
        total = 0.0
        weight_sum = 0.0
        for name, weight in _FACTOR_WEIGHTS.items():
            total += getattr(factors, name) * weight
            weight_sum += weight
        weighted_mean = total / weight_sum if weight_sum else 0.0

        dominance = max(
            factors.user_importance,
            factors.goal_relevance,
            factors.urgency,
            factors.emotional_weight,
        )
        blended = 0.55 * dominance + 0.45 * weighted_mean
        return round(100.0 * max(0.0, min(1.0, blended)), 2)


# ---------------------------------------------------------------------------
# Lighthouse facade
# ---------------------------------------------------------------------------

def _action_for_score(score: float) -> AttentionAction:
    if score >= 80:
        return AttentionAction.CRITICAL
    if score >= 50:
        return AttentionAction.FOCUS
    if score >= 20:
        return AttentionAction.OBSERVE
    return AttentionAction.IGNORE


class LighthouseAttention:
    """The rotating lighthouse: scores events, classifies rings, gates memory."""

    # Sliding window of recent events for novelty / repetition / dedup.
    _recent: list[tuple[str, set[str]]] = []
    _recent_lock = threading.Lock()
    _window = 24

    # Near-duplicate threshold for the Ring 5 noise filter.
    duplicate_threshold: float = 0.92

    @classmethod
    def reset(cls) -> None:
        """Clear the in-memory recent-event window (used by tests)."""
        with cls._recent_lock:
            cls._recent = []

    @classmethod
    def _snapshot_recent(cls) -> list[tuple[str, set[str]]]:
        with cls._recent_lock:
            return list(cls._recent)

    @classmethod
    def _remember_recent(cls, text: str, tokens: set[str]) -> None:
        with cls._recent_lock:
            cls._recent.append((text, tokens))
            if len(cls._recent) > cls._window:
                cls._recent = cls._recent[-cls._window :]

    @classmethod
    def _classify_ring(
        cls,
        score: float,
        factors: AttentionFactors,
        duplicate: bool,
        matched_goals: list[str],
        matched_entities: list[str],
        active_context: str | None,
        tokens: set[str],
    ) -> AttentionRing:
        if duplicate:
            return AttentionRing.NOISE
        critical = score >= 80 or factors.urgency >= 0.85
        if critical:
            return AttentionRing.CRITICAL
        # Direct user commands, explicit-save requests and goal/entity hits are
        # Ring 2 by definition, even if the quieter factors keep the mean low.
        if (
            factors.goal_relevance >= 0.5
            or factors.user_importance >= 0.7
            or matched_goals
            or matched_entities
        ):
            return AttentionRing.IMPORTANT
        if active_context and _jaccard(_tokens(active_context), tokens) >= 0.18:
            return AttentionRing.ACTIVE
        if score >= 20:
            return AttentionRing.BACKGROUND
        return AttentionRing.NOISE

    @staticmethod
    def _disposition(ring: AttentionRing) -> MemoryDisposition:
        if ring in (AttentionRing.CRITICAL, AttentionRing.IMPORTANT, AttentionRing.ACTIVE):
            return MemoryDisposition.STORE
        if ring is AttentionRing.BACKGROUND:
            return MemoryDisposition.COMPRESS
        return MemoryDisposition.FORGET

    @classmethod
    def process_event(
        cls,
        text: str,
        source: str = "user",
        active_context: str | None = None,
        record: bool = True,
    ) -> AttentionResult:
        """Score one event and return its attention disposition.

        Args:
            text: Raw event text from the sensory layer.
            source: Origin of the event (``user``, ``screen``, ``web``,
                ``system``, ``voice`` ...). ``user`` events get a baseline
                importance lift.
            active_context: The current conversation topic, used to detect
                Ring 3 (active context) membership.
            record: When ``True`` the event joins the recent window so that
                later events can measure novelty / repetition / duplication
                against it. Set ``False`` for hypothetical scoring.
        """
        text = (text or "").strip()
        tokens = _tokens(text)
        recent = cls._snapshot_recent()

        # Empty / contentless events are pure noise.
        if not tokens:
            return AttentionResult(
                event_id=uuid.uuid4().hex[:12],
                text=text,
                source=source,
                score=0.0,
                ring=AttentionRing.NOISE,
                action=AttentionAction.IGNORE,
                memory_disposition=MemoryDisposition.FORGET,
                factors=AttentionFactors(),
                reasons=["empty or contentless event"],
            )

        max_sim = max((_jaccard(tokens, prev_tokens) for _, prev_tokens in recent), default=0.0)
        duplicate = max_sim >= cls.duplicate_threshold

        factors, reasons, matched_goals, matched_entities = AttentionScorer.score(
            text, tokens, source, recent
        )
        score = AttentionScorer.aggregate(factors)
        ring = cls._classify_ring(
            score, factors, duplicate, matched_goals, matched_entities, active_context, tokens
        )
        action = AttentionAction.IGNORE if duplicate else _action_for_score(score)
        disposition = cls._disposition(ring)

        # Curiosity: only spend a research slot on events that won attention.
        curiosity_triggered = False
        if ring is not AttentionRing.NOISE:
            gap = CuriosityEngine.detect_gap(text)
            if gap:
                CuriosityEngine.enqueue(gap, source=source)
                curiosity_triggered = True
                reasons.append("knowledge gap queued for research")

        if duplicate:
            reasons.append(f"near-duplicate of recent event (sim={max_sim:.2f})")

        if record:
            cls._remember_recent(text, tokens)

        return AttentionResult(
            event_id=uuid.uuid4().hex[:12],
            text=text,
            source=source,
            score=score,
            ring=ring,
            action=action,
            memory_disposition=disposition,
            factors=factors,
            reasons=reasons,
            matched_goals=matched_goals,
            matched_entities=matched_entities,
            curiosity_triggered=curiosity_triggered,
            duplicate=duplicate,
        )

    @classmethod
    def reflect(cls, events: list[dict[str, Any]]) -> dict[str, Any]:
        """Reflection attention pass over a batch of recently scored events.

        Reviews what mattered, what repeated and what was ignored, and proposes
        memory-strength adjustments. Pure function over the supplied batch so it
        can run on the background reflection cycle without touching live state.
        """
        ring_counts: dict[str, int] = {ring.value: 0 for ring in AttentionRing}
        mattered: list[str] = []
        ignored: list[str] = []
        topic_counter: dict[str, int] = {}

        for ev in events:
            ring = str(ev.get("ring", AttentionRing.NOISE.value))
            ring_counts[ring] = ring_counts.get(ring, 0) + 1
            text = str(ev.get("text", ""))
            if ring in (AttentionRing.CRITICAL.value, AttentionRing.IMPORTANT.value):
                mattered.append(text)
            elif ring == AttentionRing.NOISE.value:
                ignored.append(text)
            for tok in _tokens(text):
                topic_counter[tok] = topic_counter.get(tok, 0) + 1

        recurring = sorted(
            (t for t in topic_counter.items() if t[1] >= 2),
            key=lambda kv: kv[1],
            reverse=True,
        )[:10]

        # Topics that recur should be reinforced; one-off noise should fade.
        strengthen = [topic for topic, _ in recurring]
        return {
            "events_reviewed": len(events),
            "ring_counts": ring_counts,
            "what_mattered": mattered[:10],
            "what_was_ignored": ignored[:10],
            "recurring_topics": [{"topic": t, "count": c} for t, c in recurring],
            "strengthen_memories": strengthen,
            "summary": (
                f"Reviewed {len(events)} events: "
                f"{ring_counts.get('critical', 0)} critical, "
                f"{ring_counts.get('important', 0)} important, "
                f"{ring_counts.get('noise', 0)} discarded as noise."
            ),
        }

    @classmethod
    def status(cls) -> dict[str, Any]:
        return {
            "framework": "Lighthouse Attention Framework",
            "principle": "Attention -> Memory -> Understanding -> Wisdom -> Action",
            "rings": [
                {"ring": ring.value, "index": ring.index}
                for ring in sorted(AttentionRing, key=lambda r: r.index)
            ],
            "score_bands": {
                "ignore": "0-20",
                "observe": "20-50",
                "focus": "50-80",
                "critical": "80-100",
            },
            "factor_weights": dict(_FACTOR_WEIGHTS),
            "active_goals": GoalRegistry.list_goals(),
            "relationships": RelationshipRegistry.list_entities(),
            "curiosity_pending": CuriosityEngine.list_queue(status="pending"),
            "recent_window": len(cls._snapshot_recent()),
        }


# Convenience module-level singleton-style alias.
LIGHTHOUSE = LighthouseAttention
