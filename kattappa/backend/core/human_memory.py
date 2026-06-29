"""Human-Like Memory Architecture.

A living memory ecosystem rather than a database: Kattappa remembers, forgets,
compresses, recalls and forms long-term understanding instead of storing every
detail forever.

    Sensory -> Working Memory -> Evaluation Engine -> {Forget|Compress|Store}
            -> Long-Term Vault (Episodic / Semantic / Procedural + Relationships)
            -> Compression -> Decay -> Recall -> Reflection -> Wisdom

The design folds in the remedies from the architecture critique so the system
is viable on local-first consumer hardware:

* **Deterministic scoring** - the hot ingestion path never calls an LLM, so it
  does not pay the "sensory tax" (300-1200 ms/event).
* **Sensory de-duplicator** - near-identical events are dropped before storage.
* **Memory anchors / pinning** - pinned memories bypass the decay engine.
* **Untrusted data isolation** - events from web/screen/OCR cannot be written to
  long-term semantic/procedural memory without explicit approval, defeating
  prompt-injection memory poisoning.
* **Single-writer serialization** - all SQLite writes go through one lock, so
  the "database is locked" failure mode cannot happen.
* **Graph garbage collection** - dangling relationship edges are pruned.

Storage is stdlib ``sqlite3`` (no heavy vendor dependency), WAL-mode, under the
runtime data directory so tests that set ``KATTAPPA_DATA_DIR`` stay isolated.
"""

from __future__ import annotations

import json
import re
import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Iterable

from backend.core.config import runtime_data_root


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class MemoryType(str, Enum):
    EPISODIC = "episodic"      # events / experiences
    SEMANTIC = "semantic"      # facts
    PROCEDURAL = "procedural"  # skills / how-to
    WISDOM = "wisdom"          # life insights (highest layer)


class StoreDecision(str, Enum):
    FORGET = "forget"
    COMPRESS = "compress"
    STORE = "store"


class DecayStage(str, Enum):
    ACTIVE = "active"
    DORMANT = "dormant"
    ARCHIVED = "archived"
    FORGOTTEN = "forgotten"


class TrustLevel(str, Enum):
    TRUSTED = "trusted"        # user / system originated
    UNTRUSTED = "untrusted"    # web scrape, screen OCR, file contents


class CompressionLevel(int, Enum):
    RAW = 0
    SUMMARY = 1
    PATTERN = 2
    INSIGHT = 3


# ---------------------------------------------------------------------------
# Tokenisation
# ---------------------------------------------------------------------------

_STOPWORDS = frozenset(
    """a an the and or but if then is are was were be been being to of in on at for
    with from by as it its this that these those i you he she we they me my your our
    do does did can could should would will just now please have has had not""".split()
)
_WORD_RE = re.compile(r"[a-z0-9]+")


def _tokens(text: str) -> set[str]:
    return {t for t in _WORD_RE.findall(text.lower()) if len(t) > 2 and t not in _STOPWORDS}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


# ---------------------------------------------------------------------------
# Score model
# ---------------------------------------------------------------------------

_PERSONAL_TERMS = (
    "career", "job", "work", "role", "project", "goal", "prefer", "favorite",
    "family", "friend", "name", "born", "live", "company", "team", "study",
)
_EMOTION_TERMS = (
    "excited", "love", "hate", "amazing", "terrible", "frustrated", "angry",
    "worried", "stressed", "happy", "sad", "afraid", "proud", "anxious", "thrilled",
)
_FUTURE_UTILITY_TERMS = (
    "how to", "steps", "deploy", "build", "command", "config", "setup", "api",
    "key", "path", "procedure", "deadline", "schedule", "remember to", "password",
    "credential", "token",
)
_EXPLICIT_SAVE_TERMS = (
    "remember", "store this", "never forget", "keep in mind", "note that",
    "don't forget", "save this", "memorize",
)
_PROCEDURAL_CUES = ("how to", "steps to", "deploy", "build", "run ", "install",
                    "configure", "setup", "to do this", "procedure", "first ", "then ")
_SEMANTIC_CUES = (" is a ", " is an ", " are ", "knows", "likes", "prefers",
                  "i am", "my name", "user ", " works as", " lives", " means ")


@dataclass(frozen=True)
class ImportanceScore:
    personal: float
    emotional: float
    repetition: float
    future_utility: float
    explicit_save: float
    total: float
    decision: StoreDecision

    def as_dict(self) -> dict[str, Any]:
        return {
            "personal": round(self.personal, 3),
            "emotional": round(self.emotional, 3),
            "repetition": round(self.repetition, 3),
            "future_utility": round(self.future_utility, 3),
            "explicit_save": round(self.explicit_save, 3),
            "total": round(self.total, 3),
            "decision": self.decision.value,
        }


