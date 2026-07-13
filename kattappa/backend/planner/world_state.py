from __future__ import annotations
import hashlib
import json
from typing import Any, Dict, List, Optional

class WorldState:
    """Represents a hybrid (symbolic + vector) world state representation for HTN planning."""

    def __init__(self, variables: Optional[Dict[str, Any]] = None, vector_hashes: Optional[Dict[str, str]] = None) -> None:
        self.variables = dict(variables or {})
        self.vector_hashes = dict(vector_hashes or {})

    def update(self, updates: Dict[str, Any]) -> None:
        """Updates symbolic state variables."""
        self.variables.update(updates)

    def set_vector_hash(self, key: str, value_hash: str) -> None:
        """Associates a semantic vector reference hash with a key."""
        self.vector_hashes[key] = value_hash

    def get_sha256(self) -> str:
        """Generates a cryptographic SHA-256 hash of the complete world state dictionary."""
        state_repr = {
            "variables": {k: self.variables[k] for k in sorted(self.variables.keys())},
            "vector_hashes": {k: self.vector_hashes[k] for k in sorted(self.vector_hashes.keys())}
        }
        serialized = json.dumps(state_repr, sort_keys=True)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    def clone(self) -> WorldState:
        """Returns a cloned copy of the current state instance."""
        return WorldState(
            variables=dict(self.variables),
            vector_hashes=dict(self.vector_hashes)
        )
