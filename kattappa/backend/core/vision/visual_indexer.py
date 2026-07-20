import json
from datetime import datetime
import numpy as np
from backend.core.memory.memory_store import MemoryStore

class VisualIndexer:
    def __init__(self):
        self._ensure_table()

    def _ensure_table(self) -> None:
        """Creates the visual snapshots index table if not exists."""
        conn = MemoryStore._get_conn()
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS visual_snapshots (
                id TEXT PRIMARY KEY,
                filepath TEXT,
                embedding_json TEXT,
                created_at TEXT
            )
        """)
        conn.commit()

    def index_snapshot(self, snapshot_id: str, filepath: str, image_data: bytes) -> list[float]:
        """Generates mock CLIP embedding vectors and indexes the snapshot in SQLite."""
        # Mock 128-dimensional CLIP normalized feature vector
        np.random.seed(hash(snapshot_id) % 2**32)
        emb = np.random.randn(128)
        emb = (emb / np.linalg.norm(emb)).tolist()
        
        conn = MemoryStore._get_conn()
        now = datetime.now().isoformat()
        with MemoryStore._lock:
            conn.execute("""
                INSERT OR REPLACE INTO visual_snapshots (id, filepath, embedding_json, created_at)
                VALUES (?, ?, ?, ?)
            """, (snapshot_id, filepath, json.dumps(emb), now))
            conn.commit()
            
        return emb

    def search_snapshots(self, query_emb: list[float], top_k: int = 5) -> list[dict]:
        """Performs cosine similarity searches across registered CLIP screenshots."""
        conn = MemoryStore._get_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM visual_snapshots")
        rows = [dict(row) for row in cursor.fetchall()]
        
        results = []
        q_vec = np.array(query_emb)
        
        for r in rows:
            if not r["embedding_json"]:
                continue
            r_vec = np.array(json.loads(r["embedding_json"]))
            # Cosine similarity calculation
            score = float(np.dot(q_vec, r_vec))
            results.append({
                "id": r["id"],
                "filepath": r["filepath"],
                "score": score
            })
            
        # Sort by highest match score
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:top_k]
