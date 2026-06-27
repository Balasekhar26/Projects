#!/usr/bin/env python3
"""
KM-5.3 — Kattappa Gated Training Engine with Proactive Admission Control
======================================================================
Main training loop for Kattappa-100M from scratch.

Features:
  - OS-style predictive admission control (estimated memory requirements gating)
  - Global mutual exclusion lock via Unix flock to serialize heavyweight tasks
  - Step-based curriculum sequence lengths (256 -> 512 -> 1024 -> 2048)
  - Proactive parameter scaling (microbatch and seq length reduction)
  - Clean serialized evaluations and checkpoints
"""

import argparse
import csv
from datetime import datetime, timezone
import json
import math
import os
import psutil
import random
import sys
import time
from pathlib import Path
from typing import Iterator, List

import torch
import torch.nn as nn

WORKSPACE_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(WORKSPACE_ROOT))

from kattappa_native.model.model import KattappaConfig, KattappaModel
from kattappa_native.training.checkpoint import CheckpointManager
from kattappa_native.training.optimizer import build_optimizer
from kattappa_native.training.scheduler import CosineScheduler
from kattappa_runtime.resource_governor.monitor import ResourceMonitor
from kattappa_runtime.resource_governor.safety_controller import (
    SafetyController,
    heavyweight_task,
)
from kattappa_runtime.resource_governor.schema import (
    SafetyThresholds,
    TrainerBudget,
    TrainingConfig,
)


