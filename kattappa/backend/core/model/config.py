"""Kattappa Model Configuration (Program 27C).

Defines architectural parameters, presets, and constraints for the
Kattappa Native Foundation Model.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict


@dataclass
class KattappaConfig:
    """Configuration class for the Kattappa transformer model."""

    vocab_size: int = 16000
    hidden_size: int = 768
    num_hidden_layers: int = 12
    num_attention_heads: int = 12
    num_key_value_heads: int | None = None  # None defaults to Multi-Head Attention (MHA)
    intermediate_size: int | None = None   # None defaults to SwiGLU scaling of hidden_size
    max_position_embeddings: int = 2048
    rope_theta: float = 10000.0
    rms_norm_eps: float = 1e-6
    initializer_range: float = 0.02
    bos_token_id: int = 2
    eos_token_id: int = 3
    pad_token_id: int = 0
    use_cache: bool = True

    def __post_init__(self) -> None:
        # Resolve intermediate size if not specified (SwiGLU standard calculation)
        if self.intermediate_size is None:
            # Standard SwiGLU formula: 2/3 * 4 * hidden_size, aligned to 256
            raw_size = int(2 * self.hidden_size * 4 / 3)
            # Align to nearest multiple of 256
            self.intermediate_size = ((raw_size + 255) // 256) * 256

        # Default Grouped Query Attention (GQA) key_value heads to standard MHA
        if self.num_key_value_heads is None:
            self.num_key_value_heads = self.num_attention_heads

        # Validation checks
        if self.hidden_size % self.num_attention_heads != 0:
            raise ValueError(
                f"hidden_size ({self.hidden_size}) must be divisible by "
                f"num_attention_heads ({self.num_attention_heads})"
            )

        if self.num_attention_heads % self.num_key_value_heads != 0:
            raise ValueError(
                f"num_attention_heads ({self.num_attention_heads}) must be divisible by "
                f"num_key_value_heads ({self.num_key_value_heads})"
            )

    @classmethod
    def from_preset(cls, name: str, **kwargs: Any) -> KattappaConfig:
        """Loads a config template preset.

        Presets:
            - 'prototype' (135M)
            - 'small' (360M)
            - 'standard' (1B)
        """
        presets = {
            "prototype": {
                "vocab_size": 16000,
                "hidden_size": 768,
                "num_hidden_layers": 12,
                "num_attention_heads": 12,
                "num_key_value_heads": 12,
                "max_position_embeddings": 2048,
            },
            "small": {
                "vocab_size": 32000,
                "hidden_size": 1024,
                "num_hidden_layers": 24,
                "num_attention_heads": 16,
                "num_key_value_heads": 8,  # GQA
                "max_position_embeddings": 2048,
            },
            "standard": {
                "vocab_size": 32000,
                "hidden_size": 2048,
                "num_hidden_layers": 24,
                "num_attention_heads": 32,
                "num_key_value_heads": 8,  # GQA
                "max_position_embeddings": 4096,
            },
        }

        if name not in presets:
            raise ValueError(f"Unknown preset name: {name}. Available: {list(presets.keys())}")

        params = dict(presets[name])
        params.update(kwargs)
        return cls(**params)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "vocab_size": self.vocab_size,
            "hidden_size": self.hidden_size,
            "num_hidden_layers": self.num_hidden_layers,
            "num_attention_heads": self.num_attention_heads,
            "num_key_value_heads": self.num_key_value_heads,
            "intermediate_size": self.intermediate_size,
            "max_position_embeddings": self.max_position_embeddings,
            "rope_theta": self.rope_theta,
            "rms_norm_eps": self.rms_norm_eps,
            "initializer_range": self.initializer_range,
            "bos_token_id": self.bos_token_id,
            "eos_token_id": self.eos_token_id,
            "pad_token_id": self.pad_token_id,
            "use_cache": self.use_cache,
        }
