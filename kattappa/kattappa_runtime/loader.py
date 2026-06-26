import os
import time
import random
from enum import Enum

class Mode(Enum):
    BASE = "base"
    LORA = "lora"
    MOCK = "mock"

class ModelLoader:
    def __init__(self, mode="mock", model_id="Qwen/Qwen2.5-1.5B-Instruct", adapter_path="kattappa-lora-v1"):
        self.mode = Mode(mode)
        self.model_id = model_id
        self.adapter_path = adapter_path
        self.model = None
        self.tokenizer = None
        self.device = "cpu"

    def load_model(self):
        """Loads model and tokenizer based on configured mode."""
        print(f"Loading Kattappa model in [{self.mode.value.upper()}] mode...")
        
        if self.mode == Mode.MOCK:
            print("Model loader running in simulated fallback (Mock Mode).")
            return self

        try:
            import torch
            import transformers
            from transformers import AutoTokenizer, AutoModelForCausalLM
            
            self.device = "cuda" if torch.cuda.is_available() else ("mps" if torch.backends.mps.is_available() else "cpu")
            print(f"Using execution device: {self.device}")
            
            self.tokenizer = AutoTokenizer.from_pretrained(self.model_id)
            
            # Load Base Model
            self.model = AutoModelForCausalLM.from_pretrained(
                self.model_id,
                torch_dtype=torch.float16 if self.device == "cuda" else torch.float32,
                device_map="auto" if self.device == "cuda" else None
            )
            
            if self.mode == Mode.LORA:
                if os.path.exists(self.adapter_path):
                    from peft import PeftModel
                    print(f"Merging LoRA adapter weights from: {self.adapter_path}")
                    self.model = PeftModel.from_pretrained(self.model, self.adapter_path)
                else:
                    print(f"Warning: Adapter path '{self.adapter_path}' not found. Falling back to BASE.")
                    
        except ImportError:
            print("Warning: Transformers/Torch not installed. Falling back to MOCK mode.")
            self.mode = Mode.MOCK
            
        return self

    def generate_stream(self, prompt, max_new_tokens=256):
        """Yields character/word tokens in a streaming generator loop."""
        if self.mode == Mode.MOCK:
            yield from self._generate_mock_stream(prompt)
            return

        # Real causal model streaming using TextIteratorStreamer
        try:
            import torch
            from transformers import TextIteratorStreamer
            from threading import Thread
            
            inputs = self.tokenizer(prompt, return_tensors="pt").to(self.device)
            streamer = TextIteratorStreamer(self.tokenizer, skip_prompt=True, skip_special_tokens=True)
            
            generation_kwargs = dict(
                inputs=inputs.input_ids,
                attention_mask=inputs.attention_mask,
                streamer=streamer,
                max_new_tokens=max_new_tokens,
                pad_token_id=self.tokenizer.eos_token_id
            )
            
            thread = Thread(target=self.model.generate, kwargs=generation_kwargs)
            thread.start()
            
            for new_text in streamer:
                yield new_text
        except Exception as e:
            yield f"\n[Generation Error: {e}]"

    def _generate_mock_stream(self, prompt):
        """Generates dynamic mock responses to test CLI/routing loops without weights."""
        content = prompt.lower()
        
        # Rule 1: Tool invocation matching
        if "calculate" in content or "compute" in content or "math" in content or "expression" in content:
            # Check if there is an equation/math string in prompt
            import re
            math_match = re.search(r"(\d+[\s\+\-\*\/]+\d+)", content)
            expr = math_match.group(1) if math_match else "25*4"
            response = f'Thinking: Initiating tool call to compute equation.\n\n```json\n{{\n  "tool": "calculator",\n  "arguments": {{\n    "expression": "{expr}"\n  }}\n}}\n```'
        elif "time" in content or "clock" in content or "date" in content:
            response = 'Thinking: Clock query detected.\n\n```json\n{\n  "tool": "clock",\n  "arguments": {}\n}\n```'
        elif "search" in content or "lookup" in content or "google" in content:
            response = 'Thinking: External query detected.\n\n```json\n{\n  "tool": "search_mock",\n  "arguments": {\n    "query": "Kattappa OS Release Date"\n  }\n}\n```'
        # Rule 2: Memory update or recall matching
        elif "my name is" in content:
            # Extract name
            words = prompt.split()
            name = words[-1].strip(".!?") if words else "Balu"
            response = f"Thinking: Storing user name in persistent memory.\n\nAnswer: Hello {name}! I have stored your name in memory."
        elif "who am i" in content or "my name" in content:
            response = "Thinking: Querying memory for user profile.\n\nAnswer: You are Balu, the lead creator of Kattappa."
        elif "telugu" in content or "cheppu" in content or "enti" in content:
            response = "Thinking: Directing response in Roman Telugu code-switch.\n\nAnswer: Cheppandi Balu garu! Menu ready ga unnanu. Enti sangati?"
        else:
            # Default response
            response = "Thinking: Standard conversational prompt response.\n\nAnswer: Hello! I am Kattappa, your AI Operating System. How can I assist you today?"

        # Stream words with slight delay to mimic natural streaming
        for word in response.split(" "):
            yield word + " "
            time.sleep(0.015)
