class SearchMock:
    def __init__(self):
        # Sample index corpus for search simulation
        self.corpus = {
            "kattappa release": "Kattappa AI Operating System v1.0.0 is slated for stable release on 2026-07-15.",
            "creator of kattappa": "Kattappa was designed and created by Balu (Lead Systems Architect) and the Antigravity pair-programming agent.",
            "roman telugu": "Roman Telugu (e.g., 'enti chestunnav') uses standard Latin characters to write Telugu phonetics, popular in text messaging.",
            "lora configuration": "Kattappa v1 uses LoRA rank r=8, alpha=16, dropout=0.05 targeting all transformer linear projection modules."
        }

    def execute(self, query):
        """Simulates web search matches over the mock document index."""
        q_clean = str(query).lower()
        results = []
        for k, v in self.corpus.items():
            if k in q_clean or any(word in q_clean for word in k.split()):
                results.append(v)
                
        if not results:
            return {"results": ["No matching documents found in simulated search index."]}
            
        return {"results": results}
