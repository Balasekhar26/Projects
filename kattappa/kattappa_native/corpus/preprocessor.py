#!/usr/bin/env python3
"""
KM-5.0.5 — Text Preprocessor
==============================
Cleans and chunks raw downloaded JSONL records into training-ready
fixed-length JSONL chunks suitable for BPE tokenizer training and
language model pre-training.

Pipeline per record:
  1. Unicode NFC normalisation
  2. Collapse excessive whitespace
  3. Remove Gutenberg / Wikipedia artefacts
  4. Sentence-aware chunking (target 256–512 words)
  5. Language tag assignment

Usage:
    PYTHONPATH=. python3 kattappa_native/corpus/preprocessor.py \\
        --input-dir  kattappa_native/corpus/raw \\
        --output-dir kattappa_native/corpus/processed
"""

import re
import json
import unicodedata
import argparse
from pathlib import Path
from typing import Generator, Dict, List

# ── Cleaning helpers ───────────────────────────────────────────────────────────

# Telugu Unicode block
TELUGU_RE = re.compile(r"[\u0C00-\u0C7F]")

# Patterns to remove
WIKI_ARTIFACTS = re.compile(
    r"\{\{[^}]+\}\}"           # {{template}}
    r"|\[\[[^\]]*\|([^\]]+)\]]"  # [[link|text]] → text
    r"|\[\[([^\]]+)\]\]"        # [[link]]
    r"|<[^>]+>"                 # HTML tags
    r"|={2,}[^=]+=+",           # == Section headers ==
    re.DOTALL,
)
MULTI_NEWLINE = re.compile(r"\n{3,}")
MULTI_SPACE   = re.compile(r"[ \t]{2,}")
REF_RE        = re.compile(r"\[\d+\]")   # [1] citation markers


def clean_text(text: str) -> str:
    """Apply full cleaning pipeline to raw text."""
    # NFC unicode normalisation
    text = unicodedata.normalize("NFC", text)
    # Remove Wiki markup
    text = WIKI_ARTIFACTS.sub(" ", text)
    # Remove citation references
    text = REF_RE.sub("", text)
    # Collapse whitespace
    text = MULTI_NEWLINE.sub("\n\n", text)
    text = MULTI_SPACE.sub(" ", text)
    # Strip leading/trailing
    return text.strip()


def detect_language(text: str) -> str:
    """Simple language detection based on Unicode script distribution."""
    if not text:
        return "unknown"
    telugu_chars = sum(1 for c in text if TELUGU_RE.match(c))
    ratio = telugu_chars / max(len(text), 1)
    if ratio > 0.3:
        return "te"
    # Check for Roman Telugu markers
    roman_markers = {"meeru", "nenu", "ela", "cheppandi", "ikkada", "vachha"}
    words = set(text.lower().split())
    if words.intersection(roman_markers):
        return "roman_te"
    return "en"


# ── Chunking ──────────────────────────────────────────────────────────────────

def chunk_text(text: str, min_words: int = 50, max_words: int = 400) -> List[str]:
    """
    Split text into sentence-aware chunks of max_words words.
    Tries to break on sentence boundaries ('. ', '? ', '! ').
    """
    # Split on sentence endings, keeping delimiter
    sentences = re.split(r"(?<=[.!?])\s+", text)
    chunks = []
    current: List[str] = []
    current_words = 0

    for sent in sentences:
        words_in_sent = len(sent.split())
        if current_words + words_in_sent > max_words and current:
            chunk = " ".join(current).strip()
            if len(chunk.split()) >= min_words:
                chunks.append(chunk)
            current = [sent]
            current_words = words_in_sent
        else:
            current.append(sent)
            current_words += words_in_sent

    # Flush remaining
    if current:
        chunk = " ".join(current).strip()
        if len(chunk.split()) >= min_words:
            chunks.append(chunk)

    return chunks


# ── Main processing pipeline ───────────────────────────────────────────────────

def process_file(input_path: Path, output_path: Path,
                 chunk_min: int = 50, chunk_max: int = 400) -> int:
    """Process one JSONL file. Returns number of output chunks written."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    chunk_id = 0

    with open(input_path, "r", encoding="utf-8", errors="replace") as fin, \
         open(output_path, "w", encoding="utf-8") as fout:

        for line in fin:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue

            # Extract raw text from known field names
            raw_text = ""
            for field in ("text", "response", "instruction", "content", "extract", "output", "question", "solution_outline", "answer"):
                if field in rec and isinstance(rec[field], str):
                    raw_text += " " + rec[field]

            if len(raw_text.strip()) < 30:
                continue

            # Clean
            cleaned = clean_text(raw_text)
            if len(cleaned.split()) < chunk_min:
                continue

            # Detect language
            lang = detect_language(cleaned)
            # Override if source gives us the language
            source = rec.get("source", "unknown")
            if "telugu" in source or rec.get("lang") == "te":
                lang = "te"
            elif "roman_telugu" in rec.get("category", ""):
                lang = "roman_te"

            # Chunk
            chunks = chunk_text(cleaned, min_words=chunk_min, max_words=chunk_max)
            for chunk in chunks:
                out_rec = {
                    "id": f"{input_path.stem}_{chunk_id:07d}",
                    "text": chunk,
                    "lang": lang,
                    "source": source,
                    "word_count": len(chunk.split()),
                    "orig_title": rec.get("title", ""),
                }
                fout.write(json.dumps(out_rec, ensure_ascii=False) + "\n")
                chunk_id += 1
                written += 1

    return written


def run_preprocessing(input_dir: Path, output_dir: Path) -> int:
    """Process all JSONL files in input_dir."""
    jsonl_files = sorted(input_dir.rglob("*.jsonl"))
    if not jsonl_files:
        print(f"  ⚠  No JSONL files found in {input_dir}")
        return 0

    total = 0
    for path in jsonl_files:
        rel = path.relative_to(input_dir)
        out_path = output_dir / rel
        n = process_file(path, out_path)
        total += n
        print(f"  ✅  {rel.name:<45} → {n:>7,} chunks")

    print(f"\n  Total chunks written: {total:,}")
    return total


def main():
    parser = argparse.ArgumentParser(description="Kattappa Corpus Preprocessor")
    parser.add_argument("--input-dir",  default="kattappa_native/corpus/raw")
    parser.add_argument("--output-dir", default="kattappa_native/corpus/processed")
    parser.add_argument("--chunk-min",  type=int, default=50)
    parser.add_argument("--chunk-max",  type=int, default=400)
    args = parser.parse_args()

    input_dir  = Path(args.input_dir)
    output_dir = Path(args.output_dir)

    print(f"\n🔧  Kattappa Corpus Preprocessor")
    print(f"    Input : {input_dir}")
    print(f"    Output: {output_dir}")
    print(f"    Chunk : {args.chunk_min}–{args.chunk_max} words\n")

    total = run_preprocessing(input_dir, output_dir)
    print(f"\n✅  Preprocessing complete. {total:,} training chunks ready.\n")


if __name__ == "__main__":
    main()
