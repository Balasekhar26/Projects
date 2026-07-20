import ast
import inspect
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.agents.planner import route_task
from backend.core.readiness import runtime_readiness
from backend.main import app
import backend.tools.finance_brain as finance_brain
from backend.tools.finance_brain import compare_forecasts, forecast_ohlcv, kronos_status

SAMPLE_CANDLES = [
    {
        "timestamp": "2026-05-31T10:00:00",
        "open": 100,
        "high": 102,
        "low": 99,
        "close": 101,
        "volume": 1200,
    },
    {
        "timestamp": "2026-05-31T10:05:00",
        "open": 101,
        "high": 103,
        "low": 100,
        "close": 102,
        "volume": 1100,
    },
    {
        "timestamp": "2026-05-31T10:10:00",
        "open": 102,
        "high": 104,
        "low": 101,
        "close": 103,
        "volume": 1250,
    },
    {
        "timestamp": "2026-05-31T10:15:00",
        "open": 103,
        "high": 105,
        "low": 102,
        "close": 104,
        "volume": 1300,
    },
]


@pytest.mark.unit
def test_kronos_status_reports_installation() -> None:
    status = kronos_status()
    assert status["installed"] is True
    assert "imports" in status
    assert status["source"] == "vendored"
    assert Path(status["path"]).resolve() == finance_brain.KRONOS_VENDOR.resolve()
    assert status["default_model"] == "NeoQuasar/Kronos-small"


@pytest.mark.unit
def test_fallback_finance_forecast_returns_predictions() -> None:
    result = forecast_ohlcv(SAMPLE_CANDLES, horizon=3, use_kronos=False)
    assert result["engine"] == "kattappa-local-ohlcv-baseline"
    assert len(result["predictions"]) == 3
    assert "trend_signal" in result["summary"]
    assert "financial advice" in result["risk_warning"]


@pytest.mark.integration
def test_finance_forecast_endpoint() -> None:
    client = TestClient(app)
    response = client.post(
        "/finance/forecast",
        json={"candles": SAMPLE_CANDLES, "horizon": 2, "use_kronos": False},
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data["predictions"]) == 2
    assert data["summary"]["last_close"] == 104


@pytest.mark.unit
def test_finance_compare_returns_baseline_and_kronos_detail(monkeypatch) -> None:
    monkeypatch.setattr(finance_brain, "_forecast_with_kronos", _raise_kronos_probe)
    result = compare_forecasts(SAMPLE_CANDLES, horizon=2)
    assert result["mode"] == "baseline-vs-kronos"
    assert result["baseline"]["engine"] == "kattappa-local-ohlcv-baseline"
    assert len(result["baseline"]["predictions"]) == 2
    assert "kronos_status" in result
    assert "risk_warning" in result


@pytest.mark.integration
def test_finance_compare_endpoint(monkeypatch) -> None:
    monkeypatch.setattr(finance_brain, "_forecast_with_kronos", _raise_kronos_probe)
    client = TestClient(app)
    response = client.post(
        "/finance/compare",
        json={"candles": SAMPLE_CANDLES, "horizon": 2, "use_kronos": True},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["baseline"]["input_candles"] == 4
    assert data["kronos"] is not None or data["fallback_after_kronos_error"] is not None


@pytest.mark.integration
def test_ready_endpoint_reports_vendored_finance_without_loading_model(
    monkeypatch,
) -> None:
    def status_only() -> dict[str, object]:
        return {"installed": True, "source": "vendored"}

    monkeypatch.setattr("backend.core.readiness.kronos_status", status_only)
    client = TestClient(app)
    response = client.get("/ready")
    alias_response = client.get("/api/v1/ready")

    assert response.status_code == 200
    assert alias_response.status_code == 200
    assert alias_response.json() == response.json()
    assert response.json() == {
        "status": "ready",
        "ready": True,
        "finance_brain": {
            "available": True,
            "source": "vendored",
            "execution_enabled": False,
        },
    }


@pytest.mark.unit
def test_external_and_unavailable_kronos_sources_are_explicit(
    monkeypatch, tmp_path: Path
) -> None:
    external = tmp_path / "Kronos"
    external.mkdir()
    monkeypatch.setattr(finance_brain, "KRONOS_ROOT", external)
    assert kronos_status()["source"] == "external"

    monkeypatch.setattr(finance_brain, "KRONOS_ROOT", tmp_path / "missing")
    assert kronos_status()["source"] == "unavailable"


@pytest.mark.unit
def test_finance_readiness_never_enables_execution(monkeypatch) -> None:
    monkeypatch.setattr(
        "backend.core.readiness.kronos_status",
        lambda: {"installed": True, "source": "vendored"},
    )
    assert runtime_readiness().finance_brain.execution_enabled is False


@pytest.mark.safety
@pytest.mark.unit
def test_finance_brain_exposes_no_order_execution_api() -> None:
    forbidden_terms = ("place_order", "submit_order", "cancel_order", "modify_order")
    assert not any(hasattr(finance_brain, name) for name in forbidden_terms)

    tree = ast.parse(inspect.getsource(finance_brain))
    imported_modules = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    imported_modules.update(
        node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
    )
    assert not any("broker" in module.lower() for module in imported_modules)


@pytest.mark.integration
@pytest.mark.slow
def test_vendored_kronos_package_imports() -> None:
    from backend.vendor.kronos.model import Kronos, KronosPredictor, KronosTokenizer

    assert all((Kronos, KronosPredictor, KronosTokenizer))


@pytest.mark.unit
def test_finance_agent_route() -> None:
    decision = route_task("use kronos to forecast BTC OHLCV candles")
    assert decision["agent"] == "finance"


def _raise_kronos_probe(*args, **kwargs) -> None:
    raise RuntimeError("Kronos probe disabled in tests.")
