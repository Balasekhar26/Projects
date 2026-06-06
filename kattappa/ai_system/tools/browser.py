from __future__ import annotations

from dataclasses import dataclass

from ai_system.core.config import Settings


@dataclass
class BrowserTool:
    settings: Settings

    def read_page(self, url: str, timeout_ms: int = 30000) -> str:
        if not self.settings.allow_browser_control:
            return "Browser control is disabled in config/settings.yaml."
        try:
            from playwright.sync_api import sync_playwright
        except Exception as exc:
            return f"Browser support is unavailable in this runtime: {exc}"
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                page = browser.new_page()
                page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
                title = page.title()
                text = page.locator("body").inner_text(timeout=timeout_ms)
                browser.close()
            return f"# {title}\n\n{text[:12000]}"
        except Exception as exc:
            return f"Browser runtime could not start. Install Playwright Chromium. Error: {exc}"
