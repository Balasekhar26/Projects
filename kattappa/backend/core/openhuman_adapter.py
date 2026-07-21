from __future__ import annotations

import os
import shutil
import subprocess
import time
import uuid
import platform
from typing import Any, Dict

class OpenHumanAdapter:
    """
    OpenHuman execution substrate adapter ("Hanuman").
    Interfaces with the OpenHuman local runtime or falls back to native OS sandboxed processes.
    """

    @classmethod
    def execute_action(
        cls,
        agent_name: str,
        action: str,
        params: Dict[str, Any],
        state: Dict[str, Any]
    ) -> Any:
        """
        Routes the action to the OpenHuman runtime.
        Bypasses to mock actions if in test mode.
        """
        action_upper = action.upper()

        # Check Test Mode
        if os.getenv("KATTAPPA_TEST_MODE") == "true" or os.getenv("KATTAPPA_ENV") == "test":
            return cls._execute_mock(action_upper, params, state)

        # Standard Execution Path
        try:
            # Check if openhuman library is available locally
            import openhuman
            # Invoke OpenHuman execute task block (Simulated integration)
            oh_res = openhuman.execute(action_upper, params)
            return oh_res
        except ImportError:
            # Fall back to native implementation
            return cls._execute_fallback(action_upper, params, state)

    @classmethod
    def _execute_mock(cls, action: str, params: Dict[str, Any], state: Dict[str, Any]) -> Any:
        """Mock responses for test scenarios preserving type semantics."""
        # Filesystem
        if action in ("CREATE_FILE", "WRITE_FILE"):
            target_file = params.get("target") or params.get("path")
            return {"success": True, "message": f"Wrote file '{target_file}' (mocked)"}
        elif action in ("FILE_WRITE", "FILE_MODIFY"):
            target_file = params.get("target") or params.get("path")
            return f"Successfully wrote to file '{target_file}' (mocked)"
        elif action == "READ_FILE":
            target_file = params.get("target") or params.get("path")
            return {"success": True, "content": f"Mock content for file: {target_file}"}
        elif action == "DELETE_FILE":
            target_file = params.get("target") or params.get("path")
            return {"success": True, "message": f"Deleted file '{target_file}' (mocked)"}
        elif action == "FILE_DELETE":
            target_file = params.get("target") or params.get("path")
            return f"Deleted file '{target_file}' (mocked)"
        elif action == "MOVE_FILE":
            source = params.get("source")
            destination = params.get("destination")
            return {"success": True, "message": f"Moved '{source}' to '{destination}' (mocked)"}
        elif action == "LIST_DIR":
            target_dir = params.get("target") or params.get("path") or "."
            return {"success": True, "items": [f"file_1.txt", f"file_2.py"]}

        # Shell
        elif action == "RUN_SHELL":
            command = params.get("command") or params.get("cmd") or ""
            return {
                "success": True,
                "stdout": f"Mock output for shell command: {command}",
                "stderr": "",
                "exit_code": 0
            }
        elif action == "RUN_TESTS":
            return {
                "success": True,
                "stdout": "All 1 test passed (mocked)",
                "stderr": "",
                "returncode": 0
            }

        # Browser
        elif action.startswith("BROWSER_"):
            url = params.get("url", "https://example.com")
            if action in ("BROWSER_NAVIGATE", "BROWSER_READ", "BROWSER_EXTRACT_INFO", "BROWSER_FILL_FORM", "BROWSER_CLICK_SUBMIT", "BROWSER_LOGIN"):
                return {
                    "content": f"Mock HTML content from url {url}",
                    "source": url,
                    "source_url": url,
                    "timestamp": time.time(),
                    "trust": 95,
                    "trust_score": 95,
                    "provenance": "UNTRUSTED"
                }
            elif action == "BROWSER_MAP_LINKS":
                return f"Browser mapped links:\n{url}/page1\n{url}/page2"
            elif action == "BROWSER_DOWNLOAD_FILE":
                return (
                    f"Browser download success:\n"
                    f"Filename: mock_file.zip\n"
                    f"Path: /tmp/mock_file.zip\n"
                    f"Size: 100 bytes\n"
                    f"SHA256: mock_sha"
                )
            elif action == "BROWSER_SPEEDTEST":
                from backend.core.macros.browser_macros import execute_speedtest
                return execute_speedtest()
            return {"success": True, "message": f"Browser action '{action}' executed (mocked)"}

        # Desktop
        elif action.startswith("DESKTOP_"):
            if action == "DESKTOP_SHUTDOWN":
                return "Shutdown request completed (simulated)"
            elif action == "DESKTOP_DELETE_FILE":
                path = params.get("path")
                return f"Deleted file '{path}' (simulated)"
            elif action == "DESKTOP_SCREENSHOT":
                return {
                    "window": "active_window",
                    "elements": [],
                    "timestamp": time.time(),
                    "sha256": "mock_hash",
                    "provenance": "UNTRUSTED_UI_DATA"
                }
            elif action == "DESKTOP_READ_SCREEN":
                return {
                    "window": "active_window",
                    "elements": [],
                    "text": "mock active screen text",
                    "timestamp": time.time(),
                    "provenance": "UNTRUSTED_UI_DATA"
                }
            return f"Desktop action '{action}' executed (mocked)"

        return {"success": False, "error": f"Unhandled action '{action}' in mock engine"}

    @classmethod
    def _execute_fallback(cls, action: str, params: Dict[str, Any], state: Dict[str, Any]) -> Any:
        """Fall back to native Python and OS subprocess operations."""
        # Filesystem
        if action in ("CREATE_FILE", "WRITE_FILE"):
            target_file = params.get("target") or params.get("path")
            code_content = params.get("code") or params.get("content", "")
            os.makedirs(os.path.dirname(target_file), exist_ok=True)
            with open(target_file, "w", encoding="utf-8") as f:
                f.write(code_content)
            return {"success": True, "message": f"Wrote file '{target_file}'"}
        elif action in ("FILE_WRITE", "FILE_MODIFY"):
            target_file = params.get("target") or params.get("path")
            content = params.get("content") or params.get("code") or ""
            os.makedirs(os.path.dirname(target_file), exist_ok=True)
            with open(target_file, "w", encoding="utf-8") as f:
                f.write(content)
            return f"Successfully wrote to file '{target_file}'"
        elif action == "READ_FILE":
            target_file = params.get("target") or params.get("path")
            with open(target_file, "r", encoding="utf-8") as f:
                content = f.read()
            return {"success": True, "content": content}
        elif action == "DELETE_FILE":
            target_file = params.get("target") or params.get("path")
            if os.path.exists(target_file):
                from backend.core.action_broker import ActionBroker
                q_path = ActionBroker._quarantine_file(target_file)
                return {"success": True, "message": f"Deleted file '{target_file}' (quarantined to {q_path})"}
            else:
                return {"success": False, "error": "File not found"}
        elif action == "FILE_DELETE":
            target_file = params.get("target") or params.get("path")
            if os.path.exists(target_file):
                from backend.core.action_broker import ActionBroker
                q_path = ActionBroker._quarantine_file(target_file)
                return f"Deleted file '{target_file}' (quarantined to {q_path})"
            else:
                return "File not found"
        elif action == "MOVE_FILE":
            source = params.get("source")
            destination = params.get("destination")
            shutil.move(source, destination)
            return {"success": True, "message": f"Moved '{source}' to '{destination}'"}
        elif action == "LIST_DIR":
            target_dir = params.get("target") or params.get("path") or "."
            items = os.listdir(target_dir)
            return {"success": True, "items": items}

        # Shell
        elif action == "RUN_SHELL":
            command = params.get("command") or params.get("cmd") or ""
            from backend.core.sandbox_runtime import SandboxRuntime
            is_windows = platform.system().lower() == "windows"
            cmd_list = ["cmd.exe", "/c", command] if is_windows else ["/bin/sh", "-c", command]
            res = SandboxRuntime.run_command(cmd_list)
            return {
                "success": res.returncode == 0,
                "stdout": res.stdout,
                "stderr": res.stderr,
                "exit_code": res.returncode
            }

        # Browser Fallbacks
        elif action.startswith("BROWSER_"):
            from backend.tools.browser_tools import read_url, search_web_basic, map_links, fill_form, download_file
            url = params.get("url")
            if action in ("BROWSER_NAVIGATE", "BROWSER_READ", "BROWSER_EXTRACT_INFO"):
                res = read_url(url)
                return {
                    "content": res.get("text", "")[:4000],
                    "source": url,
                    "source_url": url,
                    "timestamp": time.time(),
                    "trust": 95,
                    "trust_score": 95,
                    "provenance": "UNTRUSTED"
                }
            elif action == "BROWSER_SEARCH":
                query = params.get("query")
                res = search_web_basic(query)
                prov_url = f"https://www.google.com/search?q={urllib.parse.quote_plus(query)}" if url is None else url
                return {
                    "content": res.get("text", "")[:4000],
                    "source": prov_url,
                    "source_url": prov_url,
                    "timestamp": time.time(),
                    "trust": 95,
                    "trust_score": 95,
                    "provenance": "UNTRUSTED"
                }
            elif action == "BROWSER_MAP_LINKS":
                links = map_links(url)
                return f"Browser mapped links:\n" + "\n".join(links[:50])
            elif action in ("BROWSER_FILL_FORM", "BROWSER_CLICK_SUBMIT", "BROWSER_LOGIN"):
                form_data = params.get("form_data", {})
                sub_sel = params.get("submit_selector")
                res = fill_form(url, form_data, sub_sel)
                return {
                    "content": res.get("text", "")[:4000],
                    "source": url,
                    "source_url": url,
                    "timestamp": time.time(),
                    "trust": 95,
                    "trust_score": 95,
                    "provenance": "UNTRUSTED"
                }
            elif action == "BROWSER_DOWNLOAD_FILE":
                click_sel = params.get("click_selector")
                res = download_file(url, click_sel)
                if res.get("success"):
                    return (
                        f"Browser download success:\n"
                        f"Filename: {res.get('filename')}\n"
                        f"Path: {res.get('path')}\n"
                        f"Size: {res.get('size_bytes')} bytes\n"
                        f"SHA256: {res.get('sha256')}"
                    )
                else:
                    return f"Browser download failed: {res.get('error')}"

        # Desktop Fallbacks
        elif action.startswith("DESKTOP_"):
            from backend.tools.desktop_tools import (
                open_application, move_mouse, click_element, type_text, press_key, take_screenshot, read_screen
            )
            if action == "DESKTOP_SHUTDOWN":
                return "Shutdown request completed (simulated)"
            elif action == "DESKTOP_DELETE_FILE":
                path = params.get("path")
                if os.path.exists(path):
                    from backend.core.action_broker import ActionBroker
                    q_path = ActionBroker._quarantine_file(path)
                    return f"Deleted file '{path}' (quarantined to {q_path})"
                return "File not found"
            elif action == "DESKTOP_OPEN_APP":
                app_name = params.get("app_name", "VS Code")
                return open_application(app_name)
            elif action == "DESKTOP_MOUSE_MOVE":
                x_norm = params.get("x_norm", 500.0)
                y_norm = params.get("y_norm", 500.0)
                return move_mouse(x_norm, y_norm)
            elif action == "DESKTOP_MOUSE_CLICK":
                x_norm = params.get("x_norm", 500.0)
                y_norm = params.get("y_norm", 500.0)
                button = params.get("button", "left")
                click_type = params.get("click_type", "single")
                return click_element(x_norm, y_norm, button, click_type)
            elif action == "DESKTOP_KEYBOARD_TYPING":
                text = params.get("text", "")
                return type_text(text)
            elif action == "DESKTOP_SCREENSHOT":
                meta = take_screenshot()
                return {
                    "window": meta["window"],
                    "elements": [],
                    "timestamp": meta["timestamp"],
                    "sha256": meta["sha256"],
                    "provenance": "UNTRUSTED_UI_DATA"
                }
            elif action == "DESKTOP_READ_SCREEN":
                res_screen = read_screen()
                return {
                    "window": res_screen["window"],
                    "elements": res_screen["elements"],
                    "text": res_screen["text"],
                    "timestamp": res_screen["timestamp"],
                    "provenance": "UNTRUSTED_UI_DATA"
                }
            return f"Desktop action '{action}' executed."

        return {"success": False, "error": f"Unhandled fallback action '{action}'"}
