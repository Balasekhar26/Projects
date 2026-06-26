#!/usr/bin/env python3
"""
KM-5.4 — Tool Evaluation Wrapper
==================================
Wraps the existing KM-4 Evaluation Engine to measure tool-call F1
from Kattappa-100M's autoregressive output.

Usage:
    PYTHONPATH=. python3 kattappa_native/evaluation/tool_eval.py
"""

import sys
import json
import re
from pathlib import Path
from typing import Dict, List, Optional

WORKSPACE_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(WORKSPACE_ROOT))

TOOL_PROMPTS = [
    {"prompt": "What is 144 divided by 12?",
     "expected_tool": "calculator", "expected_keyword": "12"},
    {"prompt": "What time is it right now?",
     "expected_tool": "clock", "expected_keyword": None},
    {"prompt": "Search for information about the Godavari river.",
     "expected_tool": "search_mock", "expected_keyword": "godavari"},
    {"prompt": "Calculate the square root of 225.",
     "expected_tool": "calculator", "expected_keyword": "15"},
    {"prompt": "What is 7 factorial?",
     "expected_tool": "calculator", "expected_keyword": "5040"},
]

TOOL_CALL_RE = re.compile(
    r'(?:use|call|invoke)\s+tool\s*[:\-]?\s*([a-zA-Z_]\w{2,})',
    re.IGNORECASE,
)


def detect_tool_call(text: str) -> Optional[str]:
    """Extract tool name from model output if present."""
    m = TOOL_CALL_RE.search(text)
    if m:
        return m.group(1).lower()
    # Check for JSON-style tool call
    json_re = re.search(r'"tool"\s*:\s*"(\w+)"', text)
    if json_re:
        return json_re.group(1).lower()
    return None


class ToolEvaluator:
    """Evaluates tool-use ability by measuring tool-call F1."""

    def __init__(self, prompts: List[Dict] = None):
        self.prompts = prompts or TOOL_PROMPTS

    def evaluate_model(self, model, tokenize_fn, decode_fn,
                       device, max_new_tokens: int = 64) -> Dict:
        """Run evaluation against a live model."""
        tp = fp = fn = 0
        results = []

        for item in self.prompts:
            ids = tokenize_fn(item["prompt"]).unsqueeze(0).to(device)
            out = model.generate(ids, max_new_tokens=max_new_tokens)
            text = decode_fn(out[0, ids.shape[1]:].tolist())
            pred_tool = detect_tool_call(text)
            gold_tool = item["expected_tool"]

            correct_tool = pred_tool is not None and (
                pred_tool == gold_tool or gold_tool in (pred_tool or "")
            )
            if correct_tool:
                tp += 1
            elif pred_tool is not None:
                fp += 1
            else:
                fn += 1

            results.append({
                "prompt": item["prompt"],
                "expected_tool": gold_tool,
                "predicted_tool": pred_tool,
                "response": text.strip(),
                "correct": correct_tool,
            })

        precision = tp / max(tp + fp, 1)
        recall    = tp / max(tp + fn, 1)
        f1        = 2 * precision * recall / max(precision + recall, 1e-8)

        return {
            "precision": round(precision, 4),
            "recall":    round(recall, 4),
            "f1":        round(f1, 4),
            "tp": tp, "fp": fp, "fn": fn,
            "results": results,
        }

    def mock_evaluate(self) -> Dict:
        """Self-test the tool detection regex."""
        test_cases = [
            ("I will use tool: calculator to solve this.", "calculator"),
            ('{"tool": "clock", "query": "current time"}', "clock"),
            ("Let me call tool search_mock for this.", "search_mock"),
            ("I don't need any tool here.", None),
        ]
        all_pass = True
        print(f"\n  Tool Evaluator Checks:")
        for text, expected in test_cases:
            detected = detect_tool_call(text)
            ok = detected == expected
            status = "✅" if ok else "❌"
            print(f"  {status}  '{text[:50]}...' → {detected!r} (expected {expected!r})")
            if not ok:
                all_pass = False

        print(f"\n  Total probes: {len(self.prompts)}")
        print(f"  ✅  Tool evaluator self-test {'passed' if all_pass else 'FAILED'}.\n")
        return {"all_pass": all_pass}


if __name__ == "__main__":
    ev = ToolEvaluator()
    ev.mock_evaluate()
