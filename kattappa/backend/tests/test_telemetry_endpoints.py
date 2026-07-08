from fastapi.testclient import TestClient
from backend.main import app
from backend.core.cos.kernel import KERNEL
from backend.core.ledger.models.event import LedgerEvent
from backend.core.ledger.models.enums import EventType

client = TestClient(app)


def test_telemetry_endpoints():
    # 1. Test record metric endpoint
    response = client.post(
        "/api/v1/telemetry/record", json={"metric_name": "cpu_usage", "value": 45.5}
    )
    assert response.status_code == 200
    assert response.json()["status"] == "success"
    assert response.json()["value"] == 45.5

    # 2. Test generate report endpoint
    response = client.get("/api/v1/telemetry/report")
    assert response.status_code == 200
    report = response.json()
    assert "cpu_usage" in report
    assert report["cpu_usage"]["count"] == 1.0
    assert report["cpu_usage"]["mean"] == 45.5

    # 3. Test list ledger events endpoint
    assert KERNEL.ledger is not None
    e1 = LedgerEvent(
        event_id="t1",
        parent_event_ids=[],
        goal_id="g_tel",
        session_id="s1",
        correlation_id="c1",
        timestamp_utc=100.0,
        actor="user",
        subsystem="scheduler",
        event_type=EventType.GOAL_CREATED,
        payload={},
    )
    e2 = LedgerEvent(
        event_id="t2",
        parent_event_ids=["t1"],
        goal_id="g_tel",
        session_id="s1",
        correlation_id="c1",
        timestamp_utc=101.0,
        actor="system",
        subsystem="planner",
        event_type=EventType.PLAN_GENERATED,
        payload={},
    )
    try:
        KERNEL.ledger.append(e1)
        KERNEL.ledger.append(e2)
    except ValueError:
        pass

    response = client.get("/api/v1/telemetry/events")
    assert response.status_code == 200
    events = response.json()
    assert len(events) >= 2
    assert any(ev["event_id"] == "t1" for ev in events)

    # 4. Test ancestors endpoint
    response = client.get("/api/v1/telemetry/events/t2/ancestors")
    assert response.status_code == 200
    ancestors = response.json()
    assert len(ancestors) == 1
    assert ancestors[0]["event_id"] == "t1"

    # 5. Test descendants endpoint
    response = client.get("/api/v1/telemetry/events/t1/descendants")
    assert response.status_code == 200
    descendants = response.json()
    assert len(descendants) == 1
    assert descendants[0]["event_id"] == "t2"
