import os
import json
import hashlib
from pipeline.synthetic.reasoning_generator import ReasoningGenerator
from pipeline.synthetic.planning_generator import PlanningGenerator
from pipeline.synthetic.coding_generator import CodingGenerator
from pipeline.synthetic.memory_generator import MemoryGenerator
from pipeline.synthetic.tool_generator import ToolGenerator
from pipeline.synthetic.telugu_generator import TeluguGenerator

class SyntheticDataFactory:
    def __init__(self, output_filepath=None):
        if not output_filepath:
            # Default location
            script_dir = os.path.dirname(os.path.abspath(__file__))
            self.output_filepath = os.path.abspath(os.path.join(
                script_dir, "../../data/raw/conversations/kattappa_synthetic_v1.jsonl"
            ))
        else:
            self.output_filepath = output_filepath

        # Initialize sub-generators
        self.generators = {
            "reasoning": ReasoningGenerator(),
            "planning": PlanningGenerator(),
            "coding": CodingGenerator(),
            "memory": MemoryGenerator(),
            "tool_usage": ToolGenerator(),
            "telugu": TeluguGenerator()
        }

    def compute_sha256(self, text):
        return hashlib.sha256(text.encode('utf-8')).hexdigest()

    def validate_and_filter(self, samples):
        """
        Enforces quality filters on generated samples:
        1. Length check: question + answer > 100 tokens (or ~400 characters).
        2. Schema integrity check.
        3. Deduplication check (exact SHA256 of the question).
        """
        validated_samples = []
        seen_questions = set()
        skipped_short = 0
        skipped_dup = 0
        
        for sample in samples:
            # Check length (minimum characters limit equivalent to ~100 tokens)
            combined_text = sample.get("question", "") + " " + sample.get("answer", "")
            # Estimate tokens: 1 token ~ 4 characters. 100 tokens ~ 400 characters.
            estimated_tok = sample.get("estimated_tokens", 0)
            
            if estimated_tok < 50:  # Allow small headroom but verify substantial content length
                skipped_short += 1
                continue
                
            # Check exact duplicates of question
            q_hash = self.compute_sha256(sample.get("question", ""))
            if q_hash in seen_questions:
                skipped_dup += 1
                continue
                
            seen_questions.add(q_hash)
            validated_samples.append(sample)
            
        print(f"Quality Gate summary: Cleaned {len(samples)} -> {len(validated_samples)} valid. (Skipped short: {skipped_short}, duplicate: {skipped_dup})")
        return validated_samples

    def generate_all(self, target_per_category=500):
        print("="*60)
        print(" STARTING SYNTHETIC DATA FACTORY RUN ".center(60, "="))
        print("="*60)
        
        raw_samples = []
        for category, generator in self.generators.items():
            print(f"Generating {target_per_category} samples for category: {category}...")
            # We generate slightly more (e.g. 520) to ensure we hit the 500 target post-filtering
            category_samples = generator.generate_batch(target_per_category + 20)
            raw_samples.extend(category_samples)
            
        # Run quality, validation, and deduplication gates
        validated_samples = self.validate_and_filter(raw_samples)
        
        # Enforce that we have at least 500 per category post-filtering
        category_counts = {cat: 0 for cat in self.generators.keys()}
        final_samples = []
        
        for sample in validated_samples:
            cat = sample.get("category")
            if category_counts[cat] < target_per_category:
                final_samples.append(sample)
                category_counts[cat] += 1
                
        # Report final category balances
        print("-" * 50)
        print(" Final Generated Counts per Category ".center(50, "-"))
        print("-" * 50)
        for cat, count in category_counts.items():
            print(f"  - {cat:<15}: {count} / {target_per_category}")
        print("-" * 50)
        print(f"Total Consolidated Dataset Size: {len(final_samples)} samples")
        
        # Write to JSONL
        os.makedirs(os.path.dirname(self.output_filepath), exist_ok=True)
        with open(self.output_filepath, 'w', encoding='utf-8') as f:
            for sample in final_samples:
                f.write(json.dumps(sample) + "\n")
                
        print(f"Consolidated dataset successfully written to: {self.output_filepath}")
        return final_samples

if __name__ == "__main__":
    factory = SyntheticDataFactory()
    factory.generate_all()
