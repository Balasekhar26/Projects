from __future__ import annotations

from pathlib import Path

from backend.core.config import load_config


def take_screenshot(path: str | None = None) -> str:
    import mss
    from PIL import Image

    config = load_config()
    config.screenshots_dir.mkdir(parents=True, exist_ok=True)
    target = Path(path) if path else config.screenshots_dir / "current_screen.png"
    capture_factory = getattr(mss, "MSS", mss.mss)
    with capture_factory() as capture:
        monitor = capture.monitors[1]
        image = capture.grab(monitor)
        Image.frombytes("RGB", image.size, image.rgb).save(target)
    return str(target)


def ocr_image(path: str) -> str:
    import pytesseract
    from PIL import Image

    return pytesseract.image_to_string(Image.open(path)).strip()


def ocr_image_words(path: str) -> list[dict[str, int | str]]:
    import pytesseract
    from PIL import Image
    from pytesseract import Output

    image = Image.open(path)
    data = pytesseract.image_to_data(image, output_type=Output.DICT)
    words: list[dict[str, int | str]] = []
    for index, text in enumerate(data.get("text", [])):
        clean = str(text).strip()
        if not clean:
            continue
        try:
            confidence = int(float(data["conf"][index]))
        except (KeyError, TypeError, ValueError):
            confidence = -1
        if confidence < 0:
            continue
        words.append(
            {
                "text": clean,
                "left": int(data["left"][index]),
                "top": int(data["top"][index]),
                "width": int(data["width"][index]),
                "height": int(data["height"][index]),
                "confidence": confidence,
            }
        )
    return words


def read_screen_snapshot() -> dict[str, object]:
    try:
        path = take_screenshot()
    except Exception as exc:
        return {
            "text": f"Screen capture unavailable: {exc}",
            "screenshot_path": "",
            "width": 0,
            "height": 0,
            "words": [],
            "error": str(exc),
        }

    try:
        from PIL import Image

        image = Image.open(path)
        text = ocr_image(path)
        words = ocr_image_words(path)
    except Exception as exc:
        return {
            "text": f"Screenshot saved to {path}; OCR failed: {exc}",
            "screenshot_path": path,
            "width": 0,
            "height": 0,
            "words": [],
            "error": str(exc),
        }

    return {
        "text": text or f"Screenshot saved to {path}; no OCR text found.",
        "screenshot_path": path,
        "width": image.width,
        "height": image.height,
        "words": words,
        "error": "",
    }


def read_screen_text() -> str:
    return str(read_screen_snapshot()["text"])
