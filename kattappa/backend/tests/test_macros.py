from __future__ import annotations

import pytest
from backend.core.macros.browser_macros import execute_speedtest
from backend.main import handle_fast_path

def test_speedtest_macro_execution():
    res = execute_speedtest()
    assert isinstance(res, str)
    assert len(res) > 0
    assert "Internet Speed Test Results:" in res or "Failed to test" in res or "Playwright" in res

def test_fast_path_speedtest_routing():
    payload = handle_fast_path("test internet speed")
    assert payload is not None
    assert payload["state"]["selected_agent"] == "macro_browser_speedtest"
    assert "Internet Speed Test Results:" in payload["response"] or "Failed to test" in payload["response"] or "Playwright" in payload["response"]
