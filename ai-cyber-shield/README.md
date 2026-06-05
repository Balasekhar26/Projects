# Balu Cyber Shield

Balu Cyber Shield is a defensive security agent and dashboard prototype for user-owned machines. It focuses on stopping attacker access, collecting evidence, hardening the local device, and wasting attacker time through honeypots. It does not attack, damage, or access another device.

The project now has two layers:

- `bin/balu-shield`: dependency-free shell agent that works on this machine today.
- `bin/asa-agent`: Python-ready Autonomous Security Agent engine matching the full architecture in `docs/ARCHITECTURE.md`.
- `setup.bat` and `run.exe`: the canonical Windows setup and launch flow for this workspace.

## What It Does

- Scans running processes for suspicious names, paths, and high resource usage.
- Watches established network connections for risky ports and known blocked endpoints.
- Creates local honeypot files with fake secrets and detects tampering.
- Contains local user-owned processes safely with `TERM` by default.
- Adds suspicious IPs to a local blocklist for evidence and future alerts.
- Generates Markdown incident reports from the evidence log.
- Optionally enriches Python ASA incident reports with NVIDIA NIM defensive analysis.
- Creates a credential rotation checklist after a suspected compromise.
- Adds a Python ASA architecture with system mapping, threat scoring, self-healing, hardening audits, monitoring, response, and learning.
- Adds an optional physical-presence correlation module using Wi-Fi CSI presence events from the downloaded CSI-Sense-Zero reference.

## Project Layout

```text
balu-cyber-shield/
  bin/balu-shield            Main CLI
  bin/asa-agent              Python ASA CLI wrapper
  asa/                       Python ASA engine modules
  config/shield.conf         Safe default configuration
  config/asa-policy.json     Python ASA policy
  lib/                       Detection, honeypot, containment, reporting modules
  docs/ARCHITECTURE.md       Full system design
  asa/physical_presence/     Optional Wi-Fi CSI physical presence correlation
  runtime/                   Local logs, evidence, honeypots, quarantine area
  reports/                   Generated incident reports
  tests/smoke.sh             Basic validation script
```

Reference project:

```text
C:\Users\balu\Projects\external-projects\CSI-Sense-Zero
```

## Quick Start

Windows workspace flow:

```bat
setup.bat
run.exe
```

Python ASA flow from this folder:

```bash
python -m asa.cli scan
python -m asa.cli hardening-audit
python -m asa.cli report
```

For continuous monitoring:

```bash
./bin/balu-shield watch 15
```

Press `Ctrl+C` to stop the watcher.

When Python is available:

```bash
export NVIDIA_NIM_API_KEY="nvapi-..."   # optional hosted report analysis
./bin/asa-agent baseline
./bin/asa-agent scan
./bin/asa-agent hardening-audit
./bin/asa-agent report
```

## Commands

```text
init                       Create runtime folders and honeypot files
scan                       Run one defensive scan
watch [seconds]            Run scans repeatedly
honeypot init              Recreate honeypot files and manifest
honeypot check             Check whether honeypot files changed
contain pid <pid>          Terminate a suspicious process owned by current user
contain ip <ip>            Add an IP to the local blocklist
credential-plan            Generate a credential rotation checklist
report                     Generate an incident report
status                     Show local shield status
self-test                  Run basic validation checks
help                       Show CLI help
```

## Python ASA Commands

```text
map                       Print system map as JSON
scan                      Run one ASA scan
watch [seconds]           Run the ASA monitoring loop
baseline                  Save normal behavior baseline
hardening-audit           Audit local hardening state
architecture-audit        Check ASA architecture and safety boundaries
report                    Generate ASA incident report
contain-pid <pid>         Dry-run local process containment
contain-pid <pid> --apply Actually send TERM to a safe local process
block-ip <ip>             Add IP to local blocklist
```

## NVIDIA NIM Report Analysis

The Python ASA report command can call NVIDIA NIM through the free/serverless
developer API tier when `NVIDIA_NIM_API_KEY` is set. It sends only a compact
summary of recent ASA events, not raw evidence files or honeypot contents, and
adds defensive triage guidance to the Markdown report.

Disable it by setting `"nvidia": { "enabled": false }` in
`config/asa-policy.json`.

## Important Safety Boundary

This tool does not retaliate against outside systems. That is intentional. Reliable attribution is hard, and active retaliation can harm innocent devices. The safe counter-strategy is:

- remove attacker access,
- deceive and observe,
- preserve evidence,
- rotate credentials,
- report abuse to the right provider or authority.

## Notes

The shell agent is dependency-free. It uses standard macOS shell utilities instead of Python or Node, because this machine currently does not have Node/npm and `python3` is blocked by missing command-line tools.

The Python ASA engine is already scaffolded and ready for the next environment step. Once Python works, install optional dependencies with:

```bash
python3 -m pip install -r requirements.txt
```

## Production Gate

- Keep `setup.bat` as the only setup entrypoint and `run.exe` as the only root run executable.
- The ASA pipeline must run as one workflow and continue after non-fatal layer failures.
- Runtime logs, evidence, blocklists, honeypot contents, quarantine files, and reports must remain local and untracked except placeholder `.gitkeep` files.
- Auto-containment must stay disabled by default unless an operator explicitly enables it in policy.
