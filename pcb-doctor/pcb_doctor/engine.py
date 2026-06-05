from __future__ import annotations

from .models import DiagnosticReport, FaultFinding, Measurement, NodeSpec


class DiagnosticEngine:
    """Rule and graph based PCB fault inference."""

    def __init__(self, board: dict[str, NodeSpec]) -> None:
        self.board = board

    def diagnose(self, measurements: list[Measurement]) -> DiagnosticReport:
        by_node = {item.node_id: item for item in measurements}
        findings = sorted(
            self._findings(by_node),
            key=lambda item: item.score,
            reverse=True,
        )
        root_path = self._trace_root_path(findings, by_node)
        summary = self._summary(findings, root_path)
        return DiagnosticReport(
            findings=tuple(findings),
            root_cause_path=tuple(root_path),
            summary=summary,
        )

    def _findings(self, by_node: dict[str, Measurement]) -> list[FaultFinding]:
        findings: list[FaultFinding] = []
        for node_id, measurement in by_node.items():
            spec = self.board.get(node_id)
            if spec is None:
                findings.append(
                    FaultFinding(
                        node_id=node_id,
                        severity="warning",
                        score=30,
                        kind="unknown_node",
                        message="Measurement references a node that is not in the board model",
                        evidence={"measurement": measurement.__dict__},
                        probable_causes=("board model is incomplete",),
                        next_steps=("Add this node to the board JSON before trusting the diagnosis.",),
                    )
                )
                continue
            findings.extend(self._node_findings(spec, measurement))
        return findings

    def _node_findings(self, spec: NodeSpec, measurement: Measurement) -> list[FaultFinding]:
        findings: list[FaultFinding] = []
        voltage = measurement.voltage
        current = measurement.current
        resistance = measurement.resistance
        thermal_delta = measurement.thermal_delta_c
        visual_damage = measurement.visual_damage_confidence
        programmer_status = measurement.programmer_status.strip().lower()

        if spec.expected_voltage and voltage is not None and not spec.expected_voltage.contains(voltage):
            expected = spec.expected_voltage
            nominal = expected.nominal if expected.nominal is not None else expected.maximum
            missing_threshold = 0.05
            if nominal is not None:
                missing_threshold = max(missing_threshold, nominal * 0.1)

            if voltage <= missing_threshold:
                findings.append(
                    self._finding(
                        spec,
                        "critical",
                        95,
                        "missing_voltage",
                        "Expected voltage is absent",
                        {"observed_voltage": voltage},
                        ("open upstream path", "dead regulator", "short pulling rail to ground"),
                    )
                )
            elif nominal is not None and voltage < nominal:
                findings.append(
                    self._finding(
                        spec,
                        "high",
                        80,
                        "low_voltage",
                        "Observed voltage is below expected range",
                        {"observed_voltage": voltage},
                        ("overload", "weak regulator", "partial short", "high resistance upstream path"),
                    )
                )
            else:
                findings.append(
                    self._finding(
                        spec,
                        "medium",
                        65,
                        "high_voltage",
                        "Observed voltage is above expected range",
                        {"observed_voltage": voltage},
                        ("regulator feedback fault", "wrong supply", "open load path"),
                    )
                )

        if spec.expected_current and current is not None and not spec.expected_current.contains(current):
            findings.append(
                self._finding(
                    spec,
                    "high",
                    75,
                    "current_out_of_range",
                    "Observed current is outside expected range",
                    {"observed_current": current},
                    ("short circuit", "open load", "faulty downstream component"),
                )
            )

        if spec.expected_resistance and resistance is not None and not spec.expected_resistance.contains(resistance):
            if resistance <= 2:
                kind = "low_resistance_short"
                causes = ("short to ground", "failed capacitor", "solder bridge")
            else:
                kind = "resistance_out_of_range"
                causes = ("open component", "cracked trace", "wrong component value")
            findings.append(
                self._finding(
                    spec,
                    "high",
                    78,
                    kind,
                    "Observed resistance is outside expected range",
                    {"observed_resistance": resistance},
                    causes,
                )
            )

        if thermal_delta is not None and thermal_delta >= 18.0:
            findings.append(
                self._finding(
                    spec,
                    "high",
                    82,
                    "thermal_hotspot",
                    "Thermal camera indicates abnormal heating around this node",
                    {"thermal_delta_c": thermal_delta},
                    ("shorted component", "overloaded IC", "reverse polarity damage", "regulator stress"),
                )
            )

        if visual_damage is not None and visual_damage >= 0.75:
            findings.append(
                self._finding(
                    spec,
                    "high",
                    79,
                    "visual_damage",
                    "Camera inspection indicates likely visible damage",
                    {"visual_damage_confidence": visual_damage},
                    ("burn mark", "cracked package", "corrosion", "solder bridge", "lifted pad"),
                )
            )

        if programmer_status in {"no_response", "timeout", "id_mismatch", "locked"}:
            findings.append(
                self._finding(
                    spec,
                    "medium",
                    68,
                    "programmer_communication_fault",
                    "Programmer/debug adapter could not communicate reliably with this node",
                    {"programmer_status": programmer_status},
                    ("missing power rail", "reset held low", "clock fault", "damaged MCU", "wrong programming header"),
                )
            )

        return findings

    def _finding(
        self,
        spec: NodeSpec,
        severity: str,
        score: int,
        kind: str,
        message: str,
        evidence: dict,
        probable_causes: tuple[str, ...],
    ) -> FaultFinding:
        steps = (
            f"Measure upstream node(s): {', '.join(spec.upstream) or 'none'}",
            "Capture a close-up image and thermal reading for this area if available.",
            "If this node is programmable, retry read-id/connect with current-limited bench power.",
            f"Inspect component(s): {', '.join(spec.components) or spec.label}",
            "Record the next measurement and rerun PCB Doctor.",
        )
        return FaultFinding(
            node_id=spec.node_id,
            severity=severity,
            score=score,
            kind=kind,
            message=message,
            evidence=evidence | {"label": spec.label},
            probable_causes=probable_causes,
            next_steps=steps,
        )

    def _trace_root_path(self, findings: list[FaultFinding], by_node: dict[str, Measurement]) -> list[str]:
        if not findings:
            return []
        start = findings[0].node_id
        path = [start]
        current = start
        seen = {start}

        while True:
            spec = self.board.get(current)
            if spec is None or not spec.upstream:
                return list(reversed(path))

            bad_upstream = [
                upstream
                for upstream in spec.upstream
                if upstream in by_node and any(f.node_id == upstream for f in findings)
            ]
            if not bad_upstream:
                return list(reversed(path))

            current = bad_upstream[0]
            if current in seen:
                return list(reversed(path))
            seen.add(current)
            path.append(current)

    def _summary(self, findings: list[FaultFinding], root_path: list[str]) -> str:
        if not findings:
            return "No faults detected from the provided measurements."
        root = root_path[0] if root_path else findings[0].node_id
        top = findings[0]
        return f"Most likely root area: {root}. Top finding: {top.kind} at {top.node_id}."
