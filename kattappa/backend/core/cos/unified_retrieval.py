from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from backend.core.knowledge_graph import KnowledgeGraph
from backend.core.semantic_memory import SemanticMemory
from backend.core.episodic_memory import EpisodicMemory

logger = logging.getLogger(__name__)


class UnifiedRetrievalPipeline:
    """Combines vector-based memory recalls with graph-based probabilistic path reasoning."""

    @classmethod
    def retrieve(
        cls,
        query: str,
        session_id: str | None = None,
        limit: int = 5,
        max_depth: int = 3,
        min_probability: float = 0.1,
    ) -> Dict[str, Any]:
        """Runs the unified retrieval flow.

        Returns a dict:
        {
            "facts": [...],
            "episodes": [...],
            "graph_paths": [...],
            "provenance": {...},
            "context_text": str
        }
        """
        # 1. Vector/FTS recalls
        try:
            semantic_results = SemanticMemory.recall(query=query, limit=limit) or []
        except Exception as exc:
            logger.debug("UnifiedRetrieval: SemanticMemory recall failed: %s", exc)
            semantic_results = []

        try:
            episodic_results = EpisodicMemory.recall(query=query, limit=limit, session_id=session_id) or []
        except Exception as exc:
            logger.debug("UnifiedRetrieval: EpisodicMemory recall failed: %s", exc)
            episodic_results = []

        # Parse list if dictionary is returned
        if isinstance(episodic_results, dict):
            episodic_results = episodic_results.get("episodes", [])

        # 2. Extract entities and resolve to canonical targets
        kg = KnowledgeGraph.get_instance()
        matched_canonical_ids = set()

        # Collect entity candidate names from search results
        candidate_names = set()
        for r in semantic_results:
            r_dict = dict(r) if not isinstance(r, dict) else r
            title = r_dict.get("title")
            if title:
                candidate_names.add(title)
            content = r_dict.get("content_raw") or r_dict.get("content") or ""
            for word in content.split():
                if word.istitle() and len(word) > 2:
                    candidate_names.add(word.strip(".,;:?!()\"'"))

        for r in episodic_results:
            r_dict = dict(r) if not isinstance(r, dict) else r
            summary = r_dict.get("summary", "")
            for word in summary.split():
                if word.istitle() and len(word) > 2:
                    candidate_names.add(word.strip(".,;:?!()\"'"))
            participants = r_dict.get("participants", [])
            if isinstance(participants, list):
                candidate_names.update(participants)

        # Query FTS in KnowledgeGraph directly for node matches
        try:
            fts_nodes = kg.search_nodes_fts(query, limit=limit) or []
            for fn in fts_nodes:
                matched_canonical_ids.add(fn["id"])
        except Exception as exc:
            logger.debug("UnifiedRetrieval: Node FTS search failed: %s", exc)

        # Resolve candidates to canonical IDs
        for name in candidate_names:
            try:
                resolved = kg.resolve_entity(name)
                if resolved:
                    matched_canonical_ids.add(resolved.id)
            except Exception:
                pass

        # 3. Trace paths (Dijkstra find_top_k_paths) in the PKG
        graph_paths = []
        provenance = {}

        # Iterate over pairs of matched canonical IDs to find connections
        canonical_list = list(matched_canonical_ids)[:10]  # Cap search entities to 10 for latency
        for i in range(len(canonical_list)):
            for j in range(i + 1, len(canonical_list)):
                src = canonical_list[i]
                tgt = canonical_list[j]

                # Check path both ways
                for s_id, t_id in [(src, tgt), (tgt, src)]:
                    try:
                        res = kg.query_probabilistic(s_id, t_id, max_depth=max_depth)
                        if res and res.combined_probability >= min_probability:
                            graph_paths.append({
                                "source": s_id,
                                "target": t_id,
                                "path": res.best_path,
                                "probability": res.combined_probability,
                                "explanation": res.explanation.explanation_text,
                            })
                            # Extract edge/node provenance metadata
                            for node in res.explanation.visited_nodes:
                                node_data = kg.get_node(node)
                                if node_data:
                                    provenance[node] = {
                                        "entity_type": node_data.get("type") or node_data.get("entity_type"),
                                        "confidence": node_data.get("confidence", 1.0),
                                        "belief_state": node_data.get("belief_state", "BELIEVED"),
                                        "evidence": node_data.get("evidence", []),
                                    }
                    except Exception as exc:
                        logger.debug("UnifiedRetrieval: PKG query failed: %s", exc)

        # Assemble human-readable context text
        context_lines = []
        if semantic_results:
            context_lines.append("=== RETRIEVED SEMANTIC FACTS ===")
            for r in semantic_results:
                r_dict = dict(r) if not isinstance(r, dict) else r
                context_lines.append(f"- {r_dict.get('title')}: {r_dict.get('content_raw') or r_dict.get('content')}")
            context_lines.append("")

        if episodic_results:
            context_lines.append("=== RETRIEVED EPISODIC CONTEXT ===")
            for r in episodic_results:
                r_dict = dict(r) if not isinstance(r, dict) else r
                context_lines.append(f"- Episode {r_dict.get('id') or r_dict.get('node_id')}: {r_dict.get('summary')}")
            context_lines.append("")

        if graph_paths:
            context_lines.append("=== KNOWLEDGE GRAPH RELATIONSHIPS ===")
            for gp in graph_paths:
                context_lines.append(f"- Path: {' -> '.join(gp['path'])} (Joint Probability: {gp['probability']:.4f})")
                context_lines.append(f"  Explanation: {gp['explanation'].splitlines()[-1] if gp['explanation'] else ''}")
            context_lines.append("")

        context_text = "\n".join(context_lines)

        return {
            "facts": semantic_results,
            "episodes": episodic_results,
            "graph_paths": graph_paths,
            "provenance": provenance,
            "context_text": context_text,
        }
