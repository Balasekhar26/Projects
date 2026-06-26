import time
from typing import Dict, Any, List

from kattappa_runtime.memory.episodic_memory import EpisodicMemory
from kattappa_runtime.memory.semantic_memory import SemanticMemory

class MemoryConsolidator:
    def __init__(self, episodic: EpisodicMemory, semantic: SemanticMemory):
        self.episodic = episodic
        self.semantic = semantic

    def consolidate(self) -> Dict[str, Any]:
        """Scans episodic histories to consolidate multiple project tasks into a single high-level summary fact."""
        episodes = self.episodic.get_all()
        if len(episodes) < 3:
            return {"consolidated": False, "message": "Insufficient episodes to run consolidation."}

        # Look for events related to building or completing phases (e.g., "KM-1", "KM-2", "KM-3", "KM-4", "KM-5")
        phases_completed = []
        for ep in episodes:
            event_text = ep["event"].lower()
            if "completed km-" in event_text or "working on km-" in event_text:
                # Extract phase label
                import re
                match = re.search(r"(km-\d+(\.\d+)?)", event_text)
                if match:
                    phase = match.group(1).upper()
                    if phase not in phases_completed:
                        phases_completed.append(phase)

        if len(phases_completed) >= 2:
            summary_fact = f"User completed development of multiple Kattappa milestones: {', '.join(sorted(phases_completed))}."
            
            # Store summary fact in semantic memory
            self.semantic.store_fact("User Profile", "completed_milestones", summary_fact, confidence=0.98)
            
            # Clean up the redundant episodic items to prevent database growth
            # We filter out raw episodic events that were consolidated to save memory footprint
            initial_count = len(self.episodic.episodes)
            self.episodic.episodes = [ep for ep in self.episodic.episodes if not ("completed km-" in ep["event"].lower() or "working on km-" in ep["event"].lower())]
            self.episodic.save_all()
            
            # Add one high level episode to record that consolidation happened
            self.episodic.add_episode(f"Consolidated completed milestones {phases_completed} into semantic memory.", importance=0.8)
            
            return {
                "consolidated": True,
                "phases_consolidated": phases_completed,
                "summary": summary_fact,
                "cleanup_count": initial_count - len(self.episodic.episodes)
            }

        return {"consolidated": False, "message": "No consolidatable patterns identified in episodic timeline."}
