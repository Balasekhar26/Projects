"""
backend/core/memory/memory_manager.py

Abstract interface and registry for the Kattappa Persistent Memory Engine (v0.2).

IMemoryStore defines the mandatory contract that all memory subsystems
(WorkingMemoryStore, EpisodicMemoryStore, SemanticMemoryStore, etc.) must satisfy.

MemoryManager is a lightweight registry that routes MemoryRecord instances to the
correct store based on their MemoryType.  It does not own or initialize any store
itself; stores are registered externally by the bootstrap layer.

Design principles:
  - Stores are always accessed through their MemoryType key for routing clarity.
  - IMemoryStore is an ABC so type checkers can validate store implementations.
  - MemoryManager raises clear errors on missing or unregistered stores.
  - No global singleton is forced; callers instantiate and wire as needed.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from .schemas import MemoryRecord, MemoryType


class IMemoryStore(ABC):
    """Abstract contract that every memory subsystem must implement.

    A store is responsible for a specific MemoryType tier.  It handles
    its own persistence backend (SQLite, ChromaDB, in-memory, etc.)
    and exposes a uniform interface upward to the MemoryManager.
    """

    # The MemoryType this store is responsible for.  Subclasses must set this.
    memory_type: MemoryType

    @abstractmethod
    def save(self, record: MemoryRecord) -> None:
        """Persist or update a single MemoryRecord.

        Args:
            record: A fully validated MemoryRecord whose ``memory_type``
                    matches ``self.memory_type``.

        Raises:
            TypeError:  If the record's memory_type does not match this store.
            RuntimeError: On unrecoverable storage backend failures.
        """
        ...

    @abstractmethod
    def retrieve(self, query: Dict[str, Any], limit: int = 20) -> List[MemoryRecord]:
        """Query stored records matching the supplied filter dict.

        Supported filter keys are store-specific but the common set is:
            - ``tags``: List[str]  — any-match tag filter.
            - ``source_agent``: str — exact agent match.
            - ``min_importance``: float — lower bound on importance_score.
            - ``min_confidence``: float — lower bound on confidence.
            - ``since``: float — Unix epoch lower bound on timestamp.
            - ``until``: float — Unix epoch upper bound on timestamp.
            - ``text``: str — full-text or semantic query string.

        Args:
            query: Dict of filter keys and values (all optional).
            limit: Maximum number of records to return.

        Returns:
            List of matching MemoryRecord instances, newest-first.
        """
        ...

    @abstractmethod
    def forget(self, retention_threshold: float = 0.0) -> int:
        """Prune records whose current retention_score falls below the threshold.

        The ForgettingEngine calls this periodically.  Permanent memory types
        (PROCEDURAL, POLICY) should return 0 without touching any records.

        Args:
            retention_threshold: Records with score <= this value are removed.

        Returns:
            Number of records deleted.
        """
        ...

    # ------------------------------------------------------------------
    # Optional hook — stores may override for health reporting
    # ------------------------------------------------------------------
    def health_check(self) -> Dict[str, Any]:
        """Return basic health and capacity metrics for this store.

        Returns:
            Dict with at minimum ``{"status": "ok"|"degraded"|"unavailable"}``.
        """
        return {"status": "ok", "memory_type": self.memory_type.value}


class MemoryManager:
    """Registry and router for all registered IMemoryStore instances.

    Usage
    -----
    .. code-block:: python

        manager = MemoryManager()
        manager.register(working_store)
        manager.register(episodic_store)

        record = MemoryRecord(
            memory_type=MemoryType.EPISODIC,
            source_agent="goal_manager",
            payload={"goal": "deploy pipeline", "outcome": "success"},
        )
        manager.save(record)

        recent = manager.retrieve(
            MemoryType.EPISODIC,
            query={"min_importance": 0.6, "limit": 10},
        )
    """

    def __init__(self) -> None:
        self._stores: Dict[MemoryType, IMemoryStore] = {}

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------
    def register(self, store: IMemoryStore) -> None:
        """Register a store for its declared memory_type.

        Registering a second store for the same type replaces the first,
        allowing hot-swap in tests and future migration scenarios.

        Args:
            store: An IMemoryStore subclass instance.

        Raises:
            TypeError: If ``store`` does not expose a valid MemoryType.
        """
        if not isinstance(store, IMemoryStore):
            raise TypeError(
                f"Expected IMemoryStore subclass; got {type(store)!r}"
            )
        mt = getattr(store, "memory_type", None)
        if not isinstance(mt, MemoryType):
            raise TypeError(
                f"Store {type(store).__name__!r} must declare a MemoryType on .memory_type; got {mt!r}"
            )
        self._stores[mt] = store

    def unregister(self, memory_type: MemoryType) -> None:
        """Remove the registered store for a given memory type.

        Silently ignored if the type was not registered.
        """
        self._stores.pop(memory_type, None)

    def has_store(self, memory_type: MemoryType) -> bool:
        """Return True if a store is registered for the given MemoryType."""
        return memory_type in self._stores

    def get_store(self, memory_type: MemoryType) -> IMemoryStore:
        """Return the registered store for a given type.

        Raises:
            KeyError: If no store is registered for the requested type.
        """
        if memory_type not in self._stores:
            raise KeyError(
                f"No IMemoryStore registered for MemoryType.{memory_type.name}. "
                f"Registered types: {[t.value for t in self._stores]}"
            )
        return self._stores[memory_type]

    # ------------------------------------------------------------------
    # Core routing API
    # ------------------------------------------------------------------
    def save(self, record: MemoryRecord) -> None:
        """Route a MemoryRecord to the appropriate store and persist it.

        Args:
            record: A valid MemoryRecord.

        Raises:
            KeyError: If no store is registered for the record's memory_type.
            TypeError: If ``record`` is not a MemoryRecord.
        """
        if not isinstance(record, MemoryRecord):
            raise TypeError(f"Expected MemoryRecord; got {type(record)!r}")
        store = self.get_store(record.memory_type)
        store.save(record)

    def retrieve(
        self,
        memory_type: MemoryType,
        query: Optional[Dict[str, Any]] = None,
        limit: int = 20,
    ) -> List[MemoryRecord]:
        """Query a specific store for matching records.

        Args:
            memory_type: Which store tier to query.
            query:       Optional filter dict (see IMemoryStore.retrieve).
            limit:       Maximum records to return.

        Returns:
            Matching records, newest-first.
        """
        store = self.get_store(memory_type)
        return store.retrieve(query or {}, limit=limit)

    def forget(
        self,
        memory_type: Optional[MemoryType] = None,
        retention_threshold: float = 0.0,
    ) -> Dict[MemoryType, int]:
        """Trigger forgetting in one or all registered stores.

        Args:
            memory_type:         If supplied, prune only that store.
                                 If None, prune all registered stores.
            retention_threshold: Prune records whose retention_score is
                                 <= this value.

        Returns:
            Dict mapping each pruned MemoryType to the number of records deleted.
        """
        targets: List[MemoryType] = (
            [memory_type] if memory_type is not None else list(self._stores)
        )
        results: Dict[MemoryType, int] = {}
        for mt in targets:
            store = self.get_store(mt)
            results[mt] = store.forget(retention_threshold)
        return results

    def health(self) -> Dict[str, Any]:
        """Return health metrics for all registered stores."""
        return {mt.value: store.health_check() for mt, store in self._stores.items()}

    def retrieve_context(
        self,
        query_text: str,
        limit: int = 5,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Queries all registered stores, merges matching records, resolves conflicts, and
        sorts results via RRF ranking fusion.

        Returns:
            dict containing lists of matching memory records grouped by MemoryType values,
            plus a combined ranked list of context records.
        """
        results: Dict[str, List[MemoryRecord]] = {}
        all_candidates: List[MemoryRecord] = []

        query = {"text": query_text}
        if session_id is not None:
            query["session_id"] = session_id

        # Query all registered stores
        for mt, store in self._stores.items():
            try:
                records = store.retrieve(query, limit=limit * 2)
                results[mt.value] = records
                all_candidates.extend(records)
            except Exception:
                results[mt.value] = []

        # Resolve conflicts among candidates
        resolved = self.resolve_conflicts(all_candidates)

        # Apply Reciprocal Rank Fusion (RRF) for the combined ranked list.
        rrf_scores: Dict[str, float] = {}
        record_map: Dict[str, MemoryRecord] = {}
        
        resolved_ids = {r.memory_id for r in resolved}
        for mt_val, records in results.items():
            filtered_recs = [r for r in records if r.memory_id in resolved_ids]
            for rank, r in enumerate(filtered_recs):
                mid = r.memory_id
                record_map[mid] = r
                rrf_scores[mid] = rrf_scores.get(mid, 0.0) + (1.0 / (60.0 + rank))

        # Sort the resolved records by their RRF score
        ranked_ids = sorted(rrf_scores.keys(), key=lambda k: rrf_scores[k], reverse=True)
        combined_ranked = [record_map[mid] for mid in ranked_ids][:limit]

        return {
            "results": {k: [r for r in v if r.memory_id in record_map] for k, v in results.items()},
            "combined": combined_ranked,
        }

    def resolve_conflicts(self, records: List[MemoryRecord]) -> List[MemoryRecord]:
        """Resolves overlapping or contradictory memory records.
        
        Heuristic:
        - If multiple records represent the same entity/problem/title:
          - Keeps the active/pinned status over deprecated status.
          - Keeps the highest confidence score.
          - Keeps the newer record if confidence matches.
        """
        groups: Dict[str, List[MemoryRecord]] = {}
        for r in records:
            gkey = (
                r.payload.get("title") or 
                r.payload.get("concept") or 
                r.payload.get("rule_name") or 
                r.payload.get("skill_name") or 
                r.payload.get("key") or 
                r.memory_id
            )
            gkey_clean = " ".join(str(gkey).strip().lower().split())
            groups.setdefault(gkey_clean, []).append(r)

        resolved: List[MemoryRecord] = []
        for gkey, cluster in groups.items():
            if len(cluster) == 1:
                resolved.append(cluster[0])
                continue

            def sort_key(rec: MemoryRecord) -> Tuple[int, float, float]:
                is_pinned = 1 if (
                    rec.payload.get("status") == "ACTIVE" or
                    rec.payload.get("active") is True or
                    rec.payload.get("pinned") is True or
                    rec.importance_score == 1.0
                ) else 0
                
                is_deprecated = 1 if (
                    rec.payload.get("status") == "DEPRECATED" or
                    rec.payload.get("active") is False or
                    rec.payload.get("revoked") is True
                ) else 0

                status_score = is_pinned - is_deprecated
                return (status_score, rec.confidence, rec.timestamp)

            cluster.sort(key=sort_key, reverse=True)
            resolved.append(cluster[0])

        return resolved

    def __repr__(self) -> str:
        registered = [mt.value for mt in self._stores]
        return f"MemoryManager(registered={registered!r})"

    @classmethod
    def record_interaction(cls, text: str, importance: float = 0.5) -> None:
        """Parses interaction text, records entities and relationships, and commits an episodic memory trace."""
        import uuid
        from backend.core.memory.memory_store import MemoryStore
        from backend.core.memory.entity_extractor import EntityExtractor
        from backend.core.memory.relationship_extractor import RelationshipExtractor
        
        entities = EntityExtractor.extract_entities(text)
        for ent in entities:
            MemoryStore.upsert_entity(
                entity_id=ent["id"],
                name=ent["name"],
                entity_type=ent["type"],
                metadata=ent.get("metadata")
            )
            
        relationships = RelationshipExtractor.extract_relationships(text, entities)
        for rel in relationships:
            MemoryStore.add_relationship(
                rel_id=rel["id"],
                source_id=rel["source_id"],
                target_id=rel["target_id"],
                predicate=rel["predicate"],
                metadata=rel.get("metadata")
            )
            
        # Save episodic memory
        mem_id = f"mem_ep_{uuid.uuid4().hex[:6]}"
        MemoryStore.add_memory(
            mem_id=mem_id,
            content=text,
            mem_type="episodic",
            importance=importance,
            confidence=1.0
        )

    @classmethod
    def get_planner_context(cls, query: str) -> dict:
        """Assembles scoring-weighted context fragments and entity link triples for query terms."""
        from backend.core.memory.memory_retriever import MemoryRetriever
        mems = MemoryRetriever.retrieve_memories(query)
        triples = MemoryRetriever.retrieve_graph_context(query)
        
        return {
            "relevant_memories": [m["content"] for m in mems],
            "relationships": triples
        }
