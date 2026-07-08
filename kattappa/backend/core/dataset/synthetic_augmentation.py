"""Synthetic Augmentation (Program 26.0).

Expands dataset coverage by generating instruction paraphrases through
deterministic template substitution — no external model required.
"""
from __future__ import annotations

import copy
from typing import Any, Dict, List

# Paraphrase prefix templates applied to instruction strings
_PREFIXES = [
    "Please ",
    "I need you to ",
    "Your task is to ",
    "Can you ",
    "Help me to ",
]

# Light verb substitutions to increase surface variation
_VERB_SUBS: List[tuple[str, str]] = [
    ("create", "build"),
    ("build", "construct"),
    ("deploy", "launch"),
    ("run", "execute"),
    ("check", "verify"),
    ("generate", "produce"),
    ("analyze", "examine"),
    ("install", "set up"),
]


def _paraphrase(instruction: str, prefix: str) -> str:
    """Applies a prefix and optional verb substitution to an instruction."""
    text = instruction.strip()

    # Lowercase leading char when adding a prefix
    if text and not text[0].isupper():
        first = text
    else:
        first = text[0].lower() + text[1:] if len(text) > 1 else text.lower()

    paraphrased = prefix + first

    # Apply one verb substitution (first match wins)
    for original, replacement in _VERB_SUBS:
        if original in paraphrased.lower():
            paraphrased = paraphrased.lower().replace(original, replacement, 1)
            # Restore capitalisation if prefix started with uppercase
            if prefix[0].isupper():
                paraphrased = paraphrased[0].upper() + paraphrased[1:]
            break

    return paraphrased


class SyntheticAugmentation:
    """Generates instruction variants from existing records without calling any LLM."""

    @classmethod
    def augment(
        cls,
        records: List[Dict[str, Any]],
        variants_per_record: int = 2,
    ) -> List[Dict[str, Any]]:
        """Produces `variants_per_record` paraphrased copies of each record.

        The originals are included in the returned list.
        """
        result: List[Dict[str, Any]] = []
        prefixes = _PREFIXES[:variants_per_record]

        for rec in records:
            result.append(rec)  # keep original
            instruction = rec.get("instruction", "")
            for prefix in prefixes:
                variant = copy.deepcopy(rec)
                variant["instruction"] = _paraphrase(instruction, prefix)
                variant["augmented"] = True
                result.append(variant)

        return result
