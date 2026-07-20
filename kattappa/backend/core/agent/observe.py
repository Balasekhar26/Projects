from backend.core.accessibility.accessibility_engine import AccessibilityEngine
from backend.core.vision.visual_working_memory import VisualWorkingMemory

class Observer:
    def __init__(self):
        self.accessibility = AccessibilityEngine()
        self.visual_memory = VisualWorkingMemory()

    def capture_world_state(self) -> dict:
        """Sweeps system accessibility trees and visual workspace caches to assemble active situational context."""
        # 1. Pull native controls from accessibility tree
        ui_elements = self.accessibility.get_visible_elements()
        
        # 2. Sync to visual working memory
        if ui_elements:
            self.visual_memory.add_snapshot("path/to/screenshot.png", ui_elements)
            
        latest_elements = self.visual_memory.get_latest_elements()
        
        return {
            "focused_application": "Notepad" if latest_elements else "Unknown",
            "active_elements_count": len(latest_elements),
            "elements": [e.to_dict() for e in latest_elements]
        }
