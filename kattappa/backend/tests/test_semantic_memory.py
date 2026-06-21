import json
import sqlite3
import time
import unittest
from unittest.mock import patch

from backend.core.semantic_memory import SemanticMemory


class NoCloseConnection:
    def __init__(self, conn):
        self._conn = conn

    def __getattr__(self, name):
        return getattr(self._conn, name)

    def close(self):
        # Do not close the shared in-memory test database
        pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass


class TestSemanticMemory(unittest.TestCase):

    def setUp(self):
        # Reset query cache so stale embeddings don't carry over between tests
        SemanticMemory._query_cache.clear()

        # Fully reset the Chroma collection to prevent state bleed between tests
        try:
            SemanticMemory._get_chroma_collection()  # ensure client is initialized
            SemanticMemory._chroma_client.delete_collection("semantic_vectors")
        except Exception:
            pass
        SemanticMemory._collection = None  # force lazy re-create on next access

        # Create a single in-memory database connection for the test class to bypass slow file system handle opens on Windows
        if not hasattr(self.__class__, "_shared_conn"):
            self.__class__._shared_conn = sqlite3.connect(":memory:", check_same_thread=False)
            self.__class__._shared_conn.row_factory = sqlite3.Row
            SemanticMemory._ensure_schema(self.__class__._shared_conn)
            
            from backend.core.memory_governance import MemoryGovernance
            MemoryGovernance._ensure_schema(self.__class__._shared_conn)

        # Clear tables between tests
        self.__class__._shared_conn.execute("DELETE FROM hm_semantic_edges")
        self.__class__._shared_conn.execute("DELETE FROM hm_semantic_nodes")
        self.__class__._shared_conn.execute("DELETE FROM hm_trust_registry")
        self.__class__._shared_conn.execute("DELETE FROM hm_provenance")
        self.__class__._shared_conn.commit()

        # Reset FTS5 virtual table
        try:
            self.__class__._shared_conn.execute("DELETE FROM hm_semantic_nodes_fts")
            self.__class__._shared_conn.commit()
        except Exception:
            pass

        # Patch _get_sqlite_conn to return our wrapped shared in-memory connection
        from backend.core.memory_governance import MemoryGovernance
        self.conn_patchers = [
            patch.object(SemanticMemory, "_get_sqlite_conn", return_value=NoCloseConnection(self.__class__._shared_conn)),
            patch.object(MemoryGovernance, "_get_sqlite_conn", return_value=NoCloseConnection(self.__class__._shared_conn)),
        ]
        for p in self.conn_patchers:
            p.start()

    def tearDown(self):
        SemanticMemory.stop_worker()
        for p in self.conn_patchers:
            p.stop()

    def test_semantic_node_crud(self):
        # 1. Create Node (first occurrence of a fact)
        nid = SemanticMemory.upsert_node(
            concept="Tauri framework",
            description="Tauri is a framework for building tiny, blazing fast desktop apps with web tech.",
            source_episode_id="ep-101",
            provenance="official documentation",
            confidence=0.5
        )
        self.assertIsNotNone(nid)
        SemanticMemory.flush_embeddings()

        # 2. Get Node
        node = SemanticMemory.get_node(nid)
        self.assertIsNotNone(node)
        self.assertEqual(node["concept"], "Tauri framework")
        self.assertEqual(node["confidence"], 0.5)
        self.assertEqual(node["evidence_count"], 1)
        self.assertIn("ep-101", node["source_episode_ids"])

        # 3. Delete Node
        deleted = SemanticMemory.delete_node(nid)
        self.assertTrue(deleted)
        self.assertIsNone(SemanticMemory.get_node(nid))

    def test_canonicalization_and_merging(self):
        # 1. First fact insert
        nid1 = SemanticMemory.upsert_node(
            concept="Python programming language",
            description="Python is a widely used high-level programming language.",
            source_episode_id="ep-python-1"
        )
        SemanticMemory.flush_embeddings()

        # 2. Second fact insert: highly similar semantic concept & same polarity
        # It should trigger semantic merge, resulting in same node ID.
        nid2 = SemanticMemory.upsert_node(
            concept="Python programming language",
            description="Python is a popular general-purpose high-level programming language.",
            source_episode_id="ep-python-2",
            provenance="user input"
        )
        SemanticMemory.flush_embeddings()

        self.assertEqual(nid1, nid2)

        # Check merged results
        node = SemanticMemory.get_node(nid1)
        self.assertIsNotNone(node)
        self.assertEqual(node["evidence_count"], 2)
        # Asymptotic confidence model update: min(1.0, 1.0 - (0.5 ** 2)) = 0.75
        self.assertEqual(node["confidence"], 0.75)
        self.assertIn("ep-python-1", node["source_episode_ids"])
        self.assertIn("ep-python-2", node["source_episode_ids"])
        self.assertIn("programming language", node["description"])

    def test_negation_blocking(self):
        # 1. Affirmative statement
        nid1 = SemanticMemory.upsert_node(
            concept="Kattappa OS safety",
            description="Kattappa OS is completely safe and isolated.",
            source_episode_id="ep-safe",
            similarity_threshold=0.2
        )
        SemanticMemory.flush_embeddings()

        # 2. Conflicting statement with negative polarity (contains "not")
        # Should be kept separate and not merged even though same concept.
        nid2 = SemanticMemory.upsert_node(
            concept="Kattappa OS safety",
            description="Kattappa OS is not completely safe and isolated.",
            source_episode_id="ep-unsafe",
            similarity_threshold=0.2
        )
        SemanticMemory.flush_embeddings()

        self.assertNotEqual(nid1, nid2)

    def test_contradiction_handling(self):
        # Create initial node
        nid1 = SemanticMemory.upsert_node(
            concept="Rust performance",
            description="Rust is extremely fast and performant.",
            source_episode_id="ep-fast",
            confidence=0.8
        )
        SemanticMemory.flush_embeddings()
        
        # Upsert a contradictory statement (opposite polarity)
        nid2 = SemanticMemory.upsert_node(
            concept="Rust performance",
            description="Rust is not extremely fast and performant.",
            source_episode_id="ep-not-fast",
            confidence=0.7
        )
        SemanticMemory.flush_embeddings()
        
        # They must be separate nodes
        self.assertNotEqual(nid1, nid2)
        
        # Node 1 confidence should be lowered by 0.2 (0.8 -> 0.6)
        node1 = SemanticMemory.get_node(nid1)
        self.assertAlmostEqual(node1["confidence"], 0.6)
        
        # Node 2 confidence should be lowered by 0.2 (0.7 -> 0.5)
        node2 = SemanticMemory.get_node(nid2)
        self.assertAlmostEqual(node2["confidence"], 0.5)

    def test_promotion_rules_and_provenance(self):
        # 1. First episode upsert: evidence_count = 1
        nid = SemanticMemory.upsert_node(
            concept="Aether engine",
            description="Aether engine processes hierarchical representations.",
            source_episode_id="ep-a1",
            provenance=None
        )
        SemanticMemory.flush_embeddings()
        
        # It exists in SQLite (direct lookup works)
        node = SemanticMemory.get_node(nid)
        self.assertIsNotNone(node)
        self.assertEqual(node["evidence_count"], 1)
        
        # But it should NOT be returned by recall because it is not promoted yet (evidence_count < 2)
        recalled = SemanticMemory.recall("Aether engine", limit=2)
        self.assertEqual(len(recalled), 0)
        
        # 2. Try to promote it without provenance -> should raise ValueError
        with self.assertRaises(ValueError):
            SemanticMemory.upsert_node(
                concept="Aether engine",
                description="Aether engine processes hierarchical representations.",
                source_episode_id="ep-a2",
                provenance=None
            )
        
        # 3. Promote it WITH provenance -> succeeds
        nid2 = SemanticMemory.upsert_node(
            concept="Aether engine",
            description="Aether engine processes hierarchical representations.",
            source_episode_id="ep-a2",
            provenance="System docs"
        )
        SemanticMemory.flush_embeddings()
        
        self.assertEqual(nid, nid2)
        node = SemanticMemory.get_node(nid)
        self.assertEqual(node["evidence_count"], 2)
        self.assertEqual(node["provenance"], "System docs")
        
        # Now it should be returned by recall!
        recalled = SemanticMemory.recall("Aether engine", limit=2)
        self.assertEqual(len(recalled), 1)
        self.assertEqual(recalled[0]["id"], nid)

    def test_edges_and_graph_traversal(self):
        # Create a tiny semantic property graph with promoted nodes (evidence_count = 2)
        nid_tauri = SemanticMemory.upsert_node("Tauri", "A desktop app construction framework.", "ep-1", similarity_threshold=0.2)
        SemanticMemory.upsert_node("Tauri", "A desktop app construction framework.", "ep-1-prom", provenance="test", similarity_threshold=0.2)
        
        nid_rust = SemanticMemory.upsert_node("Rust", "A systems programming language focusing on safety.", "ep-2", similarity_threshold=0.2)
        SemanticMemory.upsert_node("Rust", "A systems programming language focusing on safety.", "ep-2-prom", provenance="test", similarity_threshold=0.2)
        
        nid_cargo = SemanticMemory.upsert_node("Cargo", "The Rust package manager.", "ep-3", similarity_threshold=0.2)
        SemanticMemory.upsert_node("Cargo", "The Rust package manager.", "ep-3-prom", provenance="test", similarity_threshold=0.2)
        
        nid_crates = SemanticMemory.upsert_node("Crates.io", "The official package registry for Rust.", "ep-4", similarity_threshold=0.2)
        SemanticMemory.upsert_node("Crates.io", "The official package registry for Rust.", "ep-4-prom", provenance="test", similarity_threshold=0.2)
        
        nid_remote = SemanticMemory.upsert_node("Remote Repo", "Cloud hosting for rust packages.", "ep-5", similarity_threshold=0.2)
        SemanticMemory.upsert_node("Remote Repo", "Cloud hosting for rust packages.", "ep-5-prom", provenance="test", similarity_threshold=0.2)
        
        SemanticMemory.flush_embeddings()

        # Edges
        # Tauri -(uses)-> Rust (weight 0.9)
        # Rust -(has_tool)-> Cargo (weight 0.8)
        # Cargo -(downloads_from)-> Crates.io (weight 0.4)
        # Crates.io -(syncs_with)-> Remote Repo (weight 0.2)
        
        SemanticMemory.create_edge(nid_tauri, nid_rust, "uses", 0.9)
        SemanticMemory.create_edge(nid_rust, nid_cargo, "has_tool", 0.8)
        SemanticMemory.create_edge(nid_cargo, nid_crates, "downloads_from", 0.4)
        SemanticMemory.create_edge(nid_crates, nid_remote, "syncs_with", 0.2) # Below min_weight 0.35!

        # Traverse from Tauri (depth 3, min_weight 0.35)
        # Expected reachable: Tauri (start, hop 0) -> Rust (hop 1) -> Cargo (hop 2) -> Crates.io (hop 3)
        # Remote Repo (hop 4, and edge weight 0.2 < 0.35) should NOT be reachable.
        
        graph = SemanticMemory.traverse_graph(nid_tauri, max_hops=3, min_weight=0.35)
        
        # Verify nodes count & presence
        nodes = graph["nodes"]
        self.assertEqual(len(nodes), 4)
        self.assertIn(nid_tauri, nodes)
        self.assertIn(nid_rust, nodes)
        self.assertIn(nid_cargo, nodes)
        self.assertIn(nid_crates, nodes)
        self.assertNotIn(nid_remote, nodes)

        # Verify last_updated is present
        self.assertIn("last_updated", nodes[nid_tauri])

        # Verify edges count
        edges = graph["edges"]
        self.assertEqual(len(edges), 3)

        # Verify weight update on edge upsert
        eid_cargo_crates = SemanticMemory.create_edge(nid_cargo, nid_crates, "downloads_from", 0.95)
        edge = SemanticMemory.get_edge(eid_cargo_crates)
        self.assertEqual(edge["weight"], 0.95)

    def test_hybrid_retrieval(self):
        nid_ollama = SemanticMemory.upsert_node("Ollama server", "Ollama runs large language models locally.", "ep-o1")
        SemanticMemory.upsert_node("Ollama server", "Ollama runs large language models locally.", "ep-o1-prom", provenance="test")

        nid_gpu = SemanticMemory.upsert_node("GPU acceleration", "CUDA and ROCm enable massive hardware speedups.", "ep-o2")
        SemanticMemory.upsert_node("GPU acceleration", "CUDA and ROCm enable massive hardware speedups.", "ep-o2-prom", provenance="test")

        SemanticMemory.flush_embeddings()

        # Lexical search via FTS5
        results_lex = SemanticMemory.recall("Ollama", limit=2)
        self.assertEqual(len(results_lex), 1)
        self.assertEqual(results_lex[0]["id"], nid_ollama)

        # Semantic search via ChromaDB vector — query uses 'hardware'/'graphics' keywords
        # that map to the GPU family in the mock embedding function
        results_sem = SemanticMemory.recall("hardware graphics card execution profiles", limit=2)
        self.assertEqual(len(results_sem), 1)
        self.assertEqual(results_sem[0]["id"], nid_gpu)

    def test_vector_gc(self):
        # Create node with 2 episodes to make it promoted/GC candidate
        nid = SemanticMemory.upsert_node("GC candidate", "This will be cleaned up by the consistency sweep.", "ep-gc-1")
        SemanticMemory.upsert_node("GC candidate", "This will be cleaned up by the consistency sweep.", "ep-gc-2", provenance="GC docs")
        SemanticMemory.flush_embeddings()
        
        # Delete node only in SQLite, creating a ghost vector in Chroma
        conn = SemanticMemory._get_sqlite_conn()
        try:
            conn.execute("DELETE FROM hm_semantic_nodes WHERE id = ?", (nid,))
            conn.commit()
        finally:
            conn.close()
            
        # Trigger vector GC
        purged = SemanticMemory.run_vector_gc()
        self.assertEqual(purged, 1)
        
        # Verify removed from Chroma
        collection = SemanticMemory._get_chroma_collection()
        self.assertEqual(collection.count(), 0)

    def test_fts5_synchronization(self):
        # Create node
        nid = SemanticMemory.upsert_node("Sync target", "Initial description for sync checking.", "ep-sync-1")
        SemanticMemory.flush_embeddings()
        
        # Verify FTS5 has the concept
        conn = SemanticMemory._get_sqlite_conn()
        try:
            row = conn.execute("SELECT count(*) as c FROM hm_semantic_nodes_fts WHERE concept MATCH 'Sync'").fetchone()
            self.assertEqual(row["c"], 1)
        finally:
            conn.close()
            
        # Update node description -> trigger should sync
        SemanticMemory.upsert_node(
            concept="Sync target",
            description="Updated description for sync checking.",
            source_episode_id="ep-sync-2",
            provenance="update"
        )
        SemanticMemory.flush_embeddings()
        
        # Verify FTS5 matches updated description
        conn = SemanticMemory._get_sqlite_conn()
        try:
            row = conn.execute("SELECT count(*) as c FROM hm_semantic_nodes_fts WHERE description MATCH 'Updated'").fetchone()
            self.assertEqual(row["c"], 1)
        finally:
            conn.close()
            
        # Delete node -> trigger should delete from FTS5
        SemanticMemory.delete_node(nid)
        
        conn = SemanticMemory._get_sqlite_conn()
        try:
            row = conn.execute("SELECT count(*) as c FROM hm_semantic_nodes_fts").fetchone()
            self.assertEqual(row["c"], 0)
        finally:
            conn.close()

    def test_scalability_simulation(self):
        # We simulate 50k nodes in SQLite to verify query performance.
        # To make it run fast, perform insertions in a single transaction.
        conn = SemanticMemory._get_sqlite_conn()
        try:
            # Disable foreign keys and triggers temporarily during mass insert to make it instant
            conn.execute("PRAGMA foreign_keys = OFF")
            conn.execute("DROP TRIGGER IF EXISTS trg_hm_semantic_nodes_ai")
            
            # Insert 50,000 nodes using executemany
            now = time.time()
            nodes_data = []
            for i in range(50000):
                ev_count = 2 if i % 5000 == 0 else 1
                status = "verified" if ev_count >= 2 else "draft"
                nodes_data.append((
                    f"node-uuid-{i}",
                    f"Concept Scale {i}",
                    f"Factual knowledge description piece number {i}.",
                    0.8,
                    ev_count,
                    json.dumps([f"ep-{i}"]),
                    "simulation",
                    now,
                    now,
                    status
                ))
            
            conn.executemany(
                """
                INSERT INTO hm_semantic_nodes (
                    id, concept, description, confidence, evidence_count,
                    source_episode_ids, provenance, created_at, updated_at, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                nodes_data
            )
            conn.commit()
            
            # Re-create trigger and sync FTS virtual table
            conn.executescript(
                """
                CREATE TRIGGER trg_hm_semantic_nodes_ai AFTER INSERT ON hm_semantic_nodes BEGIN
                    INSERT INTO hm_semantic_nodes_fts(rowid, concept, description) VALUES (new.rowid, new.concept, new.description);
                END;
                INSERT INTO hm_semantic_nodes_fts(rowid, concept, description) SELECT rowid, concept, description FROM hm_semantic_nodes;
                """
            )
            conn.commit()
        finally:
            conn.close()
            
        # Warm up
        SemanticMemory.recall("warmup", limit=1)

        # Test recall execution time
        start_time = time.time()
        results = SemanticMemory.recall("Concept Scale 10000", limit=5)
        end_time = time.time()
        
        elapsed = end_time - start_time
        print(f"\n[TIMING] 50k-Node simulated recall took: {elapsed:.6f}s")
        # Must remain acceptable (< 150ms)
        self.assertLess(elapsed, 0.15)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["concept"], "Concept Scale 10000")

    def test_corroboration_trust_recheck(self):
        """Corroborating a fact with a node/episode marked as TRUST_UNTRUSTED must raise ValueError."""
        # 1. Register episode as untrusted
        from backend.core.memory_governance import MemoryGovernance
        MemoryGovernance.set_trust("ep-untrusted-1", "memory", "TRUST_UNTRUSTED")
        
        # 2. Insert original fact (starts as draft, evidence_count = 1)
        nid = SemanticMemory.upsert_node(
            concept="Unproven concept",
            description="Concept is unverified initially.",
            source_episode_id="ep-100",
            provenance="official",
            confidence=0.5
        )
        
        # 3. Attempt to corroborate with the untrusted episode, which should raise ValueError
        with self.assertRaises(ValueError):
            SemanticMemory.upsert_node(
                concept="Unproven concept",
                description="Concept is unverified initially.",
                source_episode_id="ep-untrusted-1",
                provenance="official",
                confidence=0.5
            )

    def test_contradiction_contested_status(self):
        """Opposite polarities should trigger contested status and peer contradicts_id linking."""
        # 1. Insert original fact
        nid1 = SemanticMemory.upsert_node(
            concept="Water boiling point",
            description="Water boils at 100 degrees Celsius under standard pressure.",
            source_episode_id="ep-w1",
            provenance="official",
            confidence=0.8
        )
        
        # 2. Insert contradictory fact (negated polarity)
        nid2 = SemanticMemory.upsert_node(
            concept="Water boiling point",
            description="Water does not boil at 100 degrees Celsius under standard pressure.",
            source_episode_id="ep-w2",
            provenance="official",
            confidence=0.8
        )
        
        # Both must be marked as contested
        node1 = SemanticMemory.get_node(nid1)
        node2 = SemanticMemory.get_node(nid2)
        
        self.assertEqual(node1["status"], "contested")
        self.assertEqual(node2["status"], "contested")
        self.assertEqual(node1["contradicts_id"], nid2)
        self.assertEqual(node2["contradicts_id"], nid1)
        
        # 3. Contested nodes must not be recalled
        recalled = SemanticMemory.recall("Water boiling point")
        recalled_ids = [n["id"] for n in recalled]
        self.assertNotIn(nid1, recalled_ids)
        self.assertNotIn(nid2, recalled_ids)

    def test_provenance_logged_on_promotion(self):
        """Provenance must be logged when a fact is promoted (evidence count >= 2)."""
        nid = SemanticMemory.upsert_node(
            concept="Unique fact",
            description="Description of unique fact.",
            source_episode_id="ep-u1",
            provenance="user",
            confidence=0.5
        )
        # First occurrence is draft (evidence count = 1), no provenance logged in governance yet
        from backend.core.memory_governance import MemoryGovernance
        self.assertIsNone(MemoryGovernance.get_provenance(nid))
        
        # Corroborate to promote (evidence count = 2)
        SemanticMemory.upsert_node(
            concept="Unique fact",
            description="Description of unique fact.",
            source_episode_id="ep-u2",
            provenance="user",
            confidence=0.5
        )
        
        # Verify provenance is logged in governance
        prov = MemoryGovernance.get_provenance(nid)
        self.assertIsNotNone(prov)
        self.assertEqual(prov["memory_type"], "semantic")
        self.assertEqual(prov["source"], "episodic_promotion")
