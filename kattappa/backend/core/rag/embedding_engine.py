import hashlib
import logging
import os
import sys


logger = logging.getLogger(__name__)


class EmbeddingEngine:
    _model = None
    _provider_mode = "uninitialized"
    _last_error: str | None = None

    @staticmethod
    def _deterministic_embedding(text: str) -> list[float]:
        vector = []
        for i in range(384):
            val = int(hashlib.md5(f"{text}_{i}".encode()).hexdigest(), 16) % 1000
            vector.append((val / 500.0) - 1.0)
        return vector

    @classmethod
    def get_embedding(cls, text: str) -> list[float]:
        """Generates a 384-dimensional vector embedding for the input text."""
        use_mock = (
            "pytest" in sys.modules or
            os.getenv("KATTAPPA_TEST_MODE") == "true" or
            os.getenv("KATTAPPA_MOCK_RAG") == "true"
        )
        if use_mock:
            cls._provider_mode = "deterministic_test"
            cls._last_error = None
            return cls._deterministic_embedding(text)

        # Production real embedding generation using sentence-transformers
        try:
            if cls._model is None:
                from sentence_transformers import SentenceTransformer
                cls._model = SentenceTransformer("BAAI/bge-small-en-v1.5")
            embedding = cls._model.encode(text)
            cls._provider_mode = "bge-small-en-v1.5"
            cls._last_error = None
            return embedding.tolist()
        except Exception as exc:
            cls._provider_mode = "deterministic_fallback"
            cls._last_error = f"{type(exc).__name__}: {exc}"
            logger.warning(
                "Kattappa embedding model unavailable; using deterministic fallback: %s",
                cls._last_error,
            )
            return cls._deterministic_embedding(text)

    @classmethod
    def status(cls) -> dict[str, str | bool | None]:
        """Return the active provider without loading model weights."""

        return {
            "available": cls._provider_mode not in {
                "uninitialized",
                "deterministic_fallback",
            },
            "mode": cls._provider_mode,
            "reason": cls._last_error,
        }
