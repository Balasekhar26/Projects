class DialogueManager:
    def __init__(self):
        self.context = {}

    def process_input(self, text: str) -> str:
        """Processes transcribed audio text and returns dialogue responses."""
        text_clean = text.lower().strip()
        if "hello" in text_clean:
            return "నమస్కారం, నేను కట్టప్పను. మీకు ఎలా సహాయపడగలను?" # Telugu: "Hello, I am Kattappa. How can I help you?"
        elif "status" in text_clean:
            return "వ్యవస్థ అంతా బాగుంది." # Telugu: "The system is fine."
        else:
            return "సరే, నేను గ్రహించాను." # Telugu: "Okay, I understand."
