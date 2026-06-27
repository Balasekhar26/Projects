import os
import json
import hashlib
from pathlib import Path
from datetime import datetime

def compute_sha256(filepath):
    path = Path(filepath)
    if not path.exists():
        return "not-found"
    sha256 = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(8192):
            sha256.update(chunk)
    return sha256.hexdigest()

def main():
    root = Path(__file__).parent.parent.parent
    
    # Target files to freeze
    trainer_path = root / "kattappa_native/training/trainer.py"
    optimizer_path = root / "kattappa_native/training/optimizer.py"
    scheduler_path = root / "kattappa_native/training/scheduler.py"
    model_path = root / "kattappa_native/model/model.py"
    attention_path = root / "kattappa_native/model/attention.py"
    block_path = root / "kattappa_native/model/block.py"
    tokenizer_path = root / "kattappa_native/tokenizer/kattappa_tokenizer.model"
    
    # Compute hashes
    hashes = {
        "trainer_py_sha256": compute_sha256(trainer_path),
        "optimizer_py_sha256": compute_sha256(optimizer_path),
        "scheduler_py_sha256": compute_sha256(scheduler_path),
        "model_py_sha256": compute_sha256(model_path),
        "attention_py_sha256": compute_sha256(attention_path),
        "block_py_sha256": compute_sha256(block_path),
        "tokenizer_model_sha256": compute_sha256(tokenizer_path)
    }
    
    # Model Configurations
    model_config = {
        "n_layers": 12,
        "n_heads": 12,
        "n_kv_heads": 4,
        "d_model": 768,
        "d_ff": 3072,
        "context_length": 2048,
        "vocab_size": 32000,
        "rope_theta": 10000.0
    }
    
    # Training Configurations
    training_config = {
        "steps": 50000,
        "batch_size": 2,
        "initial_seq_len": 256,
        "max_seq_len": 2048,
        "curriculum_training": True,
        "lr": 3e-4,
        "grad_clip": 1.0,
        "lr_scheduler": "CosineScheduler",
        "optimizer": "AdamW",
        "weight_decay": 0.1,
        "beta1": 0.9,
        "beta2": 0.95
    }
    
    baseline_lock = {
        "baseline_version": "baseline-v1.0.0",
        "frozen_timestamp": datetime.utcnow().isoformat() + "Z",
        "file_hashes": hashes,
        "model_config": model_config,
        "training_config": training_config
    }
    
    out_path = root / "baseline_lock_v1.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(baseline_lock, f, indent=2)
        
    print(f"✅ Baseline locked and saved successfully to {out_path.name}")
    print(json.dumps(baseline_lock, indent=2))

if __name__ == "__main__":
    main()
