from __future__ import annotations

import json
import time
from unittest.mock import MagicMock, patch
import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.core.action_scheduler import ActionScheduler
from backend.core.node_manager import NodeManager
from backend.core.node_selector import NodeSelector


@pytest.fixture(autouse=True)
def clean_node_db():
    """Wipes the node registry and scheduler db tables before and after each test."""
    def _clean():
        ActionScheduler._schema_ensured = False
        conn = ActionScheduler._get_conn()
        try:
            conn.execute("DELETE FROM node_registry")
            conn.execute("DELETE FROM action_queue")
            conn.execute("DELETE FROM scheduler_metrics")
            conn.commit()
        finally:
            conn.close()

    _clean()
    yield
    _clean()


def test_node_registration_and_get():
    """Verify nodes can be registered and retrieved with exact metadata details."""
    NodeManager.register_node(
        node_id="laptop-01",
        node_name="My Laptop",
        node_type="worker",
        cpu_logical=8,
        ram_gb=16.0,
        gpu_info="None",
        capabilities=["WEB_SEARCH", "VISION"]
    )

    nodes = NodeManager.get_nodes()
    assert len(nodes) == 1
    assert nodes[0]["node_id"] == "laptop-01"
    assert nodes[0]["node_name"] == "My Laptop"
    assert nodes[0]["cpu_logical"] == 8
    assert nodes[0]["ram_gb"] == 16.0
    assert "WEB_SEARCH" in nodes[0]["capabilities"]
    assert "VISION" in nodes[0]["capabilities"]
    assert nodes[0]["status"] == "alive"


def test_node_heartbeat_updates():
    """Ensure heartbeat updates resource usage percentages and status changes."""
    NodeManager.register_node(
        node_id="office-gpu-01",
        node_name="Office Server",
        node_type="worker",
        cpu_logical=32,
        ram_gb=128.0,
        gpu_info="RTX 4090",
        capabilities=["GPU_TRAINING"]
    )

    success = NodeManager.update_heartbeat(
        node_id="office-gpu-01",
        system_cpu_pct=34.5,
        system_ram_pct=60.0,
        active_tasks=2,
        status="degraded"
    )
    assert success is True

    nodes = NodeManager.get_active_nodes()
    assert len(nodes) == 1
    assert nodes[0]["node_id"] == "office-gpu-01"
    assert nodes[0]["system_cpu_pct"] == 34.5
    assert nodes[0]["system_ram_pct"] == 60.0
    assert nodes[0]["active_tasks"] == 2
    assert nodes[0]["status"] == "degraded"


def test_node_selector_routing():
    """Assert NodeSelector routes tasks to the node with the matching capability and lowest utilization."""
    # 1. Register two nodes with matching capability (WEB_SEARCH)
    # Node 1: High utilization (CPU 90)
    NodeManager.register_node(
        node_id="high-load-node",
        node_name="Busy Node",
        node_type="worker",
        cpu_logical=8,
        ram_gb=16.0,
        capabilities=["WEB_SEARCH"]
    )
    NodeManager.update_heartbeat(
        node_id="high-load-node",
        system_cpu_pct=90.0,
        system_ram_pct=80.0,
        active_tasks=4
    )

    # Node 2: Low utilization (CPU 15)
    NodeManager.register_node(
        node_id="low-load-node",
        node_name="Idle Node",
        node_type="worker",
        cpu_logical=8,
        ram_gb=16.0,
        capabilities=["WEB_SEARCH"]
    )
    NodeManager.update_heartbeat(
        node_id="low-load-node",
        system_cpu_pct=15.0,
        system_ram_pct=25.0,
        active_tasks=0
    )

    # 3. Route task "web_search" -> should select low-load-node
    best_node = NodeSelector.select_node(action="web_search")
    assert best_node is not None
    assert best_node["node_id"] == "low-load-node"


def test_node_sweep_cleanup():
    """Verify that nodes with stale heartbeats are swept to offline status."""
    NodeManager.register_node(
        node_id="temp-node",
        node_name="Temporary Worker",
        node_type="worker",
        cpu_logical=4,
        ram_gb=8.0,
        capabilities=[]
    )

    # Backdate heartbeat to 2 minutes ago
    conn = ActionScheduler._get_conn()
    try:
        conn.execute("UPDATE node_registry SET last_heartbeat = ?", (time.time() - 120.0,))
        conn.commit()
    finally:
        conn.close()

    # Sweep nodes (threshold 60 seconds)
    swept = NodeManager.sweep_nodes(timeout_secs=60.0)
    assert swept == 1

    nodes = NodeManager.get_nodes()
    assert nodes[0]["status"] == "offline"


