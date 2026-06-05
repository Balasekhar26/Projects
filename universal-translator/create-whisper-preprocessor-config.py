#!/usr/bin/env python3
import json
import os
from pathlib import Path

# Whisper preprocessor config for tiny model
preprocessor_config = {
    "chunk_length": 30000,
    "feature_extractor_type": "WhisperFeatureExtractor",
    "feature_size": 80,
    "mel_freq_base": 0.0,
    "mel_freq_top": 8000.0,
    "n_fft": 400,
    "n_mels": 80,
    "n_samples": 480000,
    "padding_side": "right",
    "padding_value": 0.0,
    "processor_class": "WhisperProcessor",
    "return_attention_mask": False,
    "sampling_rate": 16000
}

# Find and create in HuggingFace cache
hf_cache = Path.home() / ".cache" / "huggingface" / "hub" / "models--Systran--faster-whisper-tiny"
snapshot_dir = list(hf_cache.glob("snapshots/*"))[0]

config_path = snapshot_dir / "preprocessor_config.json"
print(f"Creating preprocessor config at: {config_path}")

with open(config_path, 'w') as f:
    json.dump(preprocessor_config, f, indent=2)

print(f"✓ Config created ({config_path.stat().st_size} bytes)")

# Verify it can be read
with open(config_path, 'r') as f:
    loaded = json.load(f)
    print(f"✓ Config verified: {list(loaded.keys())}")