def _contains_any(text: str, terms: Iterable[str]) -> int:
    return sum(1 for term in terms if term in text)


class ImportanceScorer:
    """Deterministic importance scoring (no LLM on the hot path)."""

    _weights = {
        "personal": 0.30,
        "emotional": 0.15,
        "repetition": 0.20,
        "future_utility": 0.25,
        "explicit_save": 0.10,
    }

    @classmethod
    def score(
        cls,
        text: str,
        *,
        repetition_count: int = 0,
        trusted: bool = True,
        relationship_hit: bool = False,
    ) -> ImportanceScore:
        lower = text.lower()

        personal = min(1.0, 0.25 * _contains_any(lower, _PERSONAL_TERMS))
        if relationship_hit:
            personal = max(personal, 0.7)

        emotional = min(1.0, 0.4 + 0.2 * _contains_any(lower, _EMOTION_TERMS)) if _contains_any(lower, _EMOTION_TERMS) else 0.0
        repetition = min(1.0, repetition_count / 4.0)
        future_utility = min(1.0, 0.35 * _contains_any(lower, _FUTURE_UTILITY_TERMS))

        explicit = min(1.0, 0.6 + 0.2 * _contains_any(lower, _EXPLICIT_SAVE_TERMS)) if _contains_any(lower, _EXPLICIT_SAVE_TERMS) else 0.0
        # Untrusted external content cannot earn an "explicit save" boost - this
        # is the anti-memory-poisoning guard from the critique.
        if not trusted:
            explicit = 0.0

        total = 0.0
        for name, weight in cls._weights.items():
            total += {
                "personal": personal,
                "emotional": emotional,
                "repetition": repetition,
                "future_utility": future_utility,
                "explicit_save": explicit,
            }[name] * weight
        total = max(0.0, min(1.0, total))

        # An explicit, trusted save request is always worth storing.
        if explicit >= 0.6:
            decision = StoreDecision.STORE
        elif total >= 0.5:
            decision = StoreDecision.STORE
        elif total >= 0.22:
            decision = StoreDecision.COMPRESS
        else:
            decision = StoreDecision.FORGET

        return ImportanceScore(personal, emotional, repetition, future_utility, explicit, total, decision)


def classify_memory_type(text: str) -> MemoryType:
    lower = f" {text.lower()} "
    if any(cue in lower for cue in _PROCEDURAL_CUES):
        return MemoryType.PROCEDURAL
    if any(cue in lower for cue in _SEMANTIC_CUES):
        return MemoryType.SEMANTIC
    return MemoryType.EPISODIC


# ---------------------------------------------------------------------------
# Records
# ---------------------------------------------------------------------------

@dataclass
class MemoryRecord:
    id: str
    type: MemoryType
    content: str
    importance: float
    confidence: float
    decay_score: float
    recall_count: int
    created_at: float
    last_recall_at: float
    pinned: bool
    trusted: bool
    source: str
    compression_level: int
    tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    pending_approval: bool = False

    @property
    def stage(self) -> DecayStage:
        if self.pinned:
            return DecayStage.ACTIVE
        if self.decay_score >= 0.6:
            return DecayStage.ACTIVE
        if self.decay_score >= 0.3:
            return DecayStage.DORMANT
        if self.decay_score >= 0.1:
            return DecayStage.ARCHIVED
        return DecayStage.FORGOTTEN

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type.value,
            "content": self.content,
            "importance": round(self.importance, 3),
            "confidence": round(self.confidence, 3),
            "decay_score": round(self.decay_score, 3),
            "stage": self.stage.value,
            "recall_count": self.recall_count,
            "created_at": self.created_at,
            "last_recall_at": self.last_recall_at,
            "pinned": self.pinned,
            "trusted": self.trusted,
            "source": self.source,
            "compression_level": self.compression_level,
            "tags": list(self.tags),
            "metadata": dict(self.metadata),
            "pending_approval": self.pending_approval,
        }


# ---------------------------------------------------------------------------
# Storage (single-writer SQLite)
# ---------------------------------------------------------------------------

def _storage_dir() -> Path:
    return runtime_data_root() / "backend" / "data" / "memory_human"


