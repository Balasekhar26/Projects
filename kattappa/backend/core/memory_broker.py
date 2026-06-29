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
    TrustLevel,
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

            # Determine if content needs pending approval (untrusted sources go to quarantine).
            # Trusted broker writes bypass ActionBroker — the broker is internal pipeline
            # code that has already scored and deduped the content.  External agent writes
            # still go through the full approval gate via MemoryService.write().
            #
            # Quarantine ALL untrusted content: any source that is not in the
            # explicitly-trusted set is held pending human review, regardless of
            # memory type, to prevent prompt-injection via any ingestion vector.
            pending = not trusted

            record = cls._direct_ingest_record(
                text=text,
                mem_type=mem_type,
                source=source,
                trusted=trusted,
                score=score,
                pending_approval=pending,
            )

            res = IngestResult(
                stored=not record.pending_approval,
                decision=score.decision,
                duplicate=False,
                pending_approval=record.pending_approval,
                record=record,
                score=score,
                reasons=reasons
            )
            item_results.append((item, res))

        for item, res in item_results:
            item["result"] = res
            if item.get("done_event"):
                item["done_event"].set()

    # -----------------------------------------------------------------------
    # Internal direct-write path (trusted broker writes only)
    # -----------------------------------------------------------------------

    @classmethod
    def _direct_ingest_record(
        cls,
        text: str,
        mem_type: MemoryType,
        source: str,
        trusted: bool,
        score: ImportanceScore,
        pending_approval: bool = False,
    ) -> MemoryRecord:
        """Write a pre-scored memory record straight to HumanMemoryStore.

        This path is for **broker-internal** writes only.  The broker has already
        run ImportanceScorer, SensoryDeduplicator, and WorkingMemory before
        reaching this point.  External agent writes must still use
        MemoryService.write() → ActionBroker.intake_request() for the full
        approval gate.

        Security contract:
          - Only reached after score.decision is STORE or COMPRESS (FORGET exits earlier).
          - Untrusted semantic/procedural content is stored with pending_approval=True
            (quarantine path identical to old behaviour).
          - No capability token or approval-engine bypass is created here;
            this code path cannot grant permissions or elevate trust.
        """
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
            compression_level=0,
            tags=["pending_approval"] if pending_approval else [],
            metadata={},
            pending_approval=pending_approval,
        )
        HumanMemoryStore.insert(record)
        return record

    @classmethod
    def retrieve(
        cls,
        query: str,
        *,
        limit: int = 5,
        session_id: str = "primary"
    ) -> dict[str, Any]:
        """Unified Memory Fabric Retrieval.
        
        Performs retrieval across Episodic, Semantic, Procedural, Relationship, Goal,
        and Belief memory systems, then runs a Unified Ranker (RRF) to select
        the top relevant context elements and returns a ContextBuilder structure.
        """
        # 1. Semantic Memory
        from backend.core.semantic_memory import SemanticMemory
        semantic_nodes = []
        try:
            semantic_nodes = SemanticMemory.recall(query, limit=limit)
        except Exception as e:
            from backend.core.logger import log_event
            log_event(f"MemoryBroker retrieve: semantic recall failed: {e}")
            
        # 2. Episodic Memory
        from backend.core.episodic_memory import EpisodicMemory
        episodic_nodes = []
        try:
            episodic_nodes = EpisodicMemory.recall(query, limit=limit, session_id=session_id)
        except Exception as e:
            from backend.core.logger import log_event
            log_event(f"MemoryBroker retrieve: episodic recall failed: {e}")
            
        # 3. Procedural Memory
        from backend.core.procedural_memory import ProceduralMemory
        procedural_nodes = []
        try:
            procedural_nodes = ProceduralMemory.match_trigger(query)
        except Exception as e:
            from backend.core.logger import log_event
            log_event(f"MemoryBroker retrieve: procedural match failed: {e}")

        # 4. Goal Memory
        from backend.core.goal_memory import GoalMemory
        goal_nodes = []
        try:
            all_goals = GoalMemory.list_goals()
            q_lower = query.lower()
            q_words = [w for w in q_lower.split() if len(w) > 2]
            for g in all_goals:
                title_lower = g["title"].lower()
                desc_lower = (g.get("description") or "").lower()
                if q_lower in title_lower or q_lower in desc_lower or (
                    q_words and any(w in title_lower or w in desc_lower for w in q_words)
                ):
                    goal_nodes.append(g)
            goal_nodes = goal_nodes[:limit]
        except Exception as e:
            from backend.core.logger import log_event
            log_event(f"MemoryBroker retrieve: goal match failed: {e}")

        # 5. Belief System
        from backend.core.human_memory import HumanMemory
        belief_nodes = []
        try:
            belief_nodes = HumanMemory.list_beliefs(query)
            if not belief_nodes:
                all_beliefs = HumanMemory.list_beliefs(include_history=False)
                q_lower = query.lower()
                q_words = [w for w in q_lower.split() if len(w) > 2]
                for b in all_beliefs:
                    key_lower = b["key"].lower()
                    val_lower = b["value"].lower()
                    if (
                        q_lower in key_lower
                        or q_lower in val_lower
                        or (q_words and any(w in key_lower or w in val_lower for w in q_words))
                    ):
                        belief_nodes.append(b)
            belief_nodes = belief_nodes[:limit]
        except Exception as e:
            from backend.core.logger import log_event
            log_event(f"MemoryBroker retrieve: belief match failed: {e}")

        # 6. Relationship Memory
        from backend.core.relationship_memory import RelationshipMemory
        relationship_notes = {}
        try:
            relationship_notes = RelationshipMemory.assemble("bala")
        except Exception as e:
            from backend.core.logger import log_event
            log_event(f"MemoryBroker retrieve: relationship assemble failed: {e}")

        # Rank all candidates and build unified context
        return cls._build_unified_context(
            query=query,
            semantic=semantic_nodes,
            episodic=episodic_nodes,
            procedural=procedural_nodes,
            goals=goal_nodes,
            beliefs=belief_nodes,
            relationship=relationship_notes,
            limit=limit
        )

    @classmethod
    def _build_unified_context(
        cls,
        query: str,
        semantic: list[dict[str, Any]],
        episodic: list[dict[str, Any]],
        procedural: list[dict[str, Any]],
        goals: list[dict[str, Any]],
        beliefs: list[dict[str, Any]],
        relationship: dict[str, Any],
        limit: int
    ) -> dict[str, Any]:
        """RRF Ranker & Context Builder.
        
        Ranks all returned memory candidates across systems and builds a formatted
        context block for the planner.
        """
        candidates = []
        
        # Normalize semantic candidates
        for node in semantic:
            candidates.append({
                "type": "semantic",
                "id": node.get("node_id") or node.get("id"),
                "content": f"[Semantic Concept: {node['title']}] {node['content_raw']}",
                "confidence": node.get("confidence_score") or node.get("confidence", 0.5),
                "decay_score": 1.0,
                "created_at": node.get("created_at", time.time())
            })
            
        # Normalize episodic candidates
        for ep in episodic:
            candidates.append({
                "type": "episodic",
                "id": ep.get("id"),
                "content": f"[Episode] {ep['content']}",
                "confidence": ep.get("importance", 0.5),
                "decay_score": ep.get("decay_score", 1.0),
                "created_at": ep.get("created_at", time.time())
            })

        # Normalize procedural candidates
        for proc in procedural:
            candidates.append({
                "type": "procedural",
                "id": proc.get("id"),
                "content": f"[Skill Trigger: {proc['trigger_phrase']}] Skill Name: {proc['skill_name']}, Steps: {proc['steps_json']}",
                "confidence": 1.0 if proc.get("trust_level") == "trusted" else 0.7,
                "decay_score": 1.0,
                "created_at": proc.get("created_at", time.time())
            })

        # Normalize goals
        for g in goals:
            candidates.append({
                "type": "goal",
                "id": g.get("goal_id") or g.get("id"),
                "content": f"[Goal: {g['title']}] Status: {g['status']}, Progress: {g['progress'] * 100:.1f}%, Priority: {g['priority']}",
                "confidence": g.get("confidence_score", 100.0) / 100.0,
                "decay_score": 1.0,
                "created_at": g.get("created_at", time.time())
            })

        # Normalize beliefs
        for b in beliefs:
            candidates.append({
                "type": "belief",
                "id": b.get("id"),
                "content": f"[Belief: {b['key']}] Current Value: {b['value']}, Active: {b['active']}",
                "confidence": b.get("confidence", 0.8),
                "decay_score": 1.0,
                "created_at": b.get("created_at", time.time())
            })

        # Calculate a unified score for each candidate
        # Score = (Keyword overlap * 0.40) + (Confidence * 0.35) + (Decay Score * 0.25)
        scored_candidates = []
        q_words = set(query.lower().split())
        for c in candidates:
            # Keyword overlap using Jaccard-like term overlap
            content_words = set(c["content"].lower().replace("[", " ").replace("]", " ").split())
            overlap = len(q_words.intersection(content_words)) / max(len(q_words), 1)
            
            score = (overlap * 0.40) + (c["confidence"] * 0.35) + (c["decay_score"] * 0.25)
            scored_candidates.append((c, score))

        # Sort by unified score descending
        scored_candidates.sort(key=lambda x: x[1], reverse=True)
        top_candidates = [item[0] for item in scored_candidates[:limit]]

        # Context Builder: build a clean structured markdown context
        context_lines = []
        context_lines.append("### Unified Memory Context")
        if relationship:
            context_lines.append(f"**Relationship context:** {relationship.get('summary', 'Active session with user')}")
            
        if not top_candidates:
            context_lines.append("No matching episodic, semantic, belief, or procedural memories found.")
        else:
            for item in top_candidates:
                context_lines.append(f"- {item['content']} (Source: {item['type'].upper()})")

        unified_context = "\n".join(context_lines)

        return {
            "top_candidates": top_candidates,
            "relationship_notes": relationship,
            "unified_context_string": unified_context
        }
