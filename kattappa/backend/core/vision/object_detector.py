class ObjectDetector:
    def __init__(self, model_size: str = "yolov8n"):
        self.model_size = model_size

    def detect_objects(self, image_data: bytes | None) -> list[dict]:
        """Runs local object classification on raw image bytes, returning label bounding boxes."""
        if image_data is None:
            return []
            
        # Mock detections mimicking local YOLOv8n predictions on screen snapshots
        return [
            {
                "label": "button",
                "confidence": 0.95,
                "box": [120, 200, 180, 230] # x1, y1, x2, y2
            },
            {
                "label": "input_field",
                "confidence": 0.91,
                "box": [300, 450, 500, 490]
            }
        ]
