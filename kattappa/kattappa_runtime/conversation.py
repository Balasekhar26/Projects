import uuid

class ConversationState:
    def __init__(self, session_id=None, max_tokens=2048):
        self.session_id = session_id or str(uuid.uuid4())
        self.messages = []
        self.max_tokens = max_tokens

    def add_message(self, role, content):
        """Appends a new turn to the message store."""
        self.messages.append({
            "role": role,
            "content": content
        })

    def get_recent(self, max_turns=10):
        """Returns the last N turns of the chat history."""
        return self.messages[-max_turns:]

    def estimate_tokens(self, tokenizer=None):
        """Calculates token counts, falling back to a word heuristic (1.3 tokens/word)."""
        if tokenizer is not None:
            try:
                full_text = "".join([m["content"] for m in self.messages])
                return len(tokenizer.encode(full_text))
            except Exception:
                pass
                
        # Heuristic count
        words = sum(len(m["content"].split()) for m in self.messages)
        return int(words * 1.3)

    def prune_history(self, tokenizer=None):
        """Removes older turns from history until under the max token threshold."""
        while len(self.messages) > 2 and self.estimate_tokens(tokenizer) > self.max_tokens:
            # Drop the oldest user-assistant turn pair (indices 0 and 1)
            # Make sure we don't drop the system prompt if stored here (system is in prompt_builder, not messages)
            self.messages.pop(0)

    def clear(self):
        """Resets conversation state."""
        self.messages = []
