from backend.core.vision.ui_element import UIElement

class AttentionEngine:
    def __init__(self):
        self.focused_window_id = ""
        self.active_dialog_id = ""

    def set_focus(self, window_id: str, dialog_id: str = "") -> None:
        """Sets active window focus values to throttle object updates."""
        self.focused_window_id = window_id
        self.active_dialog_id = dialog_id

    def filter_elements(self, elements: list[UIElement]) -> list[UIElement]:
        """Filters out background window elements if a dialog or active frame focus is set."""
        filtered = []
        for elem in elements:
            # 1. If active dialog exists, discard everything outside of it
            if self.active_dialog_id:
                if elem.window_id == self.active_dialog_id:
                    filtered.append(elem)
            # 2. If focused window exists, discard background window objects
            elif self.focused_window_id:
                if elem.window_id == self.focused_window_id:
                    filtered.append(elem)
            # 3. Fallback: keep all elements if no focus is set
            else:
                filtered.append(elem)
        return filtered
