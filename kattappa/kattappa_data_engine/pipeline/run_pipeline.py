import os
import json
import yaml
import sys
import glob

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../")))

from pipeline.ingest.base_extractor import BaseExtractor
from pipeline.ingest.lang_detector import KattappaLanguageDetector
from pipeline.cleaning.text_normalizer import TextNormalizer
from pipeline.safety.safety_filter import SafetyFilter
from pipeline.dedup.exact_hash import ExactDeduplicator
from pipeline.dedup.minhash_lsh import MinHashLSH
from pipeline.scoring.quality_metrics import QualityScorer
from pipeline.classification.domain_tagger import DomainTagger
from pipeline.tokenizer.bpe_streamer import BPEStreamer
from pipeline.shard_builder.bin_packer import BinPacker
from pipeline.evaluation.contamination_checker import ContaminationChecker
from pipeline.evaluation.ablation_runner import AblationRunner

class KDEPipeline:
    def __init__(self, config_path=None):
        # Resolve config path
        if not config_path:
            config_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../config/pipeline_config.yaml"))
            
        self.workspace_dir = os.path.abspath(os.path.join(os.path.dirname(config_path), "../"))
        
        with open(config_path, 'r') as f:
            self.config = yaml.safe_load(f)
            
        # Initialize paths
        paths_cfg = self.config["paths"]
        self.raw_dir = os.path.join(self.workspace_dir, paths_cfg["raw_dir"])
        self.cleaned_dir = os.path.join(self.workspace_dir, paths_cfg["cleaned_dir"])
        self.safe_dir = os.path.join(self.workspace_dir, paths_cfg["safe_dir"])
        self.dedup_dir = os.path.join(self.workspace_dir, paths_cfg["deduplicated_dir"])
        self.scored_dir = os.path.join(self.workspace_dir, paths_cfg["scored_dir"])
        self.shards_dir = os.path.join(self.workspace_dir, paths_cfg["shards_dir"])
        self.reports_dir = os.path.join(self.workspace_dir, paths_cfg["reports_dir"])
        
        # Create folders
        for folder in [self.raw_dir, self.cleaned_dir, self.safe_dir, self.dedup_dir, self.scored_dir, self.shards_dir, self.reports_dir]:
            os.makedirs(folder, exist_ok=True)
            
        # Initialize modules
        self.extractor = BaseExtractor()
        self.lang_detector = KattappaLanguageDetector(self.config["language"]["roman_telugu_indicators"])
        self.normalizer = TextNormalizer()
        self.safety_filter = SafetyFilter(
            self.config["safety"]["quarantine_licenses"],
            self.config["safety"]["toxicity_keywords"]
        )
        self.exact_dedup = ExactDeduplicator()
        self.minhash_lsh = MinHashLSH(
            num_hashes=self.config["dedup"]["num_permutations"],
            jaccard_threshold=self.config["dedup"]["jaccard_threshold"]
        )
        self.scorer = QualityScorer()
        self.tagger = DomainTagger()
        
        # Load custom BPE Tokenizer
        tokenizer_path = os.path.abspath(os.path.join(self.workspace_dir, self.config["tokenizer"]["bpe_vocab_file"]))
        self.bpe_streamer = BPEStreamer(vocab_file_path=tokenizer_path)
        
        self.bin_packer = BinPacker(
            output_dir=self.shards_dir,
            train_ratio=self.config["sharding"]["train_ratio"],
            val_ratio=self.config["sharding"]["val_ratio"],
            test_ratio=self.config["sharding"]["test_ratio"],
            sequence_length=self.config["tokenizer"]["sequence_length"]
        )
        self.contamination_checker = ContaminationChecker()

    def generate_mock_raw_data(self):
        """Generates realistic mock files to allow instant execution/tests."""
        print("Generating mock raw files to process...")
        mock_files = {
            "books/story1.txt": "The ancient king ruled the land with a golden hand. He loved reading stories about distant planets. Today, the sun shines bright on his castle.",
            "books/story2_dup.txt": "The ancient king ruled the land with a golden hand. He loved reading stories about distant planets. Today, the sun shines bright on his castle.", # Near-duplicate
            "code/math_utils.py": "# Python math helpers\ndef add(a, b):\n    '''Returns a + b'''\n    return a + b\n\ndef multiply(x, y):\n    return x * y\n",
            "code/math_gpl.py": "# GPL Licensed helper\n# License: GPL-2.0\ndef calculate_sum(arr):\n    return sum(arr)\n", # restricted license file
            "conversations/chat1.jsonl": json.dumps({
                "source": "manual",
                "content": "User: hello! Nuva ela unnavu?\nKattappa: Nenu bagunnanu! Enti visheshalu?\nUser: Tell me about yourself.\nKattappa: Nenu Kattappa OS, your assistant.",
                "license": "MIT"
            }) + "\n" + json.dumps({
                "source": "manual",
                "content": "User: what is 1234567890?\nKattappa: It is a large number.",
                "license": "MIT"
            }),
            "docs/api_spec.md": "# API Specifications\nThis endpoint uses standard protocols. SSN of creator is 000-12-3456. Email developer@kattappa.io for keys. api_key=abc123xyz789secrettoken", # contains PII
            "web/wiki1.txt": "This website uses cookies to ensure you get the best experience. Accept. Paris is the capital of France. It is famous for the Eiffel Tower. Copyright © 2026. All rights reserved.", # contains boilerplate + mmlu benchmark content
        }
        
        for rel_path, content in mock_files.items():
            abs_path = os.path.join(self.raw_dir, rel_path)
            os.makedirs(os.path.dirname(abs_path), exist_ok=True)
            with open(abs_path, 'w', encoding='utf-8') as f:
                f.write(content)
        print(f"Mock raw files written to {self.raw_dir}")

    def run(self, generate_mock=True, run_ablation=True):
        """Executes all stages of the KDE pipeline."""
        print("="*60)
        print(" KATTAPPA DATA ENGINE (KDE-v1) START ".center(60, "="))
        print("="*60)
        
        # Ensure folders exist (can be deleted during tests after init)
        for folder in [self.cleaned_dir, self.safe_dir, self.dedup_dir, self.scored_dir, self.shards_dir, self.reports_dir]:
            os.makedirs(folder, exist_ok=True)

        if generate_mock:
            self.generate_mock_raw_data()
            
        # Search all files recursively in raw_dir
        raw_files = []
        for ext in ["**/*.txt", "**/*.md", "**/*.py", "**/*.jsonl"]:
            raw_files.extend(glob.glob(os.path.join(self.raw_dir, ext), recursive=True))
            
        print(f"Found {len(raw_files)} raw files to process.")
        
        # 1. Ingestion & Custom Language ID
        ingested_docs = []
        for filepath in raw_files:
            # Determine macro/micro class based on path
            rel_path = os.path.relpath(filepath, self.raw_dir)
            macro_class = "TEXT"
            if rel_path.startswith("books"):
                macro_class = "BOOK"
            elif rel_path.startswith("code"):
                macro_class = "CODE"
            elif rel_path.startswith("papers"):
                macro_class = "PAPER"
            elif rel_path.startswith("conversations"):
                macro_class = "CHAT"
            elif rel_path.startswith("docs"):
                macro_class = "TECH_DOC"
                
            # License extraction guess
            license_tag = "MIT"
            if "gpl" in filepath.lower():
                license_tag = "GPL-2.0"
                
            if filepath.endswith(".jsonl"):
                # Parse JSONL lines
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        for idx, line in enumerate(f):
                            if not line.strip():
                                continue
                            item = json.loads(line)
                            content = item.get("content", "")
                            if not content and "question" in item and "answer" in item:
                                if "solution_outline" in item:
                                    content = f"User: {item['question']}\nThinking: {item['solution_outline']}\nKattappa: {item['answer']}"
                                else:
                                    content = f"User: {item['question']}\nKattappa: {item['answer']}"
                            license_tag = item.get("license", "MIT")
                            doc = self.extractor.extract_document(
                                content, 
                                f"{filepath}#L{idx}", 
                                macro_class,
                                license_tag=license_tag
                            )
                            if doc:
                                # Copy synthetic metadata keys if present
                                for k in ["category", "difficulty", "language", "skills", "estimated_tokens", "generator"]:
                                    if k in item:
                                        doc[k] = item[k]
                                ingested_docs.append(doc)
                except Exception as e:
                    print(f"Error reading JSONL line: {e}")
            else:
                doc = self.extractor.process_file(filepath, macro_class, license_tag=license_tag)
                if doc:
                    ingested_docs.append(doc)
                    
        print(f"Ingested {len(ingested_docs)} documents.")
        
        # Apply custom Language Detector
        for doc in ingested_docs:
            lang, conf = self.lang_detector.detect_language(doc["content"])
            doc["language"] = lang
            
        # Write Ingested checkpoint
        ingested_path = os.path.join(self.cleaned_dir, "ingested.jsonl")
        with open(ingested_path, 'w', encoding='utf-8') as f:
            for doc in ingested_docs:
                f.write(json.dumps(doc) + "\n")
                
        # 2. Cleaning & Normalization
        cleaned_docs = []
        for doc in ingested_docs:
            norm_content = self.normalizer.clean(doc["content"])
            doc["content"] = norm_content
            doc["metadata"]["char_count"] = len(norm_content)
            doc["metadata"]["line_count"] = len(norm_content.splitlines())
            
            # Skip near-empty documents post-cleaning
            if len(norm_content.strip()) > 10:
                cleaned_docs.append(doc)
                
        print(f"Cleaned {len(cleaned_docs)} documents (dropped {len(ingested_docs) - len(cleaned_docs)} empty/short documents).")
        
        # 3. Safety & PII Sanitizer
        safe_docs = []
        quarantined_docs = []
        quarantine_logs = []
        
        for doc in cleaned_docs:
            processed_doc, is_quar, reason = self.safety_filter.process_document(doc)
            if is_quar:
                quarantined_docs.append(processed_doc)
                quarantine_logs.append({
                    "doc_id": doc["id"],
                    "source": doc["source"],
                    "reason": reason
                })
            else:
                safe_docs.append(processed_doc)
                
        print(f"Safety gate: {len(safe_docs)} documents marked safe, {len(quarantined_docs)} quarantined.")
        
        # 4. Deduplication
        unique_docs = []
        exact_dup_count = 0
        near_dup_count = 0
        
        # Phase A: Exact Match SHA256
        for doc in safe_docs:
            sha256 = doc["fingerprint"]["sha256"]
            if self.exact_dedup.is_duplicate(sha256):
                exact_dup_count += 1
                continue
                
            # Phase B: Near-dup LSH check
            is_near_dup = self.minhash_lsh.add_document(
                doc["id"], 
                doc["content"], 
                doc["fingerprint"]["minhash_signature"],
                is_code=(doc["macro_class"] == "CODE")
            )
            if is_near_dup:
                near_dup_count += 1
                continue
            
            # Paragraph-level deduplication
            doc["content"] = self.minhash_lsh.process_paragraphs_and_dedup(doc["content"])
            unique_docs.append(doc)
            
        # Get duplicate clusters from LSH
        duplicate_clusters = self.minhash_lsh.get_duplicate_clusters()
        # Find count of documents in duplicate groups
        grouped_ids = set()
        for root_id, doc_ids in duplicate_clusters.items():
            grouped_ids.update(doc_ids)
            
        print(f"Deduplication: {len(unique_docs)} unique documents. (Removed {exact_dup_count} exact dups, {near_dup_count} near dups).")
        
        # Write deduplicated checkpoint
        dedup_path = os.path.join(self.dedup_dir, "deduplicated.jsonl")
        with open(dedup_path, 'w', encoding='utf-8') as f:
            for doc in unique_docs:
                f.write(json.dumps(doc) + "\n")
                
        # 5. Domain Classification & Quality Scoring
        final_scored_docs = []
        rejected_by_quality = 0
        
        for doc in unique_docs:
            # Route and tag macro/micro classes + curriculum difficulty
            self.tagger.tag_document(doc)
            
            # Quality score
            score, metrics = self.scorer.score_document(doc)
            doc["metadata"]["quality_score"] = round(score, 2)
            doc["metadata"]["quality_metrics"] = metrics
            
            # Domain specific quality gates
            min_score = 50.0 if doc["macro_class"] == "CODE" else 45.0
            if score >= min_score:
                final_scored_docs.append(doc)
            else:
                rejected_by_quality += 1
                
        print(f"Scoring: {len(final_scored_docs)} documents passed quality threshold. Rejected {rejected_by_quality} low-score documents.")
        
        # Write scored checkpoint
        scored_path = os.path.join(self.scored_dir, "scored.jsonl")
        with open(scored_path, 'w', encoding='utf-8') as f:
            for doc in final_scored_docs:
                f.write(json.dumps(doc) + "\n")
                
        # 6. Pre-Flight Contamination Check
        clean_docs, contaminated, contamination_report = self.contamination_checker.process_dataset(final_scored_docs)
        print(f"Contamination check: {len(clean_docs)} clean documents. Quarantined {len(contaminated)} contaminated documents.")
        
        # Write reports
        reports_subdir = os.path.join(self.reports_dir, "quality_reports")
        os.makedirs(reports_subdir, exist_ok=True)
        with open(os.path.join(reports_subdir, "quarantine_logs.json"), 'w') as f:
            json.dump(quarantine_logs, f, indent=2)
        with open(os.path.join(reports_subdir, "contamination_report.json"), 'w') as f:
            json.dump(contamination_report, f, indent=2)
            
        # Ensure BPE Tokenizer exists or train dynamically on the processed clean text to initialize
        tokenizer_path = os.path.abspath(os.path.join(self.workspace_dir, self.config["tokenizer"]["bpe_vocab_file"]))
        if not os.path.exists(tokenizer_path):
            print("BPE merges cache not found. Dynamically training tokenizer on cleaned text...")
            all_text = " ".join([d["content"] for d in clean_docs])
            # Ensure text is long enough to train merges
            if len(all_text) < 1000:
                all_text += " " * (1000 - len(all_text))
            self.bpe_streamer.train_on_corpus(all_text, tokenizer_path)
            
        # 7. Shard Builder & Binary Packing
        splits = self.bin_packer.split_and_pack(clean_docs, duplicate_clusters, self.bpe_streamer)
        
        # 8. Ablation Runner (Filter Verification)
        if run_ablation and len(clean_docs) > 1:
            print("\n" + "="*50)
            print(" RUNNING ABLATION TESTING GATES ".center(50, "="))
            print("="*50)
            
            # Setup tokens for test
            # Dataset A: Cleaned, quality scored, decontaminated
            dataset_a_tokens = []
            for doc in clean_docs:
                dataset_a_tokens.extend(self.bpe_streamer.encode(doc["content"]))
                
            # Dataset B: Raw uncleaned (no safety, no quality check, but tokenized)
            dataset_b_tokens = []
            for doc in ingested_docs:
                dataset_b_tokens.extend(self.bpe_streamer.encode(doc["content"]))
                
            # Held-out val tokens
            val_tokens = []
            if splits.get("validation") and splits["validation"]["tokens"]:
                val_tokens = splits["validation"]["tokens"]
            else:
                val_tokens = dataset_a_tokens[:100] # Fallback if val split empty
                
            ablation_runner = AblationRunner()
            ablation_runner.run_ablation(dataset_a_tokens, dataset_b_tokens, val_tokens, filter_name="Clean + Quality Filters")
            
        print("\n" + "="*60)
        print(" KATTAPPA DATA ENGINE (KDE-v1) COMPLETED ".center(60, "="))
        print("="*60)

if __name__ == "__main__":
    pipeline = KDEPipeline()
    pipeline.run()
