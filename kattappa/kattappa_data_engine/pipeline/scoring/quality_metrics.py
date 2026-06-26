import re
import ast

def count_syllables(word):
    """Simple heuristic to count syllables in a word."""
    word = word.lower().strip()
    if not word:
        return 0
    # Simple vowel group count
    vowels = "aeiouy"
    count = 0
    prev_char_was_vowel = False
    for char in word:
        is_vowel = char in vowels
        if is_vowel and not prev_char_was_vowel:
            count += 1
        prev_char_was_vowel = is_vowel
    # Adjustments
    if word.endswith("e"):
        count -= 1
    if word.endswith("le") and len(word) > 2 and word[-3] not in vowels:
        count += 1
    if count == 0:
        count = 1
    return count

class QualityScorer:
    def __init__(self):
        pass

    def calculate_flesch_reading_ease(self, text):
        """Calculates Flesch Reading Ease score (0 to 100+)."""
        sentences = re.split(r'[.!?]+', text)
        sentences = [s.strip() for s in sentences if s.strip()]
        
        words = re.findall(r'\b[a-zA-Z]+\b', text)
        
        if not words or not sentences:
            return 0.0
            
        total_words = len(words)
        total_sentences = len(sentences)
        total_syllables = sum(count_syllables(w) for w in words)
        
        # Flesch Reading Ease Formula
        words_per_sentence = total_words / total_sentences
        syllables_per_word = total_syllables / total_words
        
        fre = 206.835 - (1.015 * words_per_sentence) - (84.6 * syllables_per_word)
        return max(0.0, min(120.0, fre))

    def get_symbol_ratio(self, text):
        """Calculates ratio of non-alphanumeric/non-whitespace symbols to total characters."""
        if not text:
            return 0.0
        # Symbols are anything not letter, number, or standard space/newline
        alphanumerics = len(re.findall(r'[a-zA-Z0-9\s]', text))
        symbols = len(text) - alphanumerics
        return symbols / len(text)

    def is_valid_python_syntax(self, code_text):
        """Checks if python code parses successfully."""
        try:
            ast.parse(code_text)
            return True
        except SyntaxError:
            return False

    def check_braces_balance(self, text):
        """Basic balanced brace check for non-python code languages (C/C++)."""
        stack = []
        mapping = {")": "(", "}": "{", "]": "["}
        for char in text:
            if char in mapping.values():
                stack.append(char)
            elif char in mapping.keys():
                if not stack or stack[-1] != mapping[char]:
                    return False
                stack.pop()
        # Allow small unclosed brace counts in incomplete snippets, but penalize major mismatches
        return len(stack) < 5

    def score_prose(self, text):
        """
        Scores prose documents (TEXT, BOOK, CHAT, PAPER).
        Factors: Readability, symbol ratio, structure.
        """
        fre = self.calculate_flesch_reading_ease(text)
        sym_ratio = self.get_symbol_ratio(text)
        
        # Readability score normalization: map fre ~60-90 to highest score (100)
        # Low readability (hard text) is fine for papers, but very low (<20) might be junk
        readability_points = 50.0
        if fre > 30:
            readability_points += 20.0
        if fre > 50:
            readability_points += 15.0
        if fre > 70:
            readability_points += 15.0
            
        # Symbol ratio penalty: high symbols = low quality
        symbol_penalty = max(0.0, (sym_ratio - 0.1) * 100.0) # Penalty starts after 10% symbols
        
        # Basic word count structure
        word_count = len(text.split())
        length_points = 15.0 if word_count > 100 else (word_count / 100.0) * 15.0
        
        final_score = readability_points + length_points - symbol_penalty
        return max(0.0, min(100.0, final_score)), {
            "flesch_reading_ease": fre,
            "symbol_ratio": sym_ratio,
            "word_count": word_count
        }

    def score_code(self, code_text, file_extension=".py"):
        """
        Scores code documents.
        Factors: Syntax validity, lines length, comment ratio.
        """
        # 1. Syntax check
        syntax_ok = True
        if file_extension == ".py":
            syntax_ok = self.is_valid_python_syntax(code_text)
        else:
            syntax_ok = self.check_braces_balance(code_text)
            
        syntax_points = 50.0 if syntax_ok else 15.0
        
        # 2. Line length check
        lines = code_text.splitlines()
        max_line_len = max(len(l) for l in lines) if lines else 0
        line_length_penalty = 0.0
        if max_line_len > 300:
            line_length_penalty = 15.0
        elif max_line_len > 150:
            line_length_penalty = 5.0
            
        # 3. Comment density
        comment_lines = sum(1 for l in lines if l.strip().startswith(('#', '//', '/*', '*')))
        total_lines = len(lines)
        comment_ratio = comment_lines / total_lines if total_lines > 0 else 0.0
        
        comment_points = 20.0 if 0.05 <= comment_ratio <= 0.35 else 10.0
        
        # 4. Length points
        length_points = 30.0 if total_lines > 15 else (total_lines / 15.0) * 30.0
        
        final_score = syntax_points + comment_points + length_points - line_length_penalty
        return max(0.0, min(100.0, final_score)), {
            "syntax_valid": syntax_ok,
            "max_line_length": max_line_len,
            "comment_ratio": comment_ratio,
            "line_count": total_lines
        }

    def score_document(self, doc):
        """Determines appropriate domain scoring and computes quality."""
        macro_class = doc.get("macro_class", "TEXT")
        content = doc.get("content", "")
        source = doc.get("source", "")
        
        if macro_class == "CODE":
            _, ext = os.path.splitext(source) if hasattr(os, 'path') else ("", ".py")
            score, metrics = self.score_code(content, ext or ".py")
        else:
            score, metrics = self.score_prose(content)
            
        return score, metrics
import os
