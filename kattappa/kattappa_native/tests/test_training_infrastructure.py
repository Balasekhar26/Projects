import os
import shutil
import tempfile
import random
import json
import math
import numpy as np
import torch
import torch.nn as nn
from pathlib import Path
import pytest

from kattappa_native.model.model import KattappaModel, KattappaConfig
from kattappa_native.training.checkpoint import CheckpointManager
from kattappa_native.training.scheduler import CosineScheduler
from kattappa_native.training.optimizer import build_optimizer


# 1. Deterministic Seed Validation
def test_deterministic_seed():
    def run_with_seed(seed):
        random.seed(seed)
        np.random.seed(seed)
        torch.manual_seed(seed)
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(seed)
        config = KattappaConfig(vocab_size=100, n_layers=2, n_heads=2, n_kv_heads=2, d_model=32, d_ff=64)
        model = KattappaModel(config)
        x = torch.randint(0, 100, (1, 10))
        return model(x)[0]

    out1 = run_with_seed(42)
    out2 = run_with_seed(42)
    out3 = run_with_seed(43)

    assert torch.allclose(out1, out2), "Same seed did not produce identical predictions!"
    assert not torch.allclose(out1, out3), "Different seeds produced identical predictions!"


# 2. LR Scheduler Verification
def test_learning_rate_scheduler():
    config = KattappaConfig(vocab_size=100, n_layers=1, n_heads=1, n_kv_heads=1, d_model=16, d_ff=32)
    model = KattappaModel(config)
    optimizer = build_optimizer(model, lr=3e-4)
    total_steps = 100
    warmup_ratio = 0.1
    scheduler = CosineScheduler(optimizer, total_steps=total_steps, peak_lr=3e-4, warmup_ratio=warmup_ratio)

    lrs = []
    for step in range(total_steps):
        lrs.append(optimizer.param_groups[0]['lr'])
        scheduler.step()

    # Peak LR reached at step 10 (warmup_steps = total_steps * warmup_ratio = 10)
    assert lrs[10] == pytest.approx(3e-4), "Peak learning rate not reached at end of warmup!"
    # Check that LR starts low and increases during warmup
    assert lrs[1] < lrs[10], "Warmup not working correctly!"
    # Check that final LR decays to min_lr
    assert lrs[-1] == pytest.approx(scheduler.min_lr, abs=1e-6), "Scheduler did not decay to min_lr!"


# 3. Checkpoint Save and Resume
def test_checkpoint_save_and_resume():
    with tempfile.TemporaryDirectory() as tmp_dir:
        config = KattappaConfig(vocab_size=100, n_layers=2, n_heads=2, n_kv_heads=2, d_model=32, d_ff=64)
        model = KattappaModel(config)
        optimizer = build_optimizer(model, lr=3e-4)
        scheduler = CosineScheduler(optimizer, total_steps=100)
        
        manager = CheckpointManager(tmp_dir, keep_last_n=2)
        
        # Save initial checkpoint
        orig_weights = {k: v.clone() for k, v in model.state_dict().items()}
        path = manager.save(step=5, model=model, optimizer=optimizer, scheduler=scheduler, val_ppl=10.5)
        
        # Mutate weights
        with torch.no_grad():
            for p in model.parameters():
                p.add_(1.0)
        
        # Verify weights changed
        mutated_weights = model.state_dict()
        assert not any(torch.allclose(orig_weights[k], mutated_weights[k]) for k in orig_weights), "Weights did not mutate!"
        
        # Resume
        state = manager.load(path=path, model=model, optimizer=optimizer, scheduler=scheduler)
        assert state["step"] == 5
        assert state["val_ppl"] == 10.5
        
        # Verify weights restored
        restored_weights = model.state_dict()
        for k in orig_weights:
            assert torch.allclose(orig_weights[k], restored_weights[k]), f"Weight {k} was not restored!"


# 4. Checkpoint Rollback
def test_checkpoint_rollback():
    with tempfile.TemporaryDirectory() as tmp_dir:
        config = KattappaConfig(vocab_size=100, n_layers=2, n_heads=2, n_kv_heads=2, d_model=32, d_ff=64)
        model = KattappaModel(config)
        optimizer = build_optimizer(model, lr=3e-4)
        scheduler = CosineScheduler(optimizer, total_steps=100)
        
        manager = CheckpointManager(tmp_dir, keep_last_n=2)
        
        # Save a healthy checkpoint
        orig_weights = {k: v.clone() for k, v in model.state_dict().items()}
        path = manager.save(step=10, model=model, optimizer=optimizer, scheduler=scheduler, val_ppl=8.2)
        
        # Simulate step that encounters NaN / divergence
        encounter_nan = False
        try:
            # Let's say loss goes NaN
            loss = torch.tensor(float('nan'))
            if torch.isnan(loss):
                raise ValueError("NaN encountered in training loss!")
        except ValueError:
            encounter_nan = True
            # Rollback to the healthy checkpoint
            manager.load(path=path, model=model, optimizer=optimizer, scheduler=scheduler)
            
        assert encounter_nan is True
        # Verify model weights rolled back successfully
        restored_weights = model.state_dict()
        for k in orig_weights:
            assert torch.allclose(orig_weights[k], restored_weights[k]), f"Rollback failed to restore weight {k}!"


