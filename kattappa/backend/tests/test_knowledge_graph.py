from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.core.config import load_config, BackendConfig
from backend.core.knowledge_graph import KnowledgeGraph


@pytest.fixture(autouse=True)
def mock_db(tmp_path, monkeypatch):
    original_config = load_config()
    test_db = tmp_path / "kattappa_test.db"
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
    KnowledgeGraph._schema_ensured = False
    yield test_db


def test_knowledge_graph_node_and_edge_operations():
    # Insert nodes
    KnowledgeGraph.add_node("agent_coder", "agent", {"name": "Kattappa Coder"})
    KnowledgeGraph.add_node("tool_write", "tool", {"name": "Write File"})

    node = KnowledgeGraph.get_node("agent_coder")
    assert node is not None
    assert node["type"] == "agent"
    assert node["properties"]["name"] == "Kattappa Coder"

    # Link nodes
    KnowledgeGraph.add_edge("agent_coder", "tool_write", "USES")

    # Verify neighbors query
    neighbors = KnowledgeGraph.query_neighbors("agent_coder", direction="out")
    assert len(neighbors) == 1
    assert neighbors[0]["node_id"] == "tool_write"
    assert neighbors[0]["relation"] == "USES"


def test_knowledge_graph_shortest_path():
    KnowledgeGraph.add_node("A", "concept")
    KnowledgeGraph.add_node("B", "concept")
    KnowledgeGraph.add_node("C", "concept")
    KnowledgeGraph.add_node("D", "concept")

    KnowledgeGraph.add_edge("A", "B", "LINK")
    KnowledgeGraph.add_edge("B", "C", "LINK")
    KnowledgeGraph.add_edge("C", "D", "LINK")
    KnowledgeGraph.add_edge("A", "C", "SHORTCUT")

    # Shortest path from A to D: A -> C -> D (length 3, not A -> B -> C -> D length 4)
    path = KnowledgeGraph.find_shortest_path("A", "D")
    assert path == ["A", "C", "D"]


def test_knowledge_graph_subgraph():
    KnowledgeGraph.add_node("X", "concept")
    KnowledgeGraph.add_node("Y", "concept")
    KnowledgeGraph.add_node("Z", "concept")

    KnowledgeGraph.add_edge("X", "Y", "LINK")
    KnowledgeGraph.add_edge("Y", "Z", "LINK")

    subgraph = KnowledgeGraph.get_subgraph(["X"], depth=2)
    assert len(subgraph["nodes"]) == 3
    assert len(subgraph["edges"]) == 2


def test_knowledge_graph_api():
    client = TestClient(app)

    # 1. Create source and target nodes via API
    resp_n1 = client.post("/cognitive/knowledge-graph/node", json={"node_id": "api_A", "node_type": "concept"})
    assert resp_n1.status_code == 200
    resp_n2 = client.post("/cognitive/knowledge-graph/node", json={"node_id": "api_B", "node_type": "concept"})
    assert resp_n2.status_code == 200

    # 2. Link nodes
    resp_e = client.post(
        "/cognitive/knowledge-graph/edge",
        json={"source_id": "api_A", "target_id": "api_B", "relation_type": "LINKS_TO"},
    )
    assert resp_e.status_code == 200

    # 3. Shortest Path API
    path_resp = client.get("/cognitive/knowledge-graph/shortest-path?source=api_A&target=api_B")
    assert path_resp.status_code == 200
    assert path_resp.json()["path"] == ["api_A", "api_B"]

    # 4. Subgraph API
    sub_resp = client.get("/cognitive/knowledge-graph/subgraph?nodes=api_A&depth=1")
    assert sub_resp.status_code == 200
    assert len(sub_resp.json()["subgraph"]["nodes"]) == 2
