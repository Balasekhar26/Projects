"""OCR Engine (Program 18.0).

Handles local optical character recognition and word bounding box parsing using PyTesseract.
"""
from __future__ import annotations

import io
import logging
from typing import Any, Dict, List

from PIL import Image

logger = logging.getLogger(__name__)


class OCREngine:
    """Wraps PyTesseract and structures visual textual regions into coordinate mappings."""

    def __init__(self) -> None:
        pass

    @staticmethod
    def extract_text_regions(image_bytes: bytes) -> List[Dict[str, Any]]:
        """Run OCR on image bytes and extract text items with coordinates.

        Each item in returned list is a dictionary:
            {
                "text": "Submit",
                "x": 100,      # left
                "y": 200,      # top
                "w": 50,       # width
                "h": 20,       # height
                "confidence": 95.0
            }
        """
        if not image_bytes:
            return []

        try:
            import pytesseract
            img = Image.open(io.BytesIO(image_bytes))
            
            # Retrieve detailed layout data using image_to_data
            # output format is a TSV-like text structure
            data_str = pytesseract.image_to_data(img, output_type=pytesseract.Output.STRING)
            
            regions = []
            lines = data_str.strip().split("\n")
            if len(lines) <= 1:
                return []

            header = lines[0].split("\t")
            # Map column headers to indexes
            col_map = {col: i for i, col in enumerate(header)}

            for line in lines[1:]:
                cols = line.split("\t")
                if len(cols) < len(header):
                    continue

                text = cols[col_map["text"]].strip() if "text" in col_map else ""
                conf = float(cols[col_map["conf"]]) if "conf" in col_map else 0.0

                # Skip empty text or low confidence markers (-1 is used by tesseract for empty regions)
                if not text or conf < 0.0:
                    continue

                left = int(cols[col_map["left"]]) if "left" in col_map else 0
                top = int(cols[col_map["top"]]) if "top" in col_map else 0
                width = int(cols[col_map["width"]]) if "width" in col_map else 0
                height = int(cols[col_map["height"]]) if "height" in col_map else 0

                regions.append({
                    "text": text,
                    "x": left,
                    "y": top,
                    "w": width,
                    "h": height,
                    "confidence": conf
                })

            return regions

        except Exception as e:
            # Degrade gracefully if tesseract binary is missing or errors out
            logger.debug("OCREngine: Tesseract OCR execution failed — %s", e)
            return []
