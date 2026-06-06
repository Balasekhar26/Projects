#!/usr/bin/env sh
set -eu

ROOT="$(cd "$(dirname "$0")" && pwd)"

if command -v python3 >/dev/null 2>&1; then
  python3 "$ROOT/tests_smoke.py"
elif command -v python >/dev/null 2>&1; then
  python "$ROOT/tests_smoke.py"
else
  printf '%s\n' "Python was not found. Install Python 3.10+ and rerun this script." >&2
  exit 1
fi

test -f "$ROOT/kattappa_ai_system.py"
test -f "$ROOT/config.json"
test -f "$ROOT/requirements.txt"
test -f "$ROOT/README.md"
test -d "$ROOT/workspace"
test -d "$ROOT/memory"
test -d "$ROOT/logs"
test -x "$ROOT/bin/run.sh"

grep -q "safe_workspace_path" "$ROOT/kattappa_ai_system.py"
grep -q "multi_agent_simulation" "$ROOT/kattappa_ai_system.py"
grep -q "coding_agent" "$ROOT/kattappa_ai_system.py"
grep -q "search_web" "$ROOT/kattappa_ai_system.py"
grep -q "ollama_chat" "$ROOT/kattappa_ai_system.py"
grep -q "doctor" "$ROOT/kattappa_ai_system.py"
grep -q "remember" "$ROOT/kattappa_ai_system.py"
grep -q "scan_workspace_secrets" "$ROOT/kattappa_ai_system.py"
grep -q "context_budget_report" "$ROOT/kattappa_ai_system.py"
grep -q "backup_workspace_file" "$ROOT/kattappa_ai_system.py"

echo "Smoke test passed."
