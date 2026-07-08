"""Image Ingestion (Program 18.0).

Handles screen capturing, file loading, clipboard extraction, and ingestion privacy gates.
"""
from __future__ import annotations

import hashlib
import io
import logging
from typing import Any, Dict, Optional

from PIL import Image

from backend.core.perception.perception_frame import PerceptionFrame

logger = logging.getLogger(__name__)


class ImageIngestion:
    """Core manager for screenshot capture, file loading, and image normalizations."""

    def __init__(self) -> None:
        pass

    @staticmethod
    def capture_screenshot(monitor_index: int = 1, bbox: Optional[tuple[int, int, int, int]] = None) -> PerceptionFrame:
        """Capture the active desktop screen using mss.

        bbox: Optional tuple (left, top, width, height)
        """
        try:
            import mss
            with mss.mss() as sct:
                # Capture specific region or full monitor
                if bbox:
                    left, top, width, height = bbox
                    monitor = {"top": top, "left": left, "width": width, "height": height}
                else:
                    monitors = sct.monitors
                    if len(monitors) > monitor_index:
                        monitor = monitors[monitor_index]
                    else:
                        monitor = monitors[0]  # Fallback to virtual monitor

                sct_img = sct.grab(monitor)
                img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
                
                # Compress to PNG bytes
                output = io.BytesIO()
                img.save(output, format="PNG")
                png_bytes = output.getvalue()

                frame_hash = hashlib.sha256(png_bytes).hexdigest()
                metadata = {
                    "width": img.width,
                    "height": img.height,
                    "format": "PNG",
                    "hash": frame_hash,
                    "monitor": monitor_index,
                }
                return PerceptionFrame(
                    source="screenshot",
                    image_bytes=png_bytes,
                    metadata=metadata
                )
        except Exception as e:
            logger.error("ImageIngestion: Failed to capture desktop via mss — %s", e)
            # Safe mock fallback for headless / server envs
            return ImageIngestion.generate_mock_frame("Failed capture fallback")

    @staticmethod
    def load_from_file(file_path: str) -> PerceptionFrame:
        """Loads an image from the local filesystem."""
        try:
            with open(file_path, "rb") as f:
                img_bytes = f.read()

            img = Image.open(io.BytesIO(img_bytes))
            frame_hash = hashlib.sha256(img_bytes).hexdigest()
            metadata = {
                "width": img.width,
                "height": img.height,
                "format": img.format or "PNG",
                "hash": frame_hash,
                "file_path": file_path
            }
            return PerceptionFrame(
                source="file",
                image_bytes=img_bytes,
                metadata=metadata
            )
        except Exception as e:
            logger.error("ImageIngestion: Failed to load file %s — %s", file_path, e)
            raise ValueError(f"Failed to ingest image file: {e}")

    @staticmethod
    def load_from_clipboard() -> Optional[PerceptionFrame]:
        """Ingest image currently stored in OS clipboard."""
        try:
            from PIL import ImageGrab
            img = ImageGrab.grabclipboard()
            if isinstance(img, Image.Image):
                output = io.BytesIO()
                img.save(output, format="PNG")
                png_bytes = output.getvalue()

                frame_hash = hashlib.sha256(png_bytes).hexdigest()
                metadata = {
                    "width": img.width,
                    "height": img.height,
                    "format": "PNG",
                    "hash": frame_hash
                }
                return PerceptionFrame(
                    source="clipboard",
                    image_bytes=png_bytes,
                    metadata=metadata
                )
        except Exception as e:
            logger.debug("ImageIngestion: Clipboard is empty or unsupported — %s", e)
        return None

    @staticmethod
    def generate_mock_frame(text_tag: str = "mock") -> PerceptionFrame:
        """Generates a simple 100x100 white PNG in-memory representation for tests."""
        img = Image.new("RGB", (100, 100), color="white")
        output = io.BytesIO()
        img.save(output, format="PNG")
        png_bytes = output.getvalue()
        frame_hash = hashlib.sha256(png_bytes).hexdigest()
        return PerceptionFrame(
            source="mock",
            image_bytes=png_bytes,
            metadata={
                "width": 100,
                "height": 100,
                "format": "PNG",
                "hash": frame_hash,
                "tag": text_tag
            }
        )
