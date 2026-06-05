import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from asa import pipeline as pipeline_module
from asa.config import load_config
from asa.models import ProcessInfo, SystemMap
from asa.pipeline import run_pipeline


class PipelineTest(unittest.TestCase):
    def test_pipeline_records_layer_error_and_keeps_report(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            policy_file = root / "asa-policy.json"
            policy_file.write_text(
                json.dumps({"suspicious_process_patterns": ["xmrig"]}),
                encoding="utf-8",
            )
            config = load_config(root=root, policy_file=policy_file)
            system_map = SystemMap(
                processes=[
                    ProcessInfo(
                        pid=4242,
                        user="tester",
                        name="xmrig-worker",
                        exe=str(root / "xmrig-worker.exe"),
                    )
                ]
            )

            with (
                patch.object(pipeline_module.SystemMapper, "build", return_value=system_map),
                patch.object(
                    pipeline_module.HardeningLayer,
                    "audit",
                    side_effect=RuntimeError("hardening unavailable"),
                ),
            ):
                report = run_pipeline(config)

            self.assertEqual(report.system_counts["processes"], 1)
            self.assertEqual(report.findings[0].kind, "suspicious_process_name")
            self.assertEqual(report.errors[0]["layer"], "layer4_harden")
            self.assertEqual(report.severity, "critical")


if __name__ == "__main__":
    unittest.main()
