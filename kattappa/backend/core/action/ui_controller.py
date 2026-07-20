class UIController:
    def __init__(self):
        self.mouse_x = 0
        self.mouse_y = 0
        self.active_window = "Desktop"

    def move_to(self, x: int, y: int) -> None:
        """Simulates moving the cursor to coordinate x, y."""
        self.mouse_x = x
        self.mouse_y = y

    def click(self) -> None:
        """Simulates a left-click at current cursor coordinates."""
        pass

    def type_text(self, text: str) -> None:
        """Simulates typing characters."""
        pass

    def activate_window(self, window_title: str) -> None:
        """Simulates switching focused window focus."""
        self.active_window = window_title
