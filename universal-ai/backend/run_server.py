from __future__ import annotations

import sys
from pathlib import Path

import uvicorn


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
LOG_DIR = ROOT / "logs"
LOG_DIR.mkdir(exist_ok=True)

sys.stdout = (LOG_DIR / "backend-launch.log").open("w", encoding="utf-8", buffering=1)
sys.stderr = (LOG_DIR / "backend-launch.err.log").open("w", encoding="utf-8", buffering=1)

uvicorn.run("backend.main:app", host="127.0.0.1", port=8000, log_level="info")
