#!/usr/bin/env python3
"""
Tokenization Experiments & Concept Verification (Step 23).

Trains Character, Word, and BPE tokenizers on a mixed corpus.
Tests and compares their representations for:
- Numbers
- Spelling mistakes
- Arithmetic formulas

Outputs conceptual answers to the core tokenization questions.
"""

import json
from character_tokenizer import CharacterTokenizer
from word_tokenizer import WordTokenizer
from bpe_tokenizer import BPETokenizer

# Define a mixed training corpus (text, math, spelling errors, and numbers)
TRAINING_CORPUS = """
The quick brown fox jumps over the lazy dog.
Deep learning and neural networks are built on transformers.
Mathematics and arithmetic: 2 + 2 = 4, and 12 * 12 = 144.
Large numbers like 1234567890 are hard to process.
Sometimes there are spelling mistakes like computr, intelligenc, or codng.
We want our tokenizer to be robust and learn common patterns.
Kattappa is a local AI assistant operating system.
It remembers conversations, plan steps, and executes tools.
"""

def print_section(title):
    print("\n" + "=" * 80)
    print(f" {title} ".center(80, "="))
    print("=" * 80)

def main():
    print_section("TRAINING TOKENIZERS")
    
    # 1. Train Character Tokenizer
    char_tok = CharacterTokenizer()
    char_tok.train(TRAINING_CORPUS)
    print(f"Character Tokenizer trained. Vocab size: {len(char_tok.vocab)}")
    
    # 2. Train Word Tokenizer
    word_tok = WordTokenizer()
    word_tok.train(TRAINING_CORPUS)
    print(f"Word Tokenizer trained. Vocab size: {len(word_tok.vocab)}")
    
    # 3. Train BPE Tokenizer
    # We set target vocab size to 320 (256 base bytes + 64 learned merges)
    bpe_tok = BPETokenizer()
    bpe_tok.train(TRAINING_CORPUS, vocab_size=320)
    print(f"BPE Tokenizer trained. Base vocab: 256. Learned merges: {len(bpe_tok.merges)}. Total vocab: {len(bpe_tok.vocab)}")
    print(f"Sample learned merges: {list(bpe_tok.merges.items())[:10]}")

    print_section("VERIFYING LOSSLESSNESS (DECODE(ENCODE(TEXT)) == TEXT)")
    test_sentences = [
        "The quick brown fox jumps over the lazy dog.",
        "Arithmetic: 12 * 12 = 144.",
        "Kattappa is ready.",
        "Testing numbers: 1234567890."
    ]
    for s in test_sentences:
        encoded = bpe_tok.encode(s)
        decoded = bpe_tok.decode(encoded)
        success = (s == decoded)
        print(f"Original: {s!r}")
        print(f"Encoded:  {encoded}")
        print(f"Decoded:  {decoded!r} | Lossless: {success}")
        assert success, f"BPE failed lossless check for {s!r}"

    print_section("COMPARISON: NUMBER REPRESENTATION")
    number_test = "1234567890"
    print(f"Test Number: {number_test}")
    
    char_ids = char_tok.encode(number_test)
    print(f"Character Tokenizer ({len(char_ids)} tokens):")
    print(f"  IDs:    {char_ids}")
    print(f"  Tokens: {[char_tok.decode([idx]) for idx in char_ids]}")
    
    word_ids = word_tok.encode(number_test)
    print(f"Word Tokenizer ({len(word_ids)} tokens):")
    print(f"  IDs:    {word_ids}")
    print(f"  Tokens: {[word_tok.decode([idx]) for idx in word_ids]}")
    
    bpe_ids = bpe_tok.encode(number_test)
    print(f"BPE Tokenizer ({len(bpe_ids)} tokens):")
    print(f"  IDs:    {bpe_ids}")
    print(f"  Tokens: {[bpe_tok.decode([idx]) for idx in bpe_ids]}")

    print_section("COMPARISON: SPELLING MISTAKES")
    mistake_test = "computr intelligenc codng"
    print(f"Test Typos: {mistake_test}")
    
    word_ids = word_tok.encode(mistake_test)
    print(f"Word Tokenizer (Unseen words become <UNK>):")
    print(f"  IDs:    {word_ids}")
    print(f"  Tokens: {[word_tok.decode([idx]) for idx in word_ids]}")
    
    bpe_ids = bpe_tok.encode(mistake_test)
    print(f"BPE Tokenizer (Splits unseen typo words into known sub-words):")
    print(f"  IDs:    {bpe_ids}")
    print(f"  Tokens: {[bpe_tok.decode([idx]) for idx in bpe_ids]}")

    print_section("COMPARISON: ARITHMETIC")
    math_test = "12 * 12 = 144"
    print(f"Test Formula: {math_test}")
    
    bpe_ids = bpe_tok.encode(math_test)
    print(f"BPE Tokenizer representation:")
    print(f"  IDs:    {bpe_ids}")
    print(f"  Tokens: {[bpe_tok.decode([idx]) for idx in bpe_ids]}")

    print_section("CONCEPTUAL ANSWERS")
    
    print("Q1: Why does GPT use tokens instead of words?")
    print("A1: ")
    print("    - Raw words require an infinite vocabulary (slang, names, typos) resulting")
    print("      in constant <UNK> errors, or require massive embed parameters.")
    print("    - Raw characters lead to extremely long sequences, which make the quadratic")
    print("      attention complexity cost O(N^2) computationally prohibitive.")
    print("    - Sub-word tokens (like BPE) hit the optimal balance: the vocabulary is")
    print("      bounded (typically 32k - 100k), and unseen/new words are naturally split")
    print("      into known sub-tokens without any information loss.")
    print("\n")
    
    print("Q2: Why are numbers difficult for LLMs?")
    print("A2: ")
    print("    - BPE tokenizers group digits based on their corpus frequency, not mathematical")
    print("      values. For example, '12345' might tokenise as ['12', '345'], whereas '12346'")
    print("      might tokenise as ['123', '46'].")
    print("    - This arbitrary grouping scrambles the structure, making it extremely hard")
    print("      for the neural network weights to learn addition carrying or general arithmetic")
    print("      rules. The model must essentially memorize math table outputs for random digit blocks.")
    print("\n")
    
    print("Q3: Why do spelling mistakes happen or affect performance?")
    print("A3: ")
    print("    - A single typo (e.g. 'computr' vs 'computer') completely alters the sub-word")
    print("      pairs. The tokenizer splits the typo word into unfamiliar sub-tokens like")
    print("      ['comp', 'utr'] instead of ['computer'].")
    print("    - Because the resulting token IDs are completely different, the model's active")
    print("      attention weights trigger different paths, and it fails to map the semantic")
    print("      context to the correct concept.")
    print("\n")
    
    print("Q4: Why does arithmetic fail?")
    print("A4: ")
    print("    - Arithmetic calculations are strictly digit-aligned and positional.")
    print("      However, tokenizers group digits non-uniformly.")
    print("    - When performing a sum (e.g. 542 + 239), the model does not see aligned columns")
    print("      of units, tens, and hundreds. It sees token chunks (e.g. [54, 2] + [239]).")
    print("      Because the digit positions are warped by tokenization, the model cannot")
    print("      consistently apply column-wise addition or multiplication algorithms.")
    print("=" * 80 + "\n")

if __name__ == "__main__":
    main()
