import re
import unicodedata

class TextNormalizer:
    def __init__(self):
        # Regex list for common web boilerplate patterns
        self.boilerplate_patterns = [
            # Cookie and privacy consent notices
            r'(?i)this website uses cookies to ensure you get the best experience.*?\b(agree|accept|decline|ok)\b',
            r'(?i)we value your privacy.*?cookies.*?\b(consent|learn more)\b',
            # Navigation menus & social sharing prompts
            r'(?i)share this:.*?twitter.*?facebook.*?linkedin',
            r'(?i)follow us on (twitter|facebook|instagram|linkedin)',
            r'(?i)subscribe to our newsletter',
            r'(?i)sign up to receive the latest updates',
            # Footers / copyright banners
            r'(?i)©\s*\d{4}\s+[A-Za-z0-9\s,\.\-]+?\.\s*all rights reserved\.?',
            r'(?i)copyright\s*©\s*\d{4}.*?all rights reserved\.?'
        ]
        
        # Smart quote / dash conversions
        self.quote_replacements = {
            '“': '"', '”': '"',
            '‘': "'", '’': "'",
            '„': '"', '“': '"',
            '‟': '"', '′': "'",
            '″': '"', '‹': '<',
            '›': '>', '«': '"',
            '»': '"'
        }
        self.dash_replacements = {
            '—': '-', '–': '-',
            '―': '-', '⁓': '~'
        }

    def clean_unicode(self, text):
        """Fix broken unicode surrogates and normalize encoding."""
        # Enforce NFKC Unicode normalization
        normalized = unicodedata.normalize('NFKC', text)
        return normalized

    def replace_smart_characters(self, text):
        """Replaces smart quotes and em-dashes with ASCII standard equivalents."""
        # Smart quotes
        for k, v in self.quote_replacements.items():
            text = text.replace(k, v)
        # Dashes
        for k, v in self.dash_replacements.items():
            text = text.replace(k, v)
        return text

    def remove_boilerplate(self, text):
        """Removes common web boilerplate patterns."""
        for pattern in self.boilerplate_patterns:
            text = re.sub(pattern, '', text)
        return text

    def normalize_whitespace(self, text):
        """Collapses excessive spaces while preserving double newlines for paragraph structures."""
        # Replace 3 or more newlines with exactly 2 newlines (paragraph separator)
        text = re.sub(r'\n{3,}', '\n\n', text)
        # Replace non-newline whitespace (like multiple spaces/tabs) with a single space
        text = re.sub(r'[ \t]+', ' ', text)
        # Strip leading/trailing lines
        lines = [line.strip() for line in text.splitlines()]
        return '\n'.join(lines).strip()

    def clean(self, text):
        """Performs the full text normalization pipeline."""
        if not text:
            return ""
            
        text = self.clean_unicode(text)
        text = self.replace_smart_characters(text)
        text = self.remove_boilerplate(text)
        text = self.normalize_whitespace(text)
        return text
