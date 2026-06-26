import re

class SafetyFilter:
    def __init__(self, quarantine_licenses=None, toxicity_keywords=None):
        self.quarantine_licenses = set(quarantine_licenses or [
            "GPL-2.0", "GPL-3.0", "AGPL-3.0", "LGPL-2.1", "LGPL-3.0", "GPL", "AGPL", "LGPL"
        ])
        self.toxicity_keywords = set(toxicity_keywords or [])

        # PII Regex patterns
        self.email_regex = re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,7}\b')
        self.phone_regex = re.compile(r'\b(?:\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b')
        self.ssn_regex = re.compile(r'\b\d{3}-\d{2}-\d{4}\b')
        self.credit_card_regex = re.compile(r'\b(?:\d{4}[-\s]?){3}\d{4}\b')
        
        # Secret / API key patterns (high entropy matching)
        self.api_key_regex = re.compile(
            r'\b(?:api[_-]?key|secret[_-]?key|secret|token|password|auth[_-]?token|access[_-]?token)\s*[:=]\s*["\'\s]?([a-zA-Z0-9_\-\.\=\+\/]{16,64})["\'\s]?',
            re.IGNORECASE
        )

    def redact_pii(self, text):
        """Redacts emails, phone numbers, SSNs, credit cards, and API keys."""
        # Redact emails
        text = self.email_regex.sub("[REDACTED_EMAIL]", text)
        # Redact phone numbers
        text = self.phone_regex.sub("[REDACTED_PHONE]", text)
        # Redact SSNs
        text = self.ssn_regex.sub("[REDACTED_SSN]", text)
        # Redact credit cards
        text = self.credit_card_regex.sub("[REDACTED_CARD]", text)
        
        # Redact API keys and secrets specifically
        def redact_key_match(match):
            full_match = match.group(0)
            secret_part = match.group(1)
            # Make sure we don't redact normal words
            if len(secret_part) >= 16:
                return full_match.replace(secret_part, "[REDACTED_SECRET]")
            return full_match
            
        text = self.api_key_regex.sub(redact_key_match, text)
        return text

    def contains_restricted_license(self, license_tag):
        """Checks if a license is copyleft and requires quarantine."""
        if not license_tag:
            return False
        tag_upper = license_tag.upper().strip()
        for restricted in self.quarantine_licenses:
            if restricted.upper() in tag_upper:
                return True
        return False

    def is_toxic(self, text):
        """Checks for toxic patterns or forbidden keywords."""
        if not self.toxicity_keywords:
            return False
        text_lower = text.lower()
        for keyword in self.toxicity_keywords:
            if keyword in text_lower:
                return True
        return False

    def process_document(self, doc, redact_pii=True, filter_licenses=True):
        """
        Processes document dict.
        Returns (processed_doc, is_quarantined, quarantine_reason)
        """
        content = doc.get("content", "")
        license_tag = doc.get("provenance", {}).get("license", "unknown")
        
        # 1. License Check
        if filter_licenses and self.contains_restricted_license(license_tag):
            return doc, True, f"Restricted copyleft license: {license_tag}"
            
        # 2. Toxicity Check
        if self.is_toxic(content):
            return doc, True, "Toxic content detected"
            
        # 3. PII Redaction
        if redact_pii:
            cleaned_content = self.redact_pii(content)
            # Update content
            doc["content"] = cleaned_content
            # Update stats
            doc["metadata"]["char_count"] = len(cleaned_content)
            
        return doc, False, None
