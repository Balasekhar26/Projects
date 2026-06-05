from asa.attribution import build_attribution_hint
from asa.config import load_config
from asa.learning import BaselineStore
from asa.models import NetworkConnection, SystemMap
from asa.threat_detection import ThreatDetectionEngine


def test_attribution_hint_never_claims_exact_hacker_location():
    hint = build_attribution_hint("8.8.8.8")
    assert hint.scope == "public_internet"
    assert hint.confidence == "low"
    assert "not a person" in hint.message


def test_network_findings_include_reporting_attribution(tmp_path):
    policy = tmp_path / "asa-policy.json"
    policy.write_text(
        """
        {
          "suspicious_remote_ports": [4444],
          "nvidia": { "enabled": false },
          "response": { "auto_contain": false, "dry_run": true }
        }
        """,
        encoding="utf-8",
    )
    config = load_config(root=tmp_path, policy_file=policy)
    config.ensure_dirs()
    system_map = SystemMap(
        network_connections=[
            NetworkConnection(
                pid=123,
                process_name="example",
                local_address="127.0.0.1:50000",
                remote_address="8.8.8.8:4444",
                remote_ip="8.8.8.8",
                remote_port=4444,
                status="ESTABLISHED",
            )
        ]
    )

    findings = ThreatDetectionEngine(config, BaselineStore(config)).analyze(system_map)
    assert findings
    assert findings[0].evidence["attribution"]["report_to"] == "ISP/cloud hosting abuse contact"
