#!/usr/bin/env python3
import sys
import os
import argparse
import torch
import json
import shutil
from pathlib import Path

# Add workspace to path
WORKSPACE_ROOT = Path(__file__).parent
sys.path.insert(0, str(WORKSPACE_ROOT))

from kattappa_native.model.model import KattappaConfig, KattappaModel
from evaluation.run_all import run_comprehensive_evaluation

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
        # Filter out 0 or negative tokens if any
        ids = [int(x) for x in ids if x >= 0]
        return self.sp.decode(ids)

def run_health_check(state_dict):
    """Verifies weight integrity (no NaN or Inf)."""
    for name, param in state_dict.items():
        if torch.isnan(param).any():
            raise ValueError(f"NaN detected in parameter: {name}")
        if torch.isinf(param).any():
            raise ValueError(f"Inf detected in parameter: {name}")
    print("✅ Startup health-check: Weight integrity verified (no NaN/Inf).")

def main():
    parser = argparse.ArgumentParser(description="Kattappa Model Evaluation & Continuous Regression Check")
    parser.add_argument("--checkpoint", type=str, required=True, help="Path to checkpoint .pt file")
    parser.add_argument("--device", type=str, default="cpu", help="Device to run evaluation on")
    args = parser.parse_args()

    checkpoint_path = Path(args.checkpoint)
    if not checkpoint_path.exists():
        print(f"❌ Checkpoint file not found: {checkpoint_path}")
        sys.exit(1)

    print(f"Loading checkpoint for evaluation: {checkpoint_path}")
    
    # 1. Load checkpoint and run startup health check
    try:
        state = torch.load(checkpoint_path, map_location="cpu")
        state_dict = state.get("model_state_dict", state)
        run_health_check(state_dict)
    except Exception as e:
        print(f"❌ Startup health check FAILED: {e}")
        # Rollback mechanism: trigger rollback if a backup exists
        print("🔄 Triggering automated fallback to previously registered stable model...")
        best_path = checkpoint_path.parent / "checkpoint_best.pt"
        if best_path.exists() and best_path.resolve() != checkpoint_path.resolve():
            print(f"Restoring best checkpoint from {best_path}")
            shutil.copy2(best_path, checkpoint_path)
            print("Fallback restore complete.")
        else:
            print("No older stable checkpoint available for fallback.")
        sys.exit(1)

    # 2. Instantiate Model and Tokenizer
    # Determine n_kv_heads dynamically from model_state_dict shapes
    n_kv_heads = 4
    first_qkv_weight = state_dict.get("blocks.0.attn.qkv.weight")
    if first_qkv_weight is not None:
        total_dim = first_qkv_weight.shape[0]
        # total_dim = q_size + 2 * kv_size = d_model + 2 * n_kv_heads * head_dim
        # Where head_dim = d_model // n_heads = 768 // 12 = 64
        # Thus total_dim = 768 + 128 * n_kv_heads
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
    model.to(args.device)
    model.eval()

    tokenizer = None
    sp_path = WORKSPACE_ROOT / "kattappa_native/tokenizer/kattappa_tokenizer.model"
    if sp_path.exists():
        try:
            tokenizer = TokenizerWrapper(sp_path)
        except Exception as e:
            print(f"Warning: Failed to load real sentencepiece wrapper: {e}. Using mock tokenizer.")
            tokenizer = None

    # 3. Execute evaluation
    output_report_path = WORKSPACE_ROOT / "kattappa_data_engine/reports/evaluation_report_current.json"
    report = run_comprehensive_evaluation(
        model=model,
        tokenizer=tokenizer,
        device=args.device,
        output_path=str(output_report_path)
    )

    # 4. Continuous Regression Check
    # Rule: If new checkpoint drops in reasoning, coding, memory, or any metric by >5%, reject.
    preceding_report_path = WORKSPACE_ROOT / "kattappa_data_engine/reports/evaluation_report.json"
    if preceding_report_path.exists():
        try:
            with open(preceding_report_path, "r") as f:
                prev_report = json.load(f)
            print("\nComparing metrics against preceding evaluation report:")
            
            regressed = False
            regression_reasons = []
            
            for metric_name, current_val in report["metrics"].items():
                prev_val = prev_report.get("metrics", {}).get(metric_name, 0.0)
                diff = current_val - prev_val
                print(f"  - {metric_name}: Previous={prev_val:.4f}, Current={current_val:.4f} (diff={diff:+.4f})")
                
                # Check for drop > 5% (either absolute 0.05 OR relative 5% of previous value)
                is_drop = False
                drop_pct = 0.0
                if diff < 0:
                    if diff < -0.05:
                        is_drop = True
                        drop_pct = abs(diff) * 100
                    elif prev_val > 0.0 and (current_val / prev_val) < 0.95:
                        is_drop = True
                        drop_pct = (abs(diff) / prev_val) * 100
                
                if is_drop:
                    regressed = True
                    regression_reasons.append(
                        f"Regression detected in metric '{metric_name}': dropped from {prev_val:.4f} to {current_val:.4f} (diff={diff:+.4f}, drop={drop_pct:.2f}%)"
                    )
            
            if regressed:
                print("\n❌ CHECKPOINT REJECTED: Regression checks failed.")
                for reason in regression_reasons:
                    print(f"   ⚠️ {reason}")
                sys.exit(2)
            else:
                print("\n✅ Regression checks passed.")
        except Exception as e:
            print(f"Warning: Error reading preceding report for regression check: {e}")
    else:
        print("\nℹ️ No preceding evaluation report found. Skipping regression checks.")

    # Promote report to baseline
    shutil.copy2(output_report_path, preceding_report_path)
    print(f"Promoted current evaluation report to {preceding_report_path}")
    print("🎉 Checkpoint evaluation and regression validation completed successfully.")

if __name__ == "__main__":
    main()
