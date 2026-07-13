import os
import uuid
import pytest
from fastapi.testclient import TestClient
from backend.main import app
from backend.core.cos.kernel import KERNEL
from backend.core.governance.skill_dependency_graph import verify_dependencies
from backend.core.governance.skill_resolver import resolve_skill_by_intent
from backend.core.governance.sandbox_allocator import allocate_sandbox_and_run


def test_dependency_checking():
    # Setup mock active skills
    skills = [
        {
            "name": "base.tool",
            "version": "1.0.0",
            "dependencies": [],
        },
        {
            "name": "derived.tool",
            "version": "1.1.0",
            "dependencies": [{"name": "base.tool", "version": ">=1.0.0"}],
        },
        {
            "name": "broken.tool",
            "version": "2.0.0",
            "dependencies": [{"name": "base.tool", "version": ">=2.0.0"}], # Mismatch
        },
        {
            "name": "circular.a",
            "version": "1.0.0",
            "dependencies": [{"name": "circular.b", "version": ">=1.0.0"}],
        },
        {
            "name": "circular.b",
            "version": "1.0.0",
            "dependencies": [{"name": "circular.a", "version": ">=1.0.0"}],
        }
    ]
    
    # 1. Valid derived tool
    ok, err = verify_dependencies("derived.tool", skills)
    assert ok is True
    
    # 2. Version mismatch
    ok, err = verify_dependencies("broken.tool", skills)
    assert ok is False
    assert "Version mismatch" in err
    
    # 3. Circular dependency
    ok, err = verify_dependencies("circular.a", skills)
    assert ok is False
    assert "Circular dependency" in err


def test_intent_resolution():
    skills = [
        {
            "name": "browser.search",
            "description": "Searches the web for flight data and trains",
        },
        {
            "name": "payment.quote",
            "description": "Processes money transfers and payments",
        }
    ]
    
    # Search matches "flight"
    resolved = resolve_skill_by_intent("I want to find a flight", skills)
    assert len(resolved) == 1
    assert resolved[0]["name"] == "browser.search"
    
    # Search matches "payments"
    resolved = resolve_skill_by_intent("transfer money and make payments", skills)
    assert len(resolved) == 1
    assert resolved[0]["name"] == "payment.quote"


def test_sandbox_execution():
    skill = {
        "name": "test.echo",
        "entrypoint": os.path.abspath("test_skill_script.py"),
        "timeout_seconds": 5,
        "sandbox_type": "subprocess",
    }
    args = {"hello": "world", "kattappa": "active"}
    
    res = allocate_sandbox_and_run(skill, args)
    assert res["status"] == "success"
    assert res["result"]["echoed_args"] == args
    assert res["result"]["status"] == "processed_in_sandbox"


def test_skills_api_endpoints():
    client = TestClient(app)
    
    # 1. Install base skill
    response = client.post(
        "/api/v1/skills/install",
        json={
            "name": "kattappa.base",
            "version": "1.0.0",
            "description": "Base capability skill",
            "entrypoint": os.path.abspath("test_skill_script.py"),
            "required_capabilities": ["CAP_SCREEN_READ"],
            "dependencies": [],
        }
    )
    assert response.status_code == 200
    assert response.json()["status"] == "success"
    
    # 2. Install derived skill
    response = client.post(
        "/api/v1/skills/install",
        json={
            "name": "kattappa.derived",
            "version": "1.0.0",
            "description": "Derived capability skill",
            "entrypoint": os.path.abspath("test_skill_script.py"),
            "required_capabilities": ["CAP_SCREEN_READ"],
            "dependencies": [{"name": "kattappa.base", "version": ">=1.0.0"}],
        }
    )
    assert response.status_code == 200
    
    # 3. Search and search intent
    response = client.get("/api/v1/skills/search")
    assert response.status_code == 200
    skills_list = response.json()
    assert any(s["name"] == "kattappa.base" for s in skills_list)
    
    response = client.get("/api/v1/skills/resolve?intent=base")
    assert response.status_code == 200
    assert len(response.json()) >= 1
    
    # 4. Execute skill (with allowed capabilities)
    from unittest.mock import patch
    with patch("backend.api.v1.telemetry.allocate_sandbox_and_run") as mock_run:
        mock_run.return_value = {"status": "success", "result": {"echoed_args": {"test": "val"}, "status": "processed_in_sandbox"}}
        
        response = client.post(
            "/api/v1/skills/execute",
            json={
                "name": "kattappa.base",
                "args": {"test": "val"},
                "agent_name": "browser", # browser has CAP_SCREEN_READ allowed
            }
        )
        assert response.status_code == 200
        assert response.json()["status"] == "success"
        
        # 5. Execute skill (blocked due to capability registry restriction)
        # E.g. planner is denied CAP_SCREEN_READ
        response = client.post(
            "/api/v1/skills/execute",
            json={
                "name": "kattappa.base",
                "args": {"test": "val"},
                "agent_name": "planner",
            }
        )
        # PermissionGovernor blocks, returning 403 Forbidden
        assert response.status_code == 403
        assert "Execution blocked" in response.json()["detail"]
    
    # 6. Clean up/Uninstall
    response = client.delete("/api/v1/skills/uninstall?name=kattappa.base")
    assert response.status_code == 200
    response = client.delete("/api/v1/skills/uninstall?name=kattappa.derived")
    assert response.status_code == 200
