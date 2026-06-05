from __future__ import annotations

import csv
import math
import statistics
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

PROJECTS_ROOT = Path(__file__).resolve().parents[3]
EXTERNAL_PROJECTS_ROOT = (
    PROJECTS_ROOT / "external-projects"
    if (PROJECTS_ROOT / "external-projects").exists()
    else PROJECTS_ROOT / "bin" / "external-projects"
)
KRONOS_ROOT = EXTERNAL_PROJECTS_ROOT / "Kronos"
DEFAULT_KRONOS_TOKENIZER = "NeoQuasar/Kronos-Tokenizer-base"
DEFAULT_KRONOS_MODEL = "NeoQuasar/Kronos-small"
REQUIRED_OHLC_COLUMNS = ("open", "high", "low", "close")
OPTIONAL_COLUMNS = ("timestamp", "timestamps", "volume", "amount")


@dataclass(frozen=True)
class NormalizedCandle:
    timestamp: str | None
    open: float
    high: float
    low: float
    close: float
    volume: float
    amount: float | None = None

    def to_dict(self) -> dict[str, float | str | None]:
        row: dict[str, float | str | None] = {
            "timestamp": self.timestamp,
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
        }
        if self.amount is not None:
            row["amount"] = self.amount
        return row


def kronos_status() -> dict[str, Any]:
    imports = {
        "numpy": _has_module("numpy"),
        "pandas": _has_module("pandas"),
        "torch": _has_module("torch"),
        "einops": _has_module("einops"),
        "huggingface_hub": _has_module("huggingface_hub"),
        "safetensors": _has_module("safetensors"),
    }
    return {
        "installed": KRONOS_ROOT.exists(),
        "path": str(KRONOS_ROOT),
        "license": "MIT" if (KRONOS_ROOT / "LICENSE").exists() else "unknown",
        "imports": imports,
        "ready_for_real_kronos": KRONOS_ROOT.exists() and all(imports.values()),
        "default_tokenizer": DEFAULT_KRONOS_TOKENIZER,
        "default_model": DEFAULT_KRONOS_MODEL,
        "first_real_run_note": (
            "Real Kronos mode downloads Hugging Face model weights on first use. "
            "Use use_kronos=false for the built-in local fallback forecaster."
        ),
    }


def load_ohlcv_csv(path: str | Path) -> list[dict[str, Any]]:
    csv_path = Path(path).expanduser()
    if not csv_path.exists():
        raise FileNotFoundError(f"OHLCV CSV not found: {csv_path}")
    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        return [dict(row) for row in reader]


def forecast_ohlcv(
    candles: list[dict[str, Any]],
    horizon: int = 5,
    *,
    use_kronos: bool = False,
    tokenizer_name: str = DEFAULT_KRONOS_TOKENIZER,
    model_name: str = DEFAULT_KRONOS_MODEL,
) -> dict[str, Any]:
    normalized = normalize_candles(candles)
    if horizon < 1 or horizon > 512:
        raise ValueError("horizon must be between 1 and 512 candles.")

    if use_kronos:
        try:
            return _forecast_with_kronos(
                normalized, horizon, tokenizer_name, model_name
            )
        except Exception as exc:
            fallback = _fallback_forecast(normalized, horizon)
            fallback["engine"] = "sekhar-fallback-after-kronos-error"
            fallback["kronos_error"] = str(exc)
            return fallback

    return _fallback_forecast(normalized, horizon)


def compare_forecasts(
    candles: list[dict[str, Any]],
    horizon: int = 5,
    *,
    tokenizer_name: str = DEFAULT_KRONOS_TOKENIZER,
    model_name: str = DEFAULT_KRONOS_MODEL,
) -> dict[str, Any]:
    normalized = normalize_candles(candles)
    if horizon < 1 or horizon > 512:
        raise ValueError("horizon must be between 1 and 512 candles.")

    baseline = _fallback_forecast(normalized, horizon)
    status = kronos_status()
    kronos_result: dict[str, Any] | None = None
    kronos_error: str | None = None
    fallback_after_error: dict[str, Any] | None = None

    if status["ready_for_real_kronos"]:
        try:
            kronos_result = _forecast_with_kronos(
                normalized, horizon, tokenizer_name, model_name
            )
        except Exception as exc:
            kronos_error = str(exc)
    else:
        missing_imports = [
            name for name, installed in status["imports"].items() if not installed
        ]
        if not status["installed"]:
            kronos_error = f"Kronos repository is not installed at {KRONOS_ROOT}"
        else:
            kronos_error = (
                "Kronos runtime is not ready. Missing imports: "
                + (", ".join(missing_imports) if missing_imports else "unknown")
            )

    if kronos_error:
        fallback_after_error = _fallback_forecast(normalized, horizon)
        fallback_after_error["engine"] = "sekhar-fallback-after-kronos-error"
        fallback_after_error["kronos_error"] = kronos_error

    return {
        "mode": "baseline-vs-kronos",
        "input_candles": len(normalized),
        "horizon": horizon,
        "kronos_status": status,
        "baseline": baseline,
        "kronos": kronos_result,
        "fallback_after_kronos_error": fallback_after_error,
        "kronos_error": kronos_error,
        "risk_warning": _risk_warning(),
    }


