from __future__ import annotations

import json
import math
from pathlib import Path

from .models import ExpectedRange, Measurement, NodeSpec


class BoardValidationError(ValueError):
    pass


def load_board(path: Path) -> dict[str, NodeSpec]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    validate_board_model(raw)
    nodes: dict[str, NodeSpec] = {}
    for item in raw.get("nodes", []):
        node_id = str(item["id"])
        nodes[node_id] = NodeSpec(
            node_id=node_id,
            label=str(item.get("label", node_id)),
            expected_voltage=_range(item.get("expected_voltage")),
            expected_resistance=_range(item.get("expected_resistance")),
            expected_current=_range(item.get("expected_current")),
            upstream=tuple(str(value) for value in item.get("upstream", [])),
            components=tuple(str(value) for value in item.get("components", [])),
        )
    return nodes


def load_measurements(path: Path) -> list[Measurement]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    validate_measurements(raw)
    return [
        Measurement(
            node_id=str(item["node_id"]),
            voltage=_optional_float(item.get("voltage")),
            resistance=_optional_float(item.get("resistance")),
            current=_optional_float(item.get("current")),
            note=str(item.get("note", "")),
            thermal_delta_c=_optional_float(item.get("thermal_delta_c")),
            visual_damage_confidence=_optional_float(item.get("visual_damage_confidence")),
            programmer_status=str(item.get("programmer_status", "")),
        )
        for item in raw.get("measurements", [])
    ]


def validate_board_model(raw: dict) -> None:
    nodes = raw.get("nodes", [])
    if not isinstance(nodes, list) or not nodes:
        raise BoardValidationError("Board model must contain a non-empty nodes list")

    seen: set[str] = set()
    upstream_refs: list[tuple[str, str]] = []
    for item in nodes:
        if not isinstance(item, dict) or not str(item.get("id", "")).strip():
            raise BoardValidationError("Every board node must have an id")
        node_id = str(item["id"])
        if node_id in seen:
            raise BoardValidationError(f"Duplicate board node id: {node_id}")
        seen.add(node_id)
        for field in ("expected_voltage", "expected_resistance", "expected_current"):
            _validate_range(item.get(field), field, node_id)
        for upstream in item.get("upstream", []):
            upstream_refs.append((node_id, str(upstream)))

    for node_id, upstream in upstream_refs:
        if upstream not in seen:
            raise BoardValidationError(
                f"Node {node_id} references unknown upstream node {upstream}"
            )


def validate_measurements(raw: dict) -> None:
    measurements = raw.get("measurements", [])
    if not isinstance(measurements, list):
        raise BoardValidationError("Measurements must be a list")

    for item in measurements:
        if not isinstance(item, dict) or not str(item.get("node_id", "")).strip():
            raise BoardValidationError("Every measurement must include node_id")
        node_id = str(item["node_id"])
        _validate_optional_number(item.get("voltage"), "voltage", node_id, minimum=-1000, maximum=1000)
        _validate_optional_number(item.get("current"), "current", node_id, minimum=-1000, maximum=1000)
        _validate_optional_number(item.get("resistance"), "resistance", node_id, minimum=0, maximum=1_000_000_000)
        _validate_optional_number(item.get("thermal_delta_c"), "thermal_delta_c", node_id, minimum=-273.15, maximum=500)
        _validate_optional_number(
            item.get("visual_damage_confidence"),
            "visual_damage_confidence",
            node_id,
            minimum=0,
            maximum=1,
        )


def _validate_range(raw: object, field: str, node_id: str) -> None:
    if raw in (None, ""):
        return
    if not isinstance(raw, dict):
        raise BoardValidationError(f"{node_id}.{field} must be an object")
    minimum = _optional_float(raw.get("min"))
    maximum = _optional_float(raw.get("max"))
    nominal = _optional_float(raw.get("nominal"))
    tolerance = _optional_float(raw.get("tolerance"))
    for name, value in (
        ("min", minimum),
        ("max", maximum),
        ("nominal", nominal),
        ("tolerance", tolerance),
    ):
        if value is not None and not math.isfinite(value):
            raise BoardValidationError(f"{node_id}.{field}.{name} must be finite")
    if minimum is not None and maximum is not None and minimum > maximum:
        raise BoardValidationError(f"{node_id}.{field} min cannot exceed max")
    if tolerance is not None and tolerance < 0:
        raise BoardValidationError(f"{node_id}.{field} tolerance cannot be negative")


def _validate_optional_number(
    value: object,
    field: str,
    node_id: str,
    *,
    minimum: float,
    maximum: float,
) -> None:
    converted = _optional_float(value)
    if converted is None:
        return
    if not math.isfinite(converted):
        raise BoardValidationError(f"{node_id}.{field} must be finite")
    if converted < minimum or converted > maximum:
        raise BoardValidationError(
            f"{node_id}.{field} must be between {minimum:g} and {maximum:g}"
        )


def _range(raw: dict | None) -> ExpectedRange | None:
    if not raw:
        return None
    return ExpectedRange(
        minimum=_optional_float(raw.get("min")),
        maximum=_optional_float(raw.get("max")),
        nominal=_optional_float(raw.get("nominal")),
        tolerance=_optional_float(raw.get("tolerance")),
    )


def _optional_float(value: object) -> float | None:
    if value is None or value == "":
        return None
    return float(value)