class HumanMemoryStore:
    """SQLite-backed vault with a single global write lock (no lock storms)."""

    _lock = threading.RLock()
    _conn: sqlite3.Connection | None = None
    _path: Path | None = None

    @classmethod
    def _connect(cls) -> sqlite3.Connection:
        with cls._lock:
            target = _storage_dir() / "human_memory.db"
            if cls._conn is not None and cls._path == target:
                return cls._conn
            # Path changed (e.g. test data dir) or first use.
            if cls._conn is not None:
                try:
                    cls._conn.close()
                except Exception:
                    pass
            target.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(str(target), check_same_thread=False)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            cls._conn = conn
            cls._path = target
            cls._ensure_schema(conn)
            return conn

    @staticmethod
    def _ensure_schema(conn: sqlite3.Connection) -> None:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS hm_memories (
                id TEXT PRIMARY KEY,
                type TEXT NOT NULL,
                content TEXT NOT NULL,
                importance REAL NOT NULL,
                confidence REAL NOT NULL,
                decay_score REAL NOT NULL,
                recall_count INTEGER NOT NULL DEFAULT 0,
                created_at REAL NOT NULL,
                last_recall_at REAL NOT NULL,
                pinned INTEGER NOT NULL DEFAULT 0,
                trusted INTEGER NOT NULL DEFAULT 1,
                source TEXT NOT NULL DEFAULT '',
                compression_level INTEGER NOT NULL DEFAULT 0,
                tags TEXT NOT NULL DEFAULT '[]',
                metadata TEXT NOT NULL DEFAULT '{}',
                pending_approval INTEGER NOT NULL DEFAULT 0
            );
            CREATE INDEX IF NOT EXISTS idx_hm_type ON hm_memories(type);
            CREATE INDEX IF NOT EXISTS idx_hm_decay ON hm_memories(decay_score);

            CREATE TABLE IF NOT EXISTS hm_edges (
                id TEXT PRIMARY KEY,
                src TEXT NOT NULL,
                dst TEXT NOT NULL,
                relation TEXT NOT NULL DEFAULT 'related',
                weight REAL NOT NULL DEFAULT 1.0,
                created_at REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_hm_edge_src ON hm_edges(src);

            -- FTS5 virtual table for indexing memory content
            CREATE VIRTUAL TABLE IF NOT EXISTS hm_memories_fts USING fts5(id UNINDEXED, content);

            -- Triggers to auto-sync FTS index
            CREATE TRIGGER IF NOT EXISTS hm_memories_ai AFTER INSERT ON hm_memories BEGIN
              INSERT INTO hm_memories_fts(id, content) VALUES (new.id, new.content);
            END;

            CREATE TRIGGER IF NOT EXISTS hm_memories_ad AFTER DELETE ON hm_memories BEGIN
              DELETE FROM hm_memories_fts WHERE id = old.id;
            END;

            CREATE TRIGGER IF NOT EXISTS hm_memories_au AFTER UPDATE OF content ON hm_memories BEGIN
              UPDATE hm_memories_fts SET content = new.content WHERE id = new.id;
            END;

            CREATE TABLE IF NOT EXISTS hm_beliefs (
                id TEXT PRIMARY KEY,
                key TEXT NOT NULL,
                value TEXT NOT NULL,
                confidence REAL NOT NULL CHECK (confidence BETWEEN 0.0 AND 1.0),
                active INTEGER NOT NULL DEFAULT 1,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_hm_beliefs_key ON hm_beliefs(key);
            CREATE INDEX IF NOT EXISTS idx_hm_beliefs_active ON hm_beliefs(active);
            """
        )
        # Populate FTS index if empty but memories has data
        fts_count = conn.execute("SELECT COUNT(*) AS c FROM hm_memories_fts").fetchone()["c"]
        mem_count = conn.execute("SELECT COUNT(*) AS c FROM hm_memories").fetchone()["c"]
        if fts_count == 0 and mem_count > 0:
            conn.execute("INSERT INTO hm_memories_fts (id, content) SELECT id, content FROM hm_memories")
        conn.commit()

    # -- row mapping -------------------------------------------------------
    @staticmethod
    def _row_to_record(row: sqlite3.Row) -> MemoryRecord:
        return MemoryRecord(
            id=row["id"],
            type=MemoryType(row["type"]),
            content=row["content"],
            importance=row["importance"],
            confidence=row["confidence"],
            decay_score=row["decay_score"],
            recall_count=row["recall_count"],
            created_at=row["created_at"],
            last_recall_at=row["last_recall_at"],
            pinned=bool(row["pinned"]),
            trusted=bool(row["trusted"]),
            source=row["source"],
            compression_level=row["compression_level"],
            tags=json.loads(row["tags"]),
            metadata=json.loads(row["metadata"]),
            pending_approval=bool(row["pending_approval"]),
        )

    # -- writes (serialized) ----------------------------------------------
    @classmethod
    def insert(cls, record: MemoryRecord) -> MemoryRecord:
        with cls._lock:
            conn = cls._connect()
            conn.execute(
                """INSERT INTO hm_memories
                   (id,type,content,importance,confidence,decay_score,recall_count,
                    created_at,last_recall_at,pinned,trusted,source,compression_level,
                    tags,metadata,pending_approval)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    record.id, record.type.value, record.content, record.importance,
                    record.confidence, record.decay_score, record.recall_count,
                    record.created_at, record.last_recall_at, int(record.pinned),
                    int(record.trusted), record.source, record.compression_level,
                    json.dumps(record.tags), json.dumps(record.metadata),
                    int(record.pending_approval),
                ),
            )
            conn.commit()
            return record

    @classmethod
    def update(cls, record: MemoryRecord) -> None:
        with cls._lock:
            conn = cls._connect()
            conn.execute(
                """UPDATE hm_memories SET
                   content=?,importance=?,confidence=?,decay_score=?,recall_count=?,
                   last_recall_at=?,pinned=?,compression_level=?,tags=?,metadata=?,
                   pending_approval=? WHERE id=?""",
                (
                    record.content, record.importance, record.confidence,
                    record.decay_score, record.recall_count, record.last_recall_at,
                    int(record.pinned), record.compression_level,
                    json.dumps(record.tags), json.dumps(record.metadata),
                    int(record.pending_approval), record.id,
                ),
            )
            conn.commit()

    @classmethod
    def delete(cls, memory_id: str) -> bool:
        with cls._lock:
            conn = cls._connect()
            cur = conn.execute("DELETE FROM hm_memories WHERE id=?", (memory_id,))
            conn.execute("DELETE FROM hm_edges WHERE src=? OR dst=?", (memory_id, memory_id))
            conn.commit()
            return cur.rowcount > 0

    @classmethod
    def get(cls, memory_id: str) -> MemoryRecord | None:
        with cls._lock:
            conn = cls._connect()
            row = conn.execute("SELECT * FROM hm_memories WHERE id=?", (memory_id,)).fetchone()
            return cls._row_to_record(row) if row else None

    @classmethod
    def all_records(cls, *, include_pending: bool = True) -> list[MemoryRecord]:
        with cls._lock:
            conn = cls._connect()
            rows = conn.execute("SELECT * FROM hm_memories").fetchall()
            records = [cls._row_to_record(r) for r in rows]
        if not include_pending:
            records = [r for r in records if not r.pending_approval]
        return records

    @classmethod
    def count(cls) -> int:
        with cls._lock:
            conn = cls._connect()
            return int(conn.execute("SELECT COUNT(*) AS c FROM hm_memories").fetchone()["c"])

    # -- relationship edges -----------------------------------------------
    @classmethod
    def add_edge(cls, src: str, dst: str, relation: str = "related", weight: float = 1.0) -> dict[str, Any]:
        edge = {
            "id": uuid.uuid4().hex[:12],
            "src": src,
            "dst": dst,
            "relation": relation,
            "weight": weight,
            "created_at": time.time(),
        }
        with cls._lock:
            conn = cls._connect()
            conn.execute(
                "INSERT INTO hm_edges (id,src,dst,relation,weight,created_at) VALUES (?,?,?,?,?,?)",
                (edge["id"], src, dst, relation, weight, edge["created_at"]),
            )
            conn.commit()
        return edge

    @classmethod
    def neighbors(cls, memory_id: str) -> list[dict[str, Any]]:
        with cls._lock:
            conn = cls._connect()
            rows = conn.execute(
                "SELECT * FROM hm_edges WHERE src=? OR dst=?", (memory_id, memory_id)
            ).fetchall()
            return [dict(r) for r in rows]

    @classmethod
    def all_edges(cls) -> list[dict[str, Any]]:
        with cls._lock:
            conn = cls._connect()
            return [dict(r) for r in conn.execute("SELECT * FROM hm_edges").fetchall()]

    @classmethod
    def delete_edge(cls, edge_id: str) -> None:
        with cls._lock:
            conn = cls._connect()
            conn.execute("DELETE FROM hm_edges WHERE id=?", (edge_id,))
            conn.commit()

    @classmethod
    def upsert_belief(cls, key: str, value: str, confidence: float) -> dict[str, Any]:
        """Upserts a belief by deactivating existing ones with the same key and adding a new active belief."""
        now = time.time()
        belief_id = f"belief_{uuid.uuid4().hex[:8]}"
        with cls._lock:
            conn = cls._connect()
            # Deactivate older beliefs for this key
            conn.execute("UPDATE hm_beliefs SET active = 0 WHERE key = ?", (key,))
            # Insert the new belief as active
            conn.execute(
                """INSERT INTO hm_beliefs (id, key, value, confidence, active, created_at, updated_at)
                   VALUES (?, ?, ?, ?, 1, ?, ?)""",
                (belief_id, key, value, confidence, now, now),
            )
            conn.commit()
        return {
            "id": belief_id,
            "key": key,
            "value": value,
            "confidence": confidence,
            "active": 1,
            "created_at": now,
            "updated_at": now
        }

    @classmethod
    def get_active_belief(cls, key: str) -> dict[str, Any] | None:
        """Retrieves the active belief for a key."""
        with cls._lock:
            conn = cls._connect()
            row = conn.execute(
                "SELECT * FROM hm_beliefs WHERE key = ? AND active = 1", (key,)
            ).fetchone()
            return dict(row) if row else None

    @classmethod
    def list_beliefs(cls, key: str | None = None, include_history: bool = False) -> list[dict[str, Any]]:
        """Lists beliefs, optionally filtered by key and including historical entries."""
        with cls._lock:
            conn = cls._connect()
            query = "SELECT * FROM hm_beliefs"
            params = []
            conditions = []
            if key is not None:
                conditions.append("key = ?")
                params.append(key)
            if not include_history:
                conditions.append("active = 1")
            
            if conditions:
                query += " WHERE " + " AND ".join(conditions)
            query += " ORDER BY created_at DESC"
            rows = conn.execute(query, tuple(params)).fetchall()
            return [dict(r) for r in rows]

    @classmethod
    def reset(cls) -> None:
        """Drop all data (used by tests)."""
        with cls._lock:
            conn = cls._connect()
            conn.execute("DELETE FROM hm_memories")
            conn.execute("DELETE FROM hm_edges")
            conn.execute("DELETE FROM hm_beliefs")
            conn.commit()


