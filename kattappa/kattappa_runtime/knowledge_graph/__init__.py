"""
Kattappa Knowledge Graph — Step 29
=====================================

Unified structured knowledge layer.

Usage:
    from kattappa_runtime.knowledge_graph import KnowledgeGraph, EntityType, RelationshipType

    kg = KnowledgeGraph(store_dir="/path/to/kg_data")

    rf    = kg.add("RF Systems",    EntityType.RESEARCH_TOPIC)
    smith = kg.add("Smith Chart",   EntityType.TOOL)
    kg.relate(rf, smith, RelationshipType.USES, weight=0.9)

    related = kg.find_related("RF Systems")
    gaps    = kg.find_knowledge_gaps("RF Systems")
    path    = kg.find_path("RF Systems", "Smith Chart")
"""

from kattappa_runtime.knowledge_graph.engine import KnowledgeGraph
from kattappa_runtime.knowledge_graph.schema import (
    Node, Edge, EntityType, RelationshipType, GraphStats
)
from kattappa_runtime.knowledge_graph.store  import GraphStore
from kattappa_runtime.knowledge_graph.query  import (
    GraphQuery, TraversalResult, PathResult
)

__all__ = [
    "KnowledgeGraph",
    "Node", "Edge", "EntityType", "RelationshipType", "GraphStats",
    "GraphStore",
    "GraphQuery", "TraversalResult", "PathResult",
]
