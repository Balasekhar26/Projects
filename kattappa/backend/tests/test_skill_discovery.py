"""Unit tests for Program 55.0: Skill Discovery Engine.

Verifies search queries, tool prerequisite validations, and multi-tier candidate ranking.
"""
from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path
import pytest

from backend.core.config import load_config, BackendConfig
from backend.core.skill_graph import SkillGraph
from backend.core.skill_library import SkillLibrary
from backend.core.skill_discovery import SkillDiscoveryEngine


@pytest.fixture(autouse=True)
def mock_db(tmp_path, monkeypatch):
    """Isolates the SQLite database and temp files context."""
    original_config = load_config()
    test_db = tmp_path / "kattappa_test_discovery.db"
    test_config = BackendConfig(
        root=original_config.root,
        backend_root=original_config.backend_root,
        ollama_host=original_config.ollama_host,
        model_map=original_config.model_map,
        chroma_path=original_config.chroma_path,
        sqlite_path=test_db,
        memory_collection=original_config.memory_collection,
        shell_enabled=original_config.shell_enabled,
        desktop_enabled=original_config.desktop_enabled,
        screen_capture_enabled=original_config.screen_capture_enabled,
        guidance_overlay_enabled=original_config.guidance_overlay_enabled,
        teach_mode_enabled=original_config.teach_mode_enabled,
        screenshots_dir=original_config.screenshots_dir,
        audio_dir=original_config.audio_dir,
        logs_dir=original_config.logs_dir,
        workspace_dir=original_config.workspace_dir,
        hardware_profile=original_config.hardware_profile,
        context_budget=original_config.context_budget,
    )
    monkeypatch.setattr("backend.core.config.load_config", lambda: test_config)
    monkeypatch.setattr("backend.core.knowledge_graph.load_config", lambda: test_config)
    
    # Isolate runtime folder for skills.json
    temp_dir = tempfile.mkdtemp(prefix="kattappa_discovery_")
    monkeypatch.setattr("backend.core.config.runtime_data_root", lambda: Path(temp_dir))

    from backend.core.knowledge_graph import KnowledgeGraph
    SkillGraph._schema_ensured = False
    KnowledgeGraph._schema_ensured = False
    SkillLibrary.reset()

    yield test_db

    shutil.rmtree(temp_dir, ignore_errors=True)
    SkillLibrary.reset()


def test_discover_skills_search_and_rank():
    # 1. Register skill templates in SkillLibrary
    skill_a = SkillLibrary.add_skill(
        name="Read Repository file",
        description="Reads target repo files",
        tags=["read_file"],
    )
    skill_b = SkillLibrary.add_skill(
        name="Write Repository code",
        description="Writes new repo code",
        tags=["write_file"],
    )
    # Set skill_b to trusted
    SkillLibrary.record_result("Write Repository code", success=True)
    SkillLibrary.record_result("Write Repository code", success=True)
    SkillLibrary.record_result("Write Repository code", success=True)

    # 2. Register tool/agent connections in SkillGraph
    SkillGraph.register_skill(
        skill_id=skill_a["id"],
        name="Read Repository file",
        description="Reads target repo files",
        tools=["read_tool"],
        agents=["coder"],
    )
    SkillGraph.register_skill(
        skill_id=skill_b["id"],
        name="Write Repository code",
        description="Writes new repo code",
        tools=["write_tool"],
        agents=["coder"],
    )

    # 3. Discovery run with all tools available: trusted 'Write' should rank above 'Read'
    available_tools = ["read_tool", "write_tool"]
    results = SkillDiscoveryEngine.discover_skills("Repository", available_tools)

    assert len(results) == 2
    assert results[0]["name"] == "Write Repository code"  # trusted
    assert results[1]["name"] == "Read Repository file"

    # 4. Discovery run with only 'read_tool' available: 'Read' should rank above 'Write' because prereqs are met!
    restricted_tools = ["read_tool"]
    results_restricted = SkillDiscoveryEngine.discover_skills("Repository", restricted_tools)

    assert len(results_restricted) == 2
    assert results_restricted[0]["name"] == "Read Repository file"  # prereqs met
    assert results_restricted[1]["name"] == "Write Repository code"  # prereqs missing 'write_tool'
