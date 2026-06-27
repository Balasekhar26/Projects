#!/usr/bin/env python3
import sys
import os
import argparse
import time
import torch
import json
from pathlib import Path

# Add workspace to path
WORKSPACE_ROOT = Path(__file__).parent
sys.path.insert(0, str(WORKSPACE_ROOT))

from kattappa_native.model.model import KattappaConfig, KattappaModel

class BatchEncoding(dict):
    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError:
            raise AttributeError(name)

    def to(self, device):
        for k, v in list(self.items()):
            if isinstance(v, torch.Tensor):
                self[k] = v.to(device)
        return self

class TokenizerWrapper:
    def __init__(self, sp_model_path):
        import sentencepiece as spm
        self.sp = spm.SentencePieceProcessor()
        self.sp.Load(str(sp_model_path))
        self.eos_token_id = self.sp.eos_id()
        
    def __call__(self, text, return_tensors=None):
        ids = self.sp.encode(text, out_type=int)
        if return_tensors == "pt":
            return BatchEncoding({"input_ids": torch.tensor([ids], dtype=torch.long)})
        return ids
        
    def decode(self, ids, skip_special_tokens=True):
        if hasattr(ids, "tolist"):
            ids = ids.tolist()
        ids = [int(x) for x in ids if x >= 0]
        return self.sp.decode(ids)

def main():
    parser = argparse.ArgumentParser(description="Kattappa Inference Benchmark & Logging Utility")
    parser.add_argument("--checkpoint", type=str, required=True, help="Path to checkpoint .pt file")
    parser.add_argument("--prompt", type=str, default="Raju is walking to the village. In Telugu, this is:", help="Inference prompt")
    parser.add_argument("--max-new-tokens", type=int, default=128, help="Maximum new tokens to generate")
    parser.add_argument("--temperature", type=float, default=0.7, help="Sampling temperature")
    parser.add_argument("--top-k", type=int, default=50, help="Top-k sampling")
    parser.add_argument("--device", type=str, default="cpu", help="Device to run inference on")
    args = parser.parse_args()

    checkpoint_path = Path(args.checkpoint)
    if not checkpoint_path.exists():
        print(f"❌ Checkpoint file not found: {checkpoint_path}")
        sys.exit(1)

    device = torch.device(args.device)
    print(f"Loading model on {device}...")
    
    # Load checkpoint
    state = torch.load(checkpoint_path, map_location="cpu")
    state_dict = state.get("model_state_dict", state)

    # Instantiate model
    # Determine n_kv_heads dynamically from model_state_dict shapes
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
    model.load_state_dict(state_dict, strict=False)
    model.to(device)
    model.eval()

    # Load tokenizer
    sp_path = WORKSPACE_ROOT / "kattappa_native/tokenizer/kattappa_tokenizer.model"
    if not sp_path.exists():
        print(f"❌ Tokenizer model not found at {sp_path}")
        sys.exit(1)
        
    tokenizer = TokenizerWrapper(sp_path)

    # Prepare input
    inputs = tokenizer(args.prompt, return_tensors="pt")
    input_ids = inputs["input_ids"].to(device)
    prompt_len = input_ids.shape[1]

    # Warmup step
    print("Running warmup pass...")
    with torch.no_grad():
        # A single forward pass
        _ = model(input_ids[:, :max(2, prompt_len-1)])
    if device.type == "mps":
        torch.mps.synchronize()

    # Measure Prefill Latency
    t_start = time.time()
    with torch.no_grad():
        logits, _ = model(input_ids)
    if device.type == "mps":
        torch.mps.synchronize()
    t_prefill = time.time() - t_start
    print(f"Prefill Latency: {t_prefill*1000:.2f} ms")

    # Run full generation with time tracking
    t_gen_start = time.time()
    with torch.no_grad():
        output_ids = model.generate(
            prompt_ids=input_ids,
            max_new_tokens=args.max_new_tokens,
            temperature=args.temperature,
            top_k=args.top_k,
            eos_id=tokenizer.eos_token_id
        )
    if device.type == "mps":
        torch.mps.synchronize()
    t_gen = time.time() - t_gen_start
    
    total_tokens = output_ids.shape[1]
    new_tokens = total_tokens - prompt_len
    tokens_per_sec = new_tokens / t_gen if t_gen > 0 else 0.0
    
    response = tokenizer.decode(output_ids[0][prompt_len:], skip_special_tokens=True)

    print("\n" + "="*50)
    print(f"Prompt: {args.prompt}")
    print(f"Response: {response}")
    print("="*50)
    print(f"New tokens generated: {new_tokens}")
    print(f"Total time: {t_gen:.2f} s")
    print(f"Decode speed: {tokens_per_sec:.2f} tok/s")
    print("="*50)

    # Log metrics to JSONL file
    log_entry = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "checkpoint": str(checkpoint_path.name),
        "prompt": args.prompt,
        "new_tokens": new_tokens,
        "prefill_latency_ms": round(t_prefill * 1000, 2),
        "total_generation_s": round(t_gen, 3),
        "tokens_per_second": round(tokens_per_sec, 2),
        "device": args.device
    }

    log_dir = WORKSPACE_ROOT / "logs"
    log_dir.mkdir(exist_ok=True)
    log_path = log_dir / "inference_benchmark_log.jsonl"
    
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(log_entry) + "\n")
        
    print(f"Metrics written to: {log_path}")

if __name__ == "__main__":
    main()