# ---------------------------------------------------------------------------
# Sensory de-duplicator
# ---------------------------------------------------------------------------

class SensoryDeduplicator:
    """Drop near-identical sensory events before they inflate memory."""

    similarity_threshold: float = 0.9
    window_seconds: float = 300.0
    _lock = threading.Lock()
    _recent: list[tuple[float, set[str]]] = []

    @classmethod
    def reset(cls) -> None:
        with cls._lock:
            cls._recent = []

    @classmethod
    def is_duplicate(cls, text: str, *, record: bool = True) -> bool:
        tokens = _tokens(text)
        if not tokens:
            return False
        now = time.time()
        with cls._lock:
            cls._recent = [(ts, tk) for ts, tk in cls._recent if now - ts <= cls.window_seconds]
            dup = any(_jaccard(tokens, prev) >= cls.similarity_threshold for _, prev in cls._recent)
            if record and not dup:
                cls._recent.append((now, tokens))
            return dup


# ---------------------------------------------------------------------------
# Working memory
# ---------------------------------------------------------------------------

@dataclass
class WorkingMemorySession:
    session_id: str
    active_goal: str = ""
    current_topic: str = ""
    recent_messages: list[str] = field(default_factory=list)
    open_tasks: list[str] = field(default_factory=list)
    temp_facts: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "active_goal": self.active_goal,
            "current_topic": self.current_topic,
            "recent_messages": list(self.recent_messages),
            "open_tasks": list(self.open_tasks),
            "temp_facts": list(self.temp_facts),
        }


