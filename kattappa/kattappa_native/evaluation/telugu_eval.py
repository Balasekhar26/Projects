#!/usr/bin/env python3
"""
KM-5.4 — Telugu Evaluator
===========================
Evaluates the model on three Telugu-specific capabilities:
  1. Script adherence   — output uses Telugu Unicode when prompted in Telugu
  2. Roman Telugu       — responds naturally to Romanised Telugu prompts
  3. Code-switching     — handles mid-sentence language switches

Usage:
    PYTHONPATH=. python3 kattappa_native/evaluation/telugu_eval.py
"""

import re
from typing import Dict, List, Optional

TELUGU_SCRIPT_RE = re.compile(r"[\u0C00-\u0C7F]")

SCRIPT_ADHERENCE_PROMPTS = [
    {"prompt": "తెలుగులో నమస్కారం చెప్పండి.",        "expect_telugu": True},
    {"prompt": "కత్తప్ప గురించి తెలుగులో వివరించండి.", "expect_telugu": True},
    {"prompt": "AI అంటే ఏమిటో తెలుగులో చెప్పండి.",    "expect_telugu": True},
]

ROMAN_TELUGU_PROMPTS = [
    {"prompt": "Nenu Kattappa AI ni build chestunna. Idi gurinchi cheppandi.",
     "expected_keywords": ["kattappa", "ai", "build", "model"]},
    {"prompt": "Meeru ela unnaru?",
     "expected_keywords": ["bagunnanu", "ok", "fine", "ela"]},
    {"prompt": "Mee project lo emi chestunnaru?",
     "expected_keywords": ["project", "work", "chestunna", "build"]},
]

CODE_SWITCH_PROMPTS = [
    "My project lo NLP use chestunna. What is NLP?",
    "Nenu oka model train chestunna. How many GPU hours does it take?",
    "Idi chala helpful ga undi. Can you explain more?",
]


def telugu_ratio(text: str) -> float:
    """Fraction of characters that are Telugu Unicode."""
    if not text:
        return 0.0
    telugu_chars = sum(1 for c in text if TELUGU_SCRIPT_RE.match(c))
    return telugu_chars / len(text)


class TeluguEvaluator:
    """
    Evaluates Telugu-specific capabilities of KattappaModel.
    Supports both live model and mock evaluation.
    """

    def evaluate_model(self, model, tokenize_fn, decode_fn,
                       device, max_new_tokens: int = 64) -> Dict:
        """Run all three evaluations against a live model."""
        script_results = self._eval_script_adherence(model, tokenize_fn, decode_fn, device, max_new_tokens)
        roman_results  = self._eval_roman_telugu(model, tokenize_fn, decode_fn, device, max_new_tokens)
        switch_results = self._eval_code_switch(model, tokenize_fn, decode_fn, device, max_new_tokens)

        return {
            "script_adherence": script_results,
            "roman_telugu": roman_results,
            "code_switching": switch_results,
            "overall_pass": (
                script_results["pass_rate"] >= 0.67 and
                roman_results["pass_rate"] >= 0.50
            ),
        }

    def _eval_script_adherence(self, model, tokenize_fn, decode_fn, device, max_new_tokens) -> Dict:
        import torch
        correct = 0
        for item in SCRIPT_ADHERENCE_PROMPTS:
            ids = tokenize_fn(item["prompt"]).unsqueeze(0).to(device)
            out = model.generate(ids, max_new_tokens=max_new_tokens)
            text = decode_fn(out[0, ids.shape[1]:].tolist())
            has_telugu = bool(TELUGU_SCRIPT_RE.search(text))
            if has_telugu == item["expect_telugu"]:
                correct += 1
        return {"correct": correct, "total": len(SCRIPT_ADHERENCE_PROMPTS),
                "pass_rate": correct / len(SCRIPT_ADHERENCE_PROMPTS)}

    def _eval_roman_telugu(self, model, tokenize_fn, decode_fn, device, max_new_tokens) -> Dict:
        import torch
        correct = 0
        for item in ROMAN_TELUGU_PROMPTS:
            ids = tokenize_fn(item["prompt"]).unsqueeze(0).to(device)
            out = model.generate(ids, max_new_tokens=max_new_tokens)
            text = decode_fn(out[0, ids.shape[1]:].tolist()).lower()
            matched = any(kw in text for kw in item["expected_keywords"])
            if matched:
                correct += 1
        return {"correct": correct, "total": len(ROMAN_TELUGU_PROMPTS),
                "pass_rate": correct / len(ROMAN_TELUGU_PROMPTS)}

    def _eval_code_switch(self, model, tokenize_fn, decode_fn, device, max_new_tokens) -> Dict:
        import torch
        results = []
        for prompt in CODE_SWITCH_PROMPTS:
            ids = tokenize_fn(prompt).unsqueeze(0).to(device)
            out = model.generate(ids, max_new_tokens=max_new_tokens)
            text = decode_fn(out[0, ids.shape[1]:].tolist())
            results.append({"prompt": prompt, "response": text})
        return {"samples": results, "total": len(CODE_SWITCH_PROMPTS)}

    def mock_evaluate(self) -> Dict:
        """
        Validates the evaluation framework without a model.
        """
        print(f"\n  Telugu Evaluator Checks:")

        # Script detection check
        telugu_text = "తెలుగు మాట్లాడుతున్నాను"
        english_text = "This is English text."
        assert telugu_ratio(telugu_text) > 0.8, "Telugu script detection broken"
        assert telugu_ratio(english_text) < 0.01, "False positive Telugu detection"
        print(f"  ✅  Script detection: Telugu={telugu_ratio(telugu_text):.2f}, English={telugu_ratio(english_text):.2f}")

        # Prompt counts
        print(f"  ✅  Script adherence probes: {len(SCRIPT_ADHERENCE_PROMPTS)}")
        print(f"  ✅  Roman Telugu probes:     {len(ROMAN_TELUGU_PROMPTS)}")
        print(f"  ✅  Code-switch probes:      {len(CODE_SWITCH_PROMPTS)}")
        print(f"  ✅  Telugu evaluator self-test passed.\n")

        return {"status": "mock_ok", "total_probes": len(SCRIPT_ADHERENCE_PROMPTS) + len(ROMAN_TELUGU_PROMPTS) + len(CODE_SWITCH_PROMPTS)}


if __name__ == "__main__":
    ev = TeluguEvaluator()
    ev.mock_evaluate()
