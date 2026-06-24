import os
import shutil
import tempfile
import pytest

# Globally mock DefaultEmbeddingFunction to prevent HuggingFace model download attempts in tests
try:
    import chromadb.utils.embedding_functions as ef
    import hashlib

    def mock_init(self, *args, **kwargs):
        pass

    def mock_call(self, input):
        embeddings = []
        # Define semantic family mappings for test queries and documents
        families = {
            "tauri": 1,
            "rust": 2,
            "cargo": 3,
            "crates": 4,
            "remote": 5,
            "ollama": 6,
            "gpu": 7,
            "hardware": 7,
            "graphics": 7,
            "cuda": 7,
            "rocm": 7,
            "python": 8,
            "gc": 9,
            "sync": 10,
            "aether": 11,
            "scale": 12,
            "safety": 13,
            "database": 14,
            "db": 14,
            "lockup": 14,
            "locks": 14,
            "serialization": 14,
            "consistency": 15,
            "sweeps": 15,
            "aurora": 16,
            "git": 17,
        }
        for text in input:
            text_lower = text.lower()
            # If text is in format "concept: description", check only the concept for semantic families
            if ":" in text_lower:
                part_to_check = text_lower.split(":", 1)[0]
            else:
                part_to_check = text_lower

            matched_family = None
            for key, val in families.items():
                if key in part_to_check:
                    matched_family = val
                    break
            
            if matched_family is not None:
                # Deterministic family vector
                vector = []
                for i in range(384):
                    val = ((matched_family * 31 + i) % 256) / 128.0 - 1.0
                    vector.append(val)
                embeddings.append(vector)
            else:
                # Fallback to hash-based deterministic vector
                h = hashlib.md5(text.encode("utf-8")).digest()
                vector = []
                for i in range(384):
                    byte_val = h[i % len(h)]
                    val = ((byte_val ^ i) % 256) / 128.0 - 1.0
                    vector.append(val)
                embeddings.append(vector)
        return embeddings

    ef.DefaultEmbeddingFunction.__init__ = mock_init
    ef.DefaultEmbeddingFunction.__call__ = mock_call
except ImportError:
    pass

# Create a temporary directory for the test run
tempfile.tempdir = "/tmp"
test_data_dir = tempfile.mkdtemp(prefix="kattappa_test_")
os.environ["KATTAPPA_DATA_DIR"] = test_data_dir

@pytest.fixture(scope="session", autouse=True)
def cleanup_test_data():
    yield
    # Cleanup temp directory after test session finishes
    shutil.rmtree(test_data_dir, ignore_errors=True)


@pytest.fixture(autouse=True)
def reset_all_schemas():
    """Dynamically reset _schema_ensured flags in backend.core classes for full test isolation."""
    import sys
    for name, module in list(sys.modules.items()):
        if name.startswith("backend.core"):
            for attr_name in dir(module):
                try:
                    obj = getattr(module, attr_name)
                    if isinstance(obj, type) and hasattr(obj, "_schema_ensured"):
                        setattr(obj, "_schema_ensured", False)
                except Exception:
                    pass
