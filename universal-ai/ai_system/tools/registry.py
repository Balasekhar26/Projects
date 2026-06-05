from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from ai_system.core.config import Settings
from ai_system.memory.store import MemoryStore
from ai_system.tools.browser import BrowserTool
from ai_system.tools.shell import ShellTool
from ai_system.vision.screen import ScreenVision


ToolFn = Callable[[str], str]


@dataclass
class ToolRegistry:
    settings: Settings
    memory: MemoryStore

    def __post_init__(self) -> None:
        self.browser = BrowserTool(self.settings)
        self.screen = ScreenVision(self.settings)
        self.shell = ShellTool(self.settings)

    def names(self) -> list[str]:
        return ["remember", "recall", "browse", "screen_ocr", "shell"]

    def run(self, name: str, argument: str) -> str:
        if name == "remember":
            memory_id = self.memory.remember(argument, kind="agent_note", source="agent")
            return f"Stored memory {memory_id}"
        if name == "recall":
            return "\n".join(self.memory.recall(argument, limit=5)) or "No matching memory."
        if name == "browse":
            return self.browser.read_page(argument)
        if name == "screen_ocr":
            return self.screen.ocr_latest_screen()
        if name == "shell":
            return self.shell.run(argument)
        return f"Unknown tool: {name}"
