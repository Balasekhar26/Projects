#!/usr/bin/env python3
"""
KM-5.3 — Kattappa Training Engine
====================================
Main training loop for Kattappa-100M from scratch.

Features:
  - BF16 mixed precision (GPU) / FP32 (CPU)
  - Gradient clipping (max norm 1.0)
  - Cosine LR schedule with 2% warmup
  - Eval perplexity at configurable intervals
  - Checkpoint save/resume
  - Structured per-step logging

Usage:
    # CPU dry-run (smoke test, ~10 steps)
    PYTHONPATH=. python3 kattappa_native/training/trainer.py --steps 10 --batch 2 --seq-len 64

    # GPU training (full Alpha run)
    PYTHONPATH=. python3 kattappa_native/training/trainer.py \\
        --steps 50000 --batch 8 --seq-len 2048 \\
        --lr 3e-4 --grad-clip 1.0 --eval-interval 200 \\
        --checkpoint-dir kattappa_native/checkpoints/alpha
"""

import os
import sys
import json
import math
import time
import argparse
import random
from pathlib import Path
from typing import Iterator, List

import torch
import torch.nn as nn

WORKSPACE_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(WORKSPACE_ROOT))

from kattappa_native.model.model import KattappaModel, KattappaConfig
from kattappa_native.training.optimizer import build_optimizer
from kattappa_native.training.scheduler import CosineScheduler
from kattappa_native.training.checkpoint import CheckpointManager


# ── Simple text dataloader (no external dependencies) ──────────────────────────

def load_texts_from_workspace(root: Path) -> List[str]:
    """Load all text strings from JSONL datasets in the workspace."""
    texts = []
    target_dir = root / "kattappa_native/corpus/deduped"
    if not target_dir.exists():
        target_dir = root
    jsonl_files = [
        p for p in target_dir.rglob("*.jsonl")
        if "ai_system_env" not in str(p)
        and "episodic.jsonl" not in str(p)
        and "semantic.jsonl" not in str(p)
    ]
    for path in jsonl_files:
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    text = " ".join(str(v) for v in rec.values() if isinstance(v, str))
                    if len(text) > 30:
                        texts.append(text)
        except Exception:
            continue
    return texts


# Load real SentencePiece tokenizer if available
SP_PROCESSOR = None
try:
    import sentencepiece as spm
    _tok_path = Path(__file__).parent.parent / "tokenizer/kattappa_tokenizer.model"
    if _tok_path.exists():
        SP_PROCESSOR = spm.SentencePieceProcessor()
        SP_PROCESSOR.Load(str(_tok_path))
        print(f"\n[Tokenizer] Loaded real tokenizer model from {_tok_path.name}")
except Exception as e:
    print(f"\n[Tokenizer] Warning: Failed to load real tokenizer: {e}. Falling back to mock tokenisation.")


def tokenize_text(text: str, seq_len: int, vocab_size: int = 32000) -> torch.Tensor:
    """Tokenises text using real SentencePiece model if loaded; else falls back to character-level mock."""
    if SP_PROCESSOR is not None:
        ids = SP_PROCESSOR.encode(text, out_type=int)
        # Pad with 0 (<pad>) or truncate
        if len(ids) < seq_len + 1:
            ids = ids + [0] * (seq_len + 1 - len(ids))
        else:
            ids = ids[:seq_len + 1]
        return torch.tensor(ids, dtype=torch.long)
    else:
        # Deterministic character-level token IDs for CPU smoke testing
        ids = [ord(c) % vocab_size for c in text[:seq_len]]
        while len(ids) < seq_len + 1:
            ids.append(1)  # pad (1)
        return torch.tensor(ids[:seq_len + 1], dtype=torch.long)


def batch_iterator(
    texts: List[str],
    batch_size: int,
    seq_len: int,
    vocab_size: int,
    device: torch.device,
) -> Iterator[tuple]:
    """Yields (input_ids, targets) tuples indefinitely."""
    random.shuffle(texts)
    idx = 0
    while True:
        batch_inputs, batch_targets = [], []
        for _ in range(batch_size):
            text = texts[idx % len(texts)]
            idx += 1
            tokens = tokenize_text(text, seq_len, vocab_size)
            batch_inputs.append(tokens[:-1])
            batch_targets.append(tokens[1:])
        yield (
            torch.stack(batch_inputs).to(device),
            torch.stack(batch_targets).to(device),
        )


# ── Evaluation ─────────────────────────────────────────────────────────────────

@torch.no_grad()
def evaluate(model: nn.Module, texts: List[str], batch_size: int,
             seq_len: int, vocab_size: int, device: torch.device,
             n_batches: int = 20) -> float:
    """Returns validation perplexity over n_batches batches."""
    model.eval()
    total_loss = 0.0
    itr = batch_iterator(texts, batch_size, seq_len, vocab_size, device)
    for _ in range(n_batches):
        x, y = next(itr)
        _, loss = model(x, targets=y)
        if loss is not None:
            total_loss += loss.item()
    model.train()
    return math.exp(total_loss / n_batches)


# ── Main training loop ─────────────────────────────────────────────────────────

