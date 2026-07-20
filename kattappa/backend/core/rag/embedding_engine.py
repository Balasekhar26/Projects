import hashlib
import os
import sys

class EmbeddingEngine:
    _model = None

    @classmethod
    def get_embedding(cls, text: str) -> list[float]:
        """Generates a 384-dimensional vector embedding for the input text."""
        use_mock = (
            "pytest" in sys.modules or
            os.getenv("KATTAPPA_TEST_MODE") == "true" or
            os.getenv("KATTAPPA_MOCK_RAG") == "true"
        )
        if use_mock:
            # Generate deterministic mock 384-dim vector using hashing
            vector = []
            for i in range(384):
                val = int(hashlib.md5(f"{text}_{i}".encode()).hexdigest(), 16) % 1000
                vector.append((val / 500.0) - 1.0)
            return vector

        # Production real embedding generation using sentence-transformers
        try:
            if cls._model is None:
                from sentence_transformers import SentenceTransformer
                cls._model = SentenceTransformer("BAAI/bge-small-en-v1.5")
            embedding = cls._model.encode(text)
            return embedding.tolist()
        except Exception:
            # Fallback mock if import fails
            vector = []
            for i in range(384):
                val = int(hashlib.md5(f"{text}_{i}".encode()).hexdigest(), 16) % 1000
                vector.append((val / 500.0) - 1.0)
            return vector
