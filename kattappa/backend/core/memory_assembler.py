from __future__ import annotations

"""Memory Assembler — Cross-Layer Retrieval Orchestrator.

Aggregates results from Episodic, Semantic, and Procedural memory layers
into a single ranked context response for any user query.  Uses Reciprocal
Rank Fusion (RRF) to merge the semantic-facts and episodic-experience
rankings, while matched executable procedures are surfaced separately in
an ``actions`` section.

Architecture contract:
  - Episodic memory  : authoritative in ``hm_episodes`` (SQLite).
  - Semantic memory  : authoritative in ``hm_semantic_nodes`` (SQLite).
  - Procedural memory: authoritative in ``hm_procedures`` (SQLite).
  - All Chroma / vector indices are non-authoritative look-aside caches.
  - The Assembler never writes to any layer; it is read-only.
"""

from typing import Any, Dict, List, Optional

from backend.core.logger import log_event


# Reciprocal-Rank Fusion constant (standard value from the literature).
_RRF_K: float = 60.0


class MemoryAssembler:
    """Unified cross-layer memory retrieval facade.

    Public API
    ----------
    assemble_context(query_text, limit) -> dict
        Returns a structured context dict with keys:
          - ``facts``      : ranked semantic nodes (promoted facts).
          - ``episodes``   : ranked episodic memories.
          - ``actions``    : matching procedural triggers (executable).
          - ``query``      : the original query text.
          - ``total_hits`` : total candidates before limit truncation.
    """

    # ---------- Public API ----------

    @classmethod
    def assemble_context(
        cls,
        query_text: str,
        limit: int = 5,
        include_actions: bool = True,
        skip_semantic: bool = False,
    ) -> Dict[str, Any]:
        """Retrieve a ranked cross-layer context for *query_text*.

        Parameters
        ----------
        query_text:
            Natural-language query from the user or system.
        limit:
            Maximum number of items per section (facts, episodes).
        include_actions:
            Whether to run procedural trigger matching.
        skip_semantic:
            If True, skips retrieving Tier 4 semantic/episodic recall to optimize hot-path latencies.

        Returns
        -------
        dict with keys: ``query``, ``facts``, ``episodes``, ``actions``, ``goals``,
        ``total_hits``.
        """
        query_text = query_text.strip()

        try:
            semantic_hits: List[Dict[str, Any]] = [] if skip_semantic else cls._query_semantic(query_text, limit)
        except Exception as exc:
            log_event(f"memory_assembler: semantic layer failed: {exc}")
            semantic_hits = []

        try:
            episodic_hits: List[Dict[str, Any]] = [] if skip_semantic else cls._query_episodic(query_text, limit)
        except Exception as exc:
            log_event(f"memory_assembler: episodic layer failed: {exc}")
            episodic_hits = []

        try:
            procedural_hits: List[Dict[str, Any]] = (
                cls._query_procedural(query_text) if include_actions else []
            )
        except Exception as exc:
            log_event(f"memory_assembler: procedural layer failed: {exc}")
            procedural_hits = []

        try:
            goal_hits: List[Dict[str, Any]] = cls._query_strategic(limit)
        except Exception as exc:
            log_event(f"memory_assembler: strategic layer failed: {exc}")
            goal_hits = []

        # Retrieve Layer 7 Relationship Memory (primary personalization)
        relationship_ctx: Dict[str, Any] = {}
        try:
            from backend.core.relationship_memory import RelationshipMemory
            entity_id = "primary"
            # Ensure primary user entity exists
            RelationshipMemory.get_or_create_entity(entity_id, "User", "user", "TRUST_USER")
            
            # Tier 1
            approved_prefs = RelationshipMemory.get_preferences(entity_id, min_confidence=0.5)
            active_rel_goals = [g for g in RelationshipMemory.get_user_goals(entity_id, include_unapproved=False, min_priority=0.3) if g["status"] == "active"]
            
            # Tier 2
            active_projects = [p for p in RelationshipMemory.get_projects(entity_id, min_priority=0.3) if p["status"] == "active"]
            recent_history = RelationshipMemory.get_history(entity_id, limit=5, min_importance=0.3)
            
            # Tier 3
            archived_rel_goals = [g for g in RelationshipMemory.get_user_goals(entity_id, include_unapproved=True, min_priority=0.3) if g["status"] in ("completed", "archived")]
            older_history = RelationshipMemory.get_history(entity_id, limit=20, min_importance=0.3)[5:]
            
            # Ephemeral Emotional State (Opt-in)
            emotional_state = RelationshipMemory.get_emotional_state(entity_id)

            relationship_ctx = {
                "preferences": approved_prefs,
                "active_goals": active_rel_goals,
                "active_projects": active_projects,
                "recent_history": recent_history,
                "archived_goals": archived_rel_goals,
                "older_history": older_history,
                "emotional_state": emotional_state,
            }
        except Exception as exc:
            log_event(f"memory_assembler: relationship memory layer failed: {exc}")

        # RRF fusion across facts and episodes in their respective lists.
        fused_facts, fused_episodes = cls._fuse(semantic_hits, episodic_hits, limit)

        total_hits = len(semantic_hits) + len(episodic_hits) + len(procedural_hits) + len(goal_hits)
        if relationship_ctx:
            total_hits += len(relationship_ctx.get("preferences", [])) + len(relationship_ctx.get("active_goals", []))

        return {
            "query": query_text,
            "facts": fused_facts,
            "episodes": fused_episodes,
            "actions": procedural_hits,
            "goals": goal_hits,
            "relationship_memory": relationship_ctx,
            "total_hits": total_hits,
        }

    # ---------- Layer Adapters ----------

    @classmethod
    def _query_semantic(cls, query: str, limit: int) -> List[Dict[str, Any]]:
        """Delegate to SemanticMemory.recall(); return [] on any error."""
        try:
            from backend.core.semantic_memory import SemanticMemory  # local import to avoid circular deps

            results = SemanticMemory.recall(query, limit=limit * 2)
            return results
        except Exception as exc:
            log_event(f"memory_assembler: semantic recall failed: {exc}")
            return []

    @classmethod
    def _query_episodic(cls, query: str, limit: int) -> List[Dict[str, Any]]:
        """Delegate to EpisodicMemory.recall(); return [] on any error."""
        try:
            from backend.core.episodic_memory import EpisodicMemory

            results = EpisodicMemory.recall(query, limit=limit * 2)
            return results
        except Exception as exc:
            log_event(f"memory_assembler: episodic recall failed: {exc}")
            return []

    @classmethod
    def _query_procedural(cls, query: str) -> List[Dict[str, Any]]:
        """Delegate to ProceduralMemory.match_trigger(); return [] on any error."""
        try:
            from backend.core.procedural_memory import ProceduralMemory

            matches = ProceduralMemory.match_trigger(query)
            # Surface only trusted, non-revoked procedures
            trusted = {
                "SYSTEM_TRUST",
                "USER_APPROVED",
            }
            return [
                m for m in matches
                if m.get("trust_level") in trusted and not m.get("revoked")
            ]
        except Exception as exc:
            log_event(f"memory_assembler: procedural trigger match failed: {exc}")
            return []

    @classmethod
    def _query_strategic(cls, limit: int) -> List[Dict[str, Any]]:
        """Delegate to StrategicMemory.get_active_goals(); return [] on any error."""
        try:
            from backend.core.strategic_memory import StrategicMemory
            results = StrategicMemory.get_active_goals(limit=limit)
            return results
        except Exception as exc:
            log_event(f"memory_assembler: strategic goals query failed: {exc}")
            return []

    # ---------- RRF Fusion ----------

    @classmethod
    def _fuse(
        cls,
        semantic_hits: List[Dict[str, Any]],
        episodic_hits: List[Dict[str, Any]],
        limit: int,
    ) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Apply Reciprocal Rank Fusion within each list and re-rank.

        Each list is independently re-ranked by RRF score (combining the
        original list rank with any rrf_score already computed by the layer).
        Results are truncated to *limit*.

        Note: RRF across two *different* content-type lists (facts vs episodes)
        is intentionally kept separate — the two result sets are semantically
        different types and should not be merged into one ranking.  They are
        returned as two independently-scored lists.
        """
        fused_facts = cls._rrf_rerank(semantic_hits, limit)
        fused_episodes = cls._rrf_rerank(episodic_hits, limit)
        return fused_facts, fused_episodes

    @classmethod
    def _rrf_rerank(
        cls,
        hits: List[Dict[str, Any]],
        limit: int,
    ) -> List[Dict[str, Any]]:
        """Re-rank *hits* by RRF score incorporating pre-existing rrf_score.

        If a record already has ``rrf_score`` from the layer's own hybrid
        retrieval, boost it proportionally so that the Assembler ordering
        respects layer-level fusion results.
        """
        scored: List[tuple[float, Dict[str, Any]]] = []
        for rank, hit in enumerate(hits):
            # Base RRF contribution from position in this list.
            position_score = 1.0 / (_RRF_K + rank + 1)
            # Absorb any existing rrf_score from layer-level retrieval.
            existing_rrf = float(hit.get("rrf_score", 0.0))
            total_score = position_score + existing_rrf
            hit = dict(hit)  # shallow copy to avoid mutating the original
            hit["assembler_score"] = round(total_score, 8)
            scored.append((total_score, hit))

        scored.sort(key=lambda kv: kv[0], reverse=True)
        return [item for _, item in scored[:limit]]