class WorkingMemory:
    """Short-term, session-scoped context (minutes to hours)."""

    max_recent = 12
    _lock = threading.Lock()
    _sessions: dict[str, WorkingMemorySession] = {}

    @classmethod
    def reset(cls) -> None:
        with cls._lock:
            cls._sessions = {}

    @classmethod
    def get(cls, session_id: str) -> WorkingMemorySession:
        with cls._lock:
            sess = cls._sessions.get(session_id)
            if sess is None:
                sess = WorkingMemorySession(session_id=session_id)
                cls._sessions[session_id] = sess
            return sess

    @classmethod
    def observe(cls, session_id: str, text: str, *, topic: str | None = None) -> WorkingMemorySession:
        with cls._lock:
            sess = cls._sessions.setdefault(session_id, WorkingMemorySession(session_id=session_id))
            sess.recent_messages.append(text)
            if len(sess.recent_messages) > cls.max_recent:
                sess.recent_messages = sess.recent_messages[-cls.max_recent :]
            if topic:
                sess.current_topic = topic
            return sess

    @classmethod
    def repetition_count(cls, session_id: str, text: str) -> int:
        tokens = _tokens(text)
        sess = cls.get(session_id)
        return sum(1 for m in sess.recent_messages if 0.3 <= _jaccard(tokens, _tokens(m)) < 0.95)


# ---------------------------------------------------------------------------
# Decay engine
# ---------------------------------------------------------------------------

