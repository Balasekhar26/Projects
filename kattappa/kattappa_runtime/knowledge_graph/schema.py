"""
Knowledge Graph Schema — Step 29
==================================

Foundational data types for Kattappa's structured knowledge layer.

Hierarchy
---------
KnowledgeGraph
  ├── Node[]    (entities — persons, concepts, skills, tools, ...)
  └── Edge[]    (relationships — USES, DEPENDS_ON, LEARNED_FROM, ...)

Design decisions
----------------
- Nodes and edges carry a `weight` [0.0, 1.0] for traversal ranking.
  Higher weight = stronger / more confident relationship.
- `properties` dict is open-ended: allows arbitrary metadata without
  schema migration. Keep it small — only store what's used in queries.
- Node names are normalised to lowercase-stripped form as `canonical_name`
  for deduplication. Two nodes with the same canonical_name + entity_type
  are considered the same entity.
- Relationships are DIRECTED. If you need bidirectional, add two edges.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional


class EntityType(str, Enum):
    PERSON         = "person"
    CONCEPT        = "concept"
    SKILL          = "skill"
    TOOL           = "tool"
    PROJECT        = "project"
    GOAL           = "goal"
    DOCUMENT       = "document"
    RESEARCH_TOPIC = "research_topic"
    DOMAIN         = "domain"       # top-level knowledge domain
    UNKNOWN        = "unknown"      # fallback for auto-extracted entities


class RelationshipType(str, Enum):
    USES         = "uses"
    DEPENDS_ON   = "depends_on"
    LEARNED_FROM = "learned_from"
    RELATED_TO   = "related_to"
    PART_OF      = "part_of"
    WORKED_ON    = "worked_on"
    CAUSED       = "caused"
    IMPROVES     = "improves"
    # Additional structural relationships
    PREREQUISITE_OF = "prerequisite_of"   # A must be learned before B
    APPLIES_TO      = "applies_to"        # Tool/concept applies to domain
    CONTRADICTS     = "contradicts"       # Two pieces of knowledge conflict
    CITES           = "cites"             # Document cites another


@dataclass
class Node:
    """
    One entity in the knowledge graph.

    Fields
    ------
    node_id : str
        UUID4 identifier.
    name : str
        Human-readable display name. e.g. "Smith Chart"
    entity_type : EntityType
        Category of this entity.
    canonical_name : str
        Normalised name for deduplication. Auto-generated from name if empty.
    description : str
        Short description of this entity.
    properties : Dict[str, str]
        Flexible key-value metadata. e.g. {"source": "wikipedia", "domain": "rf"}
    confidence : float
        How confident we are this entity is correctly classified [0.0, 1.0].
    mention_count : int
        How many times this entity has appeared in memory/research.
    created_at : str
        ISO-8601 UTC timestamp.
    updated_at : str
        ISO-8601 UTC timestamp of last update.
    """
    node_id:        str        = field(default_factory=lambda: str(uuid.uuid4()))
    name:           str        = ""
    entity_type:    EntityType = EntityType.CONCEPT
    canonical_name: str        = ""
    description:    str        = ""
    properties:     Dict[str, str] = field(default_factory=dict)
    confidence:     float      = 1.0
    mention_count:  int        = 1
    created_at:     str        = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    updated_at:     str        = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def __post_init__(self):
        if not self.canonical_name and self.name:
            self.canonical_name = self.name.lower().strip()

    def to_dict(self) -> dict:
        return {
            "node_id":        self.node_id,
            "name":           self.name,
            "entity_type":    self.entity_type.value,
            "canonical_name": self.canonical_name,
            "description":    self.description,
            "properties":     self.properties,
            "confidence":     self.confidence,
            "mention_count":  self.mention_count,
            "created_at":     self.created_at,
            "updated_at":     self.updated_at,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Node":
        d = dict(d)
        d["entity_type"] = EntityType(d.get("entity_type", "unknown"))
        return cls(**d)


@dataclass
class Edge:
    """
    A directed relationship between two nodes.

    Fields
    ------
    edge_id : str
        UUID4 identifier.
    source_id : str
        node_id of the source entity.
    target_id : str
        node_id of the target entity.
    relationship : RelationshipType
        Type of relationship.
    weight : float
        Strength of this relationship [0.0, 1.0]. Higher = stronger.
    evidence : str
        What created this edge. e.g. "research_result:arxiv:2301.xxxxx"
    properties : Dict[str, str]
        Extra metadata. e.g. {"context": "RF impedance matching chapter"}
    created_at : str
        ISO-8601 UTC timestamp.
    """
    edge_id:      str              = field(default_factory=lambda: str(uuid.uuid4()))
    source_id:    str              = ""
    target_id:    str              = ""
    relationship: RelationshipType = RelationshipType.RELATED_TO
    weight:       float            = 0.5
    evidence:     str              = ""
    properties:   Dict[str, str]   = field(default_factory=dict)
    created_at:   str              = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict:
        return {
            "edge_id":      self.edge_id,
            "source_id":    self.source_id,
            "target_id":    self.target_id,
            "relationship": self.relationship.value,
            "weight":       self.weight,
            "evidence":     self.evidence,
            "properties":   self.properties,
            "created_at":   self.created_at,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Edge":
        d = dict(d)
        d["relationship"] = RelationshipType(d.get("relationship", "related_to"))
        return cls(**d)


@dataclass
class GraphStats:
    """Lightweight summary of the current graph state."""
    node_count:     int
    edge_count:     int
    entity_counts:  Dict[str, int]   # entity_type → count
    rel_counts:     Dict[str, int]   # relationship → count
    top_nodes:      List[str]        # names of highest mention_count nodes

    def summary(self) -> str:
        lines = [
            f"Knowledge Graph: {self.node_count} nodes, {self.edge_count} edges",
            "Entity breakdown: "
            + ", ".join(f"{k}={v}" for k, v in self.entity_counts.items() if v > 0),
            "Top entities: " + ", ".join(self.top_nodes[:5]),
        ]
        return "\n".join(lines)
