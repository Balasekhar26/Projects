import os
import json
import time
from typing import List, Dict, Any

class EpisodicMemory:
    def __init__(self, filepath: str = None):
        self.filepath = filepath or os.path.abspath(os.path.join(
            os.path.dirname(__file__), "episodic.jsonl"
        ))
        self.episodes = []
        self.load()

    def load(self):
        self.episodes = []
        if os.path.exists(self.filepath):
            try:
                with open(self.filepath, 'r', encoding='utf-8') as f:
                    for line in f:
                        if line.strip():
                            self.episodes.append(json.loads(line.strip()))
            except Exception as e:
                print(f"Error loading episodic memories: {e}")

    def save_all(self):
        try:
            with open(self.filepath, 'w', encoding='utf-8') as f:
                for ep in self.episodes:
                    f.write(json.dumps(ep) + "\n")
        except Exception as e:
            print(f"Error saving episodic memories: {e}")

    def add_episode(self, event: str, importance: float = 0.5, confidence: float = 1.0):
        """Appends a new chronological experience to the persistent logs."""
        episode = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime()),
            "unix_time": int(time.time()),
            "event": event,
            "importance": importance,
            "confidence": confidence
        }
        self.episodes.append(episode)
        
        # Append-only write for performance
        try:
            os.makedirs(os.path.dirname(self.filepath), exist_ok=True)
            with open(self.filepath, 'a', encoding='utf-8') as f:
                f.write(json.dumps(episode) + "\n")
        except Exception as e:
            print(f"Error appending episodic memory: {e}")
        
        return episode

    def get_all(self) -> List[Dict[str, Any]]:
        return self.episodes
