#!/usr/bin/env python3
"""
KM-5.0 — Token Budget Planner
==============================
Scans existing JSONL datasets, approximates token counts per category,
computes the gap to corpus_manifest.json targets, and writes a gap report.

Usage:
    PYTHONPATH=. python3 kattappa_native/corpus/token_budget_planner.py [--run alpha|beta|tokenizer]
"""

import os
import re
import json
import argparse
from pathlib import Path
from typing import Dict, List, Tuple

# ── Constants ──────────────────────────────────────────────────────────────────
MANIFEST_PATH = Path(__file__).parent / "corpus_manifest.json"
WORKSPACE_ROOT = Path(__file__).parent.parent.parent

# Heuristic: average English word is ~4.5 characters, ~0.75 tokens
# (BPE over a mixed corpus averages ~1.33 chars/token → word/token ≈ 0.75)
WORDS_PER_TOKEN = 0.75

# ── Language / category detection ─────────────────────────────────────────────
TELUGU_SCRIPT_RE = re.compile(r"[\u0C00-\u0C7F]")  # Telugu Unicode block

CATEGORY_KEYWORDS = {
    "tool_traces":   {"tool_call", "tool_result", "calculator", "search_mock", "clock", "function"},
    "programming":   {"def ", "class ", "import ", "```python", "```js", "```typescript",
                      "function(", "=>", "printf", "return "},
    "reasoning":     {"step 1", "step 2", "therefore", "because", "chain-of-thought", "gsm8k",
                      "let me think", "let's solve", "math", "equation"},
    "engineering":   {"architecture", "system design", "latency", "throughput", "microservice",
                      "kubernetes", "docker", "pipeline", "schema"},
    "roman_telugu":  {"meeru", "nenu", "ela", "cheppandi", "cheyyi", "vachha", "poni", "ikkada"},
}


def count_words(text: str) -> int:
    return len(text.split())


def estimate_tokens(word_count: int) -> int:
    return int(word_count / WORDS_PER_TOKEN)


def detect_category(record: Dict) -> str:
    """Classify a JSONL record into one of the manifest categories."""
    text = ""
    for field in ("text", "instruction", "response", "output", "content", "event"):
        if field in record:
            text += " " + str(record[field])

    if not text.strip():
        return "general_knowledge"

    text_lower = text.lower()

    # Telugu script detection (Unicode range)
    if TELUGU_SCRIPT_RE.search(text):
        return "telugu"

    for category, keywords in CATEGORY_KEYWORDS.items():
        if any(kw in text_lower for kw in keywords):
            return category

    return "general_knowledge"


def scan_jsonl_file(filepath: Path) -> Dict[str, int]:
    """Returns {category: approximate_token_count} for one JSONL file."""
    counts: Dict[str, int] = {}
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue

                # Build full text from all string fields
                full_text = " ".join(
                    str(v) for v in record.values()
                    if isinstance(v, str)
                )
                words = count_words(full_text)
                tokens = estimate_tokens(words)
                cat = detect_category(record)
                counts[cat] = counts.get(cat, 0) + tokens
    except Exception as e:
        print(f"  ⚠  Could not read {filepath}: {e}")
    return counts


def scan_workspace(root: Path) -> Tuple[Dict[str, int], List[Dict]]:
    """Walk the workspace deduped directory, scan all JSONL files, aggregate by category."""
    global_counts: Dict[str, int] = {}
    file_reports: List[Dict] = []

    # Only scan the deduplicated directory to avoid double counting raw and processed
    target_dir = root / "kattappa_native/corpus/deduped"
    if not target_dir.exists():
        target_dir = root
    
    jsonl_paths = sorted(target_dir.rglob("*.jsonl"))
    # Exclude memory runtime files (not training data)
    jsonl_paths = [p for p in jsonl_paths if "ai_system_env" not in str(p)
                   and "episodic.jsonl" not in str(p)
                   and "semantic.jsonl" not in str(p)]

    for path in jsonl_paths:
        rel = path.relative_to(root)
        file_counts = scan_jsonl_file(path)
        file_total = sum(file_counts.values())
        file_reports.append({
            "path": str(rel),
            "total_tokens": file_total,
            "by_category": file_counts,
        })
        for cat, n in file_counts.items():
            global_counts[cat] = global_counts.get(cat, 0) + n

    return global_counts, file_reports


