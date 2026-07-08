"""Entity System — Phase K21.1.

Implements the universal Entity base class, domain-specific subclasses,
Relation, EventLog structures, AliasRegistry namespace resolver, and Entity merges.
"""

from __future__ import annotations

import fnmatch
import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from backend.core.logger import log_event

logger = logging.getLogger(__name__)


@dataclass
class Relation:
    """Directed semantic connection between two entities."""

    source_uuid: str
    target_uuid: str
    relation_type: str
    confidence: float
    valid_from: float
    valid_until: Optional[float] = None


@dataclass
class EventLog:
    """Event ledger entry recording mutations."""

    event_id: str
    timestamp: float
    event_type: str
    properties_delta: Dict[str, Any]
    source: str


@dataclass
class Entity:
    """Universal base class representing a World Model object."""

    entity_id: str
    canonical_id: str
    entity_type: str
    properties: Dict[str, Any] = field(default_factory=dict)
    relations: List[Relation] = field(default_factory=list)
    history: List[EventLog] = field(default_factory=list)
    confidence: float = 1.0
    last_observed: float = field(default_factory=time.time)
    causal_rules: List[str] = field(default_factory=list)


# -- Domain Subclasses --


@dataclass
class PhysicalEntity(Entity):
    """Represents tangible objects in physical space."""

    location: Optional[Tuple[float, float, float]] = None
    bounding_box: Optional[
        Tuple[Tuple[float, float, float], Tuple[float, float, float]]
    ] = None

    def __post_init__(self):
        self.entity_type = "physical"


@dataclass
class DigitalEntity(Entity):
    """Represents digital code, files, APIs, and repositories."""

    file_path: Optional[str] = None
    api_endpoint: Optional[str] = None

    def __post_init__(self):
        self.entity_type = "digital"


@dataclass
class HumanEntity(Entity):
    """Represents users, developers, and operators."""

    trust_score: float = 1.0
    emotional_state: str = "calm"

    def __post_init__(self):
        self.entity_type = "human"


@dataclass
class SelfEntity(Entity):
    """Represents Kattappa's internal processes and resource states."""

    cpu_load: float = 0.0
    ram_usage: float = 0.0

    def __post_init__(self):
        self.entity_type = "self"


@dataclass
class EconomicEntity(Entity):
    """Represents compute budgets and API cost dimensions."""

    token_budget: float = 0.0
    cost_per_query: float = 0.0

    def __post_init__(self):
        self.entity_type = "economic"


@dataclass
class TemporalEntity(Entity):
    """Represents schedules, windows, and time commitments."""

    start_time: Optional[float] = None
    duration: Optional[float] = None

    def __post_init__(self):
        self.entity_type = "temporal"


class AliasRegistry:
    """Thread-safe namespace translation registry for Canonical IDs and UUIDs."""

    _lock = threading.Lock()
    _aliases: Dict[str, str] = {}  # alias -> canonical_id / uuid
    _redirects: Dict[str, str] = {}  # deprecated_uuid -> active_uuid

    @classmethod
    def register_alias(cls, alias: str, target: str) -> None:
        with cls._lock:
            cls._aliases[alias] = target
            try:
                from backend.core.knowledge_graph import KnowledgeGraph
                kg = KnowledgeGraph.get_instance()
                resolved_target = kg.resolve_entity(target)
                target_id = resolved_target.id if resolved_target else target
                if kg._store.get_node(target_id):
                    kg.register_alias(canonical_id=target_id, alias_name=alias, alias_type="alias")
            except Exception:
                pass
            log_event(
                "alias_registered", f"Alias '{alias}' mapped to target '{target}'"
            )

    @classmethod
    def register_uuid_redirect(cls, old_uuid: str, new_uuid: str) -> None:
        with cls._lock:
            cls._redirects[old_uuid] = new_uuid
            try:
                from backend.core.knowledge_graph import KnowledgeGraph
                kg = KnowledgeGraph.get_instance()
                resolved_target = kg.resolve_entity(new_uuid)
                target_id = resolved_target.id if resolved_target else new_uuid
                if kg._store.get_node(target_id):
                    kg.register_alias(canonical_id=target_id, alias_name=old_uuid, alias_type="redirect")
            except Exception:
                pass
            log_event("uuid_redirect_registered", f"Redirect: {old_uuid} -> {new_uuid}")

    @classmethod
    def resolve(cls, identifier: str) -> str:
        """Resolves alias names and deprecated UUID redirects to canonical target."""
        with cls._lock:
            try:
                from backend.core.knowledge_graph import KnowledgeGraph
                kg = KnowledgeGraph.get_instance()
                resolved = kg.resolve_entity(identifier)
                if resolved:
                    return resolved.id
            except Exception:
                pass
            # 1. Resolve UUID redirects
            while identifier in cls._redirects:
                identifier = cls._redirects[identifier]
            # 2. Resolve alias string
            return cls._aliases.get(identifier, identifier)

    @classmethod
    def match_namespace(cls, pattern: str) -> List[str]:
        """Finds all registered canonical targets matching wildcard namespace."""
        with cls._lock:
            targets = set(cls._aliases.values())
            # Match using standard fnmatch wildcard logic (e.g. 'self.hardware.*')
            matches = [t for t in targets if fnmatch.fnmatch(t, pattern)]
            return sorted(list(matches))

    @classmethod
    def reset(cls) -> None:
        with cls._lock:
            cls._aliases.clear()
            cls._redirects.clear()


