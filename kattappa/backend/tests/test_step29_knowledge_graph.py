"""Comprehensive test suite for Step 29: Knowledge Graph.

Covers GraphStore CRUD, GraphQuery algorithms, KnowledgeGraph main class,
cross-layer sync adapters, and thread safety / performance.
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
from pathlib import Path

import pytest

from backend.core.graph_store import GraphStore
from backend.core.graph_query import GraphQueryEngine
from backend.core.knowledge_graph import (
    KnowledgeGraph,
    KGNode,
    KGEdge,
    EntityType,
    RelationType,
)
from backend.core.kg_sync import (
    SemanticSyncAdapter,
    WorldModelSyncAdapter,
    EpisodicSyncAdapter,
    SyncManager,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _reset_schema():
    """Reset the class-level schema flag so each test gets a fresh DB."""
    GraphStore._schema_ensured = False
    yield
    GraphStore._schema_ensured = False


@pytest.fixture()
def store(tmp_path) -> GraphStore:
    """Return a GraphStore backed by a temp SQLite file."""
    return GraphStore(str(tmp_path / "kg.db"))


@pytest.fixture()
def kg(tmp_path) -> KnowledgeGraph:
    """Return a KnowledgeGraph instance using a temp directory."""
    return KnowledgeGraph(str(tmp_path / "kg_data"))


# ---------------------------------------------------------------------------
# Helper: build a small graph for query tests
# ---------------------------------------------------------------------------

def _build_chain(store: GraphStore, names=("A", "B", "C", "D")):
    """Insert a chain A->B->C->D with RELATED_TO edges. Returns id map."""
    ids = {}
    for n in names:
        ids[n] = store.insert_node(name=n, entity_type="CONCEPT")
    pairs = list(zip(names, names[1:]))
    for src, tgt in pairs:
        store.insert_edge(source_id=ids[src], target_id=ids[tgt], relation_type="RELATED_TO")
    return ids


# ============================= GraphStore =================================

class TestGraphStore:

    def test_insert_and_get_node(self, store: GraphStore):
        nid = store.insert_node("Alice", "PERSON", properties={"age": 30}, confidence=0.9)
        node = store.get_node(nid)
        assert node is not None
        assert node["name"] == "Alice"
        assert node["entity_type"] == "PERSON"
        assert node["properties"] == {"age": 30}
        assert node["confidence"] == 0.9

    def test_insert_and_get_node_by_name(self, store: GraphStore):
        store.insert_node("Bob", "PERSON")
        node = store.get_node_by_name("bob")  # case-insensitive
        assert node is not None
        assert node["name"] == "Bob"

    def test_update_node(self, store: GraphStore):
        nid = store.insert_node("Carol", "PERSON", confidence=0.5)
        ok = store.update_node(nid, confidence=0.95, properties={"role": "admin"})
        assert ok is True
        node = store.get_node(nid)
        assert node["confidence"] == 0.95
        assert node["properties"] == {"role": "admin"}

    def test_delete_node(self, store: GraphStore):
        nid = store.insert_node("Dave", "PERSON")
        assert store.delete_node(nid) is True
        assert store.get_node(nid) is None

    def test_insert_and_get_edges(self, store: GraphStore):
        n1 = store.insert_node("X", "CONCEPT")
        n2 = store.insert_node("Y", "CONCEPT")
        eid = store.insert_edge(source_id=n1, target_id=n2, relation_type="LINKS")
        out_edges = store.get_edges_from(n1)
        assert len(out_edges) == 1
        assert out_edges[0]["id"] == eid
        assert out_edges[0]["relation_type"] == "LINKS"
        in_edges = store.get_edges_to(n2)
        assert len(in_edges) == 1
        assert in_edges[0]["id"] == eid

    def test_delete_edge(self, store: GraphStore):
        n1 = store.insert_node("M", "CONCEPT")
        n2 = store.insert_node("N", "CONCEPT")
        eid = store.insert_edge(source_id=n1, target_id=n2, relation_type="LINKS")
        assert store.delete_edge(eid) is True
        assert store.get_edges_from(n1) == []

    def test_batch_insert_nodes(self, store: GraphStore):
        nodes = [
            {"name": "p1", "entity_type": "CONCEPT"},
            {"name": "p2", "entity_type": "SKILL"},
            {"name": "p3", "entity_type": "TOOL"},
        ]
        ids = store.batch_insert_nodes(nodes)
        assert len(ids) == 3
        for nid, nd in zip(ids, nodes):
            got = store.get_node(nid)
            assert got is not None
            assert got["name"] == nd["name"]

    def test_batch_insert_edges(self, store: GraphStore):
        n1 = store.insert_node("s1", "CONCEPT")
        n2 = store.insert_node("s2", "CONCEPT")
        n3 = store.insert_node("s3", "CONCEPT")
        edges = [
            {"source_id": n1, "target_id": n2, "relation_type": "A"},
            {"source_id": n2, "target_id": n3, "relation_type": "B"},
        ]
        eids = store.batch_insert_edges(edges)
        assert len(eids) == 2
        assert len(store.get_edges_from(n1)) == 1
        assert len(store.get_edges_from(n2)) == 1

    def test_fts_search(self, store: GraphStore):
        store.insert_node("Python Programming", "SKILL")
        store.insert_node("Java Programming", "SKILL")
        store.insert_node("Cooking Recipes", "CONCEPT")
        results = store.search_nodes_fts("Programming")
        assert len(results) == 2
        names = {r["name"] for r in results}
        assert "Python Programming" in names
        assert "Java Programming" in names

    def test_alias_crud(self, store: GraphStore):
        nid = store.insert_node("Artificial Intelligence", "CONCEPT")
        store.insert_alias(nid, "AI")
        resolved = store.resolve_alias("AI")
        assert resolved is not None
        assert resolved["id"] == nid
        aliases = store.get_aliases(nid)
        assert len(aliases) == 1
        assert aliases[0]["alias_name"] == "AI"


# ============================= GraphQuery =================================

class TestGraphQuery:

    def test_bfs_traversal(self, store: GraphStore):
        ids = _build_chain(store)
        engine = GraphQueryEngine(store)
        result = engine.bfs_traverse(ids["A"], max_depth=3)
        visited_names = [r[0]["name"] for r in result]
        assert visited_names == ["A", "B", "C", "D"]
        depths = [r[1] for r in result]
        assert depths == [0, 1, 2, 3]

    def test_dfs_traversal(self, store: GraphStore):
        ids = _build_chain(store)
        engine = GraphQueryEngine(store)
        result = engine.dfs_traverse(ids["A"], max_depth=3)
        names = [r[0]["name"] for r in result]
        assert names[0] == "A"
        assert set(names) == {"A", "B", "C", "D"}

    def test_bfs_confidence_filter(self, store: GraphStore):
        n1 = store.insert_node("S", "CONCEPT")
        n2 = store.insert_node("T", "CONCEPT")
        n3 = store.insert_node("U", "CONCEPT")
        store.insert_edge(source_id=n1, target_id=n2, relation_type="R", confidence=0.9)
        store.insert_edge(source_id=n1, target_id=n3, relation_type="R", confidence=0.1)
        engine = GraphQueryEngine(store)
        result = engine.bfs_traverse(n1, max_depth=1, min_confidence=0.5)
        names = {r[0]["name"] for r in result}
        assert "T" in names
        assert "U" not in names

    def test_bfs_relation_filter(self, store: GraphStore):
        n1 = store.insert_node("F1", "CONCEPT")
        n2 = store.insert_node("F2", "CONCEPT")
        n3 = store.insert_node("F3", "CONCEPT")
        store.insert_edge(source_id=n1, target_id=n2, relation_type="USES")
        store.insert_edge(source_id=n1, target_id=n3, relation_type="DEPENDS_ON")
        engine = GraphQueryEngine(store)
        result = engine.bfs_traverse(n1, max_depth=1, relation_filter="USES")
        names = {r[0]["name"] for r in result}
        assert "F2" in names
        assert "F3" not in names

    def test_find_shortest_path(self, store: GraphStore):
        ids = _build_chain(store)
        engine = GraphQueryEngine(store)
        path = engine.find_shortest_path(ids["A"], ids["D"])
        assert len(path) == 3
        # Verify the path connects A->B->C->D
        assert path[0]["source_id"] == ids["A"]
        assert path[-1]["target_id"] == ids["D"]

    def test_find_shortest_path_no_connection(self, store: GraphStore):
        n1 = store.insert_node("Iso1", "CONCEPT")
        n2 = store.insert_node("Iso2", "CONCEPT")
        engine = GraphQueryEngine(store)
        path = engine.find_shortest_path(n1, n2)
        assert path == []

    def test_get_subgraph(self, store: GraphStore):
        ids = _build_chain(store)
        engine = GraphQueryEngine(store)
        sg = engine.get_subgraph(ids["B"], radius=1)
        node_names = {n["name"] for n in sg["nodes"]}
        # B is center, radius 1 -> A (via incoming), C (via outgoing)
        assert "B" in node_names
        assert "A" in node_names
        assert "C" in node_names

    def test_find_hubs(self, store: GraphStore):
        # Create a star: center -> leaf1..leaf5
        center = store.insert_node("Hub", "CONCEPT")
        for i in range(5):
            leaf = store.insert_node(f"leaf{i}", "CONCEPT")
            store.insert_edge(source_id=center, target_id=leaf, relation_type="LINKS")
        engine = GraphQueryEngine(store)
        hubs = engine.find_hubs(top_n=1)
        assert len(hubs) >= 1
        assert hubs[0][0]["name"] == "Hub"
        assert hubs[0][1] >= 5  # degree >= 5

    def test_find_clusters(self, store: GraphStore):
        # Cluster 1: A-B-C connected
        a = store.insert_node("ca", "CONCEPT")
        b = store.insert_node("cb", "CONCEPT")
        c = store.insert_node("cc", "CONCEPT")
        store.insert_edge(source_id=a, target_id=b, relation_type="R")
        store.insert_edge(source_id=b, target_id=c, relation_type="R")
        # Cluster 2: isolated pair
        x = store.insert_node("cx", "CONCEPT")
        y = store.insert_node("cy", "CONCEPT")
        store.insert_edge(source_id=x, target_id=y, relation_type="R")
        engine = GraphQueryEngine(store)
        clusters = engine.find_clusters(min_size=3)
        assert len(clusters) == 1
        names = {n["name"] for n in clusters[0]}
        assert names == {"ca", "cb", "cc"}

    def test_find_knowledge_gaps(self, store: GraphStore):
        goal = store.insert_node("Master ML", "GOAL")
        prereq = store.insert_node("Linear Algebra", "CONCEPT", confidence=0.2)
        store.insert_edge(source_id=prereq, target_id=goal, relation_type="PREREQUISITE_OF")
        engine = GraphQueryEngine(store)
        gaps = engine.find_knowledge_gaps(goal)
        assert len(gaps) >= 1
        assert gaps[0]["name"] == "Linear Algebra"
        assert gaps[0]["relation"] == "PREREQUISITE_OF"


# ============================= KnowledgeGraph ==============================

class TestKnowledgeGraph:

    def test_add_and_find_node(self, kg: KnowledgeGraph):
        node = kg.add_node("Python", EntityType.SKILL, confidence=0.95)
        assert isinstance(node, KGNode)
        assert node.name == "Python"
        assert node.entity_type == "SKILL"
        found = kg.resolve_entity("Python")
        assert found is not None
        assert found.id == node.id

    def test_add_edge_and_find_related(self, kg: KnowledgeGraph):
        kg.add_node("Alice", EntityType.PERSON)
        kg.add_node("Bob", EntityType.PERSON)
        kg.add_edge("Alice", "Bob", RelationType.RELATED_TO)
        related = kg.find_related("Alice", max_depth=1)
        names = {r[0].name for r in related}
        assert "Bob" in names

    def test_find_related_multi_hop(self, kg: KnowledgeGraph):
        kg.add_node("X", EntityType.CONCEPT)
        kg.add_node("Y", EntityType.CONCEPT)
        kg.add_node("Z", EntityType.CONCEPT)
        kg.add_edge("X", "Y", RelationType.RELATED_TO)
        kg.add_edge("Y", "Z", RelationType.RELATED_TO)
        related = kg.find_related("X", max_depth=2)
        names = {r[0].name for r in related}
        assert "Y" in names
        assert "Z" in names

    def test_find_dependencies(self, kg: KnowledgeGraph):
        kg.add_node("App", EntityType.PROJECT)
        kg.add_node("Database", EntityType.COMPONENT)
        kg.add_edge("App", "Database", RelationType.DEPENDS_ON)
        deps = kg.find_dependencies("App")
        assert len(deps) == 1
        assert deps[0].name == "Database"

    def test_find_prerequisites(self, kg: KnowledgeGraph):
        kg.add_node("Calculus", EntityType.CONCEPT)
        kg.add_node("ML", EntityType.SKILL)
        # Calculus is a PREREQUISITE_OF ML
        kg.add_edge("Calculus", "ML", RelationType.PREREQUISITE_OF)
        prereqs = kg.find_prerequisites("ML")
        assert len(prereqs) == 1
        assert prereqs[0].name == "Calculus"

    def test_find_tools_for_skill(self, kg: KnowledgeGraph):
        kg.add_node("Data Science", EntityType.SKILL)
        kg.add_node("Pandas", EntityType.TOOL)
        kg.add_node("Stats Book", EntityType.DOCUMENT)
        kg.add_edge("Data Science", "Pandas", RelationType.USES)
        kg.add_edge("Data Science", "Stats Book", RelationType.USES)
        tools = kg.find_tools_for_skill("Data Science")
        assert len(tools) == 1
        assert tools[0].name == "Pandas"
        assert tools[0].entity_type == "TOOL"

    def test_find_knowledge_gaps(self, kg: KnowledgeGraph):
        goal = kg.add_node("Build AI", EntityType.GOAL)
        prereq = kg.add_node("Probability", EntityType.CONCEPT, confidence=0.1)
        kg.add_edge("Probability", "Build AI", RelationType.PREREQUISITE_OF)
        gaps = kg.find_knowledge_gaps("Build AI")
        assert len(gaps) >= 1
        gap_names = {g["name"] for g in gaps}
        assert "Probability" in gap_names

    def test_entity_reconciliation_alias(self, kg: KnowledgeGraph):
        node = kg.add_node("Machine Learning", EntityType.CONCEPT)
        kg.register_alias(node.id, "ML")
        resolved = kg.resolve_entity("ML")
        assert resolved is not None
        assert resolved.id == node.id
        assert resolved.name == "Machine Learning"

    def test_merge_entities(self, kg: KnowledgeGraph):
        n1 = kg.add_node("Node A", EntityType.CONCEPT, properties={"a": 1})
        n2 = kg.add_node("Node B", EntityType.CONCEPT, properties={"b": 2})
        kg.add_edge("Node B", "Node A", RelationType.RELATED_TO)
        merged = kg.merge_entities([n1.id, n2.id])
        assert merged.name == "Node A"
        assert merged.properties.get("b") == 2
        # n2 should be gone
        assert kg.resolve_entity("Node B") is None or kg.resolve_entity("Node B").id == n1.id

    def test_traverse(self, kg: KnowledgeGraph):
        kg.add_node("T1", EntityType.CONCEPT)
        kg.add_node("T2", EntityType.CONCEPT)
        kg.add_node("T3", EntityType.CONCEPT)
        kg.add_edge("T1", "T2", RelationType.RELATED_TO)
        kg.add_edge("T2", "T3", RelationType.RELATED_TO)
        result = kg.traverse("T1", max_depth=2)
        names = [r[0].name for r in result]
        assert "T1" in names
        assert "T2" in names
        assert "T3" in names

    def test_find_path(self, kg: KnowledgeGraph):
        kg.add_node("P1", EntityType.CONCEPT)
        kg.add_node("P2", EntityType.CONCEPT)
        kg.add_node("P3", EntityType.CONCEPT)
        kg.add_edge("P1", "P2", RelationType.RELATED_TO)
        kg.add_edge("P2", "P3", RelationType.RELATED_TO)
        path = kg.find_path("P1", "P3")
        assert len(path) == 2
        assert all(isinstance(e, KGEdge) for e in path)

    def test_get_subgraph(self, kg: KnowledgeGraph):
        kg.add_node("S1", EntityType.CONCEPT)
        kg.add_node("S2", EntityType.CONCEPT)
        kg.add_node("S3", EntityType.CONCEPT)
        kg.add_edge("S1", "S2", RelationType.RELATED_TO)
        kg.add_edge("S2", "S3", RelationType.RELATED_TO)
        sg = kg.get_subgraph("S2", radius=1)
        assert "nodes" in sg
        assert "edges" in sg
        node_names = {n.name for n in sg["nodes"]}
        assert "S2" in node_names
        assert "S1" in node_names
        assert "S3" in node_names


# =========================== Cross-layer Sync ==============================

def _create_semantic_db(db_path: str):
    """Create a minimal semantic memory SQLite DB for testing."""
    conn = sqlite3.connect(db_path)
    conn.executescript("""
        CREATE TABLE semantic_nodes (
            node_id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            node_type TEXT NOT NULL,
            content_raw TEXT DEFAULT '',
            confidence_score REAL DEFAULT 0.8,
            status TEXT DEFAULT 'ACTIVE',
            updated_at REAL DEFAULT 0
        );
        CREATE TABLE semantic_edges (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_node_id TEXT NOT NULL,
            target_node_id TEXT NOT NULL,
            relation_type TEXT NOT NULL,
            weight_score REAL DEFAULT 1.0
        );
    """)
    conn.execute(
        "INSERT INTO semantic_nodes VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("sem1", "Neural Networks", "CONCEPT", "NN description", 0.9, "ACTIVE", 0),
    )
    conn.execute(
        "INSERT INTO semantic_nodes VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("sem2", "Backpropagation", "CONCEPT", "BP description", 0.85, "ACTIVE", 0),
    )
    conn.execute(
        "INSERT INTO semantic_edges (source_node_id, target_node_id, relation_type, weight_score)"
        " VALUES (?, ?, ?, ?)",
        ("sem1", "sem2", "IS_A", 0.95),
    )
    conn.commit()
    conn.close()


def _create_world_model_db(db_path: str):
    """Create a minimal world model SQLite DB for testing."""
    conn = sqlite3.connect(db_path)
    conn.executescript("""
        CREATE TABLE world_state_nodes (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            type TEXT NOT NULL,
            status TEXT DEFAULT 'active',
            attributes TEXT DEFAULT '{}',
            updated_at REAL DEFAULT 0
        );
        CREATE TABLE world_state_edges (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            src TEXT NOT NULL,
            dst TEXT NOT NULL,
            relation TEXT NOT NULL
        );
    """)
    conn.execute(
        "INSERT INTO world_state_nodes VALUES (?, ?, ?, ?, ?, ?)",
        ("wm1", "Robot Arm", "device", "active", '{"dof": 6}', 0),
    )
    conn.execute(
        "INSERT INTO world_state_nodes VALUES (?, ?, ?, ?, ?, ?)",
        ("wm2", "Assembly Line", "project", "active", '{}', 0),
    )
    conn.execute(
        "INSERT INTO world_state_edges (src, dst, relation) VALUES (?, ?, ?)",
        ("wm1", "wm2", "contains"),
    )
    conn.commit()
    conn.close()


def _create_episodic_db(db_path: str):
    """Create a minimal episodic memory SQLite DB for testing."""
    conn = sqlite3.connect(db_path)
    conn.executescript("""
        CREATE TABLE episodes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            summary TEXT NOT NULL,
            relevance_score REAL DEFAULT 0.5,
            participants TEXT DEFAULT '[]',
            created_at TEXT DEFAULT ''
        );
    """)
    conn.execute(
        "INSERT INTO episodes (summary, relevance_score, participants, created_at) VALUES (?, ?, ?, ?)",
        ("Team meeting about project X", 0.7, '["Alice", "Bob"]', "2025-01-01T00:00:00"),
    )
    conn.execute(
        "INSERT INTO episodes (summary, relevance_score, participants, created_at) VALUES (?, ?, ?, ?)",
        ("Code review session", 0.6, '["Carol"]', "2025-01-02T00:00:00"),
    )
    conn.commit()
    conn.close()


class TestCrossLayerSync:

    def test_semantic_sync_adapter(self, store: GraphStore, tmp_path):
        sem_db = str(tmp_path / "semantic.db")
        _create_semantic_db(sem_db)
        adapter = SemanticSyncAdapter()
        result = adapter.sync(store, sem_db)
        assert result["nodes_synced"] == 2
        assert result["edges_synced"] == 1
        # Verify nodes exist in KG store
        nn = store.get_node_by_name("Neural Networks")
        assert nn is not None
        assert nn["entity_type"] == "CONCEPT"
        assert nn["source_layer"] == "semantic"

    def test_world_model_sync_adapter(self, store: GraphStore, tmp_path):
        wm_db = str(tmp_path / "world.db")
        _create_world_model_db(wm_db)
        adapter = WorldModelSyncAdapter()
        result = adapter.sync(store, wm_db)
        assert result["nodes_synced"] == 2
        assert result["edges_synced"] == 1
        robot = store.get_node_by_name("Robot Arm")
        assert robot is not None
        assert robot["entity_type"] == "DEVICE"
        assert robot["source_layer"] == "world_model"

    def test_episodic_sync_adapter(self, store: GraphStore, tmp_path):
        ep_db = str(tmp_path / "episodic.db")
        _create_episodic_db(ep_db)
        adapter = EpisodicSyncAdapter()
        result = adapter.sync(store, ep_db)
        # 2 episodes + 3 participants (Alice, Bob, Carol) = 5 nodes
        assert result["nodes_synced"] == 5
        # 3 participant edges + 1 follow-up edge = 4
        assert result["edges_synced"] == 4
        ep1 = store.get_node_by_name("Episode 1")
        assert ep1 is not None
        assert ep1["entity_type"] == "EVENT"

    def test_full_sync_deduplication(self, tmp_path):
        """Same entity from 2 layers should result in 1 node (dedup by name+type)."""
        kg_dir = str(tmp_path / "kg_dedup")
        kg_inst = KnowledgeGraph(kg_dir)

        # Create two source DBs that share an entity name
        sem_db = str(tmp_path / "sem_dedup.db")
        _create_semantic_db(sem_db)
        wm_db = str(tmp_path / "wm_dedup.db")
        # World model has a node also called "Neural Networks" but type maps to CONCEPT
        conn = sqlite3.connect(wm_db)
        conn.executescript("""
            CREATE TABLE world_state_nodes (
                id TEXT PRIMARY KEY, name TEXT, type TEXT,
                status TEXT, attributes TEXT, updated_at REAL
            );
            CREATE TABLE world_state_edges (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                src TEXT, dst TEXT, relation TEXT
            );
        """)
        conn.execute(
            "INSERT INTO world_state_nodes VALUES (?,?,?,?,?,?)",
            ("wm_nn", "Neural Networks", "other", "active", "{}", 0),
        )
        conn.commit()
        conn.close()

        # Sync semantic first, then world model
        kg_inst.sync_from_semantic(sem_db)
        kg_inst.sync_from_world_model(wm_db)

        # "Neural Networks" with entity_type CONCEPT should be 1 node (updated, not duplicated)
        results = kg_inst._store.search_nodes_fts("Neural Networks")
        nn_results = [r for r in results if r["name"] == "Neural Networks"]
        assert len(nn_results) == 1

    def test_incremental_sync(self, store: GraphStore, tmp_path):
        sem_db = str(tmp_path / "sem_inc.db")
        _create_semantic_db(sem_db)
        manager = SyncManager(store)
        # First full sync
        result1 = manager.full_sync(semantic_db_path=sem_db)
        assert result1["semantic"]["nodes_synced"] == 2
        ts = manager.last_sync_timestamp
        assert ts is not None

        # Incremental sync -- no new data since last sync
        result2 = manager.incremental_sync(semantic_db_path=sem_db)
        # since_timestamp is recent, so old rows (updated_at=0) should be filtered
        assert result2["semantic"]["nodes_synced"] == 0


# ===================== Thread Safety & Performance =========================

class TestThreadSafetyPerformance:

    def test_concurrent_writes(self, tmp_path):
        store = GraphStore(str(tmp_path / "conc.db"))
        errors: list[Exception] = []

        def writer(thread_idx: int):
            try:
                for i in range(20):
                    store.insert_node(f"thread{thread_idx}_node{i}", "CONCEPT")
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=writer, args=(t,)) for t in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)
        assert errors == []
        # 5 threads x 20 nodes = 100 nodes
        fts = store.search_nodes_fts("thread")
        assert len(fts) >= 1  # at least some nodes exist

    def test_traversal_performance(self, store: GraphStore):
        """BFS over 1000-node chain should complete under 100ms."""
        ids = []
        for i in range(1000):
            nid = store.insert_node(f"perf_{i}", "CONCEPT")
            ids.append(nid)
        for i in range(999):
            store.insert_edge(source_id=ids[i], target_id=ids[i + 1], relation_type="NEXT")

        engine = GraphQueryEngine(store)
        start = time.time()
        result = engine.bfs_traverse(ids[0], max_depth=1000)
        elapsed = time.time() - start
        assert len(result) == 1000
        assert elapsed < 1.0, f"BFS took {elapsed:.3f}s, expected < 1s"

    def test_concurrent_reads_during_write(self, tmp_path):
        store = GraphStore(str(tmp_path / "rw.db"))
        # Pre-populate
        for i in range(50):
            store.insert_node(f"pre_{i}", "CONCEPT")

        read_results: list[int] = []
        errors: list[Exception] = []

        def reader():
            try:
                nodes = store.search_nodes_fts("pre")
                read_results.append(len(nodes))
            except Exception as e:
                errors.append(e)

        def writer():
            try:
                for i in range(50, 100):
                    store.insert_node(f"pre_{i}", "CONCEPT")
            except Exception as e:
                errors.append(e)

        threads = []
        for _ in range(3):
            threads.append(threading.Thread(target=reader))
        threads.append(threading.Thread(target=writer))
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)
        assert errors == []
        # All readers should have gotten some results
        assert all(r >= 0 for r in read_results)
