"""
Context Optimizer — Step 30
============================

Implements the Adaptive Context Window. Selects and crops historical and external
context documents to stay within target token budgets based on task complexity.
"""

from __future__ import annotations

from typing import Dict, List, Any
import os

from kattappa_runtime.resource_governor.governor import ResourceGovernor
from kattappa_runtime.resource_governor.router import DifficultyEstimator


class ContextOptimizer:
    """
    Optimizes context sizes to fit system resource envelopes.
    Reduces context length to minimum needed (e.g. 800 tokens) for simpler queries.
    """
    def __init__(self, governor: ResourceGovernor):
        self.governor = governor
        self.estimator = DifficultyEstimator()
        self._sp_processor = None
        self._load_tokenizer()

    def _load_tokenizer(self):
        try:
            import sentencepiece as spm
            # Locate tokenizer file (should be in parent/kattappa folder)
            path = "kattappa_tokenizer.model"
            if os.path.exists(path):
                self._sp_processor = spm.SentencePieceProcessor(model_file=path)
        except Exception:
            pass

    def estimate_tokens(self, text: str) -> int:
        """
        Estimates token count using sentencepiece if loaded, else fallback character-based heuristic.
        """
        if self._sp_processor:
            try:
                return len(self._sp_processor.encode(text))
            except Exception:
                pass
        # Fallback heuristic: 1 token is roughly 4 characters
        return max(1, len(text) // 4)

    def optimize_context(
        self,
        prompt: str,
        history: List[Dict[str, str]],
        raw_documents: List[str],
        max_allowed_tokens: int = 2048,
    ) -> Dict[str, Any]:
        """
        Calculates a target token limit based on query difficulty.
        Trims history and raw document lists to fit that target.
        """
        difficulty = self.estimator.estimate_difficulty(prompt)
        metrics = self.governor.monitor.get_metrics()
        ram_percent = metrics.ram_percent

        # 1. Determine target token limit based on difficulty and RAM pressure
        if difficulty == "simple":
            target_limit = 800
        elif difficulty == "medium":
            target_limit = 1500
        else: # complex
            target_limit = max_allowed_tokens

        # Scale limit down if system RAM is critically high (> 50% limit)
        if ram_percent > (self.governor.config.global_ram_limit * 100):
            target_limit = int(target_limit * 0.7)  # Cut context budget by 30%

        # 2. Build context backwards from prompt, then history, then documents
        prompt_tokens = self.estimate_tokens(prompt)
        available_budget = max(0, target_limit - prompt_tokens)

        # Allocate 40% to history, 60% to documents
        history_budget = int(available_budget * 0.40)
        docs_budget = int(available_budget * 0.60)

        optimized_history: List[Dict[str, str]] = []
        history_tokens_used = 0
        
        # Traverse history from newest to oldest
        for msg in reversed(history):
            msg_text = msg.get("content", "")
            msg_tokens = self.estimate_tokens(msg_text)
            if history_tokens_used + msg_tokens <= history_budget:
                optimized_history.insert(0, msg)
                history_tokens_used += msg_tokens
            else:
                # Can't fit this message, stop including older messages
                break

        optimized_docs: List[str] = []
        docs_tokens_used = 0
        for doc in raw_documents:
            doc_tokens = self.estimate_tokens(doc)
            if docs_tokens_used + doc_tokens <= docs_budget:
                optimized_docs.append(doc)
                docs_tokens_used += doc_tokens
            else:
                # Crop document if possible, or skip
                rem_budget = docs_budget - docs_tokens_used
                if rem_budget > 50:  # worth cropping
                    chars_to_keep = rem_budget * 4
                    cropped_doc = doc[:chars_to_keep] + "... [cropped]"
                    optimized_docs.append(cropped_doc)
                    docs_tokens_used += rem_budget
                break

        total_tokens = prompt_tokens + history_tokens_used + docs_tokens_used

        return {
            "optimized_prompt": prompt,
            "optimized_history": optimized_history,
            "optimized_documents": optimized_docs,
            "tokens_used": total_tokens,
            "context_limit": target_limit,
            "difficulty": difficulty,
        }
