import pytest

from backend.agents.browser import browser_node
from backend.agents.desktop import desktop_node

from backend.core.execution_policy import DEFAULT_POLICY_ENGINE, PolicyOutcome
from backend.core.capability_registry import (
    CapabilityRegistry,
    CAP_WEB_SEARCH,
    CAP_MOUSE_MOVE,
    CAP_FILE_WRITE,
    CAP_FILE_READ,
    CAP_TERMINAL_EXECUTE
)


def test_capability_registry_direct():
    # 1. Allowed capabilities
    assert CapabilityRegistry.is_capability_allowed("browser", CAP_WEB_SEARCH) is True
    assert CapabilityRegistry.is_capability_allowed("desktop", CAP_MOUSE_MOVE) is True
    assert CapabilityRegistry.is_capability_allowed("file", CAP_FILE_WRITE) is True
    
    # 2. Denied capabilities
    assert CapabilityRegistry.is_capability_allowed("browser", CAP_MOUSE_MOVE) is False
    assert CapabilityRegistry.is_capability_allowed("desktop", CAP_FILE_READ) is False
    
    # 3. Deny by default for unknown agent
    assert CapabilityRegistry.is_capability_allowed("unknown_agent", CAP_WEB_SEARCH) is False


def test_policy_engine_capability_evaluation():
    # 1. Browser trying to search (allowed CAP_WEB_SEARCH -> auto_execute)
    dec = DEFAULT_POLICY_ENGINE.evaluate("BROWSER_SEARCH", agent_name="browser")
    assert dec.outcome is PolicyOutcome.AUTO_EXECUTE
    
    # 2. Browser trying to move mouse (denied CAP_MOUSE_MOVE -> blocked)
    dec = DEFAULT_POLICY_ENGINE.evaluate("DESKTOP_MOUSE_MOVE", agent_name="browser")
    assert dec.outcome is PolicyOutcome.BLOCKED
    assert "lacks required capability" in dec.reason

    # 3. Desktop trying to click (allowed CAP_MOUSE_MOVE -> auto_execute)
    dec = DEFAULT_POLICY_ENGINE.evaluate("DESKTOP_MOUSE_CLICK", agent_name="desktop")
    assert dec.outcome is PolicyOutcome.AUTO_EXECUTE
    
    # 4. Desktop trying to delete file (allowed CAP_FILE_DELETE -> REQUIRE_HUMAN due to delete policy)
    dec = DEFAULT_POLICY_ENGINE.evaluate("DESKTOP_DELETE_FILE", agent_name="desktop")
    assert dec.outcome is PolicyOutcome.REQUIRE_HUMAN
    
    # 5. Desktop trying to read file directly (denied CAP_FILE_READ -> blocked)
    dec = DEFAULT_POLICY_ENGINE.evaluate("READ_FILE", agent_name="desktop")
    assert dec.outcome is PolicyOutcome.BLOCKED
    assert "lacks required capability" in dec.reason

    # 6. File agent trying to write file (allowed CAP_FILE_WRITE -> require_human)
    dec = DEFAULT_POLICY_ENGINE.evaluate("WRITE_FILE", agent_name="file")
    assert dec.outcome is PolicyOutcome.REQUIRE_HUMAN
    
    # 7. File agent trying to run shell command (denied CAP_TERMINAL_EXECUTE -> blocked)
    dec = DEFAULT_POLICY_ENGINE.evaluate("RUN_SHELL", agent_name="file")
    assert dec.outcome is PolicyOutcome.BLOCKED
    assert "lacks required capability" in dec.reason
