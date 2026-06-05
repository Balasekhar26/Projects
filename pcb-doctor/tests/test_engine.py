import unittest
import tempfile
from pathlib import Path

from pcb_doctor.data import BoardValidationError, load_board, load_measurements
from pcb_doctor.engine import DiagnosticEngine
from pcb_doctor.models import ExpectedRange, Measurement, NodeSpec


class DiagnosticEngineTest(unittest.TestCase):
    def test_traces_bad_downstream_node_to_nearest_fault_area(self):
        board = {
            "VIN": NodeSpec("VIN", "input", ExpectedRange(minimum=7, maximum=12)),
            "REG": NodeSpec("REG", "regulator", ExpectedRange(nominal=5, tolerance=0.2), upstream=("VIN",)),
            "MCU": NodeSpec(
                "MCU",
                "microcontroller",
                ExpectedRange(nominal=5, tolerance=0.2),
                expected_resistance=ExpectedRange(minimum=10),
                upstream=("REG",),
                components=("U2", "C5"),
            ),
        }
        report = DiagnosticEngine(board).diagnose(
            [
                Measurement("VIN", voltage=9.0),
                Measurement("REG", voltage=5.0),
                Measurement("MCU", voltage=0.2, resistance=1.0),
            ]
        )

        self.assertTrue(report.findings)
        self.assertEqual(report.root_cause_path, ("MCU",))
        self.assertEqual(report.findings[0].kind, "missing_voltage")

    def test_combines_visual_thermal_and_programmer_evidence(self):
        board = {
            "MCU": NodeSpec(
                "MCU",
                "microcontroller",
                ExpectedRange(nominal=3.3, tolerance=0.2),
                expected_resistance=ExpectedRange(minimum=10),
                components=("U2", "C5"),
            ),
        }
        report = DiagnosticEngine(board).diagnose(
            [
                Measurement(
                    "MCU",
                    voltage=3.2,
                    resistance=22.0,
                    thermal_delta_c=24.0,
                    visual_damage_confidence=0.86,
                    programmer_status="no_response",
                )
            ]
        )

        kinds = {finding.kind for finding in report.findings}
        self.assertIn("thermal_hotspot", kinds)
        self.assertIn("visual_damage", kinds)
        self.assertIn("programmer_communication_fault", kinds)
        self.assertTrue(any("thermal" in step.lower() for finding in report.findings for step in finding.next_steps))

    def test_board_loader_rejects_unknown_upstream_reference(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "bad-board.json"
            path.write_text(
                """
                {
                  "nodes": [
                    {"id": "REG", "expected_voltage": {"nominal": 5}, "upstream": ["VIN"]}
                  ]
                }
                """,
                encoding="utf-8",
            )

            with self.assertRaises(BoardValidationError):
                load_board(path)

    def test_measurement_loader_rejects_impossible_values(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "bad-measurements.json"
            path.write_text(
                """
                {
                  "measurements": [
                    {"node_id": "MCU", "voltage": -9999, "visual_damage_confidence": 2}
                  ]
                }
                """,
                encoding="utf-8",
            )

            with self.assertRaises(BoardValidationError):
                load_measurements(path)


if __name__ == "__main__":
    unittest.main()
