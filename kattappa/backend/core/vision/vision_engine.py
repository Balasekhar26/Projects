from backend.core.vision.object_detector import ObjectDetector
from backend.core.vision.ocr_extractor import OCRExtractor
from backend.core.vision.screen_grounder import ScreenGrounder
from backend.core.vision.visual_indexer import VisualIndexer

class VisionEngine:
    def __init__(self):
        self.detector = ObjectDetector()
        self.ocr = OCRExtractor()
        self.indexer = VisualIndexer()

    def process_screen(self, image_data: bytes | None) -> dict:
        """Processes screen snapshots through YOLO detectors and OCR engines."""
        detections = self.detector.detect_objects(image_data)
        ocr_results = self.ocr.extract_text(image_data)
        return {
            "detections": detections,
            "ocr_results": ocr_results
        }

    def ground_selector(self, query: str, image_data: bytes | None) -> tuple[int, int] | None:
        """Grounds a semantic layout text target to a coordinate pixel grid."""
        screen_data = self.process_screen(image_data)
        return ScreenGrounder.ground_selector(
            query=query,
            detections=screen_data["detections"],
            ocr_results=screen_data["ocr_results"]
        )
