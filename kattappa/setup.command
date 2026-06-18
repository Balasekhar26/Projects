#!/bin/bash
# Kattappa AI OS macOS setup and launch script
cd "$(dirname "$0")"

SETUP_ARGS="--accept-agreement --launch"
if [ "$1" = "--setup-only" ]; then
  SETUP_ARGS=""
elif [ "$1" = "--accept-agreement" ]; then
  SETUP_ARGS="--accept-agreement --launch"
elif [ "$1" = "--print-agreement" ]; then
  SETUP_ARGS="--print-agreement"
elif [ "$1" = "--help" ] || [ "$1" = "-h" ]; then
  echo "Usage: ./setup.command [--setup-only] [--accept-agreement] [--print-agreement]"
  exit 0
fi

# Locate Python 3
PYTHON_EXE=""
if command -v python3 >/dev/null 2>&1; then
  PYTHON_EXE="python3"
elif command -v python >/dev/null 2>&1; then
  PYTHON_EXE="python"
fi

if [ -z "$PYTHON_EXE" ]; then
  echo "Python 3 is required to install Kattappa AI OS."
  echo "Please install Python 3 and ensure it is in your PATH."
  read -p "Press Enter to exit..."
  exit 1
fi

$PYTHON_EXE installer/setup_kattappa.py $SETUP_ARGS
