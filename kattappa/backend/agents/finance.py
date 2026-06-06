from __future__ import annotations

import re
from pathlib import Path

from backend.core.model_router import ask_model
from backend.tools.finance_brain import (
    explain_forecast,
    forecast_ohlcv,
    kronos_status,
    load_ohlcv_csv,
)

CSV_PATH_PATTERN = re.compile(
    r"([A-Za-z]:\\[^\n\r\"']+?\.csv|[^\s\"']+\.csv)", re.IGNORECASE
)


def finance_node(state):
    user_input = state["user_input"]
    csv_path = _extract_csv_path(user_input)
    wants_real_kronos = any(
        token in user_input.lower()
        for token in ("real kronos", "use kronos", "kronos model")
    )

    if csv_path:
        try:
            candles = load_ohlcv_csv(csv_path)
            result = forecast_ohlcv(
                candles,
                horizon=_extract_horizon(user_input),
                use_kronos=wants_real_kronos,
            )
            state["result"] = explain_forecast(result)
            state["tool_request"] = {
                **(state.get("tool_request") or {}),
                "finance_result": result,
            }
            state["logs"].append("finance: analyzed OHLCV CSV")
            return state
        except Exception as exc:
            state["result"] = (
                f"I found a CSV path, but Finance Brain could not analyze it: {exc}"
            )
            state["logs"].append("finance: CSV analysis failed")
            return state

    status = kronos_status()
    state["result"] = ask_model(
        "Explain how Bala should use the Kattappa AI OS Finance Brain with Kronos. "
        "Be practical and concise. Mention that OHLCV candles are required, real Kronos mode can download "
        "Hugging Face weights on first use, and predictions are not financial advice.\n\n"
        f"User request: {user_input}\nKronos status: {status}",
        role="fast",
    )
    state["tool_request"] = {
        **(state.get("tool_request") or {}),
        "kronos_status": status,
    }
    state["logs"].append("finance: explained Kronos usage")
    return state


def _extract_csv_path(text: str) -> str | None:
    match = CSV_PATH_PATTERN.search(text)
    if not match:
        return None
    return str(Path(match.group(1).strip()))


def _extract_horizon(text: str) -> int:
    match = re.search(r"(?:horizon|next|forecast)\s+(\d+)", text, re.IGNORECASE)
    if not match:
        return 5
    return max(1, min(int(match.group(1)), 512))
