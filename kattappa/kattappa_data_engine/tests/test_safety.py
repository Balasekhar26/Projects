import os
import sys

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))
from pipeline.safety.safety_filter import SafetyFilter

def test_pii_redaction():
    sf = SafetyFilter()
    raw_text = "Contact developer@kattappa.io, phone 555-019-2834. SSN is 123-45-6789. secret_key=ab12cd34ef56gh78ij90kl12"
    redacted = sf.redact_pii(raw_text)
    
    assert "[REDACTED_EMAIL]" in redacted
    assert "developer@kattappa.io" not in redacted
    assert "[REDACTED_PHONE]" in redacted
    assert "555-019-2834" not in redacted
    assert "[REDACTED_SSN]" in redacted
    assert "123-45-6789" not in redacted
    assert "[REDACTED_SECRET]" in redacted
    assert "ab12cd34ef56gh78ij90kl12" not in redacted

def test_license_quarantine():
    sf = SafetyFilter(quarantine_licenses=["GPL-2.0", "AGPL-3.0"])
    
    doc_gpl = {
        "content": "def main(): pass",
        "provenance": {"license": "GPL-2.0"},
        "metadata": {"char_count": 16}
    }
    doc_mit = {
        "content": "def main(): pass",
        "provenance": {"license": "MIT"},
        "metadata": {"char_count": 16}
    }
    
    _, is_quar_gpl, reason_gpl = sf.process_document(doc_gpl)
    _, is_quar_mit, reason_mit = sf.process_document(doc_mit)
    
    assert is_quar_gpl == True
    assert "GPL-2.0" in reason_gpl
    assert is_quar_mit == False
