"""World Model (Tier 2).

Kattappa's internal map of reality: a persistent graph of entities (projects,
components, devices, people, resources, goals) and their relationships
(contains / depends_on / affects). With it, Kattappa can reason about
consequences rather than just plan:

    Changing RF Module -> affects Antenna -> affects Range -> affects Battery Life

Deterministic and persistent. It models reality; it never executes.
"""

from __future__ import annotations

import json
import threading
import time
from enum import Enum
from pathlib import Path
from typing import Any

from backend.core.config import runtime_data_root


def _path() -> Path:
    return runtime_data_root() / "backend" / "data" / "world_model.json"


class EntityType(str, Enum):
    PROJECT = "project"
    COMPONENT = "component"
    DEVICE = "device"
    PERSON = "person"
    RESOURCE = "resource"
    GOAL = "goal"
    OTHER = "other"

    @classmethod
    def coerce(cls, value: "EntityType | str") -> "EntityType":
        try:
            return value if isinstance(value, cls) else cls(str(value).strip().lower())
        except ValueError:
            return cls.OTHER


class RelationType(str, Enum):
    CONTAINS = "contains"
    DEPENDS_ON = "depends_on"
    AFFECTS = "affects"
    RELATED = "related"

    @classmethod
    def coerce(cls, value: "RelationType | str") -> "RelationType":
        try:
            return value if isinstance(value, cls) else cls(str(value).strip().lower())
        except ValueError:
            return cls.RELATED


class WorldModel:
    _lock = threading.RLock()
    _max_depth = 25

    # -- persistence -------------------------------------------------------
    @classmethod
    def _load(cls) -> dict[str, Any]:
        try:
            p = _path()
            if p.exists():
                return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            pass
        return {"entities": {}, "relations": []}

    @classmethod
    def _save(cls, data: dict[str, Any]) -> None:
        try:
            p = _path()
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception:
            pass

    @staticmethod
    def _key(name: str) -> str:
        return name.strip().lower()

    # -- entities & relations ---------------------------------------------
    @classmethod
    def add_entity(
        cls, name: str, entity_type: EntityType | str = EntityType.OTHER,
        *, status: str = "", attributes: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        name = name.strip()
        if not name:
            raise ValueError("Entity name cannot be empty")
        entity = {
            "name": name,
            "type": EntityType.coerce(entity_type).value,
            "status": status,
            "attributes": dict(attributes or {}),
            "updated_at": time.time(),
        }
        with cls._lock:
            data = cls._load()
            data.setdefault("entities", {})[cls._key(name)] = entity
            cls._save(data)
        return entity

    @classmethod
    def add_relation(cls, src: str, dst: str, relation: RelationType | str = RelationType.RELATED) -> dict[str, Any]:
        with cls._lock:
            data = cls._load()
            entities = data.setdefault("entities", {})
            if cls._key(src) not in entities:
                raise ValueError(f"Unknown entity {src!r}")
            if cls._key(dst) not in entities:
                raise ValueError(f"Unknown entity {dst!r}")
            rel = {"src": cls._key(src), "dst": cls._key(dst),
                   "relation": RelationType.coerce(relation).value}
            relations = data.setdefault("relations", [])
            if rel not in relations:
                relations.append(rel)
            cls._save(data)
        return rel

    @classmethod
    def get_entity(cls, name: str) -> dict[str, Any] | None:
        return cls._load().get("entities", {}).get(cls._key(name))

    @classmethod
    def entities(cls) -> list[dict[str, Any]]:
        return list(cls._load().get("entities", {}).values())

    @classmethod
    def relations(cls) -> list[dict[str, Any]]:
        return list(cls._load().get("relations", []))

    @classmethod
    def neighbors(cls, name: str, relation: RelationType | str | None = None,
                  *, direction: str = "out") -> list[str]:
        key = cls._key(name)
        rel = RelationType.coerce(relation).value if relation is not None else None
        entities = cls._load().get("entities", {})
        out: list[str] = []
        for r in cls.relations():
            if rel is not None and r["relation"] != rel:
                continue
            if direction == "out" and r["src"] == key:
                out.append(entities.get(r["dst"], {}).get("name", r["dst"]))
            elif direction == "in" and r["dst"] == key:
                out.append(entities.get(r["src"], {}).get("name", r["src"]))
        return out

    # -- impact reasoning --------------------------------------------------
    @classmethod
    def impact_of(cls, name: str) -> dict[str, Any]:
        """What a change to ``name`` propagates to.

        Propagates along outgoing AFFECTS edges and to entities that DEPEND_ON
        this one (incoming depends_on). Returns affected entities with the path.
        """
        data = cls._load()
        entities = data.get("entities", {})
        start = cls._key(name)
        if start not in entities:
            raise KeyError(f"No entity {name!r}")

        # adjacency: change in X reaches Y if X --affects--> Y or Y --depends_on--> X
        adj: dict[str, list[str]] = {}
        for r in data.get("relations", []):
            if r["relation"] == RelationType.AFFECTS.value:
                adj.setdefault(r["src"], []).append(r["dst"])
            elif r["relation"] == RelationType.DEPENDS_ON.value:
                adj.setdefault(r["dst"], []).append(r["src"])

        affected: list[dict[str, Any]] = []
        seen = {start}
        queue: list[tuple[str, list[str]]] = [(start, [entities[start]["name"]])]
        depth = 0
        while queue and depth < cls._max_depth:
            depth += 1
            nxt: list[tuple[str, list[str]]] = []
            for node, path in queue:
                for child in adj.get(node, []):
                    if child in seen:
                        continue
                    seen.add(child)
                    child_name = entities.get(child, {}).get("name", child)
                    new_path = path + [child_name]
                    affected.append({"entity": child_name, "depth": depth, "path": new_path})
                    nxt.append((child, new_path))
            queue = nxt

        return {
            "entity": entities[start]["name"],
            "affected": affected,
            "affected_names": [a["entity"] for a in affected],
        }

    @classmethod
    def subtree(cls, name: str) -> dict[str, Any]:
        """Hierarchy under ``name`` following CONTAINS edges."""
        data = cls._load()
        entities = data.get("entities", {})
        key = cls._key(name)
        if key not in entities:
            raise KeyError(f"No entity {name!r}")
        children_map: dict[str, list[str]] = {}
        for r in data.get("relations", []):
            if r["relation"] == RelationType.CONTAINS.value:
                children_map.setdefault(r["src"], []).append(r["dst"])

        def build(node: str, seen: set[str]) -> dict[str, Any]:
            seen = seen | {node}
            return {
                "name": entities.get(node, {}).get("name", node),
                "children": [build(c, seen) for c in children_map.get(node, []) if c not in seen],
            }

        return build(key, set())

    @classmethod
    def status(cls) -> dict[str, Any]:
        ents = cls.entities()
        by_type: dict[str, int] = {t.value: 0 for t in EntityType}
        for e in ents:
            by_type[e.get("type", "other")] = by_type.get(e.get("type", "other"), 0) + 1
        return {"entities": len(ents), "relations": len(cls.relations()), "by_type": by_type}

    @classmethod
    def reset(cls) -> None:
        with cls._lock:
            cls._save({"entities": {}, "relations": []})
