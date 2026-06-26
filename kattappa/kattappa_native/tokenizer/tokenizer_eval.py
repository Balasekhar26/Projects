#!/usr/bin/env python3
"""
KM-5.1 — Tokenizer Evaluator
=============================
Validates the trained Kattappa tokenizer against fertility and
unknown-token thresholds before model training begins.

Checks:
  1. Telugu fertility  < 3.0 tokens/word
  2. English fertility < 1.4 tokens/word
  3. Roman Telugu fert < 1.6 tokens/word
  4. Code fertility    < 2.0 tokens/word
  5. Unknown-token rate < 0.1%

Usage:
    PYTHONPATH=. python3 kattappa_native/tokenizer/tokenizer_eval.py
"""

import json
import sys
from pathlib import Path

MODEL_PATH   = Path(__file__).parent / "kattappa_tokenizer.model"
MANIFEST_PATH = Path(__file__).parent.parent / "corpus/corpus_manifest.json"

# Test sentences per script
EVAL_SAMPLES = {
    "english": [
        "The quick brown fox jumps over the lazy dog.",
        "Artificial intelligence is transforming the modern world in profound ways.",
        "The transformer architecture uses self-attention mechanisms to process sequences.",
        "Machine learning models require large amounts of training data.",
        "Software engineering best practices include code reviews and automated testing.",
    ],
    "telugu": [
        "తెలుగు భాష చాలా అందమైన భాష.",
        "కత్తప్ప అనేది ఒక స్వంత భాషా మోడల్.",
        "భారతదేశంలో అనేక భాషలు మాట్లాడబడతాయి.",
        "విజ్ఞానం మరియు సాంకేతికత ముందుకు వెళ్తున్నాయి.",
        "తెలంగాణ రాష్ట్రంలో తెలుగు అధికారిక భాష.",
    ],
    "roman_telugu": [
        "Ela unnaru, bagunnara?",
        "Nenu Kattappa ni build chestunna.",
        "Meeru ela chestunnaru idhi?",
        "Idhi chala bagundi, keep it up.",
        "Mee project gurinchi cheppandi.",
    ],
    "code": [
        "def compute_attention(q, k, v, mask=None):",
        "import torch\nimport torch.nn as nn\nclass TransformerBlock(nn.Module):",
        "SELECT user_id, COUNT(*) FROM events GROUP BY user_id HAVING COUNT(*) > 10;",
        "const fetchData = async (url) => { const res = await fetch(url); return res.json(); };",
        "for i in range(len(tokens)):\n    hidden = self.attention(tokens[i])",
    ],
}


def compute_fertility(sp, sentences: list[str]) -> tuple[float, float]:
    """Returns (mean_fertility, unknown_rate) for a list of sentences."""
    total_words = 0
    total_tokens = 0
    total_chars = 0
    unk_count = 0
    unk_id = sp.unk_id()

    for sent in sentences:
        words = sent.split()
        total_words += len(words)
        ids = sp.encode(sent, out_type=int)
        total_tokens += len(ids)
        total_chars += len(sent)
        unk_count += sum(1 for t in ids if t == unk_id)

    fertility = total_tokens / max(total_words, 1)
    unk_rate = unk_count / max(total_tokens, 1)
    return round(fertility, 3), round(unk_rate, 5)


def run_eval() -> bool:
    if not MODEL_PATH.exists():
        print(f"\n❌  Tokenizer model not found: {MODEL_PATH}")
        print("    Run train_tokenizer.py first.\n")
        return False

    try:
        import sentencepiece as spm
    except ImportError:
        print("\n❌  sentencepiece is not installed. Run: ./ai_system_env/bin/pip install sentencepiece")
        return False

    sp = spm.SentencePieceProcessor()
    sp.Load(str(MODEL_PATH))

    manifest = json.loads(MANIFEST_PATH.read_text())
    thresholds = manifest["fertility_targets"]

    print(f"\n🧪  Kattappa Tokenizer Fertility Evaluation")
    print(f"    Model: {MODEL_PATH.name}  |  Vocab: {sp.get_piece_size():,} tokens\n")
    print(f"  {'Script':<16} {'Fertility':>10} {'Threshold':>10} {'UnkRate':>10}  Status")
    print(f"  {'-'*16} {'-'*10} {'-'*10} {'-'*10}  ------")

    all_pass = True
    results = {}

    for script, sentences in EVAL_SAMPLES.items():
        fertility, unk_rate = compute_fertility(sp, sentences)
        threshold = thresholds.get(script, 99.0)
        pass_fertility = fertility <= threshold
        pass_unk = unk_rate < 0.001

        passed = pass_fertility and pass_unk
        status = "✅ PASS" if passed else "❌ FAIL"
        if not passed:
            all_pass = False

        print(f"  {script:<16} {fertility:>10.3f} {threshold:>10.3f} {unk_rate:>9.5f}%  {status}")
        results[script] = {
            "fertility": fertility,
            "threshold": threshold,
            "unk_rate": unk_rate,
            "passed": passed,
        }

        # Print example tokenisation for Telugu (most critical)
        if script == "telugu":
            example = sentences[0]
            pieces = sp.encode(example, out_type=str)
            print(f"\n       Telugu tokenisation example:")
            print(f"       Input   : {example}")
            print(f"       Pieces  : {pieces[:15]} ...")
            print()

    print(f"\n  {'='*60}")
    if all_pass:
        print(f"  ✅  ALL CHECKS PASSED — tokenizer is ready for model training")
    else:
        print(f"  ❌  CHECKS FAILED — do NOT proceed to model training")
        print(f"\n  Likely causes:")
        print(f"    • Telugu fertility too high → tokenizer was trained on too little Telugu data")
        print(f"    • Fix: add more Telugu to corpus sample and retrain tokenizer")
        print(f"    • Unknown rate too high → add more diverse scripts to corpus")
    print(f"  {'='*60}\n")

    # Save eval report
    report_path = Path(__file__).parent / "tokenizer_eval_report.json"
    report_path.write_text(json.dumps({"results": results, "all_pass": all_pass}, indent=2))
    print(f"  📄 Eval report saved to: {report_path}\n")

    return all_pass


if __name__ == "__main__":
    ok = run_eval()
    sys.exit(0 if ok else 1)
