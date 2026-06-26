import os
import sys

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))
from pipeline.ingest.lang_detector import KattappaLanguageDetector

def test_english_detection():
    detector = KattappaLanguageDetector()
    text = "The quick brown fox jumps over the lazy dog. This is a standard sentence in English."
    lang, conf = detector.detect_language(text)
    assert lang == "en"
    assert conf >= 0.90

def test_telugu_script_detection():
    detector = KattappaLanguageDetector()
    text = "కట్టప్ప ఒక శక్తివంతమైన మరియు సహాయకరమైన సహాయకుడు."
    lang, conf = detector.detect_language(text)
    assert lang == "te"
    assert conf == 1.0

def test_roman_telugu_detection():
    detector = KattappaLanguageDetector()
    text = "nuvvu ela unnavu? nenu chala bagunnanu."
    lang, conf = detector.detect_language(text)
    assert lang == "te-en"
    assert conf >= 0.70

def test_code_switched_detection():
    detector = KattappaLanguageDetector()
    # Mixed English and Roman Telugu terms
    text = "Tell me how are you doing? Nuvvu ela unnavu? Let me know if everything is fine, nenu bagunnanu."
    lang, conf = detector.detect_language(text)
    assert lang == "te-en-hybrid"
