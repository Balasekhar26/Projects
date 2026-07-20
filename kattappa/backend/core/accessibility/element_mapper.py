from datetime import datetime
from backend.core.vision.ui_element import UIElement

class ElementMapper:
    @classmethod
    def map_uia_node_to_element(cls, node: dict, screen_res: tuple[int, int] = (1920, 1080)) -> UIElement:
        """Converts an accessibility tree node dictionary into a validated UIElement instance."""
        x1, y1, x2, y2 = node["pixel_bbox"]
        
        # Calculate normalized bounds (0.0 to 1.0)
        x_norm = x1 / screen_res[0]
        y_norm = y1 / screen_res[1]
        width_norm = (x2 - x1) / screen_res[0]
        height_norm = (y2 - y1) / screen_res[1]
        
        return UIElement(
            element_id=node["automation_id"],
            text=node["name"],
            element_type=node["role"],
            confidence=1.0, # accessibility tree has absolute trust
            monitor_id=node.get("monitor_id", 1),
            role=node["role"],
            window_id=node.get("window_id", ""),
            application=node.get("application", ""),
            normalized_bbox=(x_norm, y_norm, x_norm + width_norm, y_norm + height_norm),
            pixel_bbox=node["pixel_bbox"],
            first_seen=datetime.now(),
            last_seen=datetime.now(),
            observation_count=1
        )
