#!/usr/bin/env python3
"""
KM-5.0 — Source Auditor
========================
Scans all JSONL dataset files in the workspace, classifies them by
language and domain, and flags under-represented categories relative
to corpus_manifest.json targets.

Usage:
    PYTHONPATH=. python3 kattappa_native/corpus/source_auditor.py
"""

import os
import re
import json
from pathlib import Path
from typing import Dict, List
from datetime import datetime

MANIFEST_PATH = Path(__file__).parent / "corpus_manifest.json"
WORKSPACE_ROOT = Path(__file__).parent.parent.parent

TELUGU_SCRIPT_RE = re.compile(r"[\u0C00-\u0C7F]")
ROMAN_TELUGU_MARKERS = {"meeru", "nenu", "ela", "cheppandi", "mee", "naaku", "ikkada",
                         "vachha", "poni", "ayindi", "cheyyi", "ledhu", "antav", "antaru"}
CODE_MARKERS = {"def ", "class ", "import ", "```python", "```js", "function(", "=>",
                "printf(", "return ", "SELECT ", "FROM ", "WHERE "}
REASONING_MARKERS = {"step 1", "step 2", "therefore", "because", "let me think",
                     "chain-of-thought", "let's solve", "=", "equation", "solution"}
TOOL_MARKERS = {"tool_call", "tool_result", "calculator", "search_mock", "clock"}
ENGINEERING_MARKERS = {"architecture", "latency", "throughput", "microservice",
                        "kubernetes", "docker", "pipeline", "schema", "system design"}

WORDS_PER_TOKEN = 0.75


def classify_text(text: str) -> str:
    tl = text.lower()
    if TELUGU_SCRIPT_RE.search(text):
        return "telugu"
    words = set(tl.split())
    if words.intersection(ROMAN_TELUGU_MARKERS):
        return "roman_telugu"
    if any(m in tl for m in TOOL_MARKERS):
        return "tool_traces"
    if any(m in text for m in CODE_MARKERS):
        return "programming"
    if any(m in tl for m in REASONING_MARKERS):
        return "reasoning"
    if any(m in tl for m in ENGINEERING_MARKERS):
        return "engineering"
    return "general_knowledge"


def audit_file(path: Path) -> Dict:
    lang_counts: Dict[str, int] = {}
    total_records = 0
    total_words = 0
    encoding_errors = 0

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
                total_records += 1
                text = " ".join(str(v) for v in record.values() if isinstance(v, str))
                words = len(text.split())
                total_words += words
                cat = classify_text(text)
                lang_counts[cat] = lang_counts.get(cat, 0) + int(words / WORDS_PER_TOKEN)
    except Exception as e:
        return {"error": str(e), "path": str(path)}

    return {
        "path": str(path.relative_to(WORKSPACE_ROOT)),
        "total_records": total_records,
        "approx_tokens": int(total_words / WORDS_PER_TOKEN),
        "by_category": lang_counts,
        "dominant_category": max(lang_counts, key=lang_counts.get) if lang_counts else "unknown",
    }


def run_audit() -> Dict:
    manifest = json.loads(MANIFEST_PATH.read_text())
    alpha_targets = manifest["alpha_run"]["sources"]

    jsonl_files = [
        p for p in sorted(WORKSPACE_ROOT.rglob("*.jsonl"))
        if "ai_system_env" not in str(p)
        and "episodic.jsonl" not in str(p)
        and "semantic.jsonl" not in str(p)
    ]

    print(f"\n🔎 Auditing {len(jsonl_files)} JSONL files...\n")
    file_audits: List[Dict] = []
    aggregated: Dict[str, int] = {}

    for path in jsonl_files:
        result = audit_file(path)
        file_audits.append(result)
        for cat, n in result.get("by_category", {}).items():
            aggregated[cat] = aggregated.get(cat, 0) + n

    # ── Print per-file table ───────────────────────────────────────────────────
    print(f"  {'File':<55} {'Records':>8} {'~Tokens':>10} {'Dominant':>16}")
    print(f"  {'-'*55} {'-'*8} {'-'*10} {'-'*16}")
    for a in sorted(file_audits, key=lambda x: -x.get("approx_tokens", 0)):
        if "error" in a:
            continue
        print(f"  {a['path']:<55} {a['total_records']:>8,} {a['approx_tokens']:>10,} {a['dominant_category']:>16}")

    # ── Flag under-represented categories ─────────────────────────────────────
    print(f"\n\n{'='*65}")
    print(f"  CORPUS HEALTH CHECK — Alpha Run (Target: {manifest['alpha_run']['target_total_tokens']:,} tokens)")
    print(f"{'='*65}")

    flags = []
    for cat, spec in alpha_targets.items():
        have = aggregated.get(cat, 0)
        need = spec["target_tokens"]
        pct = round(100 * have / need, 1) if need > 0 else 100.0
        status = "✅" if pct >= 90 else ("🟡" if pct >= 30 else "🔴")
        if pct < 90:
            flags.append((cat, have, need, pct))
        print(f"  {status}  {cat:<22}  have {have:>10,}  /  need {need:>12,}  ({pct:>5.1f}%)")

    print(f"\n  Total available: {sum(aggregated.values()):,} tokens")
    print(f"  Total needed:    {manifest['alpha_run']['target_total_tokens']:,} tokens")

    if flags:
        print(f"\n  ⚠  Under-represented categories (need external data collection):")
        for cat, have, need, pct in sorted(flags, key=lambda x: x[3]):
            gap = need - have
            print(f"     🔴  {cat:<22}  gap = {gap:>12,} tokens  ({pct:.1f}% filled)")
    else:
        print(f"\n  ✅ All categories meet Alpha targets.")

    print(f"\n  Tokenizer sample check:")
    tok_targets = manifest["tokenizer_sample"]["sources"]
    all_ok = True
    for cat, spec in tok_targets.items():
        have = aggregated.get(cat, 0)
        need = spec["target_tokens"]
        pct = round(100 * have / need, 1)
        status = "✅" if pct >= 80 else "⚠ "
        if pct < 80:
            all_ok = False
        print(f"     {status}  {cat:<22}  tokenizer sample: {have:>8,}/{need:>8,}  ({pct:.1f}%)")
    if not all_ok:
        print(f"\n  ⚠  Some categories lack enough data for a balanced tokenizer sample.")
        print(f"     Fix: add Telugu/Roman Telugu data BEFORE running train_tokenizer.py")
    print(f"{'='*65}\n")

    # ── Write JSON report ──────────────────────────────────────────────────────
    report = {
        "audit_timestamp": datetime.utcnow().isoformat() + "Z",
        "manifest_version": manifest.get("_version"),
        "files_audited": len(file_audits),
        "aggregated_by_category": aggregated,
        "total_available_tokens": sum(aggregated.values()),
        "alpha_target_tokens": manifest["alpha_run"]["target_total_tokens"],
        "file_details": file_audits,
    }
    out_path = WORKSPACE_ROOT / "kattappa_native/corpus/audit_report.json"
    out_path.write_text(json.dumps(report, indent=2))
    print(f"📄 Audit report written to: {out_path}\n")
    return report


if __name__ == "__main__":
    run_audit()