class DecayEngine:
    """Strength fades over time and is reinforced on recall. Anchors are exempt."""

    half_life_days: float = 14.0

    @classmethod
    def _decay_factor(cls, seconds_since_recall: float) -> float:
        days = max(0.0, seconds_since_recall) / 86400.0
        return 0.5 ** (days / cls.half_life_days)

    @classmethod
    def apply(cls, *, now: float | None = None) -> dict[str, int]:
        now = now or time.time()
        counts = {stage.value: 0 for stage in DecayStage}
        updated = 0
        for record in HumanMemoryStore.all_records():
            if record.pinned:
                counts[DecayStage.ACTIVE.value] += 1
                continue
            factor = cls._decay_factor(now - record.last_recall_at)
            # Importance slows decay (important things are stickier).
            new_score = record.decay_score * (factor + (1 - factor) * 0.4 * record.importance)
            new_score = max(0.0, min(1.0, new_score))
            if abs(new_score - record.decay_score) > 1e-6:
                record.decay_score = new_score
                HumanMemoryStore.update(record)
                updated += 1
            counts[record.stage.value] += 1
        counts["updated"] = updated
        return counts

    @staticmethod
    def reinforce(record: MemoryRecord, *, now: float | None = None) -> None:
        record.recall_count += 1
        record.last_recall_at = now or time.time()
        record.decay_score = min(1.0, record.decay_score + 0.2)


# ---------------------------------------------------------------------------
# Relationship graph (with garbage collection)
# ---------------------------------------------------------------------------

class RelationshipGraph:
    @staticmethod
    def link(src: str, dst: str, relation: str = "related", weight: float = 1.0) -> dict[str, Any]:
        return HumanMemoryStore.add_edge(src, dst, relation, weight)

    @staticmethod
    def neighbors(memory_id: str) -> list[dict[str, Any]]:
        return HumanMemoryStore.neighbors(memory_id)

    @staticmethod
    def gc() -> dict[str, Any]:
        """Prune edges whose endpoints no longer exist (critique: Graph GC)."""
        live = {r.id for r in HumanMemoryStore.all_records()}
        removed = 0
        for edge in HumanMemoryStore.all_edges():
            if edge["src"] not in live or edge["dst"] not in live:
                HumanMemoryStore.delete_edge(edge["id"])
                removed += 1
        return {"removed_dangling_edges": removed, "live_nodes": len(live)}


# ---------------------------------------------------------------------------
# Compression engine
# ---------------------------------------------------------------------------

class CompressionEngine:
    """Heuristic, LLM-free compression that raises the abstraction level."""

    @staticmethod
    def summarise(texts: list[str], *, max_terms: int = 12) -> str:
        freq: dict[str, int] = {}
        for text in texts:
            for tok in _tokens(text):
                freq[tok] = freq.get(tok, 0) + 1
        top = sorted(freq.items(), key=lambda kv: kv[1], reverse=True)[:max_terms]
        keywords = ", ".join(t for t, _ in top)
        return f"Summary of {len(texts)} related memories about: {keywords}."

    @classmethod
    def compress_group(cls, records: list[MemoryRecord], *, level: CompressionLevel) -> MemoryRecord | None:
        if not records:
            return None
        summary = cls.summarise([r.content for r in records])
        importance = max(r.importance for r in records)
        now = time.time()
        compressed = MemoryRecord(
            id=uuid.uuid4().hex,
            type=MemoryType.SEMANTIC if level >= CompressionLevel.PATTERN else records[0].type,
            content=summary,
            importance=importance,
            confidence=min(1.0, 0.5 + 0.1 * len(records)),
            decay_score=max(r.decay_score for r in records),
            recall_count=0,
            created_at=now,
            last_recall_at=now,
            pinned=False,
            trusted=all(r.trusted for r in records),
            source="compression",
            compression_level=int(level),
            tags=["compressed"],
            metadata={"source_ids": [r.id for r in records]},
        )
        return HumanMemoryStore.insert(compressed)


# ---------------------------------------------------------------------------
# Recall engine
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RecallHit:
    record: MemoryRecord
    relevance: float

    def to_dict(self) -> dict[str, Any]:
        data = self.record.to_dict()
        data["relevance"] = round(self.relevance, 3)
        return data