def compute_gap(manifest: Dict, run: str, available: Dict[str, int]) -> Dict:
    """Compare available tokens against manifest targets and compute gaps."""
    RUN_KEY_MAP = {"alpha": "alpha_run", "beta": "beta_run", "tokenizer": "tokenizer_sample"}
    run_key = RUN_KEY_MAP.get(run, run)
    targets = manifest[run_key]["sources"]
    total_target = manifest[run_key]["target_total_tokens"]
    total_available = sum(available.values())

    rows = []
    for cat, spec in targets.items():
        have = available.get(cat, 0)
        need = spec["target_tokens"]
        gap = max(0, need - have)
        pct_filled = round(100 * have / need, 1) if need > 0 else 100.0
        rows.append({
            "category": cat,
            "target_tokens": need,
            "available_tokens": have,
            "gap_tokens": gap,
            "pct_filled": pct_filled,
            "status": "✅" if gap == 0 else ("🟡" if pct_filled >= 30 else "🔴"),
        })

    return {
        "run": run,
        "total_target": total_target,
        "total_available": total_available,
        "total_gap": max(0, total_target - total_available),
        "pct_filled": round(100 * total_available / total_target, 2) if total_target > 0 else 0,
        "categories": rows,
    }


def print_gap_report(gap: Dict):
    print(f"\n{'='*70}")
    print(f"  Kattappa Token Budget Report — Run: {gap['run'].upper()}")
    print(f"{'='*70}")
    print(f"  Target : {gap['total_target']:>15,} tokens")
    print(f"  Have   : {gap['total_available']:>15,} tokens  ({gap['pct_filled']}% filled)")
    print(f"  Gap    : {gap['total_gap']:>15,} tokens still needed")
    print(f"\n  {'Category':<20} {'Target':>12} {'Have':>12} {'Gap':>12} {'Fill%':>7} Status")
    print(f"  {'-'*20} {'-'*12} {'-'*12} {'-'*12} {'-'*7} ------")
    for r in gap["categories"]:
        print(f"  {r['category']:<20} {r['target_tokens']:>12,} {r['available_tokens']:>12,} "
              f"{r['gap_tokens']:>12,} {r['pct_filled']:>6.1f}%  {r['status']}")
    print(f"\n  Overall: {gap['status_summary']}")
    print(f"{'='*70}\n")


def main():
    parser = argparse.ArgumentParser(description="Kattappa Token Budget Planner")
    parser.add_argument("--run", choices=["alpha", "beta", "tokenizer"], default="alpha",
                        help="Which manifest run target to compare against (default: alpha)")
    parser.add_argument("--output", default=None,
                        help="Optional path to write gap report JSON")
    args = parser.parse_args()

    print(f"\n🔍 Scanning workspace: {WORKSPACE_ROOT}")
    manifest = json.loads(MANIFEST_PATH.read_text())

    available, file_reports = scan_workspace(WORKSPACE_ROOT)

    print(f"\n📁 Found {len(file_reports)} JSONL source files")
    for r in sorted(file_reports, key=lambda x: -x["total_tokens"])[:10]:
        print(f"   {r['path']:60s}  ~{r['total_tokens']:>8,} tokens")
    if len(file_reports) > 10:
        print(f"   ... and {len(file_reports)-10} more files")

    gap = compute_gap(manifest, args.run, available)

    # Compute top-level summary
    if gap["pct_filled"] >= 90:
        gap["status_summary"] = "✅ READY — token budget satisfied"
    elif gap["pct_filled"] >= 50:
        gap["status_summary"] = "🟡 PARTIAL — additional data collection required"
    else:
        gap["status_summary"] = "🔴 INSUFFICIENT — significant data collection needed before tokenizer training"

    print_gap_report(gap)

    # Write output report
    report_path = args.output or str(WORKSPACE_ROOT / f"kattappa_native/corpus/gap_report_{args.run}.json")
    report = {
        "manifest_version": manifest.get("_version", "unknown"),
        "model_target": manifest.get("_model_target", "Kattappa-100M"),
        "gap_analysis": gap,
        "file_reports": file_reports,
    }
    os.makedirs(os.path.dirname(report_path), exist_ok=True)
    Path(report_path).write_text(json.dumps(report, indent=2))
    print(f"📄 Gap report written to: {report_path}\n")


if __name__ == "__main__":
    main()
