"""Tokenizer Trainer (Program 27.0 / Phase 27B).

Trains a SentencePiece Unigram tokenizer from a JSONL corpus produced by
Phase 27A. Designed for a Telugu + English dual-domain vocabulary.

Falls back to a deterministic MockTokenizer when the `sentencepiece`
C-extension is not installed, so the module loads cleanly in CI without
native dependencies.
"""
from __future__ import annotations

import io
import json
import re
import time
from pathlib import Path
from typing import Any, Dict, List

from backend.core.config import runtime_data_root
from backend.core.dataset.tokenizer_registry import TokenizerRegistry

# ── SentencePiece optional import ─────────────────────────────────────────────
try:
    import sentencepiece as spm  # type: ignore[import-untyped]
    _SP_AVAILABLE = True
except ImportError:
    spm = None  # type: ignore[assignment]
    _SP_AVAILABLE = False

# ── Constants ─────────────────────────────────────────────────────────────────
_DEFAULT_VOCAB_SIZE = 16_000
_CHAR_COVERAGE = 0.9999  # captures full Telugu Unicode block
_DOMAIN_TOKENS = ["<|plan|>", "<|action|>", "<|tool|>", "<|result|>", "<|eot|>"]

_WORD_RE = re.compile(r"[^\s]+")


def _tokenizers_dir() -> Path:
    p = runtime_data_root() / "backend" / "data" / "tokenizers"
    p.mkdir(parents=True, exist_ok=True)
    return p


# ── Text extraction ───────────────────────────────────────────────────────────

def _extract_texts_from_jsonl(jsonl_path: Path) -> List[str]:
    """Yields one text line per JSONL record, concatenating all textual fields."""
    texts: List[str] = []
    with jsonl_path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            parts = []
            for key in ("instruction", "reasoning", "output", "goal", "input"):
                v = rec.get(key, "")
                if isinstance(v, str) and v:
                    parts.append(v)
            # Flatten lists (e.g. plan_steps, tool_calls)
            for key in ("plan_steps", "tool_calls"):
                v = rec.get(key, [])
                if isinstance(v, list):
                    parts.extend(str(x) for x in v)
            if parts:
                texts.append(" ".join(parts))
    return texts


# ── Mock tokenizer (fallback when sentencepiece absent) ───────────────────────

class _MockTokenizer:
    """Whitespace tokenizer for CI environments without the sentencepiece wheel."""

    def __init__(self, vocab_size: int = _DEFAULT_VOCAB_SIZE) -> None:
        self.vocab_size = vocab_size

    def encode(self, text: str, out_type: type = str) -> List[str]:
        tokens = _WORD_RE.findall(text)
        if out_type is int:
            return [hash(t) % self.vocab_size for t in tokens]
        return tokens

    def decode(self, tokens) -> str:
        if tokens and isinstance(tokens[0], int):
            return " ".join(str(t) for t in tokens)
        return " ".join(tokens)

    def get_piece_size(self) -> int:
        return self.vocab_size


# ── Trainer ───────────────────────────────────────────────────────────────────

class TokenizerTrainer:
    """Trains a SentencePiece tokenizer from a Phase 27A JSONL corpus."""

    @classmethod
    def train_from_texts(
        cls,
        texts: List[str],
        version_id: str,
        vocab_size: int = _DEFAULT_VOCAB_SIZE,
        corpus_version: str = "unknown",
    ) -> Dict[str, Any]:
        """Trains on a list of text strings. Returns a training report dict."""
        model_path = _tokenizers_dir() / f"{version_id}.model"
        vocab_path = _tokenizers_dir() / f"{version_id}.vocab"

        if not _SP_AVAILABLE:
            # Fallback: write placeholder files and record as mock
            model_path.write_text("MOCK_MODEL", encoding="utf-8")
            vocab_path.write_text(
                "\n".join(f"<tok_{i}>\t{-i}" for i in range(min(vocab_size, 100))),
                encoding="utf-8",
            )
            entry = TokenizerRegistry.register(
                version_id=version_id,
                vocab_size=vocab_size,
                algorithm="mock_whitespace",
                corpus_version=corpus_version,
                model_path=str(model_path),
                vocab_path=str(vocab_path),
                notes="sentencepiece not installed — mock tokenizer",
            )
            return {**entry, "mock": True, "text_count": len(texts)}

        # Real SentencePiece training
        corpus_buf = io.StringIO("\n".join(texts))
        started = time.time()

        spm.SentencePieceTrainer.train(
            sentence_iterator=iter(texts),
            model_prefix=str(_tokenizers_dir() / version_id),
            vocab_size=vocab_size,
            character_coverage=_CHAR_COVERAGE,
            model_type="unigram",
            pad_id=0,
            unk_id=1,
            bos_id=2,
            eos_id=3,
            user_defined_symbols=_DOMAIN_TOKENS,
            input_sentence_size=0,       # 0 = unlimited (SentencePiece requires 0 or >100)
            shuffle_input_sentence=True,
            hard_vocab_limit=False,      # allow smaller vocab when corpus is small
        )

        elapsed = round(time.time() - started, 2)

        entry = TokenizerRegistry.register(
            version_id=version_id,
            vocab_size=vocab_size,
            algorithm="sentencepiece_unigram",
            corpus_version=corpus_version,
            model_path=str(model_path),
            vocab_path=str(vocab_path),
            notes=f"trained in {elapsed}s on {len(texts)} sentences",
        )
        return {**entry, "mock": False, "text_count": len(texts), "elapsed_s": elapsed}

    @classmethod
    def train_from_jsonl(
        cls,
        corpus_dir: str | Path,
        version_id: str | None = None,
        vocab_size: int = _DEFAULT_VOCAB_SIZE,
    ) -> Dict[str, Any]:
        """Scans a directory for JSONL files and trains from all discovered records."""
        corpus_dir = Path(corpus_dir)
        version_id = version_id or f"tok_{int(time.time())}"

        texts: List[str] = []
        for jsonl_file in sorted(corpus_dir.glob("*.jsonl")):
            texts.extend(_extract_texts_from_jsonl(jsonl_file))

        if not texts:
            raise ValueError(f"No text records found in JSONL files under {corpus_dir}")

        return cls.train_from_texts(texts, version_id=version_id, vocab_size=vocab_size)

    @classmethod
    def load(cls, version_id: str) -> "_MockTokenizer | spm.SentencePieceProcessor":
        """Loads a trained tokenizer by version ID."""
        model_path = _tokenizers_dir() / f"{version_id}.model"
        if not model_path.exists():
            raise FileNotFoundError(f"Tokenizer model not found: {model_path}")

        if not _SP_AVAILABLE or model_path.read_bytes()[:10] == b"MOCK_MODEL":
            return _MockTokenizer()

        sp = spm.SentencePieceProcessor()
        sp.Load(str(model_path))
        return sp
