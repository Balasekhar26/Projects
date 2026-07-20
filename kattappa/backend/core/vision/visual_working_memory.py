from backend.core.vision.ui_element import UIElement

class VisualWorkingMemory:
    def __init__(self, max_snapshots: int = 5):
        self.max_snapshots = max_snapshots
        self.snapshots = [] # list of dicts: {"filepath": str, "elements": list[UIElement]}
        self.active_window = ""

    def add_snapshot(self, filepath: str, elements: list[UIElement]) -> None:
        """Appends a new screenshot and its UI elements to working memory, trimming old snapshots."""
        self.snapshots.append({
            "filepath": filepath,
            "elements": elements
        })
        if len(self.snapshots) > self.max_snapshots:
            self.snapshots.pop(0)

    def get_latest_elements(self) -> list[UIElement]:
        """Returns the most recently indexed screen elements."""
        if not self.snapshots:
            return []
        return self.snapshots[-1]["elements"]

    def find_element_by_text(self, text_query: str) -> UIElement | None:
        """Searches working memory snapshots for elements containing text_query."""
        query_clean = text_query.lower().strip()
        # Search backwards starting from the most recent snapshot
        for snap in reversed(self.snapshots):
            for elem in snap["elements"]:
                if query_clean in elem.text.lower():
                    return elem
        return None

    def clear(self) -> None:
        """Flushes visual working memory snapshot queues."""
        self.snapshots.clear()
        self.active_window = ""
