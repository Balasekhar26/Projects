from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from ai_system.core.config import Settings


@dataclass
class ScreenVision:
    settings: Settings

    def screenshot(self) -> Path:
        import mss
        from PIL import Image

        self.settings.screenshots_dir.mkdir(parents=True, exist_ok=True)
        path = (
            self.settings.screenshots_dir
            / f"screen-{datetime.now().strftime('%Y%m%d-%H%M%S')}.png"
        )
        with mss.mss() as capture:
            monitor = capture.monitors[1]
            shot = capture.grab(monitor)
            Image.frombytes("RGB", shot.size, shot.rgb).save(path)
        return path

    def ocr_latest_screen(self) -> str:
        try:
            image_path = self.screenshot()
        except Exception as exc:
            return f"Screen capture is unavailable on this OS/session: {exc}"
        try:
            import pytesseract
            from PIL import Image

            text = pytesseract.image_to_string(Image.open(image_path))
        except Exception as exc:
            return f"Screenshot saved to {image_path}. OCR failed: {exc}"
        return text.strip() or f"Screenshot saved to {image_path}. OCR found no text."