class EntityMergeManager:
    """Coordinates chronological merging and redirects of duplicate entities."""

    @classmethod
    def merge_entities(cls, primary: Entity, secondary: Entity) -> Entity:
        """Chronologically merges secondary entity into primary, setting up redirect aliases."""
        if primary.entity_id == secondary.entity_id:
            return primary

        log_event(
            "entity_merge_start",
            f"Merging secondary {secondary.canonical_id} into primary {primary.canonical_id}",
        )

        # 1. Merge properties: secondary values overwrite primary only if more recently observed
        merged_properties = dict(primary.properties)

        # We check timestamps on properties if present in a dict representation:
        # otherwise we fallback to last_observed comparison
        primary_newer = primary.last_observed >= secondary.last_observed

        for k, v in secondary.properties.items():
            if k not in merged_properties:
                merged_properties[k] = v
            else:
                # If properties contain timestamped dictionaries (e.g. from K21 spec):
                # properties[k] = {"value": x, "timestamp": ts}
                p_prop = merged_properties[k]
                if (
                    isinstance(p_prop, dict)
                    and isinstance(v, dict)
                    and "timestamp" in p_prop
                    and "timestamp" in v
                ):
                    if v["timestamp"] > p_prop["timestamp"]:
                        merged_properties[k] = v
                elif not primary_newer:
                    merged_properties[k] = v

        # 2. Merge relations
        merged_relations = list(primary.relations)
        for rel in secondary.relations:
            # Re-map source/target if they point to the merged secondary entity ID
            new_source = (
                primary.entity_id
                if rel.source_uuid == secondary.entity_id
                else rel.source_uuid
            )
            new_target = (
                primary.entity_id
                if rel.target_uuid == secondary.entity_id
                else rel.target_uuid
            )

            remapped_rel = Relation(
                source_uuid=new_source,
                target_uuid=new_target,
                relation_type=rel.relation_type,
                confidence=rel.confidence,
                valid_from=rel.valid_from,
                valid_until=rel.valid_until,
            )
            if remapped_rel not in merged_relations:
                merged_relations.append(remapped_rel)

        # 3. Merge history logs chronologically
        merged_history = sorted(
            primary.history + secondary.history, key=lambda x: x.timestamp
        )

        # 4. Update primary entity properties
        primary.properties = merged_properties
        primary.relations = merged_relations
        primary.history = merged_history
        primary.last_observed = max(primary.last_observed, secondary.last_observed)
        primary.confidence = min(1.0, (primary.confidence + secondary.confidence) / 2.0)

        # 5. Register permanent redirects in the AliasRegistry
        AliasRegistry.register_uuid_redirect(secondary.entity_id, primary.entity_id)
        AliasRegistry.register_alias(secondary.canonical_id, primary.canonical_id)

        try:
            from backend.core.knowledge_graph import KnowledgeGraph
            kg = KnowledgeGraph.get_instance()
            kg.merge_entities([primary.entity_id, secondary.entity_id])
        except Exception:
            pass

        log_event(
            "entity_merge_complete",
            f"Successfully merged. Alias registry updated: {secondary.canonical_id} redirects to {primary.canonical_id}",
        )
        return primary
