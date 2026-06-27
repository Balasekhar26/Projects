"""
KM-5.2 — Kattappa-100M Model
==============================
Full decoder-only transformer: embedding → 12 × DecoderBlock → LayerNorm → LM head.

Target spec:
    n_layers      = 12
    n_heads       = 12
    d_model       = 768
    d_ff          = 3072  (4 × d_model)
    context_length = 2048
    vocab_size    = 32000
    params        ≈ 117M
"""

import torch
import torch.nn as nn
from dataclasses import dataclass, field
from typing import Optional

from kattappa_native.model.attention import precompute_freqs_cis, build_causal_mask
from kattappa_native.model.block import DecoderBlock


@dataclass
class KattappaConfig:
    """Hyperparameters for Kattappa. Lock before training."""
    n_layers: int       = 12
    n_heads: int        = 12
    n_kv_heads: int     = 4
    d_model: int        = 768
    d_ff: int           = 3072
    context_length: int = 2048
    vocab_size: int     = 32000
    dropout: float      = 0.0   # 0 for inference; 0.1 during training
    rope_theta: float   = 10000.0

    # Special token IDs (must match tokenizer)
    pad_id: int  = 0
    unk_id: int  = 1
    bos_id: int  = 2
    eos_id: int  = 3

    @classmethod
    def mini(cls) -> "KattappaConfig":
        """
        Kattappa-20M: ignition-test config.
        6 layers, d_model=384, 6 heads, ctx=1024.
        Train on 5M–10M tokens to verify pipeline before full run.
        """
        return cls(
            n_layers=6, n_heads=6, d_model=384, d_ff=1536,
            context_length=1024, vocab_size=32000, dropout=0.1,
        )

    @classmethod
    def full(cls) -> "KattappaConfig":
        """
        Kattappa-137M: full Alpha model.
        12 layers, d_model=768, 12 heads, ctx=2048.
        Requires ≥50M token corpus and trained tokenizer.
        """
        return cls(
            n_layers=12, n_heads=12, d_model=768, d_ff=3072,
            context_length=2048, vocab_size=32000, dropout=0.1,
        )


