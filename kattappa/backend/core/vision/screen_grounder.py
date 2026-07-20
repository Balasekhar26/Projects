class ScreenGrounder:
    @classmethod
    def ground_selector(
        cls, 
        query: str, 
        detections: list[dict], 
        ocr_results: list[dict],
        screen_resolution: tuple[int, int] = (1920, 1080)
    ) -> tuple[int, int] | None:
        """Finds matching selector query terms and computes center points on a normalized multi-monitor grid."""
        query_clean = query.lower().strip()
        
        # 1. Search OCR text results first (exact matching text is higher priority)
        for text_item in ocr_results:
            if query_clean in text_item["text"].lower():
                x1, y1, x2, y2 = text_item["box"]
                cx = (x1 + x2) // 2
                cy = (y1 + y2) // 2
                return cls.normalize_coordinates(cx, cy, screen_resolution)
                
        # 2. Fallback to YOLO bounding box labels
        for det in detections:
            if query_clean in det["label"].lower():
                x1, y1, x2, y2 = det["box"]
                cx = (x1 + x2) // 2
                cy = (y1 + y2) // 2
                return cls.normalize_coordinates(cx, cy, screen_resolution)
                
        return None

    @classmethod
    def normalize_coordinates(
        cls, 
        x: int, 
        y: int, 
        screen_res: tuple[int, int]
    ) -> tuple[int, int]:
        """Normalizes and bounds raw layout coordinates to screen coordinate grids."""
        # Standard clamp boundaries
        target_x = max(0, min(x, screen_res[0]))
        target_y = max(0, min(y, screen_res[1]))
        return (target_x, target_y)