# 5. Gradient Accumulation Verification
def test_gradient_accumulation():
    torch.manual_seed(42)
    config = KattappaConfig(vocab_size=100, n_layers=1, n_heads=1, n_kv_heads=1, d_model=16, d_ff=32)
    
    # Run 1: Single large batch of size 4
    model1 = KattappaModel(config)
    optimizer1 = build_optimizer(model1, lr=1e-2)
    
    # Run 2: Four micro-batches of size 1 accumulated
    model2 = KattappaModel(config)
    model2.load_state_dict(model1.state_dict()) # same start weight
    optimizer2 = build_optimizer(model2, lr=1e-2)
    
    # Generate same inputs
    inputs = torch.randint(0, 100, (4, 8))
    targets = torch.randint(0, 100, (4, 8))
    
    # Run 1 Forward + Backward
    logits1, _ = model1(inputs)
    # Target loss: cross entropy
    loss1 = nn.functional.cross_entropy(logits1.view(-1, 100), targets.view(-1))
    optimizer1.zero_grad()
    loss1.backward()
    optimizer1.step()
    
    # Run 2 Forward + Backward with accumulation steps = 4
    optimizer2.zero_grad()
    accum_loss = 0.0
    for i in range(4):
        logits2, _ = model2(inputs[i:i+1])
        loss2 = nn.functional.cross_entropy(logits2.view(-1, 100), targets[i:i+1].view(-1)) / 4.0
        loss2.backward()
        accum_loss += loss2.item()
        
    optimizer2.step()
    
    # Assert parameters are identical within tolerance
    for p1, p2 in zip(model1.parameters(), model2.parameters()):
        assert torch.allclose(p1, p2, atol=1e-5), "Gradient accumulation weights diverged from large batch weight!"


# 6. Gradient Checkpointing Validation
def test_gradient_checkpointing():
    # Make sure model can forward and backward with gradient checkpointing
    config = KattappaConfig(vocab_size=100, n_layers=2, n_heads=2, n_kv_heads=2, d_model=32, d_ff=64)
    model = KattappaModel(config)
    
    from torch.utils.checkpoint import checkpoint
    from kattappa_native.model.attention import build_causal_mask
    
    x = torch.randint(0, 100, (2, 8))
    # Test that block level forward can be wrapped in checkpoint
    block = model.blocks[0]
    # Prepare dummy input and freqs_cis / mask
    h = model.embedding(x)
    freqs_cis = model.freqs_cis[:8]
    mask = build_causal_mask(8, device=h.device)
    
    def custom_forward(hidden_states):
        return block(hidden_states, freqs_cis=freqs_cis, mask=mask)
        
    h.requires_grad_(True)
    out = checkpoint(custom_forward, h, use_reentrant=False)
    loss = out.sum()
    loss.backward()
    
    assert block.attn.qkv.weight.grad is not None, "Gradient checkpointing backprop failed!"


# 7. Mixed Precision Validation
def test_mixed_precision():
    device = torch.device("cpu")
    config = KattappaConfig(vocab_size=100, n_layers=1, n_heads=1, n_kv_heads=1, d_model=16, d_ff=32)
    model = KattappaModel(config).to(device)
    x = torch.randint(0, 100, (2, 8))
    
    try:
        with torch.amp.autocast(device_type="cpu", dtype=torch.bfloat16):
            out, _ = model(x)
        assert out.dtype == torch.bfloat16 or out.dtype == torch.float32
    except Exception as e:
        pytest.fail(f"Mixed precision autocast failed: {e}")


# 8. Dataset Integrity Verification
def test_dataset_integrity():
    from kattappa_native.training.trainer import load_texts_from_workspace
    texts = load_texts_from_workspace(Path(__file__).parent.parent.parent.parent)
    # Validate load_texts_from_workspace loads strings and they are valid non-empty sequences
    if texts:
        for t in texts[:5]:
            assert isinstance(t, str)
            assert len(t) > 30
