import re

class ContaminationChecker:
    def __init__(self, benchmark_questions=None):
        # Default mock benchmark questions for MMLU, GSM8K, HumanEval to demonstrate contamination checks
        self.benchmark_questions = benchmark_questions or {
            "gsm8k": [
                "weng earns $12 an hour babysitting. she babysits for 5 hours. how much does she earn?",
                "james writes 3 pages of a novel every day. how many pages in 4 weeks?"
            ],
            "mmlu": [
                "which planet is closest to the sun?",
                "what is the capital of France?",
                "what is the speed of light in a vacuum?"
            ],
            "humaneval": [
                "def return_unique_elements(lst):",
                "def calculate_factorial(n):"
            ]
        }
        
        # Build 13-gram sets for each benchmark
        self.benchmark_13grams = {}
        self.build_benchmark_ngrams()

    def get_tokens(self, text):
        """Extracts standard lowercased tokens from text for n-gram matching."""
        # Simple whitespace word tokenization is robust and fast for n-gram checks
        return re.findall(r'\b[a-zA-Z0-9_]+\b', text.lower())

    def get_ngrams(self, tokens, n=13):
        """Generates set of n-grams from a list of tokens."""
        if len(tokens) < n:
            return {tuple(tokens)}
        return {tuple(tokens[i:i+n]) for i in range(len(tokens) - n + 1)}

    def build_benchmark_ngrams(self):
        """Builds n-gram lookup maps for all benchmarks."""
        for benchmark, questions in self.benchmark_questions.items():
            self.benchmark_13grams[benchmark] = set()
            for q in questions:
                tokens = self.get_tokens(q)
                # If question is shorter than 13 tokens, we use its full token tuple as the n-gram
                n = min(13, len(tokens))
                if n > 0:
                    q_ngrams = self.get_ngrams(tokens, n=n)
                    self.benchmark_13grams[benchmark].update(q_ngrams)

        # Stopwords to ignore in semantic overlap checks
        self.english_stopwords = {
            "the", "and", "of", "to", "in", "is", "that", "it", "on", "for",
            "this", "with", "as", "you", "are", "have", "from", "they", "which",
            "what", "where", "how", "who", "why", "when", "be", "an", "a", "or"
        }

    def check_contamination(self, doc_text):
        """
        Checks if a document contains exact n-gram overlaps 
        or high word recall overlap against any benchmark question.
        Returns (is_contaminated, benchmark_name, matching_snippet)
        """
        doc_tokens = self.get_tokens(doc_text)
        if not doc_tokens:
            return False, None, None
            
        doc_13grams = self.get_ngrams(doc_tokens, n=13)
        
        # 1. Exact 13-gram overlap check
        for benchmark, b_ngrams in self.benchmark_13grams.items():
            overlaps = doc_13grams.intersection(b_ngrams)
            if overlaps:
                # Reconstruct sample snippet
                sample_gram = list(overlaps)[0]
                snippet = " ".join(sample_gram)
                return True, benchmark, f"13-gram overlap: '{snippet}'"
                
        # 2. Semantic content-word recall check to catch paraphrases/translations
        doc_word_set = set(doc_tokens)
        for benchmark, questions in self.benchmark_questions.items():
            for q in questions:
                q_tokens = self.get_tokens(q)
                if len(q_tokens) < 4:
                    continue
                q_set = set(q_tokens)
                
                # Filter out stopwords
                q_content_words = q_set - self.english_stopwords
                if not q_content_words:
                    q_content_words = q_set # Fallback
                    
                intersection = len(doc_word_set.intersection(q_content_words))
                recall = intersection / len(q_content_words) if q_content_words else 0.0
                
                # If 80% or more of the question's content words are present in the document
                if recall >= 0.80:
                    return True, benchmark, f"Content-word overlap {recall*100:.1f}% with question: '{q}'"
                    
        return False, None, None

    def process_dataset(self, documents):
        """
        Filters out contaminated documents from a dataset.
        Returns (clean_documents, contaminated_documents, report)
        """
        clean_docs = []
        contaminated_docs = []
        report = []
        
        for doc in documents:
            content = doc.get("content", "")
            is_contaminated, bench, reason = self.check_contamination(content)
            
            if is_contaminated:
                doc_id = doc.get("id")
                contaminated_docs.append(doc)
                report.append({
                    "doc_id": doc_id,
                    "source": doc.get("source"),
                    "benchmark": bench,
                    "reason": reason
                })
            else:
                clean_docs.append(doc)
                
        return clean_docs, contaminated_docs, report
