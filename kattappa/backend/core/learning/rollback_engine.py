"""Rollback Engine (Program 29.0).

Saves, indexes, and restores configuration states or model versions
to enable automatic recovery from failed experimental updates.
"""
from __future__ import annotations

import copy
import uuid
from typing import Any, Dict


class RollbackEngine:
    """Manages snapshots of active system configuration parameters for rollback safety."""

    def __init__(self) -> None:
        self.backups: Dict[str, Dict[str, Any]] = {}

    def backup_state(self, config_object: Any) -> str:
        """Saves a deep copy of config parameters. Returns unique state ID."""
        state_id = f"state_{uuid.uuid4()}"
        
        # Support dataclasses, standard dictionaries, or objects with dict attributes
        if hasattr(config_object, "to_dict"):
            state_data = copy.deepcopy(config_object.to_dict())
        elif hasattr(config_object, "__dict__"):
            state_data = copy.deepcopy(config_object.__dict__)
        elif isinstance(config_object, dict):
            state_data = copy.deepcopy(config_object)
        else:
            raise TypeError(
                f"Unsupported configuration backing object type: {type(config_object)}"
            )

        self.backups[state_id] = state_data
        return state_id

    def restore_state(self, config_object: Any, state_id: str) -> None:
        """Restores config object state to the saved snapshot parameters."""
        if state_id not in self.backups:
            raise KeyError(f"State backup ID not found: {state_id}")

        backup_data = self.backups[state_id]

        if isinstance(config_object, dict):
            config_object.clear()
            config_object.update(backup_data)
        elif hasattr(config_object, "__dict__"):
            # Update attributes
            for k, v in backup_data.items():
                setattr(config_object, k, copy.deepcopy(v))
        else:
            raise TypeError(
                f"Unsupported restoration target object type: {type(config_object)}"
            )

    def clean_backup(self, state_id: str) -> None:
        """Deletes a backup snapshot when an experiment completes successfully."""
        self.backups.pop(state_id, None)