class KattappaModel(nn.Module):
    """
    Kattappa-100M decoder-only language model.

    Forward pass:
        token_ids (B, T) → logits (B, T, vocab_size)
    """

    def __init__(self, config: Optional[KattappaConfig] = None):
        super().__init__()
        self.config = config or KattappaConfig()
        cfg = self.config

        # Token embedding
        self.embedding = nn.Embedding(cfg.vocab_size, cfg.d_model, padding_idx=cfg.pad_id)

        # Stack of decoder blocks
        self.blocks = nn.ModuleList([
            DecoderBlock(cfg.d_model, cfg.n_heads, cfg.d_ff, n_kv_heads=cfg.n_kv_heads, dropout=cfg.dropout)
            for _ in range(cfg.n_layers)
        ])

        # Final layer norm before LM head
        self.norm = nn.LayerNorm(cfg.d_model)

        # LM head: projects d_model → vocab_size
        # Weight tying: shares weights with embedding for parameter efficiency
        self.lm_head = nn.Linear(cfg.d_model, cfg.vocab_size, bias=False)
        self.lm_head.weight = self.embedding.weight  # weight tying

        # Precompute RoPE frequencies for the full context length
        head_dim = cfg.d_model // cfg.n_heads
        self.register_buffer(
            "freqs_cis",
            precompute_freqs_cis(head_dim, cfg.context_length, theta=cfg.rope_theta),
            persistent=False,
        )

        # Initialise weights
        self._init_weights()

    def _init_weights(self):
        """Standard GPT-2–style weight initialisation with residual scaling."""
        import math
        for name, module in self.named_modules():
            if isinstance(module, nn.Linear):
                std = 0.02
                # GPT-2 residual projection scaling:
                if "out_proj" in name or "down_proj" in name:
                    std = std / math.sqrt(2 * self.config.n_layers)
                nn.init.normal_(module.weight, mean=0.0, std=std)
                if module.bias is not None:
                    nn.init.zeros_(module.bias)
            elif isinstance(module, nn.Embedding):
                nn.init.normal_(module.weight, mean=0.0, std=0.02)
                if module.padding_idx is not None:
                    module.weight.data[module.padding_idx].zero_()

    def reset_cache(self):
        """Clears the KV Cache on all decoder blocks."""
        for block in self.blocks:
            block.attn.reset_cache()

    def forward(
        self,
        token_ids: torch.Tensor,
        targets: Optional[torch.Tensor] = None,
        start_pos: int = 0,
        use_cache: bool = False,
    ):
        """
        Args:
            token_ids: (batch, seq_len) int64 token indices
            targets:   (batch, seq_len) int64 labels for language modelling loss
                       (None during inference)
            start_pos: Start index offset for RoPE and cache mapping
            use_cache: If True, uses KV cache
        Returns:
            logits: (batch, seq_len, vocab_size) — always returned
            loss:   scalar cross-entropy loss — only if targets provided
        """
        B, T = token_ids.shape
        assert start_pos + T <= self.config.context_length, (
            f"Sequence length {start_pos + T} exceeds context_length {self.config.context_length}"
        )

        # Embed tokens
        x = self.embedding(token_ids)  # (B, T, d_model)

        # Slice precomputed RoPE frequencies for this sequence
        freqs_cis = self.freqs_cis[start_pos : start_pos + T]

        # Build causal mask for this sequence length
        if T > 1:
            mask = build_causal_mask(T, device=x.device)
            if start_pos > 0:
                zeros = torch.zeros((T, start_pos), device=x.device)
                mask = torch.cat([zeros, mask], dim=-1)
        else:
            mask = None

        # Pass through decoder blocks
        for block in self.blocks:
            x = block(x, freqs_cis, mask=mask, use_cache=use_cache)

        # Final norm and project to vocab
        x = self.norm(x)
        logits = self.lm_head(x)  # (B, T, vocab_size)

        if targets is None:
            return logits, None

        # Cross-entropy loss (shift by 1 for causal LM)
        loss = nn.functional.cross_entropy(
            logits.view(-1, self.config.vocab_size),
            targets.view(-1),
            ignore_index=self.config.pad_id,
        )
        return logits, loss

    @torch.no_grad()
    def generate(
        self,
        prompt_ids: Optional[torch.Tensor] = None,
        max_new_tokens: int = 128,
        temperature: float = 0.8,
        top_k: int = 50,
        eos_id: Optional[int] = None,
        input_ids: Optional[torch.Tensor] = None,
        *args,
        **kwargs
    ) -> torch.Tensor:
        """
        Autoregressive greedy / top-k sampling.

        Args:
            prompt_ids:     (1, T) seed token IDs
            max_new_tokens: Maximum tokens to generate
            temperature:    Sampling temperature (0 → greedy)
            top_k:          Top-k sampling; set 0 to disable
            eos_id:         Stop generation on this token ID

        Returns:
            generated: (1, T + max_new_tokens) full sequence
        """
        self.eval()
        self.reset_cache()
        eos_id = eos_id or self.config.eos_id
        actual_ids = prompt_ids if prompt_ids is not None else input_ids
        if actual_ids is None:
            raise ValueError("Either prompt_ids or input_ids must be provided")
        ids = actual_ids.clone()
        B, prompt_len = ids.shape

        # Prefill stage (process prompt)
        logits, _ = self.forward(ids, start_pos=0, use_cache=True)
        next_logits = logits[:, -1, :] / max(temperature, 1e-8)

        if top_k > 0:
            topk_vals, _ = torch.topk(next_logits, top_k)
            threshold = topk_vals[:, -1].unsqueeze(-1)
            next_logits = next_logits.masked_fill(next_logits < threshold, float("-inf"))

        probs = torch.softmax(next_logits, dim=-1)
        next_id = torch.multinomial(probs, num_samples=1)
        ids = torch.cat([ids, next_id], dim=-1)

        if next_id.item() == eos_id:
            return ids

        # Decode stage (autoregressive generation one token at a time)
        for step in range(1, max_new_tokens):
            current_pos = prompt_len + step - 1
            if current_pos >= self.config.context_length:
                break
            
            # Forward pass only on the last generated token
            logits, _ = self.forward(next_id, start_pos=current_pos, use_cache=True)
            next_logits = logits[:, -1, :] / max(temperature, 1e-8)

            if top_k > 0:
                topk_vals, _ = torch.topk(next_logits, top_k)
                threshold = topk_vals[:, -1].unsqueeze(-1)
                next_logits = next_logits.masked_fill(next_logits < threshold, float("-inf"))

            probs = torch.softmax(next_logits, dim=-1)
            next_id = torch.multinomial(probs, num_samples=1)
            ids = torch.cat([ids, next_id], dim=-1)

            if next_id.item() == eos_id:
                break

        # Clean up cache state after generation
        self.reset_cache()
        return ids

    def param_count(self) -> int:
        return sum(p.numel() for p in self.parameters())

    def __repr__(self) -> str:
        cfg = self.config
        params_m = self.param_count() / 1e6
        return (
            f"KattappaModel(\n"
            f"  layers={cfg.n_layers}, heads={cfg.n_heads}, d_model={cfg.d_model},\n"
            f"  d_ff={cfg.d_ff}, context={cfg.context_length}, vocab={cfg.vocab_size},\n"
            f"  params={params_m:.1f}M\n"
            f")"
        )
