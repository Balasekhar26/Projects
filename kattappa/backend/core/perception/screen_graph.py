"""Screen Graph (Program 18.0).

Groups raw OCR text fragments into hierarchical lines, containers, and relationships.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class ScreenGraph:
    """Structures raw word boundaries into visual layout trees representing elements."""

    def __init__(self, raw_regions: List[Dict[str, Any]]) -> None:
        self.raw_regions = raw_regions
        self.text_nodes: List[Dict[str, Any]] = []
        self.containers: List[Dict[str, Any]] = []
        
        # Build logical grouped regions
        self._build_layout_graph()

    def _build_layout_graph(self) -> None:
        """Groups individual words in horizontal spatial proximity into logical lines/elements."""
        if not self.raw_regions:
            return

        # Sort top-to-bottom, then left-to-right
        sorted_regions = sorted(self.raw_regions, key=lambda r: (r["y"], r["x"]))
        
        grouped_lines: List[List[Dict[str, Any]]] = []
        
        for word in sorted_regions:
            added = False
            # Check if this word belongs to any existing line group
            for line in grouped_lines:
                # Same row approximation: center offset y difference is small
                avg_y = sum(item["y"] for item in line) / len(line)
                avg_h = sum(item["h"] for item in line) / len(line)
                
                # Height threshold check
                if abs(word["y"] - avg_y) < (avg_h * 0.7):
                    # Sort line by left coordinate
                    line.append(word)
                    line.sort(key=lambda item: item["x"])
                    added = True
                    break
            if not added:
                grouped_lines.append([word])

        # Cluster words in lines that are horizontally adjacent
        for idx, line in enumerate(grouped_lines):
            line_nodes: List[Dict[str, Any]] = []
            current_group: List[Dict[str, Any]] = []

            for word in line:
                if not current_group:
                    current_group.append(word)
                else:
                    # check horizontal distance between word end and next word start
                    prev_word = current_group[-1]
                    prev_end = prev_word["x"] + prev_word["w"]
                    distance = word["x"] - prev_end
                    
                    # If distance is within 2 average word spaces, join them
                    avg_char_w = prev_word["w"] / max(1, len(prev_word["text"]))
                    if distance < (avg_char_w * 4.0):
                        current_group.append(word)
                    else:
                        line_nodes.append(self._merge_nodes(current_group, f"elem_{idx}_{len(line_nodes)}"))
                        current_group = [word]

            if current_group:
                line_nodes.append(self._merge_nodes(current_group, f"elem_{idx}_{len(line_nodes)}"))

            self.text_nodes.extend(line_nodes)

        # Generate container structures based on overlapping columns or grid layouts
        self._generate_containers()

    def _merge_nodes(self, group: List[Dict[str, Any]], elem_id: str) -> Dict[str, Any]:
        """Combines multiple adjacent words into a single structural node."""
        text = " ".join(item["text"] for item in group)
        min_x = min(item["x"] for item in group)
        min_y = min(item["y"] for item in group)
        max_x = max(item["x"] + item["w"] for item in group)
        max_y = max(item["y"] + item["h"] for item in group)
        
        avg_conf = sum(item["confidence"] for item in group) / len(group)

        return {
            "id": elem_id,
            "text": text,
            "x": min_x,
            "y": min_y,
            "w": max_x - min_x,
            "h": max_y - min_y,
            "confidence": avg_conf,
            "words_count": len(group)
        }

    def _generate_containers(self) -> None:
        """Groups elements into vertical container channels (like columns/grids)."""
        # Simple column container heuristics for structured navigation
        columns: Dict[int, List[Dict[str, Any]]] = {}
        for node in self.text_nodes:
            # Map starting x coordinate rounded to nearest 50px
            col_key = (node["x"] // 50) * 50
            if col_key not in columns:
                columns[col_key] = []
            columns[col_key].append(node)

        for col_x, nodes in columns.items():
            min_y = min(n["y"] for n in nodes)
            max_y = max(n["y"] + n["h"] for n in nodes)
            max_w = max(n["w"] for n in nodes)
            
            self.containers.append({
                "container_id": f"col_{col_x}",
                "x": col_x,
                "y": min_y,
                "w": max_w,
                "h": max_y - min_y,
                "elements": [n["id"] for n in nodes]
            })

    def to_dict(self) -> Dict[str, Any]:
        return {
            "text_nodes": self.text_nodes,
            "containers": self.containers,
        }