def explain_forecast(result: dict[str, Any]) -> str:
    summary = result.get("summary", {})
    engine = result.get("engine", "unknown")
    signal = summary.get("trend_signal", "unknown")
    volatility = summary.get("volatility", "unknown")
    confidence = summary.get("confidence", "low")
    last_close = summary.get("last_close")
    final_close = summary.get("final_predicted_close")
    warning = result.get("risk_warning", _risk_warning())
    return (
        f"Finance Brain used {engine}. Trend signal: {signal}. "
        f"Volatility: {volatility}. Confidence: {confidence}. "
        f"Last close: {last_close}. Forecast final close: {final_close}. "
        f"{warning}"
    )


def normalize_candles(candles: list[dict[str, Any]]) -> list[NormalizedCandle]:
    if len(candles) < 3:
        raise ValueError("At least 3 OHLCV candles are required.")

    normalized: list[NormalizedCandle] = []
    for index, candle in enumerate(candles):
        missing = [
            column
            for column in REQUIRED_OHLC_COLUMNS
            if column not in candle or candle[column] in (None, "")
        ]
        if missing:
            raise ValueError(
                f"Candle {index} is missing required columns: {', '.join(missing)}"
            )

        timestamp = candle.get("timestamp") or candle.get("timestamps")
        open_price = _to_float(candle["open"], f"candle {index} open")
        high = _to_float(candle["high"], f"candle {index} high")
        low = _to_float(candle["low"], f"candle {index} low")
        close = _to_float(candle["close"], f"candle {index} close")
        volume = _to_float(candle.get("volume", 0.0), f"candle {index} volume")
        amount = (
            None
            if candle.get("amount") in (None, "")
            else _to_float(candle["amount"], f"candle {index} amount")
        )

        if high < max(open_price, close) or low > min(open_price, close):
            raise ValueError(f"Candle {index} has inconsistent OHLC values.")
        if close <= 0 or open_price <= 0 or high <= 0 or low <= 0:
            raise ValueError(f"Candle {index} price values must be positive.")
        if volume < 0:
            raise ValueError(f"Candle {index} volume must not be negative.")

        normalized.append(
            NormalizedCandle(
                timestamp=str(timestamp) if timestamp not in (None, "") else None,
                open=open_price,
                high=high,
                low=low,
                close=close,
                volume=volume,
                amount=amount,
            )
        )

    return normalized


def _forecast_with_kronos(
    candles: list[NormalizedCandle],
    horizon: int,
    tokenizer_name: str,
    model_name: str,
) -> dict[str, Any]:
    if not KRONOS_ROOT.exists():
        raise RuntimeError(f"Kronos repository is not installed at {KRONOS_ROOT}")
    if str(KRONOS_ROOT) not in sys.path:
        sys.path.insert(0, str(KRONOS_ROOT))

    import pandas as pd
    from model import Kronos, KronosPredictor, KronosTokenizer

    rows = [candle.to_dict() for candle in candles]
    df = pd.DataFrame(rows)
    timestamp_column = "timestamp"
    if df[timestamp_column].isnull().any():
        raise ValueError("Real Kronos mode requires timestamps for every input candle.")

    x_timestamp = pd.to_datetime(df[timestamp_column])
    y_timestamp = _future_timestamps(x_timestamp, horizon)
    kronos_df = df[["open", "high", "low", "close", "volume"]].copy()
    if "amount" in df.columns and not df["amount"].isnull().all():
        kronos_df["amount"] = df["amount"].fillna(
            df["volume"] * df[["open", "high", "low", "close"]].mean(axis=1)
        )

    tokenizer = KronosTokenizer.from_pretrained(tokenizer_name)
    model = Kronos.from_pretrained(model_name)
    predictor = KronosPredictor(model, tokenizer, max_context=min(512, len(kronos_df)))
    pred_df = predictor.predict(
        df=kronos_df,
        x_timestamp=x_timestamp,
        y_timestamp=y_timestamp,
        pred_len=horizon,
        T=1.0,
        top_p=0.9,
        sample_count=1,
        verbose=False,
    )

    predictions = [
        {
            "timestamp": str(index),
            "open": float(row["open"]),
            "high": float(row["high"]),
            "low": float(row["low"]),
            "close": float(row["close"]),
            "volume": float(row["volume"]),
            "amount": float(row["amount"]) if "amount" in row else None,
        }
        for index, row in pred_df.iterrows()
    ]
    return _result("kronos", candles, predictions)


