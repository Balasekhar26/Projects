import os
import json
import time
from typing import List, Dict, Any

class SemanticMemory:
    def __init__(self, filepath: str = None):
        self.filepath = filepath or os.path.abspath(os.path.join(
            os.path.dirname(__file__), "semantic.jsonl"
        ))
        self.facts = []
        self.load()

    def load(self):
        self.facts = []
        if os.path.exists(self.filepath):
            try:
                with open(self.filepath, 'r', encoding='utf-8') as f:
                    for line in f:
                        if line.strip():
                            self.facts.append(json.loads(line.strip()))
            except Exception as e:
                print(f"Error loading semantic memories: {e}")

    def save_all(self):
        try:
            with open(self.filepath, 'w', encoding='utf-8') as f:
                for fact in self.facts:
                    f.write(json.dumps(fact) + "\n")
        except Exception as e:
            print(f"Error saving semantic memories: {e}")

    def store_fact(self, subject: str, relation: str, fact: str, confidence: float = 1.0):
        """Stores or updates a generalized factual statement."""
        # Check if relation already exists for subject to update instead of duplicate
        for existing in self.facts:
            if existing["subject"].lower() == subject.lower() and existing["relation"].lower() == relation.lower():
                existing["fact"] = fact
                existing["confidence"] = confidence
                existing["timestamp"] = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime())
                existing["unix_time"] = int(time.time())
                self.save_all()
                return existing
                
        new_fact = {
            "subject": subject,
            "relation": relation,
            "fact": fact,
            "confidence": confidence,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime()),
            "unix_time": int(time.time())
        }
        self.facts.append(new_fact)
        
        try:
            os.makedirs(os.path.dirname(self.filepath), exist_ok=True)
            with open(self.filepath, 'a', encoding='utf-8') as f:
                f.write(json.dumps(new_fact) + "\n")
        except Exception as e:
            print(f"Error appending semantic memory: {e}")
            
        return new_fact

    def remove_fact(self, subject: str, relation: str) -> bool:
        """Forgets/purges a specific fact tuple."""
        initial_len = len(self.facts)
        self.facts = [f for f in self.facts if not (f["subject"].lower() == subject.lower() and f["relation"].lower() == relation.lower())]
        if len(self.facts) < initial_len:
            self.save_all()
            return True
        return False

    def get_all(self) -> List[Dict[str, Any]]:
        return self.facts
