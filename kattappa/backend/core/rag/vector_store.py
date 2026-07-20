import numpy as np
import os
import sys

class VectorStore:
    def __init__(self):
        self.embeddings = {}

    def add_embeddings(self, chunk_id: str, embedding: list[float]) -> None:
        self.embeddings[chunk_id] = np.array(embedding, dtype=np.float32)

    def clear(self) -> None:
        self.embeddings.clear()

    def search(self, query_embedding: list[float], top_k: int = 10) -> list[tuple[str, float]]:
        """Performs cosine similarity search using numpy vector matrices."""
        q_vec = np.array(query_embedding, dtype=np.float32)
        q_norm = np.linalg.norm(q_vec)
        
        scores = []
        for chunk_id, vec in self.embeddings.items():
            vec_norm = np.linalg.norm(vec)
            if q_norm > 0 and vec_norm > 0:
                dot_product = np.dot(q_vec, vec)
                sim = dot_product / (q_norm * vec_norm)
                scores.append((chunk_id, float(sim)))
                
        # Sort desc by score
        scores.sort(key=lambda x: x[1], reverse=True)
        return scores[:top_k]
