from __future__ import annotations

import json
import queue
import threading
import time
import uuid
from typing import Any

from backend.core.human_memory import (
    HumanMemoryStore,
    ImportanceScorer,
    SensoryDeduplicator,
    WorkingMemory,
    MemoryRecord,
    MemoryType,
    StoreDecision,
    CompressionLevel,
    IngestResult,
    classify_memory_type,
    _tokens,
    ImportanceScore,
)

class MemoryBroker:
    """Asynchronous batch memory ingestion worker queue."""
    _queue: queue.Queue[dict[str, Any]] = queue.Queue()
    _worker_thread: threading.Thread | None = None
    _stop_event = threading.Event()
    _lock = threading.Lock()

    @classmethod
    def start(cls) -> None:
        with cls._lock:
            if cls._worker_thread is not None and cls._worker_thread.is_alive():
                return
            cls._stop_event.clear()
            cls._worker_thread = threading.Thread(target=cls._worker_loop, daemon=True)
            cls._worker_thread.start()

    @classmethod
    def stop(cls) -> None:
        with cls._lock:
            if cls._worker_thread is None:
                return
            cls._stop_event.set()
            cls._queue.put({"action": "stop"})
            cls._worker_thread.join(timeout=2.0)
            cls._worker_thread = None

    @classmethod
    def enqueue_and_wait(
        cls,
        text: str,
        source: str = "user",
        session_id: str = "primary",
        trusted: bool | None = None,
        relationship_hit: bool = False,
    ) -> IngestResult:
        cls.start()
        
        done_event = threading.Event()
        payload = {
            "action": "ingest",
            "text": text,
            "source": source,
            "session_id": session_id,
            "trusted": trusted,
            "relationship_hit": relationship_hit,
            "done_event": done_event,
            "result": None,
            "error": None,
        }
        cls._queue.put(payload)
        done_event.wait()
        if payload["error"]:
            raise payload["error"]
        return payload["result"]

    @classmethod
    def _worker_loop(cls) -> None:
        while not cls._stop_event.is_set():
            try:
                first_item = cls._queue.get(timeout=1.0)
            except queue.Empty:
                continue

            if first_item.get("action") == "stop":
                cls._queue.task_done()
                break

            items = [first_item]
            while True:
                try:
                    next_item = cls._queue.get_nowait()
                    if next_item.get("action") == "stop":
                        cls._queue.put(next_item)
                        break
                    items.append(next_item)
                except queue.Empty:
                    break

            try:
                cls._process_batch(items)
            except Exception as e:
                for item in items:
                    if item.get("done_event"):
                        item["error"] = e
                        item["done_event"].set()
            finally:
                for _ in range(len(items)):
                    cls._queue.task_done()

    @classmethod
    def _process_batch(cls, items: list[dict[str, Any]]) -> None:
        item_results: list[tuple[dict[str, Any], IngestResult]] = []

        with HumanMemoryStore._lock:
            conn = HumanMemoryStore._connect()
            cursor = conn.cursor()
            
            try:
                for item in items:
                    if item.get("action") != "ingest":
                        continue
                    
                    text = (item["text"] or "").strip()
                    source = item["source"]
                    session_id = item["session_id"]
                    trusted = item["trusted"]
                    relationship_hit = item["relationship_hit"]
                    reasons: list[str] = []

                    if trusted is None:
                        trusted = source in {"user", "system", "voice"}

                    if not _tokens(text):
                        res = IngestResult(False, StoreDecision.FORGET, False, False, None,
                                           ImportanceScore(0, 0, 0, 0, 0, 0, StoreDecision.FORGET),
                                           ["empty or contentless event"])
                        item_results.append((item, res))
                        continue

                    if SensoryDeduplicator.is_duplicate(text):
                        reasons.append("near-duplicate sensory event discarded")
                        res = IngestResult(False, StoreDecision.FORGET, True, False, None,
                                           ImportanceScore(0, 0, 0, 0, 0, 0, StoreDecision.FORGET), reasons)
                        item_results.append((item, res))
                        continue

                    WorkingMemory.observe(session_id, text)
                    repetition = WorkingMemory.repetition_count(session_id, text)

                    score = ImportanceScorer.score(
                        text, repetition_count=repetition, trusted=trusted, relationship_hit=relationship_hit
                    )
                    reasons.append(f"importance={score.total:.2f} decision={score.decision.value}")

                    if score.decision is StoreDecision.FORGET:
                        reasons.append("below storage threshold; kept only in working memory")
                        res = IngestResult(False, score.decision, False, False, None, score, reasons)
                        item_results.append((item, res))
                        continue

                    mem_type = classify_memory_type(text)

                    pending = False
                    if not trusted and mem_type in (MemoryType.SEMANTIC, MemoryType.PROCEDURAL):
                        pending = True
                        reasons.append("untrusted source: held for approval before long-term store")

                    now = time.time()
                    record = MemoryRecord(
                        id=uuid.uuid4().hex,
                        type=mem_type,
                        content=text,
                        importance=score.total,
                        confidence=0.8 if trusted else 0.4,
                        decay_score=max(0.5, score.total),
                        recall_count=0,
                        created_at=now,
                        last_recall_at=now,
                        pinned=False,
                        trusted=trusted,
                        source=source,
                        compression_level=(int(CompressionLevel.RAW)
                                           if score.decision is StoreDecision.STORE
                                           else int(CompressionLevel.SUMMARY)),
                        tags=["pending_approval"] if pending else [],
                        metadata={"session_id": session_id},
                        pending_approval=pending,
                    )
                    
                    cursor.execute(
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
                    
                    res = IngestResult(
                        stored=not pending,
                        decision=score.decision,
                        duplicate=False,
                        pending_approval=pending,
                        record=record,
                        score=score,
                        reasons=reasons,
                    )
                    item_results.append((item, res))
                
                conn.commit()
            except Exception as e:
                conn.rollback()
                raise e

            for item, res in item_results:
                item["result"] = res
                if item.get("done_event"):
                    item["done_event"].set()
