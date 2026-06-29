"""Probabilistic Knowledge Graph (PKG) — Phase K21.7.4 - K21.7.6.

Implements ProbabilisticKnowledgeGraph with temporal validity filtering, relation filters,
exact dependency-aware probability combination via recursive edge conditioning,
probabilistic node confidence discounting, best-first Dijkstra search (Top-K paths), and
taxonomic ontological transitivity rules.
"""

from __future__ import annotations

import heapq
import logging
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple

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

    def __init__(self, graph_store: Optional[Any] = None):
        # Maps source_uuid -> List of Relation objects (in-memory fallback)
        self.adjacency: Dict[str, List[Relation]] = {}
        # Maps node_uuid -> confidence float (in-memory fallback)
        self.node_confidences: Dict[str, float] = {}
        self.graph_store = graph_store

    def __deepcopy__(self, memo):
        import copy
        new_pkg = self.__class__(graph_store=self.graph_store)
        new_pkg.adjacency = copy.deepcopy(self.adjacency, memo)
        new_pkg.node_confidences = copy.deepcopy(self.node_confidences, memo)
        return new_pkg

    def register_node_confidence(self, node_uuid: str, confidence: float) -> None:
        """Register the confidence value of an entity node."""
        if self.graph_store:
            existing = self.graph_store.get_node(node_uuid)
            if existing:
                self.graph_store.update_node(node_uuid, confidence=confidence)
            else:
                self.graph_store.insert_node(name=node_uuid, entity_type="CONCEPT", confidence=confidence, node_id=node_uuid)
        else:
            self.node_confidences[node_uuid] = confidence

    def get_node_confidence(self, node_uuid: str) -> float:
        """Returns registered node confidence, defaulting to 1.0."""
        if self.graph_store:
            node = self.graph_store.get_node(node_uuid)
            return node["confidence"] if node else 1.0
        return self.node_confidences.get(node_uuid, 1.0)

    def add_relation(self, relation: Relation) -> None:
        """Adds a relation to the knowledge graph."""
        if self.graph_store:
            src_node = self.graph_store.get_node(relation.source_uuid)
            if not src_node:
                self.graph_store.insert_node(name=relation.source_uuid, entity_type="CONCEPT", node_id=relation.source_uuid)
            tgt_node = self.graph_store.get_node(relation.target_uuid)
            if not tgt_node:
                self.graph_store.insert_node(name=relation.target_uuid, entity_type="CONCEPT", node_id=relation.target_uuid)
            
            edges = self.graph_store.get_edges_from(relation.source_uuid, relation_type=relation.relation_type)
            existing_edge = next((e for e in edges if e["target_id"] == relation.target_uuid), None)
            if existing_edge:
                self.graph_store.update_edge(
                    existing_edge["id"],
                    confidence=relation.confidence,
                    valid_from=str(relation.valid_from) if relation.valid_from is not None else None,
                    valid_until=str(relation.valid_until) if relation.valid_until is not None else None
                )
            else:
                self.graph_store.insert_edge(
                    source_id=relation.source_uuid,
                    target_id=relation.target_uuid,
                    relation_type=relation.relation_type,
                    confidence=relation.confidence,
                    valid_from=str(relation.valid_from) if relation.valid_from is not None else None,
                    valid_until=str(relation.valid_until) if relation.valid_until is not None else None
                )
        else:
            self.adjacency.setdefault(relation.source_uuid, []).append(relation)
        log_event(
            "pkg_relation_added",
            f"PKG: Added relation {relation.source_uuid} --[{relation.relation_type}]--> {relation.target_uuid} (conf={relation.confidence})",
        )

    def get_relations(self, source_uuid: str) -> List[Relation]:
        """Returns all relations originating from the source entity."""
        if self.graph_store:
            edges = self.graph_store.get_edges_from(source_uuid)
            relations = []
            for e in edges:
                try:
                    vf = float(e.get("valid_from") or 0.0)
                except (ValueError, TypeError):
                    vf = 0.0
                try:
                    vu = float(e.get("valid_until")) if e.get("valid_until") else None
                except (ValueError, TypeError):
                    vu = None
                relations.append(Relation(
                    source_uuid=e["source_id"],
                    target_uuid=e["target_id"],
                    relation_type=e["relation_type"],
                    confidence=e.get("confidence", 1.0),
                    valid_from=vf,
                    valid_until=vu
                ))
            return relations
        return self.adjacency.get(source_uuid, [])

    def compose_relations(self, relations: List[Relation]) -> Optional[str]:
        """Composes a chain of relations semantically using taxonomic transitivity rules."""
        if not relations:
            return None
        curr_type = relations[0].relation_type
        for rel in relations[1:]:
            next_type = rel.relation_type
            # Ontological Transitivity Rules
            if curr_type == "INSTANCE_OF" and next_type == "SUBCLASS_OF":
                curr_type = "INSTANCE_OF"
            elif curr_type == "SUBCLASS_OF" and next_type == "SUBCLASS_OF":
                curr_type = "SUBCLASS_OF"
            elif curr_type == "PART_OF" and next_type == "PART_OF":
                curr_type = "PART_OF"
            elif curr_type == "causes" and next_type == "causes":
                curr_type = "causes"
            else:
                return None
        return curr_type

    def find_paths(
        self, source_uuid: str, target_uuid: str, visited: Optional[Set[str]] = None
    ) -> List[Tuple[List[str], float]]:
        """DFS traversing the graph to find all unique simple paths, returning node lists and path probabilities."""
        raw_paths = self._find_paths_with_relations(
            source_uuid, target_uuid, visited=visited
        )
        paths = []
        for path_nodes, rels in raw_paths:
            # Traditional edge-only probability multiplication for backward compatibility
            path_prob = 1.0
            for r in rels:
                path_prob *= r.confidence
            paths.append((path_nodes, path_prob))
        return paths

    def infer_indirect_relation_probability(
        self, source_uuid: str, target_uuid: str
    ) -> float:
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
        visited: Optional[Set[str]] = None,
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

        for rel in self.get_relations(source_uuid):
            # 1. Temporal Validity Filtering
            if at_time is not None:
                if at_time < rel.valid_from:
                    continue
                if rel.valid_until is not None and at_time > rel.valid_until:
                    continue

            # 2. Relation Type Filtering
            if (
                allowed_relations is not None
                and rel.relation_type not in allowed_relations
            ):
                continue

            next_node = rel.target_uuid
            if next_node not in visited:
                sub_paths = self._find_paths_with_relations(
                    next_node,
                    target_uuid,
                    max_depth,
                    at_time,
                    allowed_relations,
                    visited,
                )
                for path, relations in sub_paths:
                    paths.append(([source_uuid] + path, [rel] + relations))

        visited.remove(source_uuid)
        return paths

    def find_top_k_paths(
        self,
        source_uuid: str,
        target_uuid: str,
        k: int = 5,
        max_depth: int = 6,
        at_time: Optional[float] = None,
        allowed_relations: Optional[List[str]] = None,
    ) -> List[Tuple[List[str], List[Relation], float]]:
        """Finds top-k highest probability paths using Best-First Search (Dijkstra-style).

        This is highly scalable, avoiding DFS exponential search blowup.
        """
        pq = []
        # Initial path probability starts with source node confidence
        p_init = self.get_node_confidence(source_uuid)
        heapq.heappush(pq, (-p_init, source_uuid, [source_uuid], []))

        completed_paths = []

        while pq and len(completed_paths) < k:
            neg_prob, curr_node, path_nodes, path_relations = heapq.heappop(pq)
            prob = -neg_prob

            if curr_node == target_uuid:
                completed_paths.append((path_nodes, path_relations, prob))
                continue

            if len(path_nodes) - 1 >= max_depth:
                continue

            for rel in self.get_relations(curr_node):
                # Temporal filter
                if at_time is not None:
                    if at_time < rel.valid_from:
                        continue
                    if rel.valid_until is not None and at_time > rel.valid_until:
                        continue

                # Allowed relations or ontological composition transitivity
                if allowed_relations is not None:
                    temp_relations = path_relations + [rel]
                    composed = self.compose_relations(temp_relations)
                    if composed is None or composed not in allowed_relations:
                        # Fallback check on individual relation type
                        if rel.relation_type not in allowed_relations:
                            continue

                next_node = rel.target_uuid
                if next_node in path_nodes:
                    continue

                # Next probability factors in target node confidence AND relation confidence
                next_prob = prob * self.get_node_confidence(next_node) * rel.confidence
                heapq.heappush(
                    pq,
                    (
                        -next_prob,
                        next_node,
                        path_nodes + [next_node],
                        path_relations + [rel],
                    ),
                )

        return completed_paths

    def query(
        self,
        source_uuid: str,
        target_uuid: str,
        max_depth: int = 6,
        min_probability: float = 0.05,
        at_time: Optional[float] = None,
        allowed_relations: Optional[List[str]] = None,
        explain: True = True,
    ) -> InferenceResult:
        """Queries the PKG using exact dependency-aware probability, filtering and returning trace explanations."""
        start_time = time.time()

        # Find top paths using Best-First Search
        raw_paths = self.find_top_k_paths(
            source_uuid=source_uuid,
            target_uuid=target_uuid,
            k=20,  # Max candidate paths for exact evaluation
            max_depth=max_depth,
            at_time=at_time,
            allowed_relations=allowed_relations,
        )

        visited_nodes = set()
        paths_nodes: List[List[str]] = []
        edge_probs: Dict[Tuple[str, str, str], float] = {}
        paths_edges: List[List[Tuple[str, str, str]]] = []

        for node_list, rel_list, path_prob in raw_paths:
            path_edge_keys = []
            for rel in rel_list:
                edge_key = (rel.source_uuid, rel.target_uuid, rel.relation_type)
                edge_probs[edge_key] = rel.confidence
                path_edge_keys.append(edge_key)

            if path_prob >= min_probability:
                paths_nodes.append(node_list)
                paths_edges.append(path_edge_keys)
                for n in node_list:
                    visited_nodes.add(n)

        # Exact Dependency-Aware Probability Solver via Recursive Conditioning
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

            return p_edge * compute_exact_probability(paths_true) + (
                1.0 - p_edge
            ) * compute_exact_probability(paths_false)

        # Base nodes probability discount
        nodes_factor = 1.0
        for node in visited_nodes:
            nodes_factor *= self.get_node_confidence(node)

        combined_prob = compute_exact_probability(paths_edges) * nodes_factor

        # Find best path
        best_path = None
        if raw_paths:
            best_path = raw_paths[0][0]

        # Build Explanation
        edge_confidences_str = {
            f"{k[0]} --[{k[2]}]--> {k[1]}": v for k, v in edge_probs.items()
        }

        explanation_lines = [
            f"Query: {source_uuid} to {target_uuid}",
            f"Combined Exact Probability (with Node Discount): {combined_prob:.4f}",
            f"Paths evaluated: {len(paths_nodes)}",
            "Individual Path Traces:",
        ]
        for i, p in enumerate(paths_nodes, 1):
            explanation_lines.append(f" {i}. {' -> '.join(p)}")

        explanation = InferenceExplanation(
            paths=paths_nodes,
            edge_confidences=edge_confidences_str,
            combined_probability=combined_prob,
            visited_nodes=sorted(list(visited_nodes)),
            explanation_text="\n".join(explanation_lines),
        )

        return InferenceResult(
            paths=paths_nodes,
            combined_probability=combined_prob,
            best_path=best_path,
            explanation=explanation,
            visited_nodes=sorted(list(visited_nodes)),
            computation_time=time.time() - start_time,
        )
