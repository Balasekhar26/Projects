"""Step 29: Cross-layer synchronization adapters for Knowledge Graph.

Bridges Semantic Memory, World Model, and Episodic Memory into the
unified Knowledge Graph.  Each adapter reads from its source SQLite
database and inserts / upserts corresponding nodes and edges into the
:class:`GraphStore`.

A :class:`SyncManager` orchestrates all three adapters, supporting both
full and incremental synchronization with deduplication and confidence
normalization.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Confidence normalization helpers
# ---------------------------------------------------------------------------

def _normalize_semantic_confidence(raw: float) -> float:
    """Semantic memory confidence is already in [0, 1]."""
    return max(0.0, min(1.0, raw))


def _normalize_world_confidence(raw: float) -> float:
    """World model belief confidence is in [0, 1]."""
    return max(0.0, min(1.0, raw))


def _normalize_episodic_confidence(raw: float) -> float:
    """Episodic relevance score — clamp to [0, 1]."""
    return max(0.0, min(1.0, raw))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _open_readonly(db_path: str) -> sqlite3.Connection:
    """Open a read-only SQLite connection to *db_path*."""
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, check_same_thread=False, timeout=10.0)
    conn.row_factory = sqlite3.Row
    return conn


def _find_existing_by_name_type(
    store: Any, name: str, entity_type: str
) -> Optional[Dict[str, Any]]:
    """Deduplication lookup: find a KG node matching (name, entity_type)."""
    return store.get_node_by_name(name, entity_type=entity_type)


# ---------------------------------------------------------------------------
# Semantic Sync Adapter
# ---------------------------------------------------------------------------

# Semantic entity types → KG entity types
_SEMANTIC_TYPE_MAP: Dict[str, str] = {
    "FACT": "FACT",
    "CONCEPT": "CONCEPT",
    "SKILL": "SKILL",
    "DEFINITION": "CONCEPT",
    "HYPOTHESIS": "HYPOTHESIS",
}

# Semantic relation types are passed through directly
_SEMANTIC_RELATIONS: Set[str] = {
    "IS_A", "USES", "SUPPORTS", "RELATED_TO", "IMPLEMENTS",
    "EXTENDS", "CONTRADICTS", "SUPERSEDES", "OBSOLETES", "VERSION_OF",
}


class SemanticSyncAdapter:
    """Maps Semantic Memory nodes and relations into the Knowledge Graph."""

    def sync(
        self,
        graph_store: Any,
        source_db_path: str,
        *,
        since_timestamp: Optional[float] = None,
    ) -> Dict[str, int]:
        """Synchronize semantic memory into *graph_store*.

        Parameters
        ----------
        graph_store:
            Target :class:`GraphStore`.
        source_db_path:
            Path to the semantic memory SQLite database.
        since_timestamp:
            If provided, only sync nodes updated after this epoch timestamp
            (incremental sync).

        Returns
        -------
        A dict ``{"nodes_synced": int, "edges_synced": int}``.
        """
        nodes_synced = 0
        edges_synced = 0
        id_map: dict[str, str] = {}  # semantic node_id → kg node id

        try:
            conn = _open_readonly(source_db_path)
        except Exception as exc:
            logger.error("kg_sync: cannot open semantic DB %s: %s", source_db_path, exc)
            return {"nodes_synced": 0, "edges_synced": 0}

        try:
            # --- Nodes ---
            if since_timestamp is not None:
                rows = conn.execute(
                    "SELECT * FROM semantic_nodes WHERE updated_at >= ? AND status != 'DEPRECATED'",
                    (since_timestamp,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM semantic_nodes WHERE status != 'DEPRECATED'"
                ).fetchall()

            node_batch: list[Dict[str, Any]] = []
            for row in rows:
                sem_id = row["node_id"]
                kg_type = _SEMANTIC_TYPE_MAP.get(row["node_type"], "CONCEPT")
                existing = _find_existing_by_name_type(graph_store, row["title"], kg_type)

                if existing:
                    id_map[sem_id] = existing["id"]
                    graph_store.update_node(
                        existing["id"],
                        properties={"description": row["content_raw"], "original_type": row["node_type"]},
                        confidence=_normalize_semantic_confidence(row["confidence_score"]),
                        source_layer="semantic",
                    )
                else:
                    new_id = graph_store.insert_node(
                        name=row["title"],
                        entity_type=kg_type,
                        properties={"description": row["content_raw"], "original_type": row["node_type"]},
                        confidence=_normalize_semantic_confidence(row["confidence_score"]),
                        source_layer="semantic",
                    )
                    id_map[sem_id] = new_id
                nodes_synced += 1

            # --- Edges ---
            edge_rows = conn.execute("SELECT * FROM semantic_edges").fetchall()
            for erow in edge_rows:
                src_sem = erow["source_node_id"]
                tgt_sem = erow["target_node_id"]
                rel = erow["relation_type"]

                if rel not in _SEMANTIC_RELATIONS:
                    rel = "RELATED_TO"

                src_kg = id_map.get(src_sem)
                tgt_kg = id_map.get(tgt_sem)
                if not src_kg or not tgt_kg:
                    continue

                graph_store.insert_edge(
                    source_id=src_kg,
                    target_id=tgt_kg,
                    relation_type=rel,
                    weight=erow["weight_score"],
                    confidence=_normalize_semantic_confidence(erow["weight_score"]),
                    source_layer="semantic",
                )
                edges_synced += 1

        except Exception as exc:
            logger.error("kg_sync: semantic sync error: %s", exc)
        finally:
            conn.close()

        return {"nodes_synced": nodes_synced, "edges_synced": edges_synced}


# ---------------------------------------------------------------------------
# World Model Sync Adapter
# ---------------------------------------------------------------------------

_WORLD_TYPE_MAP: Dict[str, str] = {
    "project": "PROJECT",
    "component": "COMPONENT",
    "device": "DEVICE",
    "person": "PERSON",
    "resource": "RESOURCE",
    "goal": "GOAL",
    "other": "CONCEPT",
}

_WORLD_RELATION_MAP: Dict[str, str] = {
    "contains": "CONTAINS",
    "depends_on": "DEPENDS_ON",
    "affects": "AFFECTS",
    "related": "RELATED_TO",
}


class WorldModelSyncAdapter:
    """Maps World Model entities and relations into the Knowledge Graph."""

    def sync(
        self,
        graph_store: Any,
        source_db_path: str,
        *,
        since_timestamp: Optional[float] = None,
    ) -> Dict[str, int]:
        """Synchronize world model into *graph_store*."""
        nodes_synced = 0
        edges_synced = 0
        id_map: dict[str, str] = {}

        try:
            conn = _open_readonly(source_db_path)
        except Exception as exc:
            logger.error("kg_sync: cannot open world model DB %s: %s", source_db_path, exc)
            return {"nodes_synced": 0, "edges_synced": 0}

        try:
            if since_timestamp is not None:
                rows = conn.execute(
                    "SELECT * FROM world_state_nodes WHERE updated_at >= ?",
                    (since_timestamp,),
                ).fetchall()
            else:
                rows = conn.execute("SELECT * FROM world_state_nodes").fetchall()

            for row in rows:
                wm_id = row["id"]
                kg_type = _WORLD_TYPE_MAP.get(row["type"], "CONCEPT")
                attrs = json.loads(row["attributes"]) if row["attributes"] else {}
                existing = _find_existing_by_name_type(graph_store, row["name"], kg_type)

                if existing:
                    id_map[wm_id] = existing["id"]
                    graph_store.update_node(
                        existing["id"],
                        properties={"status": row["status"] or "", **attrs},
                        source_layer="world_model",
                    )
                else:
                    new_id = graph_store.insert_node(
                        name=row["name"],
                        entity_type=kg_type,
                        properties={"status": row["status"] or "", **attrs},
                        confidence=0.7,
                        source_layer="world_model",
                    )
                    id_map[wm_id] = new_id
                nodes_synced += 1

            edge_rows = conn.execute("SELECT * FROM world_state_edges").fetchall()
            for erow in edge_rows:
                rel = _WORLD_RELATION_MAP.get(erow["relation"], "RELATED_TO")
                src_kg = id_map.get(erow["src"])
                tgt_kg = id_map.get(erow["dst"])
                if not src_kg or not tgt_kg:
                    continue
                graph_store.insert_edge(
                    source_id=src_kg,
                    target_id=tgt_kg,
                    relation_type=rel,
                    source_layer="world_model",
                )
                edges_synced += 1

        except Exception as exc:
            logger.error("kg_sync: world model sync error: %s", exc)
        finally:
            conn.close()

        return {"nodes_synced": nodes_synced, "edges_synced": edges_synced}


# ---------------------------------------------------------------------------
# Episodic Sync Adapter
# ---------------------------------------------------------------------------


class EpisodicSyncAdapter:
    """Maps Episodic Memory events and people into the Knowledge Graph."""

    def sync(
        self,
        graph_store: Any,
        source_db_path: str,
        *,
        since_timestamp: Optional[float] = None,
    ) -> Dict[str, int]:
        """Synchronize episodic memory into *graph_store*."""
        nodes_synced = 0
        edges_synced = 0
        id_map: dict[str, str] = {}

        try:
            conn = _open_readonly(source_db_path)
        except Exception as exc:
            logger.error("kg_sync: cannot open episodic DB %s: %s", source_db_path, exc)
            return {"nodes_synced": 0, "edges_synced": 0}

        try:
            # Check if the episodes table exists
            table_check = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='episodes'"
            ).fetchone()
            if not table_check:
                logger.info("kg_sync: no 'episodes' table in %s, skipping", source_db_path)
                return {"nodes_synced": 0, "edges_synced": 0}

            if since_timestamp is not None:
                ep_rows = conn.execute(
                    "SELECT * FROM episodes WHERE created_at >= ?", (since_timestamp,)
                ).fetchall()
            else:
                ep_rows = conn.execute("SELECT * FROM episodes").fetchall()

            for row in ep_rows:
                ep_id = str(row["id"]) if "id" in row.keys() else str(row[0])
                summary = row["summary"] if "summary" in row.keys() else ""
                created = row["created_at"] if "created_at" in row.keys() else _utcnow_iso()
                relevance = float(row["relevance_score"]) if "relevance_score" in row.keys() else 0.5

                event_name = f"Episode {ep_id}"
                existing = _find_existing_by_name_type(graph_store, event_name, "EVENT")
                if existing:
                    kg_id = existing["id"]
                    graph_store.update_node(
                        kg_id,
                        properties={"summary": summary, "created": str(created)},
                        confidence=_normalize_episodic_confidence(relevance),
                        source_layer="episodic",
                    )
                else:
                    kg_id = graph_store.insert_node(
                        name=event_name,
                        entity_type="EVENT",
                        properties={"summary": summary, "created": str(created)},
                        confidence=_normalize_episodic_confidence(relevance),
                        source_layer="episodic",
                    )
                id_map[ep_id] = kg_id
                nodes_synced += 1

                # Extract people from participants if available
                if "participants" in row.keys() and row["participants"]:
                    try:
                        participants = json.loads(row["participants"])
                        for person_name in participants:
                            person_existing = _find_existing_by_name_type(
                                graph_store, person_name, "PERSON"
                            )
                            if not person_existing:
                                person_kg = graph_store.insert_node(
                                    name=person_name,
                                    entity_type="PERSON",
                                    source_layer="episodic",
                                )
                            else:
                                person_kg = person_existing["id"]
                            graph_store.insert_edge(
                                source_id=kg_id,
                                target_id=person_kg,
                                relation_type="RELATED_TO",
                                source_layer="episodic",
                            )
                            edges_synced += 1
                            nodes_synced += 1 if not person_existing else 0
                    except (json.JSONDecodeError, TypeError):
                        pass

            # Link consecutive episodes
            ep_id_list = list(id_map.keys())
            for i in range(len(ep_id_list) - 1):
                graph_store.insert_edge(
                    source_id=id_map[ep_id_list[i]],
                    target_id=id_map[ep_id_list[i + 1]],
                    relation_type="FOLLOW_UP_TO",
                    source_layer="episodic",
                )
                edges_synced += 1

        except Exception as exc:
            logger.error("kg_sync: episodic sync error: %s", exc)
        finally:
            conn.close()

        return {"nodes_synced": nodes_synced, "edges_synced": edges_synced}


# ---------------------------------------------------------------------------
# Sync Manager
# ---------------------------------------------------------------------------


class SyncManager:
    """Orchestrates cross-layer synchronization for the Knowledge Graph.

    Parameters
    ----------
    graph_store:
        The target :class:`GraphStore`.
    """

    def __init__(self, graph_store: Any) -> None:
        self._store = graph_store
        self._last_sync_timestamp: Optional[float] = None
        self._semantic_adapter = SemanticSyncAdapter()
        self._world_adapter = WorldModelSyncAdapter()
        self._episodic_adapter = EpisodicSyncAdapter()

    @property
    def last_sync_timestamp(self) -> Optional[float]:
        """Epoch timestamp of the last successful sync."""
        return self._last_sync_timestamp

    def full_sync(
        self,
        semantic_db_path: Optional[str] = None,
        world_model_db_path: Optional[str] = None,
        episodic_db_path: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Run a full synchronization of all available layers.

        Parameters
        ----------
        semantic_db_path:
            Path to semantic memory SQLite DB.
        world_model_db_path:
            Path to world model SQLite DB.
        episodic_db_path:
            Path to episodic memory SQLite DB.

        Returns
        -------
        Aggregated sync statistics dict.
        """
        results: Dict[str, Any] = {}

        if semantic_db_path:
            results["semantic"] = self._semantic_adapter.sync(
                self._store, semantic_db_path
            )

        if world_model_db_path:
            results["world_model"] = self._world_adapter.sync(
                self._store, world_model_db_path
            )

        if episodic_db_path:
            results["episodic"] = self._episodic_adapter.sync(
                self._store, episodic_db_path
            )

        self._last_sync_timestamp = time.time()
        results["synced_at"] = _utcnow_iso()
        return results

    def incremental_sync(
        self,
        semantic_db_path: Optional[str] = None,
        world_model_db_path: Optional[str] = None,
        episodic_db_path: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Run an incremental sync (only new/modified since last sync).

        Falls back to full sync if no previous sync timestamp exists.
        """
        since = self._last_sync_timestamp
        if since is None:
            return self.full_sync(semantic_db_path, world_model_db_path, episodic_db_path)

        results: Dict[str, Any] = {}

        if semantic_db_path:
            results["semantic"] = self._semantic_adapter.sync(
                self._store, semantic_db_path, since_timestamp=since
            )

        if world_model_db_path:
            results["world_model"] = self._world_adapter.sync(
                self._store, world_model_db_path, since_timestamp=since
            )

        if episodic_db_path:
            results["episodic"] = self._episodic_adapter.sync(
                self._store, episodic_db_path, since_timestamp=since
            )

        self._last_sync_timestamp = time.time()
        results["synced_at"] = _utcnow_iso()
        return results
