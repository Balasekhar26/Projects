"""CognitiveMemoryBus — Phase K8.

Single entry-point for all memory reads and writes across Kattappa's 6-layer
cognitive memory hierarchy.  Every subsystem (orchestrator agents, planner, graph
pipeline) should route through this bus rather than importing memory modules
directly.

Memory types and their storage policies
─────────────────────────────────────────
  working      Session-scoped, always writable, cleared on session end.
  episodic     90-day TTL, importance-gated recall, LRU eviction.
  semantic     Indefinite, confidence ≥ 0.6 write gate.
  procedural   Indefinite, requires verification before write.
  long_term    Indefinite, human-approved writes only (gated by caller).
  knowledge_graph  Indefinite, evaluation-gate confidence ≥ 0.7, triggers KG sync.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any

from backend.core.logger import log_event


# ──────────────────────────────────────────────────────────────────────────────
# Storage Policies
# ──────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class StoragePolicy:
    """Defines write / read / eviction rules for one memory tier."""
    name: str
    ttl_days: float | None        # None = indefinite
    min_confidence: float         # minimum confidence score required to write
    requires_verification: bool   # external verification gate
    human_approval_required: bool
    triggers_kg_sync: bool        # whether a write should kick off KG sync


POLICIES: dict[str, StoragePolicy] = {
    "working": StoragePolicy(
        name="working",
        ttl_days=None,          # session-scoped (managed by WorkingMemory itself)
        min_confidence=0.20,    # very permissive — transient scratch space
        requires_verification=False,
        human_approval_required=False,
        triggers_kg_sync=False,
    ),
    "episodic": StoragePolicy(
        name="episodic",
        ttl_days=90.0,
        min_confidence=0.45,    # moderate — real events, but fallible recall
        requires_verification=False,
        human_approval_required=False,
        triggers_kg_sync=False,
    ),
    "semantic": StoragePolicy(
        name="semantic",
        ttl_days=None,
        min_confidence=0.75,    # high — durable conceptual knowledge
        requires_verification=False,
        human_approval_required=False,
        triggers_kg_sync=True,
    ),
    "procedural": StoragePolicy(
        name="procedural",
        ttl_days=None,
        min_confidence=0.90,    # very high — executed workflows affect real systems
        requires_verification=True,
        human_approval_required=False,
        triggers_kg_sync=False,
    ),
    "long_term": StoragePolicy(
        name="long_term",
        ttl_days=None,
        min_confidence=0.80,    # high, but gate is human approval, not confidence alone
        requires_verification=True,
        human_approval_required=True,  # final gate: human approved only
        triggers_kg_sync=False,
    ),
    "knowledge_graph": StoragePolicy(
        name="knowledge_graph",
        ttl_days=None,          # highest bar — KG is the shared truth substrate
        min_confidence=0.95,
        requires_verification=True,
        human_approval_required=False,
        triggers_kg_sync=True,
    ),
    "preference": StoragePolicy(
        name="preference",
        ttl_days=None,
        min_confidence=0.50,
        requires_verification=False,
        human_approval_required=False,
        triggers_kg_sync=False,
    ),
    "relationship": StoragePolicy(
        name="relationship",
        ttl_days=None,
        min_confidence=0.60,
        requires_verification=False,
        human_approval_required=False,
        triggers_kg_sync=False,
    ),
    "goal": StoragePolicy(
        name="goal",
        ttl_days=None,
        min_confidence=0.30,
        requires_verification=False,
        human_approval_required=False,
        triggers_kg_sync=False,
    ),
    "belief_graph": StoragePolicy(
        name="belief_graph",
        ttl_days=None,
        min_confidence=0.60,
        requires_verification=False,
        human_approval_required=False,
        triggers_kg_sync=True,
    ),
}


# ──────────────────────────────────────────────────────────────────────────────
# Write / Read result types
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class WriteResult:
    success: bool
    memory_type: str
    reason: str = ""
    record_id: str | None = None


@dataclass
class ReadResult:
    memory_type: str
    records: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None


# ──────────────────────────────────────────────────────────────────────────────
# CognitiveMemoryBus
# ──────────────────────────────────────────────────────────────────────────────

class CognitiveMemoryBus:
    """Central router for Kattappa's 6-layer cognitive memory hierarchy.

    Usage
    -----
    bus = CognitiveMemoryBus()

    # Write an episodic event
    result = bus.write("episodic", {"content": "...", "importance": 0.8, ...})

    # Read across multiple layers
    results = bus.read("radar signal processing", memory_types=["semantic", "knowledge_graph"])
    """

    _instance: "CognitiveMemoryBus | None" = None
    _lock: threading.Lock = threading.Lock()

    def __new__(cls) -> "CognitiveMemoryBus":
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
        return cls._instance

    # ── Write ──────────────────────────────────────────────────────────────

    def write(
        self,
        memory_type: str,
        data: dict[str, Any],
        confidence: float = 1.0,
        verified: bool = False,
    ) -> WriteResult:
        """Route a write to the appropriate memory tier.

        Parameters
        ----------
        memory_type:  one of working / episodic / semantic / procedural /
                      long_term / knowledge_graph
        data:         payload for the target memory store
        confidence:   caller-supplied confidence score (0.0–1.0)
        verified:     whether the caller has externally verified the data
        """
        policy = POLICIES.get(memory_type)
        if policy is None:
            return WriteResult(
                success=False,
                memory_type=memory_type,
                reason=f"Unknown memory type: {memory_type!r}. "
                       f"Valid types: {list(POLICIES)}",
            )

        # Policy gates
        if confidence < policy.min_confidence:
            return WriteResult(
                success=False,
                memory_type=memory_type,
                reason=(
                    f"Confidence {confidence:.2f} below minimum "
                    f"{policy.min_confidence:.2f} for {memory_type!r}"
                ),
            )
        if policy.requires_verification and not verified:
            return WriteResult(
                success=False,
                memory_type=memory_type,
                reason=f"{memory_type!r} writes require external verification",
            )
        if policy.human_approval_required and not data.get("human_approved"):
            return WriteResult(
                success=False,
                memory_type=memory_type,
                reason=f"{memory_type!r} writes require human_approved=True in data",
            )

        handler = getattr(self, f"_write_{memory_type}", None)
        if handler is None:
            return WriteResult(
                success=False,
                memory_type=memory_type,
                reason=f"No write handler implemented for {memory_type!r}",
            )

        try:
            record_id = handler(data)
            log_event(
                "cognitive_memory_bus_write",
                f"{memory_type} write OK — id={record_id} conf={confidence:.2f}",
            )
            if policy.triggers_kg_sync:
                self._trigger_kg_sync()
            return WriteResult(success=True, memory_type=memory_type, record_id=record_id)
        except Exception as exc:
            log_event("cognitive_memory_bus_write_error", f"{memory_type}: {exc}")
            return WriteResult(success=False, memory_type=memory_type, reason=str(exc))

    # ── Read ───────────────────────────────────────────────────────────────

    def read(
        self,
        query: str,
        memory_types: list[str] | None = None,
        session_id: str | None = None,
        limit: int = 10,
    ) -> list[ReadResult]:
        """Fan-out a read across one or more memory tiers.

        Parameters
        ----------
        query:        natural language query string
        memory_types: explicit tier override.  When None (default), the
                      IntentRouter classifies the query and selects the
                      optimal tiers automatically.
        session_id:   optional session context for working/episodic reads
        limit:        max records per tier

        Returns a list of ReadResult objects in the order of memory_types.
        """
        if memory_types is None:
            from backend.core.intent_router import IntentRouter
            decision = IntentRouter.route(query)
            memory_types = decision.memory_types
            log_event(
                "cognitive_memory_bus_intent_routed",
                f"Query intent={decision.intent.value} → tiers={memory_types}: {decision.reasoning}",
            )

        results: list[ReadResult] = []
        for mt in memory_types:
            handler = getattr(self, f"_read_{mt}", None)
            if handler is None:
                results.append(ReadResult(
                    memory_type=mt,
                    error=f"No read handler for {mt!r}",
                ))
                continue
            try:
                records = handler(query, session_id=session_id, limit=limit)
                results.append(ReadResult(memory_type=mt, records=records))
            except Exception as exc:
                log_event("cognitive_memory_bus_read_error", f"{mt}: {exc}")
                results.append(ReadResult(memory_type=mt, error=str(exc)))
        return results

    # ── Per-type write handlers ────────────────────────────────────────────

    def _write_working(self, data: dict[str, Any]) -> str | None:
        from backend.core.working_memory import WorkingMemory
        session_id = data.get("session_id", "default")
        goal_text = data.get("goal_text")
        trace_type = data.get("trace_type", "thought")
        content = data.get("content", "")

        if goal_text:
            return WorkingMemory.push_goal(session_id, goal_text, data.get("parent_goal_id"))
        return WorkingMemory.log_trace(
            session_id=session_id,
            goal_id=data.get("goal_id"),
            task_id=data.get("task_id"),
            trace_type=trace_type,
            content=content,
        )

    def _write_episodic(self, data: dict[str, Any]) -> str | None:
        from backend.core.episodic_memory import EpisodicMemory
        # create_episode returns a str (event_id)
        event_id = EpisodicMemory.create_episode(
            content=data.get("content", ""),
            importance=data.get("importance", 0.5),
            category=data.get("category", "PLANNING"),
            session_id=data.get("session_id", "primary"),
            tags=data.get("tags", []),
            pinned=int(data.get("pinned", 0)),
            source=data.get("source", "cognitive_bus"),
        )
        return event_id

    def _write_semantic(self, data: dict[str, Any]) -> str | None:
        from backend.core.semantic_memory import SemanticMemory
        # upsert_node returns a str (node_id)
        node_id = SemanticMemory.upsert_node(
            concept=data.get("concept", ""),
            description=data.get("description", ""),
            source_episode_id=data.get("source_episode_id", "cognitive_bus"),
            provenance=data.get("provenance"),
            confidence=data.get("confidence", 0.7),
            node_type=data.get("node_type", "FACT"),
            source_type=data.get("source_type", "REFLECTION_CORROBORATED"),
        )
        return node_id

    def _write_procedural(self, data: dict[str, Any]) -> str | None:
        import json as _json
        from backend.core.procedural_memory import ProceduralMemory
        steps = data.get("steps", [])
        steps_json = _json.dumps(steps) if not isinstance(steps, str) else steps
        # register_procedure returns a str (procedure_id)
        pid = ProceduralMemory.register_procedure(
            skill_name=data.get("skill_name", "unknown"),
            trigger_phrase=data.get("trigger_phrase"),
            steps_json=steps_json,
            trust_level=data.get("trust_level", "USER_APPROVED"),
            derived_from_nodes=data.get("derived_from_nodes"),
            failure_reason=data.get("failure_reason"),
        )
        return pid

    def _write_long_term(self, data: dict[str, Any]) -> str | None:
        from backend.core.long_term_memory import LongTermMemory
        partition = data.get("partition", "General")
        LongTermMemory.add_record(partition, data.get("record"))
        return f"{partition}:appended"

    def _write_knowledge_graph(self, data: dict[str, Any]) -> str | None:
        from backend.core.graph_store import GraphStore
        from backend.core.config import load_config
        config = load_config()
        store = GraphStore(str(config.sqlite_path))
        node_id = store.insert_node(
            name=data.get("name", ""),
            entity_type=data.get("entity_type", "CONCEPT"),
            description=data.get("description", ""),
            properties=data.get("properties", {}),
            confidence=data.get("confidence", 0.7),
        )
        # Optional edge
        if data.get("relates_to"):
            target = store.get_node_by_name(data["relates_to"])
            if target:
                store.insert_edge(
                    source_id=node_id,
                    target_id=target["id"],
                    relation_type=data.get("relation_type", "RELATES_TO"),
                    properties={},
                    confidence=data.get("confidence", 0.7),
                )
        return node_id

    def _write_preference(self, data: dict[str, Any]) -> str | None:
        from backend.core.preference_memory import PreferenceMemory
        key = data.get("key", "")
        value = data.get("value")
        confidence = data.get("confidence", 1.0)
        res = PreferenceMemory.set_preference(key, value, confidence)
        return key

    def _write_relationship(self, data: dict[str, Any]) -> str | None:
        from backend.core.relationship_memory import RelationshipMemory
        entity_id = data.get("entity_id", "user")
        name = data.get("name", "User")
        entity_type = data.get("entity_type", "user")
        trust_level = data.get("trust_level", "TRUST_UNVERIFIED")
        RelationshipMemory.get_or_create_entity(entity_id, name, entity_type, trust_level)
        if "emotion" in data:
            RelationshipMemory.set_emotional_state(entity_id, data["emotion"], data.get("confidence", 1.0))
        return entity_id

    def _write_goal(self, data: dict[str, Any]) -> str | None:
        from backend.core.goal_manager import GoalManager
        goal = GoalManager.add_goal(
            title=data.get("title", ""),
            description=data.get("description"),
            priority=data.get("priority", "MEDIUM"),
            parent_id=data.get("parent_id"),
            depends_on=data.get("depends_on"),
            max_retries=data.get("max_retries", 0),
        )
        return goal["goal_id"]

    def _write_belief_graph(self, data: dict[str, Any]) -> str | None:
        from backend.core.cos.belief_engine import BeliefEngine
        from backend.core.cos.state_representation import BeliefState, EvidenceSource, ObservedState, PropertyValue
        import uuid
        b_state = BeliefState(state_id=data.get("state_id", "default_state"), branch_id=data.get("branch_id", "main"))
        engine = BeliefEngine(b_state)
        obs = ObservedState(state_id=f"obs_{uuid.uuid4().hex[:8]}", branch_id=data.get("branch_id", "main"))
        src = EvidenceSource(
            name=data.get("source_name", "sensor"),
            source_type=data.get("source_type", "sensor"),
            reliability=data.get("reliability", 0.8)
        )
        pv = PropertyValue(
            value=data.get("value"),
            confidence=data.get("confidence", 0.7),
            source=src
        )
        entity_id = data.get("entity_id", "system")
        prop_name = data.get("prop_name", "status")
        obs.set_property(entity_id, prop_name, pv)
        engine.process_observation(obs)
        return b_state.state_id

    # ── Per-type read handlers ─────────────────────────────────────────────

    def _read_working(
        self,
        query: str,
        session_id: str | None = None,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        from backend.core.working_memory import WorkingMemory
        sid = session_id or "default"
        ctx = WorkingMemory.get_active_workspace_context(sid)
        # Return combined traces filtered by query substring
        traces = ctx.get("traces", [])
        if query:
            traces = [t for t in traces if query.lower() in t.get("content", "").lower()]
        return traces[:limit]

    def _read_episodic(
        self,
        query: str,
        session_id: str | None = None,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        from backend.core.episodic_memory import EpisodicMemory
        results = EpisodicMemory.recall(
            query=query,
            limit=limit,
            session_id=session_id,
        )
        episodes = results.get("episodes", []) if isinstance(results, dict) else (results or [])
        return self._apply_act_r_ranking(episodes, limit)

    def _read_semantic(
        self,
        query: str,
        session_id: str | None = None,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        from backend.core.semantic_memory import SemanticMemory
        results = SemanticMemory.recall(
            query=query,
            limit=limit,
        )
        return self._apply_act_r_ranking(results or [], limit)

    def _read_procedural(
        self,
        query: str,
        session_id: str | None = None,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        from backend.core.procedural_memory import ProceduralMemory
        matches = ProceduralMemory.match_trigger(query)
        return matches[:limit]

    def _read_knowledge_graph(
        self,
        query: str,
        session_id: str | None = None,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        from backend.core.graph_store import GraphStore
        from backend.core.config import load_config
        config = load_config()
        store = GraphStore(str(config.sqlite_path))
        return store.search_nodes_fts(query, limit=limit)

    def _read_preference(
        self,
        query: str,
        session_id: str | None = None,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        from backend.core.preference_memory import PreferenceMemory
        if query:
            pref = PreferenceMemory.get_preference(query)
            return [pref] if pref else []
        return PreferenceMemory.list_preferences()[:limit]

    def _read_relationship(
        self,
        query: str,
        session_id: str | None = None,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        from backend.core.relationship_memory import RelationshipMemory
        ent = RelationshipMemory.get_entity(query or "user")
        return [ent] if ent else []

    def _read_goal(
        self,
        query: str,
        session_id: str | None = None,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        from backend.core.goal_manager import GoalManager
        goals = GoalManager.list_goals()
        if query:
            goals = [g for g in goals if query.lower() in g["title"].lower() or query.lower() in (g.get("description") or "").lower()]
        return goals[:limit]

    def _read_belief_graph(
        self,
        query: str,
        session_id: str | None = None,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        from backend.core.cos.state_representation import BeliefState
        b_state = BeliefState(state_id="default_state", branch_id="main")
        return [{"state_id": b_state.state_id, "branch_id": b_state.branch_id, "query": query}]

    def _apply_act_r_ranking(self, records: list[Any], limit: int) -> list[dict[str, Any]]:
        """Rank records using Act-R dynamic activation formula."""
        import math
        import time
        now = time.time()
        ranked = []
        for r in records:
            r_dict = dict(r) if hasattr(r, "to_dict") or not isinstance(r, dict) else dict(r)
            sim = r_dict.get("similarity", 1.0)
            if sim is None:
                sim = 1.0
            act = r_dict.get("act_r_activation", 1.0) or r_dict.get("importance", 1.0) or 1.0
            created = r_dict.get("created_at") or r_dict.get("timestamp") or now
            decay_rate = r_dict.get("decay_rate", 0.05) or 0.05
            
            # Δt in hours
            dt = max(0.0, (now - created) / 3600.0)
            recency = math.exp(-decay_rate * dt)
            
            score = 0.5 * sim + 0.3 * act + 0.2 * recency
            r_dict["recall_score"] = score
            ranked.append(r_dict)
            
        ranked.sort(key=lambda x: x["recall_score"], reverse=True)
        return ranked[:limit]

    # ── KG sync trigger ────────────────────────────────────────────────────

    def _trigger_kg_sync(self) -> None:
        """Asynchronously trigger an incremental KG sync."""
        import threading

        def _sync():
            try:
                from backend.core.graph_store import GraphStore
                from backend.core.kg_sync import SyncManager
                from backend.core.config import load_config
                config = load_config()
                store = GraphStore(str(config.sqlite_path))
                manager = SyncManager(graph_store=store)
                manager.incremental_sync(db_path=str(config.sqlite_path))
                log_event("cognitive_memory_bus_kg_sync", "Incremental KG sync complete")
            except Exception as exc:
                log_event("cognitive_memory_bus_kg_sync_error", str(exc))

        threading.Thread(target=_sync, daemon=True, name="CognitiveBus-KGSync").start()


# Module-level singleton
MEMORY_BUS = CognitiveMemoryBus()
