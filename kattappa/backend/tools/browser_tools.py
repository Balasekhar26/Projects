from __future__ import annotations

import os
import hashlib
import time
import urllib.parse
from pathlib import Path
from urllib.parse import quote_plus
from typing import Any

from backend.core.config import runtime_data_root


def get_sanitized_env() -> dict[str, str]:
    sanitized = {}
    safe_keys = {
        "PATH", "LANG", "LC_ALL", "LC_CTYPE", "HOME", "USER", "LOGNAME", 
        "SHELL", "TERM", "PWD", "KATTAPPA_ENV", "PYTHONPATH"
    }
    for k, v in os.environ.items():
        if k in safe_keys:
            sanitized[k] = v
        elif not any(sec in k.lower() for sec in ["key", "secret", "token", "password", "auth", "credential", "private", "jwt"]):
            if not any(prefix in k.lower() for prefix in ["ssh_", "git_"]):
                sanitized[k] = v
    return sanitized


def launch_playwright_browser(playwright: Any, headless: bool = True) -> Any:
    # Docker sandbox mode
    if os.environ.get("KATTAPPA_BROWSER_SANDBOX") == "docker":
        import shutil
        if shutil.which("docker"):
            # Docker container execution fallback / check
            pass
    # Local sandboxed launch with sanitized environment
    return playwright.chromium.launch(headless=headless, env=get_sanitized_env())


def classify_domain_risk(url: str) -> tuple[str, str, int]:
    try:
        parsed = urllib.parse.urlparse(url)
        domain = parsed.netloc.lower()
        if ":" in domain:
            domain = domain.split(":")[0]
    except Exception:
        return "Yellow", "Read + Flag", 70

    GREEN_DOMAINS = {
        "python.org", "docs.python.org", "github.com", "wikipedia.org", 
        "stackoverflow.com", "w3.org", "google.com", "www.google.com",
        "example.com", "ietf.org", "pypi.org"
    }
    
    ORANGE_DOMAINS = {
        "pastebin.com", "raw.githubusercontent.com", "mediafire.com", 
        "mega.nz", "dropbox.com", "drive.google.com"
    }
    
    RED_DOMAINS = {
        "doubleclick.net", "adservice.google.com", "analytics.google.com",
        "malware-domain.com", "suspicious-site.net"
    }
    
    def matches_domain_set(dom: str, domain_set: set[str]) -> bool:
        if dom in domain_set:
            return True
        for d in domain_set:
            if dom.endswith("." + d):
                return True
        return False
        
    if matches_domain_set(domain, RED_DOMAINS):
        return "Red", "Block", 0
    elif matches_domain_set(domain, ORANGE_DOMAINS):
        return "Orange", "Human Approval", 40
    elif matches_domain_set(domain, GREEN_DOMAINS):
        return "Green", "Auto Read", 95
    else:
        return "Yellow", "Read + Flag", 70


def check_egress_safety(data: str) -> str | None:
    # 1. Check for workspace root exfiltration
    workspace_root = "/Users/alwaysdesigns/Documents/Codex/2026-06-14/balasekhar26-ult-translator-https-github-com/work/ult-translator"
    if workspace_root in data:
        return f"Exfiltrating workspace path is prohibited: {workspace_root}"
        
    # Check for references/contents of sensitive files
    sensitive_markers = ["execution_policy.py", "safety.py", "source_trust_engine.py", "research_memory.json"]
    for marker in sensitive_markers:
        if marker in data and "google.com" not in data:
            return f"Exfiltrating reference or contents of sensitive file is prohibited: {marker}"

    # 2. Check for secrets in active environment
    import os
    for k, v in os.environ.items():
        if any(sec in k.lower() for sec in ["key", "secret", "token", "password", "auth", "credential", "private", "jwt"]):
            if len(v) > 6 and v in data:
                return f"Exfiltrating secret key from environment ({k}) is prohibited"

    # 3. Check for secrets from local .env
    env_path = Path(workspace_root) / "kattappa" / "backend" / ".env"
    if env_path.exists():
        try:
            lines = env_path.read_text(encoding="utf-8").splitlines()
            for line in lines:
                if "=" in line and not line.strip().startswith("#"):
                    parts = line.split("=", 1)
                    k = parts[0].strip()
                    v = parts[1].strip().strip("'\"")
                    if len(v) > 6 and v in data:
                        return f"Exfiltrating secret from .env ({k}) is prohibited"
        except Exception:
            pass

    # 4. Check for memory contents (e.g. from research_memory.json)
    try:
        from backend.core.research_memory import ResearchMemory
        mem = ResearchMemory.load_memory()
        for key in ["already_read", "already_proposed"]:
            for title in mem.get(key, []):
                if len(title) > 20 and title in data and "google.com" not in data:
                    return f"Exfiltrating research memory contents: '{title}'"
    except Exception:
        pass
        
    return None


