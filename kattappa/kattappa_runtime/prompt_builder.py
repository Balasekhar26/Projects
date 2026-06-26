class PromptBuilder:
    def __init__(self, default_system="You are Kattappa, a powerful AI Operating System. You are helpful, precise, and adhere to strict safety guidelines."):
        self.default_system = default_system

    def build_prompt(self, system_rules=None, memory_context=None, conversation_history=None, user_message=""):
        """Compiles prompt parts into standard Qwen-Instruct chat templates."""
        system_content = system_rules or self.default_system
        
        # Inject memory context if present
        if memory_context:
            system_content += f"\n\n[Persistent Memory Context]\n{memory_context}"
            
        prompt = ""
        # 1. System instruction block
        prompt += f"<|im_start|>system\n{system_content}<|im_end|>\n"
        
        # 2. Conversation turns
        if conversation_history:
            for turn in conversation_history:
                role = turn.get("role", "user")
                content = turn.get("content", "")
                prompt += f"<|im_start|>{role}\n{content}<|im_end|>\n"
                
        # 3. Current active user prompt
        prompt += f"<|im_start|>user\n{user_message}<|im_end|>\n"
        
        # 4. Assistant start token to initiate generation
        prompt += "<|im_start|>assistant\n"
        return prompt
