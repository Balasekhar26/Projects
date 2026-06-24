"""Node Selector (Step 9.3).

Routes tasks to the best active node based on capability matching and resource load.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from backend.core.node_manager import NodeManager


class NodeSelector:
    """Routes tasks to the most suitable worker node."""

    # Map of action names to standardized capabilities required
    ACTION_TO_CAPABILITY_MAP = {
        "web_search": "WEB_SEARCH",
        "fetch_url": "WEB_SEARCH",
        "run_terminal_command": "TERMINAL",
        "execute_code": "TERMINAL",
        "read_screen_snapshot": "VISION",
        "ocr_image": "VISION",
        "transcribe_audio": "SPEECH",
        "text_to_speech": "SPEECH",
        "train_model": "GPU_TRAINING",
    }

    @classmethod
    def select_node(
        cls, action: str, required_capabilities: Optional[List[str]] = None
    ) -> Optional[Dict[str, Any]]:
        """Select the best active node for a given action.

        Returns the node dictionary from DB, or None if the action should be executed locally.
        """
        # Determine the required capabilities
        reqs = list(required_capabilities) if required_capabilities else []
        action_lower = action.lower()
        if action_lower in cls.ACTION_TO_CAPABILITY_MAP:
            reqs.append(cls.ACTION_TO_CAPABILITY_MAP[action_lower])
        reqs.append(action)  # Also allow direct match of the action name

        active_nodes = NodeManager.get_active_nodes()
        if not active_nodes:
            return None  # Fallback to local Core

        candidates = []
        for node in active_nodes:
            # Local Core matches everything if it's in the node list, but let's assume
            # we filter worker nodes here.
            node_caps = [c.upper() for c in node["capabilities"]]
            
            # A node matches if:
            # 1. It supports "ALL"
            # 2. Or it supports any of the required capabilities (case-insensitive match)
            is_match = "ALL" in node_caps
            if not is_match:
                for req in reqs:
                    if req.upper() in node_caps or req.lower() in [c.lower() for c in node["capabilities"]]:
                        is_match = True
                        break

            if is_match:
                candidates.append(node)

        if not candidates:
            return None  # No matching remote node -> fallback to local Core

        # Select candidate with the lowest resource utilization score
        # Utilization score = CPU % + RAM % + (Active Tasks * 10)
        def get_utilization(n: Dict[str, Any]) -> float:
            cpu = float(n.get("system_cpu_pct", 0.0))
            ram = float(n.get("system_ram_pct", 0.0))
            tasks = int(n.get("active_tasks", 0))
            return cpu + ram + (tasks * 10.0)

        best_node = min(candidates, key=get_utilization)
        return best_node
