# Kronos — Vendored (Built-in)

**Kronos** is an OHLCV market forecasting model by [shiyu-coder](https://github.com/shiyu-coder/Kronos).

This `model/` package is bundled directly inside Kattappa AI OS so the Finance Brain's
Kronos engine works without any separate git clone step.

## License
MIT — see `LICENSE` file in this directory.

## Source
Original repository: https://github.com/shiyu-coder/Kronos

## What is included
- `model/kronos.py` — core Kronos model
- `model/module.py` — Kronos building blocks
- `model/__init__.py` — package init
- `requirements.txt` — runtime Python dependencies (torch, numpy, pandas, einops, etc.)

## Runtime dependencies
To activate the Kronos engine, install:
```
pip install torch numpy pandas einops huggingface_hub safetensors
```
The Kattappa built-in OHLCV baseline forecaster works without any of these packages.
