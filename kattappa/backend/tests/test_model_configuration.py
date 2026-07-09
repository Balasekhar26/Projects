"""Unit tests for Program 27C: Kattappa Model Configuration & Architecture.

Verifies configuration templates, architectural division validation, parameter
counters, VRAM estimation, and model forward pass token sequence evaluations.
"""
from __future__ import annotations

import pytest
import torch

from backend.core.model import FlopsAnalyzer, KattappaConfig, KattappaModel


class TestModelConfiguration:
    def test_prototype_preset(self):
        cfg = KattappaConfig.from_preset("prototype")
        assert cfg.vocab_size == 16000
        assert cfg.hidden_size == 768
        assert cfg.num_hidden_layers == 12
        assert cfg.num_attention_heads == 12

    def test_small_preset(self):
        cfg = KattappaConfig.from_preset("small")
        assert cfg.vocab_size == 32000
        assert cfg.hidden_size == 1024
        assert cfg.num_hidden_layers == 24
        assert cfg.num_attention_heads == 16

    def test_invalid_hidden_size_heads_divisibility_raises(self):
        # hidden_size=768 not divisible by num_attention_heads=13
        with pytest.raises(ValueError, match="divisible by num_attention_heads"):
            KattappaConfig(hidden_size=768, num_attention_heads=13)

    def test_invalid_heads_kv_heads_divisibility_raises(self):
        # num_attention_heads=12 not divisible by num_key_value_heads=5
        with pytest.raises(ValueError, match="divisible by num_key_value_heads"):
            KattappaConfig(hidden_size=768, num_attention_heads=12, num_key_value_heads=5)

    def test_swiglu_intermediate_size_rounding(self):
        cfg = KattappaConfig(hidden_size=768)
        # Standard: 2 * 768 * 4 / 3 = 2048
        # Nearest multiple of 256 is 2048
        assert cfg.intermediate_size == 2048


class TestModelArchitecture:
    def test_forward_pass_shape(self):
        cfg = KattappaConfig(
            vocab_size=1000,
            hidden_size=128,
            num_hidden_layers=2,
            num_attention_heads=4,
            max_position_embeddings=256,
        )
        model = KattappaModel(cfg)

        # Batch size 2, Sequence length 16
        tokens = torch.randint(0, 1000, (2, 16))
        logits = model(tokens)

        # Expected output shape: (batch_size, sequence_length, vocab_size)
        assert logits.shape == (2, 16, 1000)

    def test_reset_cache(self):
        cfg = KattappaConfig(
            vocab_size=1000,
            hidden_size=128,
            num_hidden_layers=2,
            num_attention_heads=4,
            max_position_embeddings=256,
        )
        model = KattappaModel(cfg)

        tokens = torch.randint(0, 1000, (1, 8))
        # Initial forward pass filling cache
        model(tokens, use_cache=True)

        # Verify cache is populated in first block
        first_layer = model.layers[0]
        assert first_layer.attn.cache_k is not None
        assert first_layer.attn.cache_v is not None

        # Reset cache
        model.reset_cache()
        assert first_layer.attn.cache_k is None
        assert first_layer.attn.cache_v is None


class TestFlopsAnalyzer:
    def test_prototype_flops_estimation(self):
        cfg = KattappaConfig.from_preset("prototype")
        analysis = FlopsAnalyzer.analyze(cfg, batch_size=4, seq_len=1024)

        params = analysis["parameters"]
        vram = analysis["vram_mb"]
        flops = analysis["flops"]

        # 135M preset should have total parameters in the range of 100M-160M
        assert 100_000_000 < params["total"] < 160_000_000
        assert params["embeddings"] == 16000 * 768
        assert params["lm_head"] == 768 * 16000

        # Memory parameters should be non-negative
        assert vram["weights"] > 0
        assert vram["gradients"] > 0
        assert vram["optimizer"] > 0
        assert vram["activations"] > 0
        assert vram["total_training"] > 0

        # FLOP estimation per token should count forward and backward operations
        assert flops["forward_per_token"] > 0
        assert flops["backward_per_token"] == 2 * flops["forward_per_token"]
