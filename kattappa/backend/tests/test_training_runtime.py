"""Unit tests for Program 27D: Model Training Runtime.

Verifies dataset parsing, collated padding dimensions, optimization steps,
warmup/cosine decay scheduling, and checkpoint save/resume cycles.
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest
import torch
from torch.utils.data import DataLoader

from backend.core.dataset.tokenizer_trainer import _MockTokenizer
from backend.core.model import (
    KattappaConfig,
    KattappaModel,
    KattappaDataset,
    KattappaCollate,
    KattappaTrainer,
)


@pytest.fixture
def mock_dataset_jsonl():
    """Yields a temporary JSONL dataset file containing mock records."""
    records = [
        {"instruction": "deploy docker", "result": "success"},
        {"instruction": "run tests", "result": "success"},
        {"instruction": "check configs", "result": "failure"},
    ]
    with tempfile.NamedTemporaryFile(suffix=".jsonl", mode="w", delete=False, encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")
        path = Path(f.name)

    yield path

    if path.exists():
        path.unlink()


class TestTrainingDataset:
    def test_dataset_length(self, mock_dataset_jsonl):
        tok = _MockTokenizer()
        ds = KattappaDataset(mock_dataset_jsonl, tokenizer=tok, format_type="instruction_tuning")
        assert len(ds) == 3

    def test_dataset_item_shape(self, mock_dataset_jsonl):
        tok = _MockTokenizer()
        ds = KattappaDataset(mock_dataset_jsonl, tokenizer=tok, format_type="instruction_tuning")
        item = ds[0]
        assert "input_ids" in item
        assert "labels" in item
        assert isinstance(item["input_ids"], torch.Tensor)
        assert item["labels"][0] == -100  # Masked BOS token

    def test_collator_padding(self, mock_dataset_jsonl):
        tok = _MockTokenizer()
        ds = KattappaDataset(mock_dataset_jsonl, tokenizer=tok, format_type="instruction_tuning")
        collate = KattappaCollate(pad_id=0)

        # Batch contains 2 samples
        batch = [ds[0], ds[1]]
        collated = collate(batch)

        assert "input_ids" in collated
        assert "labels" in collated
        assert collated["input_ids"].ndim == 2
        assert collated["labels"].ndim == 2
        # Verify padded dimensions match
        assert collated["input_ids"].shape == collated["labels"].shape


class TestTrainingTrainer:
    def test_trainer_learning_rate_warmup_and_decay(self, mock_dataset_jsonl):
        cfg = KattappaConfig(
            vocab_size=1000,
            hidden_size=64,
            num_hidden_layers=1,
            num_attention_heads=2,
        )
        model = KattappaModel(cfg)

        tok = _MockTokenizer(vocab_size=1000)  # must match model vocab_size
        ds = KattappaDataset(mock_dataset_jsonl, tokenizer=tok)
        dl = DataLoader(ds, batch_size=2, collate_fn=KattappaCollate(pad_id=0))

        trainer = KattappaTrainer(
            model=model,
            train_dataloader=dl,
            lr=1e-3,
            warmup_steps=4,
            max_steps=10,
        )

        # Step 0 (during warmup)
        lr_0 = trainer._get_lr(0)
        assert lr_0 == 1e-3 * (1.0 / 4.0)

        # Step 3 (end of warmup)
        lr_3 = trainer._get_lr(3)
        assert lr_3 == 1e-3 * (4.0 / 4.0)

        # Step 5 (cosine decay segment)
        lr_5 = trainer._get_lr(5)
        assert lr_5 < 1e-3

    def test_training_step_updates_weights(self, mock_dataset_jsonl):
        cfg = KattappaConfig(
            vocab_size=1000,
            hidden_size=64,
            num_hidden_layers=1,
            num_attention_heads=2,
        )
        model = KattappaModel(cfg)

        # Store a copy of initial embedding weights to verify adjustments
        initial_weight = model.tok_embeddings.weight.clone()

        tok = _MockTokenizer(vocab_size=1000)  # must match model vocab_size
        ds = KattappaDataset(mock_dataset_jsonl, tokenizer=tok)
        dl = DataLoader(ds, batch_size=2, collate_fn=KattappaCollate(pad_id=0))

        trainer = KattappaTrainer(
            model=model,
            train_dataloader=dl,
            lr=1e-3,
            max_steps=5,
        )

        batch = next(iter(dl))
        loss = trainer.train_step(batch)

        assert loss > 0.0
        # Weights should have shifted slightly after backpropagation and step completion
        assert not torch.equal(model.tok_embeddings.weight, initial_weight)

    def test_save_and_load_checkpoint(self, mock_dataset_jsonl):
        cfg = KattappaConfig(
            vocab_size=1000,
            hidden_size=64,
            num_hidden_layers=1,
            num_attention_heads=2,
        )
        model = KattappaModel(cfg)
        tok = _MockTokenizer(vocab_size=1000)  # must match model vocab_size
        ds = KattappaDataset(mock_dataset_jsonl, tokenizer=tok)
        dl = DataLoader(ds, batch_size=2, collate_fn=KattappaCollate(pad_id=0))

        with tempfile.TemporaryDirectory() as tmp_dir:
            trainer = KattappaTrainer(
                model=model,
                train_dataloader=dl,
                checkpoint_dir=tmp_dir,
            )

            # Advance trainer state
            batch = next(iter(dl))
            trainer.train_step(batch)
            assert trainer.current_step == 1

            ckpt_path = Path(tmp_dir) / "test_checkpoint.pt"
            trainer.save_checkpoint(ckpt_path)
            assert ckpt_path.exists()

            # Create another model and load the checkpoint
            model_new = KattappaModel(cfg)
            trainer_new = KattappaTrainer(
                model=model_new,
                train_dataloader=dl,
                checkpoint_dir=tmp_dir,
            )

            assert trainer_new.current_step == 0
            trainer_new.load_checkpoint(ckpt_path)
            assert trainer_new.current_step == 1

            # Verify weight tensors match exactly
            assert torch.allclose(
                model_new.tok_embeddings.weight,
                model.tok_embeddings.weight,
            )
