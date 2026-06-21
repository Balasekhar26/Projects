from __future__ import annotations

import threading
import time
import uuid
from typing import Any, Dict, List, Optional


class SensoryMemory:
    """Sensory Memory Subsystem (Layer 1).
    
    Provides a transient, fast-decaying RAM cache buffering incoming environmental signals,
    user/assistant turns, and tool outputs before they are pushed to Working Memory.
    Non-persistent (in-memory only).
    """

    _lock = threading.Lock()
    _buffers: Dict[str, List[Dict[str, Any]]] = {
        "USER_TURN": [],
        "ASSISTANT_TURN": [],
        "TOOL_OBSERVATION": [],
        "ENVIRONMENT_SIGNAL": [],
        "EVENT_NOTIFICATION": []
    }

    @classmethod
    def add_observation(
        cls,
        obs_type: str,
        content: Any,
        ttl_seconds: int = 300,
        max_capacity: int = 10
    ) -> str:
        """Buffers a new sensory observation under a thread lock, enforcing capacity constraints."""
        obs_type_upper = obs_type.strip().upper()
        if obs_type_upper not in cls._buffers:
            raise ValueError(f"Invalid observation type: {obs_type}. Must be one of {list(cls._buffers.keys())}")

        obs_id = str(uuid.uuid4())
        now = time.time()
        expires_at = now + ttl_seconds

        observation = {
            "id": obs_id,
            "type": obs_type_upper,
            "content": content,
            "timestamp": now,
            "expires_at": expires_at
        }

        with cls._lock:
            buffer_list = cls._buffers[obs_type_upper]
            buffer_list.append(observation)
            
            # Keep only the last `max_capacity` elements (Eviction FIFO policy)
            if len(buffer_list) > max_capacity:
                buffer_list.pop(0)

        return obs_id

    @classmethod
    def get_recent_observations(
        cls,
        obs_type: Optional[str] = None,
        limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """Retrieves active, unexpired observations, optionally filtered by type and limit."""
        now = time.time()
        results: List[Dict[str, Any]] = []

        with cls._lock:
            if obs_type:
                obs_type_upper = obs_type.strip().upper()
                if obs_type_upper in cls._buffers:
                    # Filter out expired items
                    results = [item for item in cls._buffers[obs_type_upper] if item["expires_at"] > now]
            else:
                for buffer_list in cls._buffers.values():
                    results.extend([item for item in buffer_list if item["expires_at"] > now])

        # Sort chronologically by timestamp
        results.sort(key=lambda x: x["timestamp"])

        if limit is not None:
            results = results[-limit:]

        return results

    @classmethod
    def run_cleanup_sweep(cls) -> int:
        """Removes expired sensory observations from all RAM queues, returning count of pruned items."""
        now = time.time()
        pruned_count = 0

        with cls._lock:
            for obs_type, buffer_list in cls._buffers.items():
                initial_len = len(buffer_list)
                # Retain only unexpired elements
                cls._buffers[obs_type] = [item for item in buffer_list if item["expires_at"] > now]
                pruned_count += (initial_len - len(cls._buffers[obs_type]))

        return pruned_count

    @classmethod
    def get_sensory_context(cls) -> Dict[str, Any]:
        """Compiles recent active unexpired sensory signals into a dictionary for task planner contexts."""
        now = time.time()
        context_data: Dict[str, List[Dict[str, Any]]] = {}

        with cls._lock:
            for obs_type, buffer_list in cls._buffers.items():
                # Filter active unexpired signals
                active_signals = [
                    {
                        "id": item["id"],
                        "content": item["content"],
                        "timestamp": item["timestamp"]
                    }
                    for item in buffer_list if item["expires_at"] > now
                ]
                context_data[obs_type.lower()] = active_signals

        return context_data

    @classmethod
    def clear_all(cls) -> None:
        """Resets all sensory buffers. Used for testing and resets."""
        with cls._lock:
            for obs_type in cls._buffers:
                cls._buffers[obs_type] = []
