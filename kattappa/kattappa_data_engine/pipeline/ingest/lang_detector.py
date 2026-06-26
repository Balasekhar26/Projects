import re

class KattappaLanguageDetector:
    def __init__(self, config_roman_indicators=None):
        # Default Roman Telugu indicators if config not provided
        self.roman_telugu_indicators = set(config_roman_indicators or [
            "nuvvu", "nenu", "unnavu", "bagunnanu", "enti", "chey", "ela",
            "unnava", "chestunnav", "tinnava", "ekada", "avunu", "ledhu",
            "telugu", "kattappa", "bagunda", "avuna", "baagundi", "namaskaram",
            "emiti", "ekkada", "enduku", "vachanu", "vellanu", "chala",
            "telusu", "teliyadu", "raaju", "amma", "nanna", "entha", "ippudu",
            "appudu", "eppudu", "cheppandi", "cheppu", "kadu", "kaadhu",
            "panulu", "pani", "undhi", "undi", "unnayi", "unnaayi"
        ])
        
        # Simple English stopwords to confirm English
        self.english_stopwords = {
            "the", "and", "of", "to", "in", "is", "that", "it", "on", "for",
            "this", "with", "as", "you", "are", "have", "with", "from", "they"
        }

    def is_telugu_script(self, text):
        """Detects if text contains Telugu Unicode characters."""
        # Telugu Unicode range is 0C00 - 0C7F
        telugu_range = re.compile(r'[\u0c00-\u0c7f]')
        matches = telugu_range.findall(text)
        # If at least 5% of characters or 5 characters are Telugu, classify as Telugu Script
        return len(matches) > 5 or (len(text) > 0 and len(matches) / len(text) > 0.05)

    def detect_language(self, text):
        """
        Determines the language of the text.
        Returns a tuple: (language_code, confidence)
        Language codes:
          - "te": Telugu Script
          - "te-en": Roman Telugu (transliterated)
          - "te-en-hybrid": Telugu-English Code-switched text
          - "en": English
          - "unknown": Undetermined language
        """
        if not text or not text.strip():
            return "unknown", 0.0
            
        # 1. Check Telugu script
        if self.is_telugu_script(text):
            return "te", 1.0
            
        # Tokenize words for Latin-based script checks
        words = re.findall(r'\b[a-zA-Z]+\b', text.lower())
        if not words:
            return "unknown", 0.0
            
        unique_words = set(words)
        
        # 2. Count Roman Telugu indicators
        roman_telugu_matches = unique_words.intersection(self.roman_telugu_indicators)
        english_matches = unique_words.intersection(self.english_stopwords)
        
        total_words_count = len(words)
        roman_count = sum(1 for w in words if w in self.roman_telugu_indicators)
        english_count = sum(1 for w in words if w in self.english_stopwords)
        
        # Heuristics:
        # If we have strong Roman Telugu indicators
        if len(roman_telugu_matches) >= 2 or (len(roman_telugu_matches) >= 1 and roman_count / total_words_count > 0.05):
            # Check if there is also significant English
            if len(english_matches) >= 3 and english_count / total_words_count > 0.1:
                return "te-en-hybrid", 0.90
            else:
                return "te-en", 0.95
                
        # If we have English stop words and no/low Roman Telugu
        if len(english_matches) >= 2 or english_count / total_words_count > 0.08:
            return "en", 0.95
            
        # Check specific phonetic endings common in Roman Telugu (like a high frequency of words ending in 'u', 'o', 'a')
        vowel_endings_count = sum(1 for w in words if w.endswith(('u', 'i', 'a')) and len(w) > 2)
        if vowel_endings_count / total_words_count > 0.4 and total_words_count > 5:
            # High probability of Roman Telugu / Dravidian transliteration
            return "te-en", 0.75
            
        return "unknown", 0.50
