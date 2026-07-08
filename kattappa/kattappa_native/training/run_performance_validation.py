import os
import sys
import time
import torch
import psutil
import json
import statistics
from pathlib import Path

# Add workspace root to path
WORKSPACE_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(WORKSPACE_ROOT))

from kattappa_native.model.model import KattappaConfig, KattappaModel
from kattappa_native.training.checkpoint import CheckpointManager
from kattappa_native.training.optimizer import build_optimizer
from kattappa_native.training.scheduler import CosineScheduler

def get_current_rss():
    process = psutil.Process(os.getpid())
    return process.memory_info().rss / (1024 * 1024) # MB

import argparse

def main():
    parser = argparse.ArgumentParser(description="Kattappa Performance Validation Runner")
    parser.add_argument("--checkpoint", type=str, default="kattappa_native/checkpoints/test6/checkpoint_best.pt", help="Path to checkpoint file")
    args = parser.parse_args()
    
    print("==================================================")
    print("     KATTAPPA PERFORMANCE VALIDATION RUNNER       ")
    print("==================================================")
    
    checkpoint_path = Path(args.checkpoint)
    if not checkpoint_path.exists():
        print(f"❌ Checkpoint not found at {checkpoint_path}")
        sys.exit(1)
        
    device = torch.device("cpu")
    
    # Load state dict first to dynamically infer config shapes
    state = torch.load(checkpoint_path, map_location="cpu")
    state_dict = state.get("model_state_dict", state)
    
    # 1. Startup Latency (Config/Model initialization)
    t_start = time.time()
    
    n_kv_heads = 4
    first_qkv_weight = state_dict.get("blocks.0.attn.qkv.weight")
    if first_qkv_weight is not None:
        total_dim = first_qkv_weight.shape[0]
        n_kv_heads = (total_dim - 768) // 128
        print(f"Dynamically inferred n_kv_heads from checkpoint: {n_kv_heads}")

    model_config = KattappaConfig(
        n_layers=12,
        n_heads=12,
        n_kv_heads=n_kv_heads,
        d_model=768,
        d_ff=3072,
        context_length=2048,
        vocab_size=32000,
        dropout=0.0
    )
    model = KattappaModel(model_config)
    t_startup = time.time() - t_start
    print(f"Startup Latency (Instantiation): {t_startup*1000:.2f} ms")
    
    # 2. Resume Latency (Checkpoint loading and restoring)
    t_load_start = time.time()
    model.load_state_dict(state_dict, strict=False)
    model.to(device)
    model.eval()
    t_resume = time.time() - t_load_start
    print(f"Resume/Loading Latency: {t_resume:.4f} s")
    
    # 3. Repeat Benchmark 3 Independent Times
    print("\nRunning Inference Throughput Benchmark (3 runs)...")
    speeds = []
    
    # Simple mock inputs for benchmark consistency
    input_ids = torch.randint(0, 32000, (1, 16)).to(device)
    
    # Warmup
    with torch.no_grad():
        _ = model.generate(prompt_ids=input_ids, max_new_tokens=16)
        
    for run in range(1, 4):
        t_run_start = time.time()
        with torch.no_grad():
            output = model.generate(prompt_ids=input_ids, max_new_tokens=64)
        t_run = time.time() - t_run_start
        tokens_per_sec = 64 / t_run
        speeds.append(tokens_per_sec)
        print(f"  Run {run}: {tokens_per_sec:.2f} tokens/sec in {t_run:.3f}s")
        
    mean_speed = statistics.mean(speeds)
    std_speed = statistics.stdev(speeds) if len(speeds) > 1 else 0.0
    print(f"\nThroughput Statistics:")
    print(f"  Mean speed: {mean_speed:.2f} tokens/sec")
    print(f"  Std Dev:    {std_speed:.2f} tokens/sec")
    
    # 4. Checkpoint Latency
    print("\nMeasuring Checkpoint Saving Latency...")
    optimizer = build_optimizer(model, lr=3e-4)
    scheduler = CosineScheduler(optimizer, total_steps=100)
    
    import shutil
    tmp_dir = os.path.join(os.path.dirname(args.checkpoint), "test_val_tmp")
    os.makedirs(tmp_dir, exist_ok=True)
    try:
        manager = CheckpointManager(tmp_dir, keep_last_n=1)
        
        t_save_start = time.time()
        # Save dummy step checkpoint
        manager.save(step=999, model=model, optimizer=optimizer, scheduler=scheduler, val_ppl=12.5)
        t_save = time.time() - t_save_start
        
        # Read the performance log from checkpoint timing to get granular metrics
        perf_log_path = Path("~/Desktop/checkpoint_timing.jsonl").expanduser()
        if perf_log_path.exists():
            try:
                with open(perf_log_path, "r") as f:
                    last_line = f.readlines()[-1]
                    perf_data = json.loads(last_line)
                    print(f"  GPU Sync:            {perf_data.get('gpu_sync_s', 0)*1000:.2f} ms")
                    print(f"  DMA CPU Transfer:     {perf_data.get('state_to_cpu_s', 0)*1000:.2f} ms")
                    print(f"  Disk Write:          {perf_data.get('torch_save_s', 0)*1000:.2f} ms")
            except Exception:
                pass
        print(f"  Total Save Latency:  {t_save:.4f} s")
        
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        
    # 5. Memory footprint
    rss = get_current_rss()
    print(f"\nResource Usage:")
    print(f"  Peak RSS Memory: {rss:.2f} MB")
    print("==================================================")

if __name__ == "__main__":
    main()
