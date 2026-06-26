from typing import Dict, Any, List

class TeluguDistillGenerator:
    def __init__(self):
        # Base seed prompt templates representing the 3 tracks
        self.seeds = {
            "pure": [
                "కంప్యూటర్ నెట్‌వర్క్ అంటే ఏమిటి?",
                "UART ప్రోటోకాల్ పనితీరును వివరించండి.",
                "మెమరీ లీక్‌ను ఎలా గుర్తించాలి?",
                "సాఫ్ట్‌వేర్ డిజైన్ పద్ధతులు ఏమిటి?"
            ],
            "roman": [
                "computer network ante enti?",
                "UART protocol panitirenu vivarinchandi.",
                "memory leak ni ela gurtinchali?",
                "software design paddhatulu emiti?"
            ],
            "hybrid": [
                "Explain computer networks in Telugu language please.",
                "UART protocol working mechanism explain cheyyi clear ga.",
                "Software design patterns and architecture templates gurinchi cheppu.",
                "Memory leak debug cheyyడానికి safe practices and commands emiti?"
            ]
        }

    def generate_prompts(self, count_per_track: int = 10) -> List[Dict[str, Any]]:
        """Assembles prompt nodes across Track A, B, and C to fuel distillation runs."""
        nodes = []
        idx = 1
        
        # 1. Track A: Pure Telugu Script
        for i in range(count_per_track):
            seed = self.seeds["pure"][i % len(self.seeds["pure"])]
            nodes.append({
                "id": f"distill_te_pure_{idx}",
                "category": "telugu",
                "track": "pure_telugu",
                "prompt": f"{seed} Answer entirely in native Telugu script."
            })
            idx += 1
            
        # 2. Track B: Roman Telugu Script
        for i in range(count_per_track):
            seed = self.seeds["roman"][i % len(self.seeds["roman"])]
            nodes.append({
                "id": f"distill_te_roman_{idx}",
                "category": "telugu",
                "track": "roman_telugu",
                "prompt": f"{seed} Respond using Roman Telugu transliteration only."
            })
            idx += 1
            
        # 3. Track C: Hybrid (Code-Switching)
        for i in range(count_per_track):
            seed = self.seeds["hybrid"][i % len(self.seeds["hybrid"])]
            nodes.append({
                "id": f"distill_te_hybrid_{idx}",
                "category": "telugu",
                "track": "hybrid_telugu",
                "prompt": f"{seed} Write using natural Telugu-English hybrid code-switching."
            })
            idx += 1
            
        return nodes
