"""Probabilistic Knowledge Graph (PKG) — Phase K21.7.

Implements ProbabilisticKnowledgeGraph managing entities and directed relations with uncertainty metrics,
path probability traversal, and Noisy-OR parallel path combination logic.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Set, Tuple

from backend.core.cos.entity_system import Relation
from backend.core.logger import log_event

logger = logging.getLogger(__name__)


class ProbabilisticKnowledgeGraph:
    """Manages semantic entities and directed edges (relations) with confidence/probability propagation."""

    def __init__(self):
        # Maps source_uuid -> List of Relation objects
        self.adjacency: Dict[str, List[Relation]] = {}

    def add_relation(self, relation: Relation) -> None:
        """Adds a relation to the knowledge graph."""
        self.adjacency.setdefault(relation.source_uuid, []).append(relation)
        log_event(
            "pkg_relation_added",
            f"PKG: Added relation {relation.source_uuid} --[{relation.relation_type}]--> {relation.target_uuid} (conf={relation.confidence})"
        )

    def get_relations(self, source_uuid: str) -> List[Relation]:
        """Returns all relations originating from the source entity."""
        return self.adjacency.get(source_uuid, [])

    def find_paths(self, source_uuid: str, target_uuid: str, visited: Optional[Set[str]] = None) -> List[Tuple[List[str], float]]:
        """DFS traversing the graph to find all unique simple paths, returning node lists and path probabilities."""
        if visited is None:
            visited = set()

        if source_uuid == target_uuid:
            return [([source_uuid], 1.0)]

        visited.add(source_uuid)
        paths: List[Tuple[List[str], float]] = []

        for rel in self.adjacency.get(source_uuid, []):
            next_node = rel.target_uuid
            if next_node not in visited:
                sub_paths = self.find_paths(next_node, target_uuid, visited)
                for path, prob in sub_paths:
                    paths.append(([source_uuid] + path, prob * rel.confidence))

        visited.remove(source_uuid)
        return paths

    def infer_indirect_relation_probability(self, source_uuid: str, target_uuid: str) -> float:
        """Aggregates all parallel paths between source and target using the Noisy-OR formula."""
        paths = self.find_paths(source_uuid, target_uuid)
        if not paths:
            return 0.0

        # Calculate joint probability using Noisy-OR: P = 1 - product(1 - p_i)
        q_product = 1.0
        for _, path_prob in paths:
            q_product *= (1.0 - path_prob)

        combined_prob = 1.0 - q_product
        log_event(
            "pkg_noisy_or_inference",
            f"PKG Inference: Combined probability {source_uuid} -> {target_uuid} = {combined_prob:.4f} across {len(paths)} paths"
        )
        return combined_prob