class RecallEngine:
    """Context -> related memories -> rank -> recall (and reinforce)."""

    @staticmethod
    def recall(
        query: str,
        *,
        limit: int = 5,
        include_forgotten: bool = False,
        reinforce: bool = True,
    ) -> list[RecallHit]:
        q_tokens = _tokens(query)
        if not q_tokens:
            return []
        now = time.time()
        hits: list[RecallHit] = []
        # Use SQLite FTS5 for fast candidate selection
        clean_tokens = [re.sub(r'[^a-zA-Z0-9]', '', t) for t in q_tokens]
        clean_tokens = [t for t in clean_tokens if t]
        if not clean_tokens:
            return []

        fts_query = " OR ".join(clean_tokens)
        with HumanMemoryStore._lock:
            conn = HumanMemoryStore._connect()
            rows = conn.execute(
                """SELECT m.* FROM hm_memories m 
                   JOIN hm_memories_fts f ON m.id = f.id 
                   WHERE f.content MATCH ?""",
                (fts_query,),
            ).fetchall()
            candidates = [HumanMemoryStore._row_to_record(row) for row in rows]

        for record in candidates:
            if record.pending_approval:
                continue
            if record.stage is DecayStage.FORGOTTEN and not include_forgotten:
                continue
            overlap = _jaccard(q_tokens, _tokens(record.content))
            if overlap <= 0.0:
                continue
            recency = DecayEngine._decay_factor(now - record.last_recall_at)
            relevance = (
                0.5 * overlap
                + 0.2 * record.importance
                + 0.2 * record.decay_score
                + 0.1 * recency
            )
            hits.append(RecallHit(record, relevance))

        hits.sort(key=lambda h: h.relevance, reverse=True)
        top = hits[:limit]
        if reinforce:
            for hit in top:
                DecayEngine.reinforce(hit.record, now=now)
                HumanMemoryStore.update(hit.record)
        return top


# ---------------------------------------------------------------------------
# Reflection engine + wisdom layer
# ---------------------------------------------------------------------------

class ReflectionEngine:
    """Consolidate memories: compress, strengthen, prune noise, create insight."""

    @classmethod
    def run_cycle(cls, *, now: float | None = None) -> dict[str, Any]:
        now = now or time.time()
        records = HumanMemoryStore.all_records(include_pending=False)

        # 1. Remove noise: forgotten + low-importance, unpinned.
        pruned = 0
        for record in records:
            if not record.pinned and record.stage is DecayStage.FORGOTTEN and record.importance < 0.25:
                HumanMemoryStore.delete(record.id)
                pruned += 1
        RelationshipGraph.gc()

        # 2. Detect recurring topics across episodic memory -> wisdom insight.
        episodic = [r for r in HumanMemoryStore.all_records() if r.type is MemoryType.EPISODIC]
        topic_counter: dict[str, int] = {}
        for record in episodic:
            for tok in _tokens(record.content):
                topic_counter[tok] = topic_counter.get(tok, 0) + 1
        recurring = sorted((t for t in topic_counter.items() if t[1] >= 3),
                           key=lambda kv: kv[1], reverse=True)[:5]

        insights_created = 0
        for topic, count in recurring:
            insight_text = f"User repeatedly engages with '{topic}' ({count} memories); treat as a long-term theme."
            existing = [
                r for r in HumanMemoryStore.all_records()
                if r.type is MemoryType.WISDOM and topic in r.content
            ]
            if existing:
                continue
            CompressionEngine  # keep import used
            wisdom = MemoryRecord(
                id=uuid.uuid4().hex,
                type=MemoryType.WISDOM,
                content=insight_text,
                importance=0.8,
                confidence=min(1.0, 0.5 + 0.05 * count),
                decay_score=0.9,
                recall_count=0,
                created_at=now,
                last_recall_at=now,
                pinned=False,
                trusted=True,
                source="reflection",
                compression_level=int(CompressionLevel.INSIGHT),
                tags=["wisdom", topic],
            )
            HumanMemoryStore.insert(wisdom)
            insights_created += 1

        # 3. Strengthen important, frequently recalled memories.
        strengthened = 0
        for record in HumanMemoryStore.all_records():
            if record.importance >= 0.6 and record.recall_count >= 2 and not record.pinned:
                if record.decay_score < 0.9:
                    record.decay_score = min(1.0, record.decay_score + 0.15)
                    HumanMemoryStore.update(record)
                    strengthened += 1

        return {
            "pruned_noise": pruned,
            "insights_created": insights_created,
            "strengthened": strengthened,
            "recurring_topics": [{"topic": t, "count": c} for t, c in recurring],
            "total_memories": HumanMemoryStore.count(),
        }


class WisdomLayer:
    @staticmethod
    def insights(limit: int = 20) -> list[dict[str, Any]]:
        wisdom = [r for r in HumanMemoryStore.all_records() if r.type is MemoryType.WISDOM]
        wisdom.sort(key=lambda r: r.importance, reverse=True)
        return [r.to_dict() for r in wisdom[:limit]]


# ---------------------------------------------------------------------------
# Facade
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class IngestResult:
    stored: bool
    decision: StoreDecision
    duplicate: bool
    pending_approval: bool
    record: MemoryRecord | None
    score: ImportanceScore
    reasons: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "stored": self.stored,
            "decision": self.decision.value,
            "duplicate": self.duplicate,
            "pending_approval": self.pending_approval,
            "record": self.record.to_dict() if self.record else None,
            "score": self.score.as_dict(),
            "reasons": list(self.reasons),
        }


