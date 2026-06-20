from __future__ import annotations

import time

def execute_speedtest() -> str:
    """Deterministically runs a speed test using Playwright Chromium without LLM intervention."""
    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        return (
            "Playwright is not available in the current environment. "
            "Please run `python -m playwright install chromium` or configure setup. "
            f"Error: {exc}"
        )

    try:
        with sync_playwright() as playwright:
            # Launch headless chromium
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page()
            
            # Navigate to fast.com
            page.goto("https://fast.com", wait_until="domcontentloaded", timeout=20000)
            
            # Wait for speed test finish indicator (#speed-value.succeeded)
            page.wait_for_selector("#speed-value.succeeded", timeout=45000)
            
            speed = page.locator("#speed-value").inner_text().strip()
            unit = page.locator("#speed-units").inner_text().strip()
            browser.close()
            
            if speed:
                return f"Internet Speed Test Results: {speed} {unit}."
            return "Speed test completed but could not extract the result value."
    except Exception as exc:
        return f"Failed to test internet speed deterministically: {exc}"