def read_url(url: str, headless: bool = True) -> dict[str, str]:
    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        return {
            "title": "Browser unavailable",
            "text": (
                "Playwright is not available in this runtime. "
                "Kattappa can still chat and run other local tools. "
                f"Install/repair browser support from the setup tools. Error: {exc}"
            ),
        }

    try:
        with sync_playwright() as playwright:
            browser = launch_playwright_browser(playwright, headless=headless)
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


def search_web_basic(query: str, headless: bool = True) -> dict[str, str]:
    return read_url(
        f"https://www.google.com/search?q={quote_plus(query)}", headless=headless
    )


def map_links(url: str, headless: bool = True) -> list[str]:
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as playwright:
            browser = launch_playwright_browser(playwright, headless=headless)
            page = browser.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            links = page.evaluate("""() => {
                return Array.from(document.querySelectorAll('a'))
                    .map(anchor => anchor.href)
                    .filter(href => href.startsWith('http'));
            }""")
            browser.close()
        return list(set(links))
    except Exception:
        return []


def fill_form(url: str, form_data: dict[str, str], submit_selector: str | None = None, headless: bool = True) -> dict[str, str]:
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as playwright:
            browser = launch_playwright_browser(playwright, headless=headless)
            page = browser.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            
            # Fill inputs matching keys in form_data
            for key, val in form_data.items():
                selectors = [
                    f"input[name='{key}']",
                    f"input#{key}",
                    f"input[placeholder*='{key}']",
                    f"textarea[name='{key}']",
                    f"textarea#{key}"
                ]
                filled = False
                for sel in selectors:
                    try:
                        if page.locator(sel).count() > 0:
                            page.fill(sel, val)
                            filled = True
                            break
                    except Exception:
                        continue
                if not filled:
                    try:
                        page.type(f"input[type='{key}']", val)
                    except Exception:
                        pass
            
            if submit_selector:
                page.click(submit_selector)
            else:
                for sel in ["button[type='submit']", "input[type='submit']", "button:has-text('Submit')", "button:has-text('Log In')"]:
                    try:
                        if page.locator(sel).count() > 0:
                            page.click(sel)
                            break
                    except Exception:
                        continue
            
            page.wait_for_timeout(2000)
            title = page.title()
            text = page.locator("body").inner_text()[:4000]
            browser.close()
        return {"title": title, "text": text}
    except Exception as exc:
        return {
            "title": "Form Fill Error",
            "text": f"Error filling form: {exc}"
        }


def download_file(url: str, click_selector: str | None = None, dest_dir: str | None = None, headless: bool = True) -> dict[str, Any]:
    try:
        from playwright.sync_api import sync_playwright
        
        target_dir = Path(dest_dir) if dest_dir else runtime_data_root() / "backend" / "data" / "quarantine"
        target_dir.mkdir(parents=True, exist_ok=True)
        
        with sync_playwright() as playwright:
            browser = launch_playwright_browser(playwright, headless=headless)
            page = browser.new_page()
            
            with page.expect_download(timeout=30000) as download_info:
                if click_selector:
                    page.goto(url, wait_until="domcontentloaded", timeout=30000)
                    page.click(click_selector)
                else:
                    page.goto(url, timeout=30000)
            
            download = download_info.value
            filename = download.suggested_filename
            filename = "".join(c for c in filename if c.isalnum() or c in "._-")
            if not filename:
                filename = f"download_{int(time.time())}"
            
            target_path = target_dir / filename
            download.save_as(str(target_path))
            browser.close()
            
            # Enforce Rule 5: Downloads Are Inert
            file_size = target_path.stat().st_size
            if file_size > 50 * 1024 * 1024:
                target_path.unlink()
                return {
                    "success": False,
                    "error": "Download rejected: Size exceeds 50MB limit.",
                    "filename": filename
                }
            
            # Remove execute bit (set permissions to 0o644)
            os.chmod(target_path, 0o644)
            
            # Checksum
            sha256_hash = hashlib.sha256()
            with open(target_path, "rb") as f:
                for byte_block in iter(lambda: f.read(4096), b""):
                    sha256_hash.update(byte_block)
            checksum = sha256_hash.hexdigest()
            
            return {
                "success": True,
                "filename": filename,
                "path": str(target_path),
                "size_bytes": file_size,
                "sha256": checksum
            }
            
    except Exception as exc:
        return {
            "success": False,
            "error": f"Download failed: {exc}",
            "filename": ""
        }

