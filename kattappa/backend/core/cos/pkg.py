"""Probabilistic Knowledge Graph (PKG) — Phase K21.7.1 - K21.7.3.

Implements ProbabilisticKnowledgeGraph with temporal validity filtering, relation filters,
exact dependency-aware probability combination via recursive edge conditioning, and
structured explainability InferenceResults.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

from backend.core.cos.entity_system import Relation
from backend.core.logger import log_event

logger = logging.getLogger(__name__)


@dataclass
class InferenceExplanation:
    """Detailed trace explanation of a probabilistic graph query inference."""
    paths: List[List[str]]
    edge_confidences: Dict[str, float]
    combined_probability: float
    visited_nodes: List[str]
    explanation_text: str


@dataclass
class InferenceResult:
    """Return package for a probabilistic graph query."""
    paths: List[List[str]]
    combined_probability: float
    best_path: Optional[List[str]]
    explanation: InferenceExplanation
    visited_nodes: List[str]
    computation_time: float


class ProbabilisticKnowledgeGraph:
    """Manages semantic entities and directed edges (relations) with exact probability propagation."""

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

    def find_paths(
        self,
        source_uuid: str,
        target_uuid: str,
        visited: Optional[Set[str]] = None
    ) -> List[Tuple[List[str], float]]:
        """DFS traversing the graph to find all unique simple paths, returning node lists and path probabilities."""
        raw_paths = self._find_paths_with_relations(source_uuid, target_uuid, visited=visited)
        paths = []
        for path_nodes, rels in raw_paths:
            path_prob = 1.0
            for r in rels:
                path_prob *= r.confidence
            paths.append((path_nodes, path_prob))
        return paths

    def infer_indirect_relation_probability(self, source_uuid: str, target_uuid: str) -> float:
        """Aggregates all parallel paths between source and target using the exact joint probability query."""
        res = self.query(source_uuid, target_uuid)
        return res.combined_probability

    def _find_paths_with_relations(
        self,
        source_uuid: str,
        target_uuid: str,
        max_depth: int = 6,
        at_time: Optional[float] = None,
        allowed_relations: Optional[List[str]] = None,
        visited: Optional[Set[str]] = None
    ) -> List[Tuple[List[str], List[Relation]]]:
        """Finds all unique simple paths with temporal and relation type filters up to max_depth."""
        if visited is None:
            visited = set()

        if source_uuid == target_uuid:
            return [([source_uuid], [])]

        if len(visited) >= max_depth:
            return []

        visited.add(source_uuid)
        paths: List[Tuple[List[str], List[Relation]]] = []

        for rel in self.adjacency.get(source_uuid, []):
            # 1. Temporal Validity Filtering
            if at_time is not None:
                if at_time < rel.valid_from:
                    continue
                if rel.valid_until is not None and at_time > rel.valid_until:
                    continue

            # 2. Relation Type Filtering
            if allowed_relations is not None and rel.relation_type not in allowed_relations:
                continue

            next_node = rel.target_uuid
            if next_node not in visited:
                sub_paths = self._find_paths_with_relations(next_node, target_uuid, max_depth, at_time, allowed_relations, visited)
                for path, relations in sub_paths:
                    paths.append(([source_uuid] + path, [rel] + relations))

        visited.remove(source_uuid)
        return paths

    def query(
        self,
        source_uuid: str,
        target_uuid: str,
        max_depth: int = 6,
        min_probability: float = 0.05,
        at_time: Optional[float] = None,
        allowed_relations: Optional[List[str]] = None,
        explain: True = True
    ) -> InferenceResult:
        """Queries the PKG using exact dependency-aware probability, filtering and returning trace explanations."""
        start_time = time.time()

        # Find paths and associated edges
        raw_paths = self._find_paths_with_relations(
            source_uuid=source_uuid,
            target_uuid=target_uuid,
            max_depth=max_depth,
            at_time=at_time,
            allowed_relations=allowed_relations
        )

        visited_nodes = set()
        paths_nodes: List[List[str]] = []
        edge_probs: Dict[Tuple[str, str, str], float] = {}
        paths_edges: List[List[Tuple[str, str, str]]] = []

        for node_list, rel_list in raw_paths:
            path_edge_keys = []
            for rel in rel_list:
                edge_key = (rel.source_uuid, rel.target_uuid, rel.relation_type)
                edge_probs[edge_key] = rel.confidence
                path_edge_keys.append(edge_key)

            # Compute path probability
            path_prob = 1.0
            for rel in rel_list:
                path_prob *= rel.confidence

            if path_prob >= min_probability:
                paths_nodes.append(node_list)
                paths_edges.append(path_edge_keys)
                for n in node_list:
                    visited_nodes.add(n)

        # 3. Exact Dependency-Aware Probability Solver via Recursive Conditioning
        def compute_exact_probability(paths: List[List[Tuple[str, str, str]]]) -> float:
            if not paths:
                return 0.0
            if any(len(p) == 0 for p in paths):
                return 1.0

            # Gather remaining unique edges
            unique_edges = set(e for p in paths for e in p)
            if not unique_edges:
                return 0.0

            # Choose edge with highest frequency to branch
            edge_freq = {}
            for p in paths:
                for e in p:
                    edge_freq[e] = edge_freq.get(e, 0) + 1
            best_edge = max(unique_edges, key=lambda e: edge_freq[e])
            p_edge = edge_probs[best_edge]

            # Case 1: Edge is True (remove from all paths containing it)
            paths_true = [[e for e in p if e != best_edge] for p in paths]

            # Case 2: Edge is False (remove paths containing this edge)
            paths_false = [p for p in paths if best_edge not in p]

            return p_edge * compute_exact_probability(paths_true) + (1.0 - p_edge) * compute_exact_probability(paths_false)

        combined_prob = compute_exact_probability(paths_edges)

        # Find best path
        best_path = None
        best_prob = -1.0
        for node_list, rel_list in raw_paths:
            path_prob = 1.0
            for r in rel_list:
                path_prob *= r.confidence
            if path_prob > best_prob:
                best_prob = path_prob
                best_path = node_list

        # Build Explanation
        edge_confidences_str = {f"{k[0]} --[{k[2]}]--> {k[1]}": v for k, v in edge_probs.items()}
        
        explanation_lines = [
            f"Query: {source_uuid} to {target_uuid}",
            f"Combined Exact Probability: {combined_prob:.4f}",
            f"Paths evaluated: {len(paths_nodes)}",
            "Individual Path Traces:"
        ]
        for i, p in enumerate(paths_nodes, 1):
            explanation_lines.append(f" {i}. {' -> '.join(p)}")

        explanation = InferenceExplanation(
            paths=paths_nodes,
            edge_confidences=edge_confidences_str,
            combined_probability=combined_prob,
            visited_nodes=sorted(list(visited_nodes)),
            explanation_text="\n".join(explanation_lines)
        )

        return InferenceResult(
            paths=paths_nodes,
            combined_probability=combined_prob,
            best_path=best_path,
            explanation=explanation,
            visited_nodes=sorted(list(visited_nodes)),
            computation_time=time.time() - start_time
        )