def train(args):
    if torch.cuda.is_available():
        device = torch.device("cuda")
    elif torch.backends.mps.is_available():
        device = torch.device("mps")
    else:
        device = torch.device("cpu")
    use_bf16 = device.type == "cuda"
    dtype = torch.bfloat16 if use_bf16 else torch.float32

    print(f"\n🚀  Kattappa Training Engine")
    print(f"    Device : {device}  |  Precision: {'BF16' if use_bf16 else 'FP32'}")
    print(f"    Steps  : {args.steps}  |  Batch: {args.batch}  |  Seq: {args.seq_len}")

    # Load data
    print(f"\n📚  Loading training data...")
    all_texts = load_texts_from_workspace(WORKSPACE_ROOT)
    if len(all_texts) < 10:
        # Fallback: generate dummy text for CPU smoke testing
        all_texts = [
            f"This is Kattappa training sample number {i}. Building AI from scratch." * 5
            for i in range(200)
        ]
    print(f"    Loaded {len(all_texts):,} text records")

    # Split train / validation (90% / 10%)
    split = int(0.9 * len(all_texts))
    random.shuffle(all_texts)
    train_texts = all_texts[:split]
    val_texts   = all_texts[split:]
    print(f"    Train: {len(train_texts):,}  |  Val: {len(val_texts):,}")

    # Build model
    cfg = KattappaConfig(
        n_layers=args.n_layers,
        n_heads=args.n_heads,
        d_model=args.d_model,
        d_ff=args.d_model * 4,
        context_length=args.seq_len,
        vocab_size=32000,
        dropout=0.1,
    )
    model = KattappaModel(cfg).to(device)
    if use_bf16:
        model = model.to(dtype)
    print(f"\n🧠  {model}")

    # Build optimizer and scheduler
    optimizer = build_optimizer(model, lr=args.lr)
    scheduler = CosineScheduler(optimizer, total_steps=args.steps,
                                peak_lr=args.lr, warmup_ratio=0.02)
    ckpt_manager = CheckpointManager(args.checkpoint_dir, keep_last_n=3)

    # Resume from checkpoint if present — prefer LATEST, fall back to BEST
    start_step = 0
    ckpt_dir = Path(args.checkpoint_dir)
    latest_pts = sorted(ckpt_dir.glob("checkpoint_step_*.pt"))
    latest_ckpt = latest_pts[-1] if latest_pts else None
    best_ckpt   = ckpt_dir / "checkpoint_best.pt"
    resume_path = str(latest_ckpt) if latest_ckpt and latest_ckpt.exists() else (
                  str(best_ckpt)   if best_ckpt.exists() else None)
    if resume_path:
        state = ckpt_manager.load(path=resume_path, model=model, optimizer=optimizer,
                                  scheduler=scheduler, device=str(device))
        start_step = state.get("step", 0)
        print(f"  ▶  Resuming from step {start_step} ({Path(resume_path).name})")

    # Training loop
    model.train()
    scaler = torch.cuda.amp.GradScaler() if use_bf16 else None
    data_itr = batch_iterator(train_texts, args.batch, args.seq_len, cfg.vocab_size, device)

    print(f"\n{'='*60}")
    print(f"  Starting training from step {start_step}...")
    print(f"{'='*60}\n")

    t_start = time.time()
    for step in range(start_step, args.steps):
        x, y = next(data_itr)
        lr = scheduler.step()

        optimizer.zero_grad(set_to_none=True)

        if use_bf16:
            with torch.autocast(device_type="cuda", dtype=dtype):
                _, loss = model(x, targets=y)
            scaler.scale(loss).backward()
            scaler.unscale_(optimizer)
            torch.nn.utils.clip_grad_norm_(model.parameters(), args.grad_clip)
            scaler.step(optimizer)
            scaler.update()
        else:
            _, loss = model(x, targets=y)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), args.grad_clip)
            optimizer.step()

        # Logging
        if step % args.log_interval == 0:
            elapsed = time.time() - t_start
            tokens_per_sec = (step - start_step + 1) * args.batch * args.seq_len / max(elapsed, 1)
            print(
                f"  step {step:>7d}/{args.steps}  "
                f"loss={loss.item():.4f}  "
                f"ppl={math.exp(loss.item()):.2f}  "
                f"lr={lr:.2e}  "
                f"tok/s={tokens_per_sec:,.0f}"
            )

        # Evaluation & checkpoint
        if step > 0 and step % args.eval_interval == 0:
            # 30 batches → ~240 samples: significantly more stable PPL estimate
            val_ppl = evaluate(model, val_texts, args.batch, args.seq_len,
                               cfg.vocab_size, device, n_batches=30)
            print(f"\n  📊 Step {step} — Val PPL: {val_ppl:.4f}\n")
            ckpt_manager.save(
                step=step,
                model=model,
                optimizer=optimizer,
                scheduler=scheduler,
                val_ppl=val_ppl,
                extra={"train_loss": loss.item(), "lr": lr},
            )

    # Final save
    val_ppl = evaluate(model, val_texts, args.batch, args.seq_len,
                       cfg.vocab_size, device, n_batches=20)
    ckpt_manager.save(
        step=args.steps,
        model=model,
        optimizer=optimizer,
        scheduler=scheduler,
        val_ppl=val_ppl,
        extra={"final": True},
    )
    print(f"\n✅  Training complete. Final val PPL: {val_ppl:.4f}")
    print(f"   Checkpoints saved to: {args.checkpoint_dir}\n")


def main():
    parser = argparse.ArgumentParser(description="Kattappa-100M Trainer")
    parser.add_argument("--steps",          type=int,   default=50000)
    parser.add_argument("--batch",          type=int,   default=8)
    parser.add_argument("--seq-len",        type=int,   default=2048)
    parser.add_argument("--lr",             type=float, default=3e-4)
    parser.add_argument("--grad-clip",      type=float, default=1.0)
    parser.add_argument("--eval-interval",  type=int,   default=200)
    parser.add_argument("--log-interval",   type=int,   default=10)
    parser.add_argument("--n-layers",       type=int,   default=12)
    parser.add_argument("--n-heads",        type=int,   default=12)
    parser.add_argument("--d-model",        type=int,   default=768)
    parser.add_argument("--checkpoint-dir", type=str,
                        default="kattappa_native/checkpoints/alpha")
    args = parser.parse_args()
    train(args)


if __name__ == "__main__":
    main()
