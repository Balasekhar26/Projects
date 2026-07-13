import gzip
import pickle
from typing import Any, Dict, List, Optional

class CheckpointStore:
    """Handles serialization and deserialization of planner states into compressed binary snapshots."""

    @staticmethod
    def serialize_state(state: Dict[str, Any]) -> bytes:
        """Serializes a state dictionary into a gzip-compressed pickle stream."""
        serialized = pickle.dumps(state)
        return gzip.compress(serialized)

    @staticmethod
    def deserialize_state(checkpoint: bytes) -> Dict[str, Any]:
        """Restores a state dictionary from a gzip-compressed pickle stream."""
        decompressed = gzip.decompress(checkpoint)
        return pickle.loads(decompressed)
