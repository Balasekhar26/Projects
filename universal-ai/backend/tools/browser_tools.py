from __future__ import annotations

from urllib.parse import quote_plus


def read_url(url: str, headless: bool = True) -> dict[str, str]:
    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        return {
            "title": "Browser unavailable",
            "text": (
                "Playwright is not available in this runtime. "
                "Universal AI can still chat and run other local tools. "
                f"Install/repair browser support from the setup tools. Error: {exc}"
            ),
        }

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=headless)
            page = browser.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            title = page.title()
            text = page.locator("body").inner_text(timeout=30000)[:12000]
            browser.close()
        return {"title": title, "text": text}
    except Exception as exc:
        return {
            "title": "Browser runtime unavailable",
            "text": (
                "Browser automation could not start on this OS/session. "
                "Run setup again or install Playwright Chromium with "
                "`python -m playwright install chromium`. "
                f"Error: {exc}"
            ),
        }


def search_web_basic(query: str) -> dict[str, str]:
    return read_url(
        f"https://www.google.com/search?q={quote_plus(query)}", headless=True
    )
