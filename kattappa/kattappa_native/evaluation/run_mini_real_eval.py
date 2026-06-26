#!/usr/bin/env python3
"""
KM-5.4 — Run Real Evaluation on Kattappa-20M
============================================
Loads the trained Kattappa-20M model weights and the SentencePiece tokenizer,
and runs the evaluation suite (Reasoning, Telugu, Tool-use) on the live model.

Usage:
    PYTHONPATH=. ./ai_system_env/bin/python3 kattappa_native/evaluation/run_mini_real_eval.py
"""

import sys
from pathlib import Path
import torch

WORKSPACE_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(WORKSPACE_ROOT))

from kattappa_native.model.model import KattappaModel, KattappaConfig
from kattappa_native.evaluation.reasoning_eval import ReasoningEvaluator
from kattappa_native.evaluation.telugu_eval import TeluguEvaluator
from kattappa_native.evaluation.tool_eval import ToolEvaluator

def main():
    device = torch.device("mps" if torch.backends.mps.is_available() else ("cuda" if torch.cuda.is_available() else "cpu"))
    print(f"\n🧪 Running real evaluation on device: {device}")

    # 1. Load Tokenizer
    import sentencepiece as spm
    tok_path = WORKSPACE_ROOT / "kattappa_native/tokenizer/kattappa_tokenizer.model"
    if not tok_path.exists():
        print(f"❌ Tokenizer model not found at: {tok_path}")
        sys.exit(1)
    
    sp_processor = spm.SentencePieceProcessor()
    sp_processor.Load(str(tok_path))
    print(f"✅ Loaded SentencePiece tokenizer from {tok_path.name}")

    def tokenize_fn(text: str) -> torch.Tensor:
        ids = sp_processor.encode(text, out_type=int)
        return torch.tensor(ids, dtype=torch.long)

    def decode_fn(ids: list) -> str:
        return sp_processor.decode(ids)

    # 2. Instantiate and load Kattappa-20M Model
    config = KattappaConfig.mini()
    model = KattappaModel(config).to(device)
    
    ckpt_path = WORKSPACE_ROOT / "kattappa_native/checkpoints/mini/checkpoint_best.pt"
    if not ckpt_path.exists():
        # Try latest checkpoint if best is missing
        pts = sorted(WORKSPACE_ROOT.glob("kattappa_native/checkpoints/mini/checkpoint_step_*.pt"))
        if pts:
            ckpt_path = pts[-1]
        else:
            print(f"❌ No checkpoints found in kattappa_native/checkpoints/mini/")
            sys.exit(1)

    print(f"📂 Loading weights from: {ckpt_path}")
    state = torch.load(ckpt_path, map_location=device)
    model.load_state_dict(state["model_state_dict"])
    model.eval()
    print(f"✅ Loaded Kattappa-20M (Step: {state.get('step', 'unknown')}, Param count: {model.param_count() / 1e6:.2f}M)")

    # 3. Execute Evaluators
    print("\n--- 1. Reasoning Evaluation (GSM8K subset) ---")
    reasoning_eval = ReasoningEvaluator()
    r_results = reasoning_eval.evaluate_model(model, tokenize_fn, decode_fn, device)
    print(f"Accuracy: {r_results['accuracy'] * 100:.2f}% ({r_results['correct']}/{r_results['total']})")

    print("\n--- 2. Telugu Evaluation (Script, Roman, Code-switch) ---")
    telugu_eval = TeluguEvaluator()
    t_results = telugu_eval.evaluate_model(model, tokenize_fn, decode_fn, device)
    print(f"Script Adherence Pass Rate: {t_results['script_adherence']['pass_rate'] * 100:.2f}%")
    print(f"Roman Telugu Pass Rate: {t_results['roman_telugu']['pass_rate'] * 100:.2f}%")
    print(f"Overall Pass: {'✅ PASSED' if t_results['overall_pass'] else '❌ FAILED'}")

    print("\n--- 3. Tool-use Evaluation (Tool F1) ---")
    tool_eval = ToolEvaluator()
    tool_results = tool_eval.evaluate_model(model, tokenize_fn, decode_fn, device)
    print(f"Tool F1 Score: {tool_results['f1']:.4f}")
    print(f"Precision: {tool_results['precision']:.4f}, Recall: {tool_results['recall']:.4f}")
    print(f"TP: {tool_results['tp']}, FP: {tool_results['fp']}, FN: {tool_results['fn']}")

    # Write report file
    report_path = WORKSPACE_ROOT / "kattappa_native/checkpoints/mini/evaluation_report.json"
    report = {
        "step": state.get("step", 0),
        "reasoning": {
            "accuracy": r_results["accuracy"],
            "correct": r_results["correct"],
            "total": r_results["total"]
        },
        "telugu": t_results,
        "tool_use": {
            "f1": tool_results["f1"],
            "precision": tool_results["precision"],
            "recall": tool_results["recall"]
        }
    }
    with open(report_path, "w", encoding="utf-8") as f:
        import json
        json.dump(report, f, indent=2)
    print(f"\n📝 Wrote evaluation report to {report_path.relative_to(WORKSPACE_ROOT)}")

if __name__ == "__main__":
    main()
