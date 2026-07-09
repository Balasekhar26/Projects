"""Trace Visualizer (Program 28.0).

Constructs structured hierarchical text-based visual trees from raw Span lists,
displaying nested executions, execution statuses, and elapsed run durations.
"""
from __future__ import annotations

from typing import Dict, List, Optional
from backend.core.observability.telemetry import Span


class TraceVisualizer:
    """Formats list of spans into clean, indented hierarchic visual structures."""

    @classmethod
    def format_tree(cls, spans: List[Span]) -> str:
        """Assembles list of spans into a formatted tree diagram string."""
        if not spans:
            return "[No traces recorded]"

        # Index spans by parent_span_id to quickly traverse links
        children_map: Dict[Optional[str], List[Span]] = {}
        for s in spans:
            children_map.setdefault(s.parent_span_id, []).append(s)

        # Sort sibling spans by starting time to preserve temporal order
        for parent_id in children_map:
            children_map[parent_id].sort(key=lambda x: x.start_time)

        # Find roots: spans whose parent is None or not present in spans
        all_ids = {s.span_id for s in spans}
        roots = [s for s in spans if s.parent_span_id is None or s.parent_span_id not in all_ids]
        roots.sort(key=lambda x: x.start_time)

        lines: List[str] = []

        def _traverse(span: Span, depth: int, is_last: bool, prefix: str) -> None:
            # Generate clean node prefixes (Unicode tree branch elements)
            if depth == 0:
                connector = ""
                new_prefix = ""
            else:
                connector = "└── " if is_last else "├── "
                new_prefix = prefix + ("    " if is_last else "│   ")

            status_indicator = "✓" if span.status == "success" else "✗"
            dur_ms = span.duration * 1000.0
            line = f"{prefix}{connector}[{status_indicator}] {span.name} ({dur_ms:.2f}ms)"

            # Append metadata highlights if present
            meta_highlights = []
            for k in ("tool", "exception_type", "action", "budget_status"):
                if k in span.metadata:
                    meta_highlights.append(f"{k}={span.metadata[k]}")
            if meta_highlights:
                line += " {" + ", ".join(meta_highlights) + "}"

            lines.append(line)

            # Traverse child spans recursively
            children = children_map.get(span.span_id, [])
            for idx, child in enumerate(children):
                _traverse(
                    child,
                    depth + 1,
                    idx == len(children) - 1,
                    new_prefix,
                )

        for i, root in enumerate(roots):
            _traverse(root, depth=0, is_last=i == len(roots) - 1, prefix="")

        return "\n".join(lines)

    @classmethod
    def print_tree(cls, spans: List[Span]) -> None:
        """Prints the formatted execution tree directly to stdout."""
        print(cls.format_tree(spans))
