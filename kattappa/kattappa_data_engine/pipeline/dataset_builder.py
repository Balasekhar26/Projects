import os
import json
import random
import hashlib
from pipeline.synthetic.factory import SyntheticDataFactory

class DatasetBuilder:
    def __init__(self, output_dir=None, raw_jsonl_path=None):
        script_dir = os.path.dirname(os.path.abspath(__file__))
        self.output_dir = output_dir or os.path.abspath(os.path.join(script_dir, "../data/processed/sft"))
        self.raw_jsonl_path = raw_jsonl_path or os.path.abspath(os.path.join(
            script_dir, "../data/raw/conversations/kattappa_synthetic_v1.jsonl"
        ))
        
        # General templates for Replay Data (Alpaca/Dolly style)
        self.general_topics = [
            ("Write a short story about {noun} who wanted to {action}.", 
             "Once upon a time, a {noun} decided to {action}. It was a long journey filled with challenges, but they persisted and succeeded."),
            ("What is the capital of {country}?", "The capital of {country} is {capital}."),
            ("Solve the following simple math: what is {a} + {b}?", "The sum of {a} and {b} is {result}."),
            ("Give me 3 synonyms for the word '{word}'.", "Here are 3 synonyms for '{word}': {synonyms}."),
            ("Explain the concept of {science_topic} in simple terms.", "{science_topic} is {explanation}.")
        ]
        
        self.nouns = ["a young coder", "an old sailor", "a small robot", "a curious cat", "a brave astronaut"]
        self.actions = ["learn python", "cross the Atlantic", "find a lost key", "climb Mt. Everest", "explore Mars"]
        self.countries = [
            ("France", "Paris"), ("Germany", "Berlin"), ("Japan", "Tokyo"), 
            ("India", "New Delhi"), ("Australia", "Canberra"), ("Canada", "Ottawa")
        ]
        self.words = [
            ("happy", "joyful, cheerful, delighted"),
            ("smart", "intelligent, clever, wise"),
            ("fast", "quick, rapid, swift"),
            ("strong", "powerful, robust, sturdy")
        ]
        self.science_topics = [
            ("gravity", "the force by which a planet or other body draws objects toward its center"),
            ("photosynthesis", "the process by which green plants use sunlight to synthesize nutrients from carbon dioxide and water"),
            ("atoms", "the basic building blocks of all matter, consisting of protons, neutrons, and electrons"),
            ("evaporation", "the process of a liquid turning into vapor/gas")
        ]
        
        # Refusal Calibration Templates
        self.refusal_queries = [
            "What is the exact firmware source code for the watchdog timer in Project {project} version {ver}?",
            "Can you compute the exact RF link budget for a receiver without knowing the {missing_param}?",
            "What was the password or private API key used in the {db} database backup of last week?",
            "How do I override the hardware safety interlock of the telemetry unit model {model}?",
            "Show me the proprietary schematics of the RF transceiver chip {chip}."
        ]
        self.refusals = [
            "I do not have access to the proprietary source code or private firmware files for Project {project} version {ver}. If you share the code structure, I can help you debug it.",
            "I do not have enough information to compute the RF link budget. The {missing_param} is missing. Please provide this parameter to perform the calculation.",
            "I cannot retrieve or disclose private passwords, credentials, or API keys for the {db} database. For security reasons, please configure these via environment variables.",
            "I cannot assist in overriding or disabling hardware safety interlocks for telemetry unit model {model}. Bypassing safety constraints poses physical and electrical hazards.",
            "I do not have access to the proprietary schematics or confidential internal layout of the transceiver chip {chip}. Please refer to the manufacturer datasheet for public specifications."
        ]

    def generate_replay_data(self, count):
        """Generates general-purpose instruction samples to prevent catastrophic forgetting."""
        random.seed(42)
        samples = []
        for i in range(count):
            tpl_idx = i % len(self.general_topics)
            template, response = self.general_topics[tpl_idx]
            
            if tpl_idx == 0:
                noun = random.choice(self.nouns)
                action = random.choice(self.actions)
                inst = template.format(noun=noun, action=action)
                out = response.format(noun=noun, action=action)
            elif tpl_idx == 1:
                country, capital = random.choice(self.countries)
                inst = template.format(country=country)
                out = response.format(country=country, capital=capital)
            elif tpl_idx == 2:
                a, b = random.randint(10, 99), random.randint(10, 99)
                inst = template.format(a=a, b=b)
                out = response.format(a=a, b=b, result=a+b)
            elif tpl_idx == 3:
                word, syns = random.choice(self.words)
                inst = template.format(word=word)
                out = response.format(word=word, synonyms=syns)
            else:
                topic, exp = random.choice(self.science_topics)
                inst = template.format(science_topic=topic)
                out = response.format(science_topic=topic, explanation=exp)
                
            samples.append({
                "instruction": inst,
                "input": "",
                "output": out,
                "category": "general",
                "difficulty": "easy",
                "language": "english"
            })
        return samples

    def generate_refusal_data(self, count):
        """Generates refusal calibration examples to avoid hallucinations."""
        random.seed(99)
        samples = []
        projects = ["Aegis", "Beacon", "Chronos", "Daedalus"]
        missing_params = ["path loss", "receiver sensitivity", "antenna gains", "transmit power"]
        dbs = ["users_prod", "billing_replica", "telemetry_logs"]
        models = ["T-1000", "Z-200", "X-90"]
        chips = ["SX1276", "CC1101", "ESP32-S3"]
        
        for i in range(count):
            idx = i % len(self.refusal_queries)
            q_template = self.refusal_queries[idx]
            r_template = self.refusals[idx]
            
            project = random.choice(projects)
            ver = f"{random.randint(1, 5)}.{random.randint(0, 9)}"
            missing = random.choice(missing_params)
            db = random.choice(dbs)
            model = random.choice(models)
            chip = random.choice(chips)
            
            inst = q_template.format(project=project, ver=ver, missing_param=missing, db=db, model=model, chip=chip)
            out = r_template.format(project=project, ver=ver, missing_param=missing, db=db, model=model, chip=chip)
            
            samples.append({
                "instruction": inst,
                "input": "",
                "output": out,
                "category": "refusal",
                "difficulty": "medium",
                "language": "english"
            })
        return samples

    def build_sft_dataset(self):
        print("="*60)
        print(" STARTING SFT DATASET BUILDER (KM-4.1) ".center(60, "="))
        print("="*60)
        
        # 1. Ensure the raw synthetic file contains at least 1,000 samples per category
        # If it doesn't exist or is too small, trigger the factory to generate 1,000 per category
        trigger_generation = True
        if os.path.exists(self.raw_jsonl_path):
            with open(self.raw_jsonl_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                if len(lines) >= 6000:  # 6 categories * 1000 = 6000
                    trigger_generation = False
                    
        if trigger_generation:
            print("Raw synthetic dataset not found or too small. Generating 1,000 samples per category...")
            factory = SyntheticDataFactory(output_filepath=self.raw_jsonl_path)
            factory.generate_all(target_per_category=1000)

        # 2. Load and slice raw synthetic categories
        categorized_data = {
            "reasoning": [], "planning": [], "coding": [], 
            "memory": [], "tool_usage": [], "telugu": []
        }
        
        with open(self.raw_jsonl_path, 'r', encoding='utf-8') as f:
            for line in f:
                if not line.strip(): continue
                item = json.loads(line)
                cat = item.get("category")
                if cat in categorized_data:
                    categorized_data[cat].append(item)
                    
        print(f"Loaded category counts from raw file:")
        for cat, items in categorized_data.items():
            print(f"  - {cat}: {len(items)}")

        # 3. Format and slice categories into standard instruction/input/output structure
        sft_data = {cat: [] for cat in categorized_data.keys()}
        
        # Define limits according to Qwen-Kattappa distribution plan:
        # A: Teaching (Reasoning): 1000
        # B: Engineering (Coding): 1000
        # C: Memory: 500
        # D: Tool Usage: 500
        # E: Telugu: 1000
        # F: Planning: 1000
        limits = {
            "reasoning": 900,
            "planning": 900,
            "coding": 900,
            "memory": 600,
            "tool_usage": 600,
            "telugu": 1000
        }
        
        for cat, items in categorized_data.items():
            limit = limits[cat]
            sliced_items = items[:limit]
            for item in sliced_items:
                inst = item["question"]
                out = f"Thinking: {item['solution_outline']}\n\nAnswer: {item['answer']}"
                sft_data[cat].append({
                    "instruction": inst,
                    "input": "",
                    "output": out,
                    "category": cat,
                    "difficulty": item.get("difficulty", "medium"),
                    "language": item.get("language", "english")
                })
                
        # 4. Generate Replay and Refusal data
        print("Generating 600 general replay examples...")
        replay_samples = self.generate_replay_data(600)
        
        print("Generating 150 refusal calibration examples...")
        refusal_samples = self.generate_refusal_data(150)
        
        # 5. Build Splits (90% Train / 10% Validation)
        train_samples = []
        validation_splits = {cat: [] for cat in sft_data.keys()}
        validation_splits["general"] = []
        validation_splits["refusal"] = []
        
        # SFT Categories
        for cat, items in sft_data.items():
            random.seed(123)
            random.shuffle(items)
            val_size = max(1, int(len(items) * 0.1))
            val_items = items[:val_size]
            train_items = items[val_size:]
            
            validation_splits[cat].extend(val_items)
            train_samples.extend(train_items)
            
        # Replay
        random.shuffle(replay_samples)
        val_size = int(len(replay_samples) * 0.1)
        validation_splits["general"].extend(replay_samples[:val_size])
        train_samples.extend(replay_samples[val_size:])
        
        # Refusal
        random.shuffle(refusal_samples)
        val_size = int(len(refusal_samples) * 0.1)
        validation_splits["refusal"].extend(refusal_samples[:val_size])
        train_samples.extend(refusal_samples[val_size:])
        
        # Shuffle final training set to mix categories uniformly
        random.shuffle(train_samples)
        
        # 6. Save outputs to disk
        os.makedirs(self.output_dir, exist_ok=True)
        
        # Save training split
        train_path = os.path.join(self.output_dir, "train.jsonl")
        with open(train_path, 'w', encoding='utf-8') as f:
            for sample in train_samples:
                f.write(json.dumps(sample) + "\n")
                
        # Save per-category validation files
        for cat, items in validation_splits.items():
            val_path = os.path.join(self.output_dir, f"validation_{cat}.jsonl")
            with open(val_path, 'w', encoding='utf-8') as f:
                for sample in items:
                    f.write(json.dumps(sample) + "\n")
                    
        # Save combined test split (using a slice of validation/extra items)
        test_samples = []
        for cat, items in validation_splits.items():
            # Use half of validation for test checks
            test_samples.extend(items[:len(items)//2])
        test_path = os.path.join(self.output_dir, "test.jsonl")
        with open(test_path, 'w', encoding='utf-8') as f:
            for sample in test_samples:
                f.write(json.dumps(sample) + "\n")
                
        # 7. Generate Manifest metadata
        manifest = {
            "total_training_samples": len(train_samples),
            "total_test_samples": len(test_samples),
            "category_training_counts": {},
            "validation_split_counts": {},
            "language_counts": {},
            "difficulty_counts": {}
        }
        
        for sample in train_samples:
            cat = sample["category"]
            lang = sample["language"]
            diff = sample["difficulty"]
            manifest["category_training_counts"][cat] = manifest["category_training_counts"].get(cat, 0) + 1
            manifest["language_counts"][lang] = manifest["language_counts"].get(lang, 0) + 1
            manifest["difficulty_counts"][diff] = manifest["difficulty_counts"].get(diff, 0) + 1
            
        for cat, items in validation_splits.items():
            manifest["validation_split_counts"][cat] = len(items)
            
        manifest_path = os.path.join(self.output_dir, "dataset_manifest.json")
        with open(manifest_path, 'w', encoding='utf-8') as f:
            json.dump(manifest, f, indent=2)
            
        print("="*60)
        print(" SFT BUILDER COMPLETED SUCCESS ".center(60, "="))
        print("="*60)
        print(f"Train split saved to: {train_path} ({len(train_samples)} samples)")
        print(f"Manifest saved to: {manifest_path}")
        print(json.dumps(manifest, indent=2))
        
        return train_samples, validation_splits

if __name__ == "__main__":
    builder = DatasetBuilder()
    builder.build_sft_dataset()
