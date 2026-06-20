import re
import ollama
from pathlib import Path
from typing import Tuple
from backend.core.config import load_config
from backend.core.obsidian_memory import ObsidianMemory

class VisionAgent:
    def __init__(self, model: str = None) -> None:
        config = load_config()
        self.ollama_host = config.ollama_host
        self.model = model or config.model_map.get("vision", "qwen3-vl:8b")
        self.memory = ObsidianMemory()
        self.system_prompt = (
            "You are a GUI grounding assistant. Your task is to locate visual elements on a screen screenshot "
            "based on the user's request. Return the exact coordinate of the element center as [x, y] "
            "where x and y are normalized coordinates between 0 and 1000 (0 is top-left, 1000 is bottom-right). "
            "Example: if the target is in the center of the screen, respond with: 'Target found at [500, 500]'."
        )

    def locate_element(self, screenshot_path: str, instruction: str) -> Tuple[float, float, str]:
        """
        Queries Ollama VLM with screenshot to find coordinates of target element.
        Returns (x_norm, y_norm, description) where coordinates are 0-1000 scale.
        """
        path = Path(screenshot_path).resolve()
        if not path.exists():
            raise FileNotFoundError(f"Screenshot file not found at: {path}")

        user_prompt = f"Locate the element: '{instruction}' on this screen."
        
        messages = [
            {"role": "system", "content": self.system_prompt},
            {
                "role": "user",
                "content": user_prompt,
                "images": [str(path)]
            }
        ]

        try:
            client = ollama.Client(host=self.ollama_host)
            response = client.chat(model=self.model, messages=messages)
            content = response["message"]["content"]
            
            # Log the grounding event in Obsidian
            self.memory.write_daily_note(
                content=f"VisionAgent grounding request for: '{instruction}' -> Response: {content}",
                category="vision-grounding"
            )
            
            coords = self._parse_coordinates(content)
            if coords:
                return coords[0], coords[1], content
            else:
                raise ValueError(f"Could not parse valid coordinates from vision response: {content}")
        except Exception as e:
            error_msg = f"VisionAgent failed query to VLM: {e}"
            self.memory.write_daily_note(content=error_msg, category="error")
            return 500.0, 500.0, f"Error: {e}"

    def _parse_coordinates(self, text: str) -> Tuple[float, float] | None:
        """Parses coordinates in VLM outputs on 0-1000 scale."""
        # 1. Look for [x, y] or (x, y)
        matches = re.findall(r'[\[\(]\s*(\d{1,4})\s*,\s*(\d{1,4})\s*[\]\)]', text)
        if matches:
            x, y = map(float, matches[0])
            if 0 <= x <= 1000 and 0 <= y <= 1000:
                return x, y

        # 2. Look for bounding box [ymin, xmin, ymax, xmax]
        bbox_matches = re.findall(r'\[\s*(\d{1,4})\s*,\s*(\d{1,4})\s*,\s*(\d{1,4})\s*,\s*(\d{1,4})\s*\]', text)
        if bbox_matches:
            ymin, xmin, ymax, xmax = map(float, bbox_matches[0])
            if all(0 <= val <= 1000 for val in (ymin, xmin, ymax, xmax)):
                return (xmin + xmax) / 2, (ymin + ymax) / 2

        return None
