#!/usr/bin/env python3
"""
KM-5.1 — SentencePiece BPE Tokenizer Trainer
=============================================
Trains a 32k-vocabulary BPE tokenizer on a balanced 10M-token sample
drawn from the corpus. Outputs three locked artefacts:

    kattappa_native/tokenizer/kattappa_tokenizer.model
    kattappa_native/tokenizer/kattappa_tokenizer.json
    kattappa_native/tokenizer/vocab.json

⚠ DO NOT retrain after kattappa_native/model/ training begins.

Usage:
    PYTHONPATH=. python3 kattappa_native/tokenizer/train_tokenizer.py [--sample-limit 10000000]
"""

import os
import io
import re
import json
import random
import argparse
from pathlib import Path

WORKSPACE_ROOT = Path(__file__).parent.parent.parent
MANIFEST_PATH  = WORKSPACE_ROOT / "kattappa_native/corpus/corpus_manifest.json"
OUTPUT_DIR     = Path(__file__).parent

TELUGU_SCRIPT_RE = re.compile(r"[\u0C00-\u0C7F]")


def detect_category(text: str) -> str:
    tl = text.lower()
    if TELUGU_SCRIPT_RE.search(text):
        return "telugu"
    roman_markers = {"meeru", "nenu", "ela", "cheppandi", "ikkada", "vachha", "cheyyi", "poni"}
    if any(m in tl for m in roman_markers):
        return "roman_telugu"
    if any(m in text for m in {"def ", "class ", "import ", "```python", "function("}):
        return "programming"
    if any(m in tl for m in {"tool_call", "calculator", "search_mock"}):
        return "tool_traces"
    if any(m in tl for m in {"step 1", "therefore", "let me think", "equation"}):
        return "reasoning"
    if any(m in tl for m in {"architecture", "kubernetes", "microservice", "pipeline"}):
        return "engineering"
    return "general_knowledge"


def stream_texts_from_workspace(sample_limit: int, manifest: dict) -> list:
    """
    Draws texts from existing JSONL files, categorised and capped by
    tokenizer_sample ratios in the manifest.
    """
    tok_targets = manifest["tokenizer_sample"]["sources"]
    budgets = {cat: spec["target_tokens"] for cat, spec in tok_targets.items()}
    collected: dict[str, list[str]] = {cat: [] for cat in budgets}
    collected_tokens: dict[str, int] = {cat: 0 for cat in budgets}
    WORDS_PER_TOKEN = 0.75

    target_dir = WORKSPACE_ROOT / "kattappa_native/corpus/deduped"
    if not target_dir.exists():
        target_dir = WORKSPACE_ROOT
        
    jsonl_files = [
        p for p in sorted(target_dir.rglob("*.jsonl"))
        if "ai_system_env" not in str(p)
        and "episodic.jsonl" not in str(p)
        and "semantic.jsonl" not in str(p)
    ]
    random.shuffle(jsonl_files)

    for path in jsonl_files:
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        record = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    text = " ".join(str(v) for v in record.values() if isinstance(v, str))
                    if len(text) < 20:
                        continue
                    cat = detect_category(text)
                    est_tokens = int(len(text.split()) / WORDS_PER_TOKEN)
                    if collected_tokens.get(cat, 0) < budgets.get(cat, 0):
                        collected[cat].append(text)
                        collected_tokens[cat] = collected_tokens.get(cat, 0) + est_tokens
        except Exception:
            continue

        if all(collected_tokens.get(c, 0) >= budgets.get(c, 0) for c in budgets):
            break

    print("\n  📦 Tokenizer training sample summary:")
    all_texts = []
    for cat in budgets:
        n = len(collected[cat])
        tok = collected_tokens.get(cat, 0)
        target = budgets[cat]
        pct = round(100 * tok / target, 1) if target > 0 else 0
        status = "✅" if pct >= 70 else "⚠"
        print(f"     {status}  {cat:<22} {n:>6} records  ~{tok:>8,} tokens  ({pct:.1f}% of target)")
        all_texts.extend(collected[cat])

    random.shuffle(all_texts)
    return all_texts


