import json
import time
import unittest
from unittest.mock import patch

from backend.core.semantic_memory import SemanticMemory


class TestSemanticMemory(unittest.TestCase):

    def setUp(self):
        # Reset memory state
        try:
            SemanticMemory._get_chroma_collection()
            SemanticMemory._chroma_client.delete_collection("semantic_vectors")
            SemanticMemory._collection = None
        except Exception:
            pass
        # Reset schema ensured flag to force fresh schema check
        SemanticMemory._schema_ensured = False
        conn = SemanticMemory._get_sqlite_conn()
        try:
            conn.execute("DELETE FROM hm_semantic_edges")
            conn.execute("DELETE FROM hm_semantic_nodes")
            conn.commit()
        finally:
            conn.close()

    def tearDown(self):
        SemanticMemory.stop_worker()

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
            source_episode_id="ep-python-2"
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
        conn = SemanticMemory._get_sqlite_conn()
        schema_sql = conn.execute("SELECT sql FROM sqlite_master WHERE name='hm_semantic_nodes'").fetchone()[0]
        print("\nDATABASE SCHEMA IS:", schema_sql)
        conn.close()

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

    def test_edges_and_graph_traversal(self):
        # Create a tiny semantic property graph
        # Node A -> Node B -> Node C -> Node D -> Node E
        # Relationship paths:
        # A: Tauri (id_tauri)
        # B: Rust (id_rust)
        # C: Cargo (id_cargo)
        # D: Crates (id_crates)
        # E: Remote repository (id_remote)
        
        nid_tauri = SemanticMemory.upsert_node("Tauri", "A desktop app construction framework.", "ep-1", similarity_threshold=0.2)
        nid_rust = SemanticMemory.upsert_node("Rust", "A systems programming language focusing on safety.", "ep-2", similarity_threshold=0.2)
        nid_cargo = SemanticMemory.upsert_node("Cargo", "The Rust package manager.", "ep-3", similarity_threshold=0.2)
        nid_crates = SemanticMemory.upsert_node("Crates.io", "The official package registry for Rust.", "ep-4", similarity_threshold=0.2)
        nid_remote = SemanticMemory.upsert_node("Remote Repo", "Cloud hosting for rust packages.", "ep-5", similarity_threshold=0.2)
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

        # Verify edges count
        edges = graph["edges"]
        self.assertEqual(len(edges), 3)

        # Verify weight update on edge upsert
        eid_cargo_crates = SemanticMemory.create_edge(nid_cargo, nid_crates, "downloads_from", 0.95)
        edge = SemanticMemory.get_edge(eid_cargo_crates)
        self.assertEqual(edge["weight"], 0.95)

    def test_hybrid_retrieval(self):
        nid_ollama = SemanticMemory.upsert_node("Ollama server", "Ollama runs large language models locally.", "ep-o1")
        nid_gpu = SemanticMemory.upsert_node("GPU acceleration", "CUDA and ROCm enable massive hardware speedups.", "ep-o2")
        SemanticMemory.flush_embeddings()

        # Lexical search via FTS5
        results_lex = SemanticMemory.recall("Ollama", limit=2)
        self.assertEqual(len(results_lex), 1)
        self.assertEqual(results_lex[0]["id"], nid_ollama)

        # Semantic search via ChromaDB vector
        results_sem = SemanticMemory.recall("hardware graphics card execution profiles", limit=2)
        self.assertEqual(len(results_sem), 1)
        self.assertEqual(results_sem[0]["id"], nid_gpu)

    def test_scalability_smoke(self):
        # Verify sub-millisecond retrieval scaling on a batch insertion using mocked embeddings
        dummy_embedding = [0.1] * 384
        def mock_emb_fn(texts):
            return [dummy_embedding for _ in texts]

        with patch("chromadb.utils.embedding_functions.DefaultEmbeddingFunction.__call__", side_effect=mock_emb_fn):
            start = time.time()
            
            # Perform 50 insertions of facts and relationships
            node_ids = []
            for i in range(50):
                nid = SemanticMemory.upsert_node(
                    concept=f"Knowledge Piece {i}",
                    description=f"This is the description of the factual piece of knowledge number {i}.",
                    source_episode_id=f"ep-scale-{i}",
                    similarity_threshold=0.2
                )
                node_ids.append(nid)
                
                # Create a simple chain relation
                if i > 0:
                    SemanticMemory.create_edge(node_ids[i-1], node_ids[i], "leads_to", 0.6)
                    
            SemanticMemory.flush_embeddings()
            
            # Warm up
            SemanticMemory.recall("warmup", limit=1)

            # Measure retrieval performance
            q_start = time.time()
            results = SemanticMemory.recall("factual piece of knowledge number 25", limit=5)
            q_end = time.time()
            
            duration = q_end - q_start
            print(f"\n[TIMING] Mocked recall took: {duration:.6f}s")
            self.assertLess(duration, 0.5) # Retrieval should be fast (typically < 10ms with mocked embeddings)
            self.assertGreater(len(results), 0)
