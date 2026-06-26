"""
Word-Level Tokenizer.

Splits text into words and punctuation marks using regular expressions.
Handles out-of-vocabulary words using an <UNK> token.
"""

import re

class WordTokenizer:
    def __init__(self):
        self.vocab = ["<UNK>"]
        self.word_to_id = {"<UNK>": 0}
        self.id_to_word = {0: "<UNK>"}

    def _tokenize_raw(self, text: str) -> list[str]:
        """Split text into words and punctuation marks, discarding whitespace."""
        return re.findall(r"\w+|[^\w\s]", text)

    def train(self, text: str):
        """Build the vocabulary from unique words/punctuation marks in the training text."""
        raw_tokens = self._tokenize_raw(text)
        unique_words = sorted(list(set(raw_tokens)))
        
        self.vocab = ["<UNK>"] + unique_words
        self.word_to_id = {word: idx for idx, word in enumerate(self.vocab)}
        self.id_to_word = {idx: word for idx, word in enumerate(self.vocab)}

    def encode(self, text: str) -> list[int]:
        """Convert text into a list of word integer IDs, mapping unknown words to <UNK>."""
        raw_tokens = self._tokenize_raw(text)
        return [self.word_to_id.get(word, 0) for word in raw_tokens]

    def decode(self, ids: list[int]) -> str:
        """Reconstruct a readable string from word IDs, with basic spacing rules for punctuation."""
        words = [self.id_to_word.get(idx, "<UNK>") for idx in ids]
        result = []
        for i, word in enumerate(words):
            # Don't prefix punctuation marks with a space
            if i > 0 and word not in {".", ",", "!", "?", ";", ":", "'"}:
                result.append(" " + word)
            else:
                result.append(word)
        return "".join(result)