class HumanMemory:
    """Front door to the human-like memory ecosystem."""

    # ----- lifecycle ------------------------------------------------------
    @classmethod
    def reset(cls) -> None:
        HumanMemoryStore.reset()
        WorkingMemory.reset()
        SensoryDeduplicator.reset()

    # ----- ingestion ------------------------------------------------------
    @classmethod
    def ingest(
        cls,
        text: str,
        *,
        source: str = "user",
        session_id: str = "primary",
        trusted: bool | None = None,
        relationship_hit: bool = False,
    ) -> IngestResult:
        from backend.core.memory_broker import MemoryBroker
        return MemoryBroker.enqueue_and_wait(
            text,
            source=source,
            session_id=session_id,
            trusted=trusted,
            relationship_hit=relationship_hit,
        )

    # ----- approval of untrusted memories --------------------------------
    @classmethod
    def approve_pending(cls, memory_id: str) -> bool:
        record = HumanMemoryStore.get(memory_id)
        if record is None or not record.pending_approval:
            return False
        record.pending_approval = False
        record.confidence = 0.7
        record.tags = [t for t in record.tags if t != "pending_approval"]
        HumanMemoryStore.update(record)
        return True

    @classmethod
    def list_pending(cls) -> list[dict[str, Any]]:
        return [r.to_dict() for r in HumanMemoryStore.all_records() if r.pending_approval]

    # ----- recall ---------------------------------------------------------
    @classmethod
    def recall(cls, query: str, *, limit: int = 5, include_forgotten: bool = False) -> list[dict[str, Any]]:
        return [h.to_dict() for h in RecallEngine.recall(query, limit=limit, include_forgotten=include_forgotten)]

    # ----- pinning (memory anchors) --------------------------------------
    @classmethod
    def pin(cls, memory_id: str) -> bool:
        record = HumanMemoryStore.get(memory_id)
        if record is None:
            return False
        record.pinned = True
        record.decay_score = max(record.decay_score, 0.9)
        if "anchor" not in record.tags:
            record.tags.append("anchor")
        HumanMemoryStore.update(record)
        return True

    @classmethod
    def unpin(cls, memory_id: str) -> bool:
        record = HumanMemoryStore.get(memory_id)
        if record is None:
            return False
        record.pinned = False
        record.tags = [t for t in record.tags if t != "anchor"]
        HumanMemoryStore.update(record)
        return True

    # ----- maintenance ----------------------------------------------------
    @classmethod
    def run_decay(cls) -> dict[str, Any]:
        return DecayEngine.apply()

    @classmethod
    def reflect(cls) -> dict[str, Any]:
        return ReflectionEngine.run_cycle()

    @classmethod
    def link(cls, src: str, dst: str, relation: str = "related", weight: float = 1.0) -> dict[str, Any]:
        return RelationshipGraph.link(src, dst, relation, weight)

    @classmethod
    def garbage_collect(cls) -> dict[str, Any]:
        return RelationshipGraph.gc()

    @classmethod
    def working_memory(cls, session_id: str = "primary") -> dict[str, Any]:
        return WorkingMemory.get(session_id).to_dict()

    @classmethod
    def wisdom(cls, limit: int = 20) -> list[dict[str, Any]]:
        return WisdomLayer.insights(limit=limit)

    # ----- status ---------------------------------------------------------
    @classmethod
    def status(cls) -> dict[str, Any]:
        records = HumanMemoryStore.all_records()
        by_type: dict[str, int] = {t.value: 0 for t in MemoryType}
        by_stage: dict[str, int] = {s.value: 0 for s in DecayStage}
        pinned = 0
        pending = 0
        for record in records:
            by_type[record.type.value] += 1
            by_stage[record.stage.value] += 1
            pinned += int(record.pinned)
            pending += int(record.pending_approval)
        return {
            "framework": "Human-Like Memory Architecture",
            "pipeline": "Sensory -> Working -> Evaluation -> Vault -> Compress -> Decay -> Recall -> Reflect -> Wisdom",
            "total_memories": len(records),
            "by_type": by_type,
            "by_stage": by_stage,
            "pinned_anchors": pinned,
            "pending_approval": pending,
            "edges": len(HumanMemoryStore.all_edges()),
            "decay_half_life_days": DecayEngine.half_life_days,
        }

    # ----- belief system --------------------------------------------------
    @classmethod
    def upsert_belief(cls, key: str, value: str, confidence: float) -> dict[str, Any]:
        return HumanMemoryStore.upsert_belief(key, value, confidence)

    @classmethod
    def get_active_belief(cls, key: str) -> dict[str, Any] | None:
        return HumanMemoryStore.get_active_belief(key)

    @classmethod
    def list_beliefs(cls, key: str | None = None, include_history: bool = False) -> list[dict[str, Any]]:
        return HumanMemoryStore.list_beliefs(key, include_history)


MEMORY = HumanMemory
