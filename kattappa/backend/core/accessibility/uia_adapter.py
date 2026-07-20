class UIAAdapter:
    def __init__(self):
        pass

    def get_root_elements(self) -> list[dict]:
        """Queries native Windows UI Automation control nodes hierarchy (Mocked for testing/headless)."""
        return [
            {
                "automation_id": "save_btn",
                "name": "Save Changes",
                "role": "button",
                "application": "Notepad",
                "window_id": "win_note",
                "pixel_bbox": (800, 600, 950, 640),
                "monitor_id": 1
            },
            {
                "automation_id": "input_text",
                "name": "Edit Document",
                "role": "document",
                "application": "Notepad",
                "window_id": "win_note",
                "pixel_bbox": (100, 100, 1000, 500),
                "monitor_id": 1
            }
        ]
