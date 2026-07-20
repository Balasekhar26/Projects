from dataclasses import dataclass, field
from datetime import datetime

@dataclass
class UIElement:
    element_id: str
    text: str
    element_type: str  # button, input_field, window, label
    confidence: float
    monitor_id: int
    
    # Hierarchical fields
    role: str = ""
    subtype: str = ""
    window_id: str = ""
    application: str = ""
    
    # Bounding boxes: (x1, y1, x2, y2)
    normalized_bbox: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)
    pixel_bbox: tuple[int, int, int, int] = (0, 0, 0, 0)
    
    parent_id: str | None = None
    children_ids: list[str] = field(default_factory=list)
    
    # Temporal fields
    first_seen: datetime = field(default_factory=datetime.now)
    last_seen: datetime = field(default_factory=datetime.now)
    observation_count: int = 1
    
    embedding_id: str = ""
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "element_id": self.element_id,
            "text": self.text,
            "element_type": self.element_type,
            "confidence": self.confidence,
            "monitor_id": self.monitor_id,
            "role": self.role,
            "subtype": self.subtype,
            "window_id": self.window_id,
            "application": self.application,
            "normalized_bbox": self.normalized_bbox,
            "pixel_bbox": self.pixel_bbox,
            "parent_id": self.parent_id,
            "children_ids": self.children_ids,
            "first_seen": self.first_seen.isoformat(),
            "last_seen": self.last_seen.isoformat(),
            "observation_count": self.observation_count,
            "embedding_id": self.embedding_id,
            "metadata": self.metadata
        }
