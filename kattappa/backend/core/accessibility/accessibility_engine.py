from backend.core.accessibility.uia_adapter import UIAAdapter
from backend.core.accessibility.element_mapper import ElementMapper
from backend.core.vision.ui_element import UIElement

class AccessibilityEngine:
    def __init__(self):
        self.adapter = UIAAdapter()

    def get_visible_elements(self) -> list[UIElement]:
        """Scans the active system UI Automation tree and returns mapped UIElement objects."""
        nodes = self.adapter.get_root_elements()
        return [ElementMapper.map_uia_node_to_element(node) for node in nodes]

    def query_element_by_name(self, name_query: str) -> UIElement | None:
        """Finds elements in the active accessibility tree matching name_query."""
        elements = self.get_visible_elements()
        query_clean = name_query.lower().strip()
        for elem in elements:
            if query_clean in elem.text.lower():
                return elem
        return None