def test_websocket_heartbeat_flow():
    """Test full WebSocket registration and heartbeat message loop via TestClient."""
    client = TestClient(app)
    node_id = "test-ws-node-01"

    # Connect client
    with client.websocket_connect(f"/api/nodes/ws/{node_id}") as websocket:
        # Check that connection registration occurred
        assert NodeManager.get_connection(node_id) is not None

        # Send register packet over WS first
        websocket.send_text(json.dumps({
            "type": "register",
            "node_name": "WS Test Node",
            "node_type": "worker",
            "cpu_logical": 4,
            "ram_gb": 8.0,
            "capabilities": ["OCR"]
        }))
        time.sleep(0.1)  # Allow WS worker task to process

        # Verify heartbeat updates status to alive
        nodes = NodeManager.get_active_nodes()
        assert len(nodes) == 1
        assert nodes[0]["node_id"] == node_id
        assert nodes[0]["status"] == "alive"
        assert nodes[0]["node_name"] == "WS Test Node"
        assert "OCR" in nodes[0]["capabilities"]

        # Send heartbeat metrics
        websocket.send_text(json.dumps({
            "type": "heartbeat",
            "metrics": {
                "system_cpu_pct": 12.0,
                "system_ram_pct": 45.0,
                "active_tasks": 1
            }
        }))
        time.sleep(0.1)

        # Verify updated metrics in DB
        nodes = NodeManager.get_nodes()
        assert nodes[0]["system_cpu_pct"] == 12.0
        assert nodes[0]["system_ram_pct"] == 45.0
        assert nodes[0]["active_tasks"] == 1

    # Verify that closing websocket disconnects and marks node offline
    time.sleep(0.1)
    assert NodeManager.get_connection(node_id) is None
    nodes = NodeManager.get_nodes()
    assert nodes[0]["status"] == "offline"


def test_remote_task_delegation_websocket():
    """Test end-to-end task delegation: routing to active node and receiving result."""
    client = TestClient(app)
    node_id = "delegated-node-01"

    # Start a WebSocket mock worker
    with client.websocket_connect(f"/api/nodes/ws/{node_id}") as websocket:
        # Register worker capabilities
        websocket.send_text(json.dumps({
            "type": "register",
            "node_name": "Mock Worker",
            "node_type": "worker",
            "cpu_logical": 8,
            "ram_gb": 16.0,
            "capabilities": ["train_model"]
        }))
        time.sleep(0.1)

        # Confirm low-load-node is registered
        nodes = NodeManager.get_active_nodes()
        assert len(nodes) == 1

        # Enqueue action that targets capability of this node
        ActionScheduler.enqueue_action(
            agent_name="RESEARCHER",
            action="train_model",
            params={"dataset": "imagenet"},
            state={},
            priority=5
        )

        # In a separate thread or non-blocking async, we will call dispatch_next.
        # But wait: dispatch_next blocks waiting for the WebSocket response.
        # Since we are using TestClient in a single thread, we must spawn the dispatch
        # in a background thread so the test thread can read/write the WebSocket.
        import threading
        dispatch_result = {}
        def run_dispatch():
            try:
                res = ActionScheduler.dispatch_next()
                dispatch_result.update(res)
            except Exception as e:
                import traceback
                traceback.print_exc()
                dispatch_result["error"] = str(e)

        thread = threading.Thread(target=run_dispatch)
        thread.start()

        # Wait for WebSocket to receive task_request
        print("TEST: waiting for receive_text...")
        data = websocket.receive_text()
        print("TEST: received data:", data)
        packet = json.loads(data)
        assert packet["type"] == "task_request"
        assert packet["action"] == "train_model"
        assert packet["params"]["dataset"] == "imagenet"

        # Send task_response back
        print("TEST: sending task_response...")
        websocket.send_text(json.dumps({
            "type": "task_response",
            "queue_id": packet["queue_id"],
            "result": {"success": True, "epoch_loss": 0.012}
        }))
        print("TEST: sent task_response.")

        # Join dispatch thread
        print("TEST: joining dispatch thread...")
        thread.join(timeout=5.0)

        # Check result
        print("DEBUG dispatch_result:", dispatch_result)
        assert dispatch_result.get("status") == "dispatched"
        assert dispatch_result.get("final_status") == "COMPLETED"
        assert dispatch_result.get("result", {}).get("epoch_loss") == 0.012