def _fallback_forecast(candles: list[NormalizedCandle], horizon: int) -> dict[str, Any]:
    recent = candles[-min(len(candles), 48) :]
    closes = [candle.close for candle in recent]
    returns = [
        (closes[index] / closes[index - 1]) - 1.0
        for index in range(1, len(closes))
        if closes[index - 1] > 0
    ]
    drift = _clamp(statistics.fmean(returns) if returns else 0.0, -0.03, 0.03)
    volatility = statistics.pstdev(returns) if len(returns) > 1 else 0.0
    average_range = statistics.fmean(
        max((candle.high - candle.low) / candle.close, 0.0) for candle in recent
    )
    average_volume = statistics.fmean(candle.volume for candle in recent)

    predictions: list[dict[str, float | str | None]] = []
    previous_close = candles[-1].close
    next_times = _fallback_future_timestamps(candles, horizon)
    for step in range(horizon):
        open_price = previous_close
        close = max(open_price * (1.0 + drift), 0.00000001)
        noise_band = max(average_range, volatility * 2.0, 0.001)
        high = max(open_price, close) * (1.0 + noise_band / 2.0)
        low = min(open_price, close) * max(1.0 - noise_band / 2.0, 0.00000001)
        volume = max(average_volume * (1.0 + min(abs(drift) * 5.0, 0.25)), 0.0)
        predictions.append(
            {
                "timestamp": next_times[step],
                "open": round(open_price, 8),
                "high": round(high, 8),
                "low": round(low, 8),
                "close": round(close, 8),
                "volume": round(volume, 8),
            }
        )
        previous_close = close

    return _result("sekhar-local-ohlcv-baseline", candles, predictions)


def _result(
    engine: str,
    candles: list[NormalizedCandle],
    predictions: list[dict[str, Any]],
) -> dict[str, Any]:
    last_close = candles[-1].close
    final_close = float(predictions[-1]["close"]) if predictions else last_close
    pct_change = ((final_close / last_close) - 1.0) * 100.0 if last_close else 0.0
    returns = [
        (candles[index].close / candles[index - 1].close) - 1.0
        for index in range(1, len(candles))
        if candles[index - 1].close > 0
    ]
    vol = statistics.pstdev(returns[-48:]) if len(returns) > 1 else 0.0
    return {
        "engine": engine,
        "input_candles": len(candles),
        "predictions": predictions,
        "summary": {
            "last_close": round(last_close, 8),
            "final_predicted_close": round(final_close, 8),
            "predicted_change_percent": round(pct_change, 4),
            "trend_signal": _trend_signal(pct_change),
            "volatility": _volatility_label(vol),
            "confidence": _confidence_label(len(candles), vol, engine),
        },
        "risk_warning": _risk_warning(),
    }


def _future_timestamps(x_timestamp: Any, horizon: int) -> Any:
    import pandas as pd

    if len(x_timestamp) >= 2:
        diffs = x_timestamp.sort_values().diff().dropna()
        freq = diffs.median() if not diffs.empty else pd.Timedelta(minutes=1)
    else:
        freq = pd.Timedelta(minutes=1)
    start = x_timestamp.iloc[-1] + freq
    return pd.date_range(start=start, periods=horizon, freq=freq)


def _fallback_future_timestamps(
    candles: list[NormalizedCandle], horizon: int
) -> list[str | None]:
    parsed = [
        _parse_timestamp(candle.timestamp) for candle in candles if candle.timestamp
    ]
    if len(parsed) < 2:
        return [f"step_{index + 1}" for index in range(horizon)]
    diffs = [
        (parsed[index] - parsed[index - 1]).total_seconds()
        for index in range(1, len(parsed))
        if (parsed[index] - parsed[index - 1]).total_seconds() > 0
    ]
    seconds = statistics.median(diffs) if diffs else 60.0
    current = parsed[-1]
    return [
        (current + timedelta(seconds=seconds * (index + 1))).isoformat()
        for index in range(horizon)
    ]


def _parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    text = value.strip().replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        for pattern in (
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M",
            "%d-%m-%Y %H:%M:%S",
            "%H:%M",
        ):
            try:
                return datetime.strptime(value.strip(), pattern)
            except ValueError:
                continue
    return None


def _trend_signal(pct_change: float) -> str:
    if pct_change >= 1.0:
        return "upward"
    if pct_change <= -1.0:
        return "downward"
    if pct_change >= 0.15:
        return "slightly upward"
    if pct_change <= -0.15:
        return "slightly downward"
    return "sideways"


def _volatility_label(volatility: float) -> str:
    if volatility >= 0.04:
        return "high"
    if volatility >= 0.012:
        return "medium"
    return "low"


def _confidence_label(candle_count: int, volatility: float, engine: str) -> str:
    if engine == "kronos" and candle_count >= 128 and volatility < 0.04:
        return "medium"
    if candle_count >= 48 and volatility < 0.025:
        return "low-medium"
    return "low"


def _risk_warning() -> str:
    return (
        "This is market analysis, not a guaranteed trading signal or financial advice. "
        "News, liquidity shocks, and exchange failures can invalidate any forecast."
    )


def _to_float(value: Any, label: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be numeric.") from exc
    if not math.isfinite(number):
        raise ValueError(f"{label} must be finite.")
    return number


def _clamp(value: float, low: float, high: float) -> float:
    return min(max(value, low), high)


def _has_module(name: str) -> bool:
    try:
        __import__(name)
        return True
    except Exception:
        return False
