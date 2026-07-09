"""Self-Critique and Configuration Adaptation (Program 34.0).

Reads textual reflection reviews and suggests updates to executing configurations,
lifting deadlines, increasing retries, or blacklisting failing tools.
"""
from __future__ import annotations

from typing import Any, Dict, List


class SelfCritiqueLoop:
    """Translates reflection observations into runtime parameter modifications."""

    @classmethod
    def critique_and_adapt(
        cls,
        reflection_text: str,
        current_config: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Analyzes critique summaries and suggests modifications to the config copy."""
        adapted = dict(current_config)
        log_lower = reflection_text.lower()

        # 1. Handle timeouts: raise execution limits
        if "timeout" in log_lower or "exceeded deadline" in log_lower:
            old_timeout = adapted.get("timeout_seconds", 30)
            adapted["timeout_seconds"] = int(old_timeout * 1.5)
            # Annotate reason
            adapted["adaptation_reason"] = "Task timeout detected. Lifting deadline bounds."

        # 2. Handle crashes or permissions: raise retry bounds or blacklist tool
        elif "crashed" in log_lower or "error" in log_lower or "failed" in log_lower:
            old_retries = adapted.get("max_retries", 3)
            adapted["max_retries"] = old_retries + 2
            
            # Suggest blacklisting tool if a specific operator is blamed
            for term in reflection_text.split():
                if term.startswith("`op_") or term.startswith("`step_"):
                    tool_name = term.strip("`.")
                    blacklist = list(adapted.get("blacklisted_tools", []))
                    if tool_name not in blacklist:
                        blacklist.append(tool_name)
                    adapted["blacklisted_tools"] = blacklist
            
            adapted["adaptation_reason"] = "Operator execution error. Expanding retries limit."

        # 3. Handle success: keep or optimize budgets
        elif "success" in log_lower:
            # We can optionally slightly prune budget allocations
            adapted["adaptation_reason"] = "Stable success profile. Parameters preserved."

        return adapted