def append_step_metrics_csv(step, batch, seq, loss_val, forward_time, backward_time, optimizer_time, step_time, metrics=None, csv_path=None):
    if csv_path is None:
        csv_path = os.path.expanduser("~/Desktop/training_step_timeline.csv")
    try:
        os.makedirs(os.path.dirname(csv_path), exist_ok=True)
    except Exception:
        pass
    write_header = not os.path.exists(csv_path)
    
    # Process memory metrics
    try:
        process = psutil.Process(os.getpid())
        python_rss = process.memory_info().rss / (1024 * 1024) # MB
    except Exception:
        python_rss = 0.0
        
    # GPU Memory
    gpu_driver_allocated_bytes = 0
    gpu_current_allocated_bytes = 0
    if torch.backends.mps.is_available():
        try:
            gpu_driver_allocated_bytes = torch.mps.driver_allocated_memory()
            gpu_current_allocated_bytes = torch.mps.current_allocated_memory()
        except Exception:
            pass
            
    # System metrics
    swap_used_gb = 0.0
    compressed_memory_pct = 0.0
    pageouts_per_sec = 0.0
    if metrics is not None:
        swap_used_gb = metrics.swap_used_gb
        compressed_memory_pct = metrics.compressed_memory_pct
        pageouts_per_sec = metrics.pageouts_per_sec
    else:
        try:
            sw = psutil.swap_memory()
            swap_used_gb = sw.used / (1024**3)
        except Exception:
            pass

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
    
    with open(csv_path, mode="a", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        if write_header:
            writer.writerow([
                "timestamp", "step", "batch", "seq_len", "loss",
                "iteration_duration_s", "forward_duration_s", "backward_duration_s", "optimizer_duration_s",
                "mps_driver_allocated_bytes", "mps_current_allocated_bytes",
                "python_rss_mb", "swap_used_gb", "compressed_memory_pct", "pageouts_per_sec"
            ])
        writer.writerow([
            timestamp, step, batch, seq, f"{loss_val:.4f}",
            f"{step_time:.4f}", f"{forward_time:.4f}", f"{backward_time:.4f}", f"{optimizer_time:.4f}",
            gpu_driver_allocated_bytes, gpu_current_allocated_bytes,
            f"{python_rss:.1f}", f"{swap_used_gb:.3f}", f"{compressed_memory_pct:.1f}", f"{pageouts_per_sec:.1f}"
        ])
        f.flush()

# ── Simple text dataloader ─────────────────────────────────────────────────────

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


# Load SentencePiece tokenizer if available
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
        if len(ids) < seq_len + 1:
            ids = ids + [0] * (seq_len + 1 - len(ids))
        else:
            ids = ids[:seq_len + 1]
        return torch.tensor(ids, dtype=torch.long)
    else:
        ids = [ord(c) % vocab_size for c in text[:seq_len]]
        while len(ids) < seq_len + 1:
            ids.append(1)
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
        logits, loss = model(x, targets=y)
        if loss is not None:
            total_loss += loss.item()
        del logits, x, y
    model.train()
    return math.exp(total_loss / n_batches)


# ── Main Gated Training Loop ───────────────────────────────────────────────────

def train(args):
    if getattr(args, "device", None) is not None:
        device = torch.device(args.device)
    elif torch.cuda.is_available():
        device = torch.device("cuda")
    elif torch.backends.mps.is_available():
        device = torch.device("mps")
    else:
        device = torch.device("cpu")
    use_bf16 = device.type == "cuda"
    dtype = torch.bfloat16 if use_bf16 else torch.float32

    # ── Initialize Safety Infrastructure ─────────────────────────────────────
    monitor_interval = 1.0 if not getattr(args, "no_monitor", False) else 10.0
    monitor = ResourceMonitor(interval=monitor_interval)
    if not getattr(args, "no_monitor", False):
        monitor.start()
        print(f"\n⏱️  ResourceMonitor started (interval={monitor_interval}s)")
    else:
        # Start the monitor thread but at a very slow poll rate so get_metrics()
        # still returns a valid (stale) metrics object without subprocess overhead.
        monitor.start()
        print(f"\n⏱️  ResourceMonitor running in LOW-RATE mode (interval={monitor_interval}s) — subprocesses suppressed by slow poll")
    
    thresholds = SafetyThresholds(
        mps_pause_gb=args.kattappa_budget_gb,
        mps_warn_gb=args.kattappa_budget_gb - 1.0,
        memory_pause_level=args.memory_pause_level,
    )
    budget = TrainerBudget(
        kattappa_budget_gb=args.kattappa_budget_gb,
        d_model=args.d_model,
        n_layers=args.n_layers,
        n_heads=args.n_heads,
        bytes_per_param=2.0 if (use_bf16 or device.type == "mps") else 4.0
    )
    safety_config = TrainingConfig(
        initial_seq_len=args.initial_seq_len,
        target_seq_len=args.seq_len,
        safety_mode=args.safety_mode
    )
    
    safety = SafetyController(monitor, thresholds, budget, safety_config)

    print(f"\n🚀  Kattappa Proactive Safety Training Engine")
    print(f"    Device : {device}  |  Precision: {'BF16' if use_bf16 else 'FP16 (AMP)' if device.type == 'mps' else 'FP32'}")
    print(f"    Target Steps : {args.steps}  |  Training Budget: {args.kattappa_budget_gb} GB")
    
    # Pre-flight parameter safety approval
    approval = safety.approve_training_config(args.batch, args.seq_len)
    active_batch = approval.max_safe_batch
    active_seq_len = approval.max_safe_seq_len
    
    if not approval.approved:
        print(f"⚠️  Safety Controller adjusted configuration to protect memory budget:")
        print(f"    Requested Batch: {args.batch} -> Approved: {active_batch}")
        print(f"    Requested Seq Len: {args.seq_len} -> Approved: {active_seq_len}")
        print(f"    Reason: {approval.reason}")
    else:
        print(f"✅  Training parameters approved: batch={active_batch}, seq={active_seq_len}")

    # Load data
    print(f"\n📚  Loading training data...")
    all_texts = load_texts_from_workspace(WORKSPACE_ROOT)
    if len(all_texts) < 10:
        all_texts = [
            f"This is Kattappa training sample number {i}. Building AI from scratch." * 5
            for i in range(200)
        ]
    print(f"    Loaded {len(all_texts):,} text records")

    split = int(0.9 * len(all_texts))
    random.shuffle(all_texts)
    train_texts = all_texts[:split]
    val_texts   = all_texts[split:]
    print(f"    Train: {len(train_texts):,}  |  Val: {len(val_texts):,}")

    # Find resume checkpoint first to dynamically infer config shapes
    resume_path = None
    inferred_n_kv_heads = 4
    if getattr(args, "resume", "true") == "true":
        ckpt_dir = Path(args.checkpoint_dir)
        latest_pts = sorted(ckpt_dir.glob("checkpoint_step_*.pt"))
        latest_ckpt = latest_pts[-1] if latest_pts else None
        best_ckpt   = ckpt_dir / "checkpoint_best.pt"
        resume_path = str(latest_ckpt) if latest_ckpt and latest_ckpt.exists() else (
                      str(best_ckpt)   if best_ckpt.exists() else None)
        if resume_path:
            try:
                # Load state dict header to check shapes
                temp_state = torch.load(resume_path, map_location="cpu")
                state_dict = temp_state.get("model_state_dict", temp_state)
                first_qkv = state_dict.get("blocks.0.attn.qkv.weight")
                if first_qkv is not None:
                    total_dim = first_qkv.shape[0]
                    inferred_n_kv_heads = (total_dim - args.d_model) // 128
                    print(f"🔍  Inferred n_kv_heads from resume checkpoint: {inferred_n_kv_heads}")
                del temp_state, state_dict
            except Exception as e:
                print(f"⚠️  Failed to pre-read checkpoint shape: {e}")

    # Build model (allocate with max sequence limit configuration)
    cfg = KattappaConfig(
        n_layers=args.n_layers,
        n_heads=args.n_heads,
        n_kv_heads=inferred_n_kv_heads,
        d_model=args.d_model,
        d_ff=args.d_model * 4,
        context_length=max(active_seq_len, args.seq_len),
        vocab_size=32000,
        dropout=0.1,
    )
    model = KattappaModel(cfg).to(device)
    if use_bf16:
        model = model.to(dtype)
    print(f"\n🧠  {model}")

    optimizer = build_optimizer(model, lr=args.lr)
    scheduler = CosineScheduler(optimizer, total_steps=args.steps,
                                peak_lr=args.lr, warmup_ratio=0.02)
    ckpt_manager = CheckpointManager(args.checkpoint_dir, keep_last_n=1, timing_log_path=args.timing_log_path)

    # Resume from checkpoint if present
    start_step = 0
    if resume_path:
        state = ckpt_manager.load(path=resume_path, model=model, optimizer=optimizer,
                                  scheduler=scheduler, device=str(device))
        start_step = state.get("step", 0)
        print(f"  ▶  Resuming from step {start_step} ({Path(resume_path).name})")
        del state
        safety.emergency_gc()

    # Training loop configurations
    model.train()
    use_amp = (device.type == "mps")
    if use_bf16:
        scaler = torch.cuda.amp.GradScaler()
    elif use_amp:
        scaler = torch.amp.GradScaler("mps")
    else:
        scaler = None

    micro_batch_size = active_batch
    accum_steps = 1
    
    # Curriculum initialization based on starting step:
    # Steps 0-5k: 256
    # 5k-15k: 512
    # 15k-30k: 1024
    # 30k+: 2048
    current_seq_len = active_seq_len
    if args.curriculum:
        if start_step < 5000:
            current_seq_len = min(256, args.seq_len)
        elif start_step < 15000:
            current_seq_len = min(512, args.seq_len)
        elif start_step < 30000:
            current_seq_len = min(1024, args.seq_len)
        else:
            current_seq_len = min(2048, args.seq_len)
        print(f"📚 Curriculum Active: Step {start_step} -> Start seq_len = {current_seq_len}")

    data_itr = batch_iterator(train_texts, micro_batch_size, current_seq_len, cfg.vocab_size, device)

    print(f"\n{'='*60}")
    print(f"  Starting training from step {start_step}...")
    print(f"  Micro-batch size: {micro_batch_size} | Accumulation steps: {accum_steps} | Seq Len: {current_seq_len}")
    print(f"{'='*60}\n")

    t_start = time.time()
    optimizer.zero_grad(set_to_none=True)

    postponed_eval_pending = False
    postponed_ckpt_pending = False
    last_val_ppl = 100.0
    last_heartbeat_time = 0.0

    try:
        for step in range(start_step, args.steps):
            step_start_time = time.time()
            
            # 1-second thread heartbeat logger
            current_time = time.time()
            if current_time - last_heartbeat_time >= 1.0:
                last_heartbeat_time = current_time
                try:
                    hb_path = os.path.expanduser("~/Desktop/kattappa_heartbeat_main.txt")
                    with open(hb_path, "w") as f:
                        f.write(f"{current_time}\n")
                except Exception:
                    pass

            # ── 1. Step-based Curriculum progression ───────────────────────────────
            if args.curriculum:
                target_stage_seq = current_seq_len
                if step < 5000:
                    target_stage_seq = min(256, args.seq_len)
                elif step < 15000:
                    target_stage_seq = min(512, args.seq_len)
                elif step < 30000:
                    target_stage_seq = min(1024, args.seq_len)
                else:
                    target_stage_seq = min(2048, args.seq_len)
                
                if target_stage_seq != current_seq_len:
                    current_seq_len = target_stage_seq
                    print(f"📚 Curriculum progression to seq_len={current_seq_len} at step {step}")
                    data_itr = batch_iterator(train_texts, micro_batch_size, current_seq_len, cfg.vocab_size, device)

            # ── 2. Proactive Workload Admission Control ────────────────────────────
            eval_now = (step > 0 and step % args.eval_interval == 0) or postponed_eval_pending
            checkpointing_now = (step > 0 and step % args.eval_interval == 0) or postponed_ckpt_pending
            
            if getattr(args, "inference_only", False):
                eval_now = False
                checkpointing_now = False
                postponed_eval_pending = False
                postponed_ckpt_pending = False
            
            # Isolation flags override eval/checkpoint independently
            if getattr(args, "no_eval", False):
                eval_now = False
                postponed_eval_pending = False
            if getattr(args, "no_checkpoint", False):
                checkpointing_now = False
                postponed_ckpt_pending = False
            
            projected = safety.estimate_memory_detailed(
                micro_batch_size, current_seq_len, checkpointing=checkpointing_now
            )
            projected_memory = projected["total_projected_gb"]
            
            # Gating loop: Reduce sequence length or microbatch until projected memory fits budget
            while projected_memory > safety.budget.kattappa_budget_gb:
                if checkpointing_now:
                    print(f"⚠️  Admission Control: Postponing checkpoint/evaluation due to projected memory footprint of checkpoint buffer ({projected['estimated_checkpoint_buffers_gb']:.2f} GB).")
                    postponed_ckpt_pending = True
                    postponed_eval_pending = True
                    checkpointing_now = False
                    eval_now = False
                elif micro_batch_size > safety_config.min_microbatch:
                    micro_batch_size -= 1
                    accum_steps = math.ceil(args.batch / micro_batch_size)
                    print(f"⚠️  Admission Control: Shrinking microbatch to {micro_batch_size} to fit memory projection.")
                elif current_seq_len > safety_config.initial_seq_len:
                    lower_seqs = [s for s in safety_config.seq_len_steps if s < current_seq_len]
                    current_seq_len = max(lower_seqs) if lower_seqs else safety_config.initial_seq_len
                    print(f"⚠️  Admission Control: Shrinking sequence length to {current_seq_len} to fit memory projection.")
                else:
                    print(f"⚠️  Admission Control: Critical projected usage ({projected_memory:.2f} GB) exceeds budget ({safety.budget.kattappa_budget_gb} GB) even at minimums. Gating execution step.")
                    print("Estimated memory breakdown:")
                    for k, v in projected.items():
                        print(f"  {k}: {v:.4f} GB")
                    safety.wait_for_safe(timeout_s=180)
                    break
                
                # Re-estimate requirements with shrunken config
                projected = safety.estimate_memory_detailed(
                    micro_batch_size, current_seq_len, checkpointing=checkpointing_now
                )
                projected_memory = projected["total_projected_gb"]
                data_itr = batch_iterator(train_texts, micro_batch_size, current_seq_len, cfg.vocab_size, device)

            # ── 3. Real-Time Resource Warning & Pause Checks ───────────────────────
            verdict = safety.assess()
            if verdict.pause:
                print(f"⚠️  Safety pause triggered: {verdict.reason}")
                if args.safety_mode == "strict":
                    if eval_now or checkpointing_now:
                        postponed_ckpt_pending = True
                        postponed_eval_pending = True
                        eval_now = False
                        checkpointing_now = False
                    safety.wait_for_safe(timeout_s=180)
                    verdict = safety.assess()

            if verdict.warn:
                print(f"⚠️  Emergency Degradation triggered by safety warning: {verdict.reason}")
                if args.safety_mode == "strict":
                    if eval_now or checkpointing_now:
                        print("⚠️  Emergency Degradation: Postponing scheduled evaluation & checkpoint.")
                        postponed_ckpt_pending = True
                        postponed_eval_pending = True
                        eval_now = False
                        checkpointing_now = False
                    if current_seq_len > safety_config.initial_seq_len:
                        lower_seqs = [s for s in safety_config.seq_len_steps if s < current_seq_len]
                        current_seq_len = max(lower_seqs) if lower_seqs else safety_config.initial_seq_len
                        print(f"⚠️  Emergency Degradation: Shrinking seq_len to {current_seq_len}")
                    if micro_batch_size > safety_config.min_microbatch:
                        micro_batch_size -= 1
                        accum_steps = math.ceil(args.batch / micro_batch_size)
                        print(f"⚠️  Emergency Degradation: Shrinking microbatch to {micro_batch_size}, accum steps={accum_steps}")
                    data_itr = batch_iterator(train_texts, micro_batch_size, current_seq_len, cfg.vocab_size, device)

            elif verdict.recommended_microbatch is not None and args.safety_mode == "strict":
                new_micro = verdict.recommended_microbatch
                if new_micro < micro_batch_size:
                    micro_batch_size = max(1, new_micro)
                    accum_steps = math.ceil(args.batch / micro_batch_size)
                    print(f"⚡  Safety metrics triggered microbatch scale-down: microbatch={micro_batch_size}, accum={accum_steps}")
                    data_itr = batch_iterator(train_texts, micro_batch_size, current_seq_len, cfg.vocab_size, device)
                elif new_micro > micro_batch_size and safety.healthy_steps_counter >= safety.thresholds.stable_steps_to_grow:
                    micro_batch_size = min(active_batch, micro_batch_size + 1)
                    accum_steps = math.ceil(args.batch / micro_batch_size)
                    print(f"⚡  Safety metrics triggered microbatch scale-up: microbatch={micro_batch_size}, accum={accum_steps}")
                    data_itr = batch_iterator(train_texts, micro_batch_size, current_seq_len, cfg.vocab_size, device)
                    safety.healthy_steps_counter = 0

            # ── 4. Execute Step in Mutual Exclusion lock ─────────────────────────
            loss_val = 0.0
            forward_time = 0.0
            backward_time = 0.0
            optimizer_time = 0.0

            with heavyweight_task("training"):
                if getattr(args, "inference_only", False):
                    # Test 6: Pure Inference mode
                    with torch.no_grad():
                        for micro_step in range(accum_steps):
                            x, y = next(data_itr)
                            t_f0 = time.time()
                            if use_bf16:
                                with torch.autocast(device_type="cuda", dtype=dtype):
                                    logits, loss = model(x, targets=y)
                            elif use_amp:
                                with torch.amp.autocast(device_type="mps", dtype=torch.float16):
                                    logits, loss = model(x, targets=y)
                            else:
                                logits, loss = model(x, targets=y)
                            del logits
                            forward_time += time.time() - t_f0
                            if loss is not None:
                                loss_val += loss.item()
                            del x, y, loss
                    lr = args.lr
                else:
                    # Regular training mode
                    for micro_step in range(accum_steps):
                        x, y = next(data_itr)
                        
                        t_f0 = time.time()
                        if use_bf16:
                            with torch.autocast(device_type="cuda", dtype=dtype):
                                logits, loss = model(x, targets=y)
                            del logits
                            forward_time += time.time() - t_f0
                            
                            t_b0 = time.time()
                            loss = loss / accum_steps
                            scaler.scale(loss).backward()
                            backward_time += time.time() - t_b0
                            loss_val += loss.item() * accum_steps
                        elif use_amp:
                            with torch.amp.autocast(device_type="mps", dtype=torch.float16):
                                logits, loss = model(x, targets=y)
                            del logits
                            forward_time += time.time() - t_f0
                            
                            t_b0 = time.time()
                            loss = loss / accum_steps
                            scaler.scale(loss).backward()
                            backward_time += time.time() - t_b0
                            loss_val += loss.item() * accum_steps
                        else:
                            logits, loss = model(x, targets=y)
                            del logits
                            forward_time += time.time() - t_f0
                            
                            t_b0 = time.time()
                            loss = loss / accum_steps
                            loss.backward()
                            backward_time += time.time() - t_b0
                            loss_val += loss.item() * accum_steps
                        
                        # Delete intermediate tensors to free up MPS memory cache
                        del x, y, loss

                    # Update model parameters
                    t_o0 = time.time()
                    if use_bf16 or use_amp:
                        scaler.unscale_(optimizer)
                        torch.nn.utils.clip_grad_norm_(model.parameters(), args.grad_clip)
                        scaler.step(optimizer)
                        scaler.update()
                    else:
                        torch.nn.utils.clip_grad_norm_(model.parameters(), args.grad_clip)
                        optimizer.step()

                    lr = scheduler.step()
                    optimizer.zero_grad(set_to_none=True)
                    optimizer_time = time.time() - t_o0

            step_time = time.time() - step_start_time
            # Log metrics to CSV for pre-panic diagnostics
            try:
                append_step_metrics_csv(
                    step, args.batch, current_seq_len, loss_val,
                    forward_time, backward_time, optimizer_time,
                    step_time, monitor.get_metrics(),
                    csv_path=args.timeline_log_path
                )
            except Exception as e:
                print(f"⚠️  Failed to write timeline metrics: {e}")

            if device.type == "mps" and step % args.log_interval == 0:
                safety.emergency_gc()

            # Logging
            if step % args.log_interval == 0:
                elapsed = time.time() - t_start
                tokens_per_sec = (step - start_step + 1) * args.batch * current_seq_len / max(elapsed, 1)
                metrics = monitor.get_metrics()
                print(
                    f"  step {step:>7d}/{args.steps}  "
                    f"loss={loss_val:.4f}  "
                    f"ppl={math.exp(min(loss_val, 100.0)):.2f}  "
                    f"lr={lr:.2e}  "
                    f"tok/s={tokens_per_sec:,.0f}  "
                    f"mps_gb={metrics.unified_memory_used_gb:.2f}  "
                    f"swap_gb={metrics.swap_used_gb:.2f}  "
                    f"pageouts={metrics.pageouts_per_sec:.1f}/s"
                )

            # ── 5. Serialized Evaluation & Checkpointing ───────────────────────────
            if eval_now or checkpointing_now:
                # 1. Post-train recovery pause
                print("⌛  Post-train recovery pause...")
                time.sleep(2.0)
                safety.emergency_gc()
                safety.wait_for_safe(timeout_s=60)
                
                # 2. Checkpoint serialization
                if checkpointing_now:
                    print(f"💾  Step {step} — Saving checkpoint...")
                    with heavyweight_task("checkpoint serialization"):
                        ckpt_manager.save(
                            step=step,
                            model=model,
                            optimizer=optimizer,
                            scheduler=scheduler,
                            val_ppl=last_val_ppl,
                            extra={
                                "train_loss": loss_val,
                                "lr": lr,
                                "seq_len": current_seq_len,
                                "micro_batch": micro_batch_size
                            },
                        )
                    postponed_ckpt_pending = False
                    
                    # 3. Post-checkpoint recovery pause
                    print("⌛  Post-checkpoint recovery pause...")
                    time.sleep(2.0)
                    safety.emergency_gc()
                    safety.wait_for_safe(timeout_s=60)
                
                # 4. Evaluation
                if eval_now:
                    print(f"📊  Step {step} — Starting serialized evaluation...")
                    with heavyweight_task("evaluation"):
                        last_val_ppl = evaluate(
                            model, val_texts, micro_batch_size, current_seq_len,
                            cfg.vocab_size, device, n_batches=30
                        )
                    print(f"📊  Step {step} — Evaluation complete. Val PPL: {last_val_ppl:.4f}")
                    postponed_eval_pending = False
                    
                    # 5. Post-evaluation recovery pause
                    print("⌛  Post-evaluation recovery pause...")
                    time.sleep(2.0)
                    safety.emergency_gc()
                    safety.wait_for_safe(timeout_s=60)

        # Final save
        print("⌛  Final save preparation recovery pause...")
        time.sleep(2.0)
        safety.emergency_gc()
        safety.wait_for_safe(timeout_s=60)
        
        print("📊  Final save — Starting serialized evaluation...")
        with heavyweight_task("evaluation"):
            last_val_ppl = evaluate(
                model, val_texts, micro_batch_size, current_seq_len,
                cfg.vocab_size, device, n_batches=20
            )
            
        print("⌛  Final save — post-evaluation recovery pause...")
        time.sleep(2.0)
        safety.emergency_gc()
        safety.wait_for_safe(timeout_s=60)
        
        print("💾  Final save — Saving final checkpoint...")
        with heavyweight_task("checkpoint serialization"):
            ckpt_manager.save(
                step=args.steps,
                model=model,
                optimizer=optimizer,
                scheduler=scheduler,
                val_ppl=last_val_ppl,
                extra={"final": True},
            )
        print(f"\n✅  Training complete. Final val PPL: {last_val_ppl:.4f}")
        print(f"   Checkpoints saved to: {args.checkpoint_dir}\n")

    finally:
        monitor.stop()


def main():
    parser = argparse.ArgumentParser(description="Kattappa-100M Gated Trainer")
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
    
    # Safety Governor flags
    parser.add_argument("--kattappa-budget-gb", type=float, default=8.4,
                        help="Hard limit on unified memory (MPS) usage for the trainer in GB")
    parser.add_argument("--initial-seq-len",    type=int,   default=256,
                        help="Curriculum starting sequence length")
    parser.add_argument("--curriculum",         action="store_true",
                        help="Enable curriculum learning (seq_len steps from initial to target)")
    parser.add_argument("--safety-mode",        type=str,   default="strict",
                        choices=["strict", "monitor"],
                        help="strict mode pauses training when thresholds are violated")
    parser.add_argument("--memory-pause-level",  type=str,   default="WARNING",
                        choices=["OFF", "CRITICAL", "WARNING"],
                        help="Configure the macOS memory pressure safety pause level")
    parser.add_argument("--resume",             type=str,   default="true",
                        choices=["true", "false"],
                        help="Resume from latest checkpoint if present")
    parser.add_argument("--timeline-log-path",  type=str,   default=os.path.expanduser("~/Desktop/training_step_timeline.csv"),
                        help="Path to write the CSV timeline metrics log")
    parser.add_argument("--timing-log-path",    type=str,   default=os.path.expanduser("~/Desktop/checkpoint_timing.jsonl"),
                        help="Path to write the checkpoint timing JSONL log")
    parser.add_argument("--device",         type=str,   default=None,
                        choices=["cpu", "mps", "cuda"],
                        help="Force CPU, MPS, or CUDA device")
    parser.add_argument("--inference-only", action="store_true",
                        help="Run in pure inference mode (Test 6: no backward, no optimizer, no checkpoints)")
    
    # Isolation flags
    parser.add_argument("--no-checkpoint", action="store_true",
                        help="Disable checkpoint saving (isolation test: checkpoint subsystem)")
    parser.add_argument("--no-eval",       action="store_true",
                        help="Disable evaluation (isolation test: eval subsystem)")
    parser.add_argument("--no-monitor",    action="store_true",
                        help="Run ResourceMonitor at 10s interval instead of 1s (isolation test: subprocess overhead)")
    
    args = parser.parse_args()
    train(args)


if __name__ == "__main__":
    main()
