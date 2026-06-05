# Autonomous Security Agent Architecture

This is the buildable version of the "digital immune system" idea. It is defensive only: it cleans and hardens the protected machine, collects evidence, blocks local access paths, and reports malicious infrastructure. It does not damage or access outside devices.

## Seven Layers

1. Entry and Initial Scan
   - Module: `asa/system_map.py`
   - Collects processes, network connections, startup entries, and critical file observations.

2. Threat Detection Engine
   - Module: `asa/threat_detection.py`
   - Combines signatures, behavior rules, risky paths, network indicators, and baseline deviations into scored findings.

3. Self-Healing Engine
   - Module: `asa/self_healing.py`
   - Safely terminates local user-owned processes and quarantines local files. Defaults to dry-run behavior.

4. Hardening Layer
   - Module: `asa/hardening.py`
   - Audits blocklist, honeypots, and common remote-access ports. Future versions can apply approved firewall rules.

5. Continuous Monitoring
   - Module: `asa/monitoring.py`
   - Runs the loop: map system, analyze, log findings, respond, repeat.

6. Response Engine
   - Module: `asa/response.py`
   - Recommends reversible action by default. Auto-containment requires enabling it in `config/asa-policy.json`.

7. Intelligence and Learning
   - Module: `asa/learning.py`
   - Stores a baseline of normal processes, remote IPs, and startup entries so deviations become easier to spot.

## Safe Response Rules

- No off-device retaliation.
- No self-propagation.
- No remote exploitation.
- No destructive action against external infrastructure.
- Local containment is reversible and dry-run by default.
- Process termination refuses protected process names and other users' processes.

## Execution Flow

```text
SystemMapper.build()
  -> ThreatDetectionEngine.analyze()
  -> JsonlLogger.finding()
  -> ResponseEngine.respond()
  -> ReportWriter.write()
```

## Running the Python ASA Engine

When Python is available:

```bash
./bin/asa-agent baseline
./bin/asa-agent scan
./bin/asa-agent hardening-audit
./bin/asa-agent report
```

The current machine can still use:

```bash
./bin/balu-shield scan
./bin/balu-shield watch 15
```

## Product Roadmap

Phase 1:
- Complete process and network monitoring.
- Store baseline.
- Generate scored findings.

Phase 2:
- Add file integrity monitoring.
- Add signed allowlist and denylist.
- Add better quarantine metadata.

Phase 3:
- Add UI dashboard.
- Add approved firewall rule application.
- Add cloud-free local model for behavior classification.

Phase 4:
- Add enterprise mode with central reporting.
- Add fleet-wide threat intelligence sharing.
- Add tamper-resistance and secure update channel.
