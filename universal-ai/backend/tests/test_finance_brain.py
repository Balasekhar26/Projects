from fastapi.testclient import TestClient

from backend.agents.planner import route_task
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


def test_kronos_status_reports_installation() -> None:
    status = kronos_status()
    assert "installed" in status
    assert "imports" in status
    assert status["default_model"] == "NeoQuasar/Kronos-small"


def test_fallback_finance_forecast_returns_predictions() -> None:
    result = forecast_ohlcv(SAMPLE_CANDLES, horizon=3, use_kronos=False)
    assert result["engine"] == "sekhar-local-ohlcv-baseline"
    assert len(result["predictions"]) == 3
    assert "trend_signal" in result["summary"]
    assert "financial advice" in result["risk_warning"]


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


def test_finance_compare_returns_baseline_and_kronos_detail(monkeypatch) -> None:
    monkeypatch.setattr(finance_brain, "_forecast_with_kronos", _raise_kronos_probe)
    result = compare_forecasts(SAMPLE_CANDLES, horizon=2)
    assert result["mode"] == "baseline-vs-kronos"
    assert result["baseline"]["engine"] == "sekhar-local-ohlcv-baseline"
    assert len(result["baseline"]["predictions"]) == 2
    assert "kronos_status" in result
    assert "risk_warning" in result


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


def test_finance_agent_route() -> None:
    decision = route_task("use kronos to forecast BTC OHLCV candles")
    assert decision["agent"] == "finance"


def _raise_kronos_probe(*args, **kwargs) -> None:
    raise RuntimeError("Kronos probe disabled in tests.")
