#!/usr/bin/env python3
"""
KM-5.4 — Reasoning Evaluator (GSM8K subset)
=============================================
Evaluates the model on elementary math word problems using
exact-match on the final numeric answer.

Usage:
    PYTHONPATH=. python3 kattappa_native/evaluation/reasoning_eval.py
"""

import re
import json
import math
from pathlib import Path
from typing import List, Dict, Optional

# 20 representative GSM8K-style problems for rapid evaluation
GSM8K_SAMPLE = [
    {"question": "Janet has 3 cats. She buys 4 more cats. How many cats does she have?", "answer": "7"},
    {"question": "A store has 50 apples. They sell 18. How many are left?", "answer": "32"},
    {"question": "Maria earns $12 per hour. She works 8 hours. How much does she earn?", "answer": "96"},
    {"question": "A school has 6 classes with 25 students each. How many students total?", "answer": "150"},
    {"question": "Tom has 100 marbles. He gives away 1/4 of them. How many does he keep?", "answer": "75"},
    {"question": "A train travels 60 mph for 3 hours. How far does it go?", "answer": "180"},
    {"question": "There are 7 days in a week. How many days in 4 weeks?", "answer": "28"},
    {"question": "A pizza has 8 slices. If 3 people each eat 2 slices, how many are left?", "answer": "2"},
    {"question": "Sam buys 5 books at $8 each. How much does he spend?", "answer": "40"},
    {"question": "A farmer has 120 eggs. He sells 45. How many remain?", "answer": "75"},
    {"question": "If 3 workers can build a wall in 12 days, how many days for 1 worker?", "answer": "36"},
    {"question": "A rectangle is 7m wide and 9m long. What is its area?", "answer": "63"},
    {"question": "Lisa reads 25 pages per day. How many pages in 6 days?", "answer": "150"},
    {"question": "A bus holds 45 passengers. How many buses for 270 passengers?", "answer": "6"},
    {"question": "Mark saves $15 per week. How much in 10 weeks?", "answer": "150"},
    {"question": "A number doubled and added to 5 equals 25. What is the number?", "answer": "10"},
    {"question": "There are 36 students. 1/3 play soccer. How many play soccer?", "answer": "12"},
    {"question": "A car uses 8 litres per 100 km. How much for 350 km?", "answer": "28"},
    {"question": "Jake scored 85, 90, and 77. What is his average?", "answer": "84"},
    {"question": "A shop sells 3 items at $12 and 2 items at $15. Total revenue?", "answer": "66"},
]


def extract_numeric_answer(text: str) -> Optional[str]:
    """Extract the last number from a generated response."""
    nums = re.findall(r"-?\d+(?:\.\d+)?", text)
    return nums[-1] if nums else None


class ReasoningEvaluator:
    """
    Evaluates a model on arithmetic reasoning tasks.
    Supports both live model inference and mock greedy decode.
    """

    def __init__(self, problems: List[Dict] = None):
        self.problems = problems or GSM8K_SAMPLE

    def evaluate_model(self, model, tokenize_fn, decode_fn,
                       device, max_new_tokens: int = 64) -> Dict:
        """
        Run evaluation against a live KattappaModel.

        Args:
            model:         KattappaModel instance
            tokenize_fn:   callable(text: str) → torch.Tensor (1, T)
            decode_fn:     callable(ids: torch.Tensor) → str
            device:        torch.device
            max_new_tokens: Max generation length per problem
        """
        import torch
        model.eval()
        correct = 0
        results = []

        for prob in self.problems:
            prompt = f"Q: {prob['question']}\nA:"
            input_ids = tokenize_fn(prompt).unsqueeze(0).to(device)
            generated = model.generate(input_ids, max_new_tokens=max_new_tokens)
            answer_ids = generated[0, input_ids.shape[1]:]
            answer_text = decode_fn(answer_ids.tolist())
            pred = extract_numeric_answer(answer_text)
            gold = prob["answer"].strip()
            is_correct = (pred == gold)
            correct += int(is_correct)
            results.append({
                "question": prob["question"],
                "gold":     gold,
                "pred":     pred,
                "response": answer_text.strip(),
                "correct":  is_correct,
            })

        accuracy = correct / len(self.problems)
        return {
            "total": len(self.problems),
            "correct": correct,
            "accuracy": round(accuracy, 4),
            "results": results,
        }

    def mock_evaluate(self) -> Dict:
        """
        Dry-run evaluation using regex extraction on reference answers.
        Used for smoke-testing the evaluator without a trained model.
        """
        correct = 0
        for prob in self.problems:
            pred = extract_numeric_answer(f"The answer is {prob['answer']}.")
            if pred == prob["answer"]:
                correct += 1
        accuracy = correct / len(self.problems)
        print(f"\n  GSM8K Mock Eval:  {correct}/{len(self.problems)} = {accuracy*100:.1f}% accuracy (expected: 100%)")
        return {"accuracy": accuracy, "correct": correct, "total": len(self.problems)}


if __name__ == "__main__":
    ev = ReasoningEvaluator()
    result = ev.mock_evaluate()
    assert result["accuracy"] == 1.0, "Answer extraction regex is broken!"
    print("  ✅  Reasoning evaluator self-test passed.\n")
