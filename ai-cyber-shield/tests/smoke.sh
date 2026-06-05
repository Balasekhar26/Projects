#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

export SHIELD_RUNTIME_OVERRIDE="$TMP_DIR/runtime"
export SHIELD_REPORTS_OVERRIDE="$TMP_DIR/reports"

bash -n "$ROOT/bin/balu-shield"
bash -n "$ROOT/bin/asa-agent"
bash -n "$ROOT/lib/common.sh"
bash -n "$ROOT/lib/honeypot.sh"
bash -n "$ROOT/lib/detector.sh"
bash -n "$ROOT/lib/containment.sh"
bash -n "$ROOT/lib/report.sh"

"$ROOT/bin/balu-shield" init >/dev/null
"$ROOT/bin/balu-shield" honeypot check >/dev/null
"$ROOT/bin/balu-shield" scan >/dev/null
"$ROOT/bin/balu-shield" contain ip 127.0.0.2 >/dev/null
"$ROOT/bin/balu-shield" credential-plan >/dev/null
"$ROOT/bin/balu-shield" report >/dev/null

test -s "$SHIELD_RUNTIME_OVERRIDE/logs/events.jsonl"
test -d "$SHIELD_RUNTIME_OVERRIDE/honeypot"
test -d "$SHIELD_REPORTS_OVERRIDE"
test -f "$ROOT/config/asa-policy.json"
test -f "$ROOT/asa/cli.py"
test -f "$ROOT/docs/ARCHITECTURE.md"

echo "Smoke test passed."