def train(sample_texts: list, vocab_size: int = 32000, character_coverage: float = 1.0, output_dir: Path = OUTPUT_DIR):
    try:
        import sentencepiece as spm
    except ImportError:
        print("\n❌  sentencepiece is not installed.")
        print("    Run: ./ai_system_env/bin/pip install sentencepiece")
        return False

    output_dir.mkdir(parents=True, exist_ok=True)
    model_prefix = str(output_dir / "kattappa_tokenizer")

    # Write a temporary training corpus file
    corpus_path = output_dir / "train_corpus.tmp"
    print(f"\n  ✍  Writing {len(sample_texts):,} training texts to {corpus_path.name}...")
    with open(corpus_path, "w", encoding="utf-8") as f:
        for text in sample_texts:
            f.write(text.replace("\n", " ").strip() + "\n")

    print(f"  🏋  Training SentencePiece BPE tokenizer (vocab={vocab_size}, coverage={character_coverage})...")
    spm.SentencePieceTrainer.train(
        input=str(corpus_path),
        model_prefix=model_prefix,
        vocab_size=vocab_size,
        model_type="bpe",
        character_coverage=character_coverage,
        pad_id=0,
        unk_id=1,
        bos_id=2,
        eos_id=3,
        pad_piece="<pad>",
        unk_piece="<unk>",
        bos_piece="<bos>",
        eos_piece="<eos>",
        user_defined_symbols=["<sep>", "<mask>"],
        num_threads=4,
        input_sentence_size=5_000_000,
        shuffle_input_sentence=True,
    )
    corpus_path.unlink()  # Clean up temp file

    # Load model and export JSON vocab
    sp = spm.SentencePieceProcessor()
    sp.Load(model_prefix + ".model")

    vocab = {sp.id_to_piece(i): i for i in range(sp.get_piece_size())}

    # Write vocab.json
    vocab_path = output_dir / "vocab.json"
    vocab_path.write_text(json.dumps(vocab, indent=2, ensure_ascii=False))

    # Write kattappa_tokenizer.json (HuggingFace-compatible stub)
    tok_json = {
        "model_type": "BPE",
        "vocab_size": vocab_size,
        "model_file": "kattappa_tokenizer.model",
        "vocab_file": "vocab.json",
        "special_tokens": {
            "pad_token": "<pad>",
            "unk_token": "<unk>",
            "bos_token": "<bos>",
            "eos_token": "<eos>",
            "sep_token": "<sep>",
            "mask_token": "<mask>",
        },
        "trained_on": "Kattappa-100M balanced corpus sample",
        "version": "1.0.0",
        "lock_warning": (
            "DO NOT retrain this tokenizer after model training has started. "
            "Changing vocabulary requires a full model restart."
        ),
    }
    tok_json_path = output_dir / "kattappa_tokenizer.json"
    tok_json_path.write_text(json.dumps(tok_json, indent=2, ensure_ascii=False))

    print(f"\n  ✅  Tokenizer saved:")
    print(f"      {model_prefix}.model")
    print(f"      {tok_json_path}")
    print(f"      {vocab_path}")
    return True


def main():
    parser = argparse.ArgumentParser(description="Train Kattappa SentencePiece BPE tokenizer")
    parser.add_argument("--vocab-size", type=int, default=32000)
    parser.add_argument("--sample-limit", type=int, default=10_000_000,
                        help="Target token count for tokenizer training sample")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    random.seed(args.seed)
    manifest = json.loads(MANIFEST_PATH.read_text())

    print(f"\n🚀  Kattappa Tokenizer Trainer")
    print(f"    Vocab size   : {args.vocab_size:,}")
    print(f"    Sample limit : {args.sample_limit:,} tokens")
    print(f"    Seed         : {args.seed}")

    sample_texts = stream_texts_from_workspace(args.sample_limit, manifest)
    print(f"\n  Total training texts: {len(sample_texts):,}")

    char_cov = manifest.get("tokenizer", {}).get("character_coverage", 1.0)
    success = train(sample_texts, vocab_size=args.vocab_size, character_coverage=char_cov, output_dir=OUTPUT_DIR)
    if success:
        print(f"\n🔒  Tokenizer locked. Run tokenizer_eval.py to verify fertility before proceeding.\n")
    else:
        print(f"\n❌  Training failed. See error above.\n")


if __name__ == "__main__":
    main()
