class OCRExtractor:
    def __init__(self):
        pass

    def extract_text(self, image_data: bytes | None) -> list[dict]:
        """Extracts words and matching screen coordinates from raw image bytes."""
        if image_data is None:
            return []
            
        # Mock structural OCR outputs representing local PaddleOCR parses
        return [
            {
                "text": "Kattappa",
                "box": [100, 100, 180, 120] # x1, y1, x2, y2
            },
            {
                "text": "Submit",
                "box": [500, 600, 560, 620]
            }
        ]
