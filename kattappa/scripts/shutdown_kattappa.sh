#!/usr/bin/env sh
set -u

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
RUNTIME="$ROOT/runtime"
APP_SUPPORT="$HOME/Library/Application Support/Kattappa AI OS"
APP_RUNTIME="$APP_SUPPORT/runtime"
LOGS="$APP_SUPPORT/logs"
mkdir -p "$LOGS"

log() {
  printf '[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$1" >> "$LOGS/shutdown.log"
}

stop_pid_file() {
  path="$1"
  label="$2"
  [ -f "$path" ] || return 0
  pid=$(sed -n '1p' "$path" 2>/dev/null | tr -dc '0-9')
  if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
    log "Stopping $label pid=$pid"
    kill "$pid" 2>/dev/null || true
  fi
  rm -f "$path"
}

log "Shutdown requested."
stop_pid_file "$APP_RUNTIME/backend.pid" "backend"
stop_pid_file "$APP_RUNTIME/desktop-ui.pid" "desktop UI"
stop_pid_file "$RUNTIME/backend.pid" "backend"
stop_pid_file "$RUNTIME/desktop-ui.pid" "desktop UI"

for marker in "$APP_RUNTIME/ollama-started-by-kattappa.flag" "$RUNTIME/ollama-started-by-kattappa.flag"; do
  if [ -f "$marker" ]; then
    marker_dir=$(dirname "$marker")
    stop_pid_file "$marker_dir/ollama.pid" "ollama"
    rm -f "$marker"
  fi
done

log "Shutdown completed."
