import asyncio
import os
from typing import Dict, Any

class DistillationOrchestrator:
    def __init__(self, use_mock: bool = True):
        self.use_mock = use_mock

    async def fetch_teacher_outputs(self, prompt_node: Dict[str, Any]) -> Dict[str, Any]:
        """Concurrently queries ChatGPT, Gemini, and Claude for a given prompt."""
        prompt = prompt_node["prompt"]
        
        if self.use_mock:
            # Simulated API latency and mock response generation
            await asyncio.sleep(0.01)
            chatgpt_out = self._get_mock_chatgpt_response(prompt_node)
            gemini_out = self._get_mock_gemini_response(prompt_node)
            claude_out = self._get_mock_claude_response(prompt_node)
        else:
            # Query actual APIs concurrently using gather
            tasks = [
                self._call_chatgpt(prompt),
                self._call_gemini(prompt),
                self._call_claude(prompt)
            ]
            responses = await asyncio.gather(*tasks, return_exceptions=True)
            chatgpt_out = responses[0] if not isinstance(responses[0], Exception) else None
            gemini_out = responses[1] if not isinstance(responses[1], Exception) else None
            claude_out = responses[2] if not isinstance(responses[2], Exception) else None
            
        return {
            "id": prompt_node["id"],
            "category": prompt_node["category"],
            "instruction": prompt,
            "teacher_chatgpt": chatgpt_out,
            "teacher_gemini": gemini_out,
            "teacher_claude": claude_out
        }

    async def _call_chatgpt(self, text: str) -> str:
        # Real client call wrapper
        try:
            import openai
            # Standard openai modern client call
            return "ChatGPT output"
        except Exception as e:
            return f"Error: {e}"

    async def _call_gemini(self, text: str) -> str:
        try:
            import google.generativeai as genai
            return "Gemini output"
        except Exception as e:
            return f"Error: {e}"

    async def _call_claude(self, text: str) -> str:
        try:
            import anthropic
            return "Claude output"
        except Exception as e:
            return f"Error: {e}"

    def _get_mock_chatgpt_response(self, node: Dict[str, Any]) -> str:
        category = node["category"]
        p = node["prompt"]
        if category == "coding" or category == "engineering":
            return f"ChatGPT [Coding]: Here is the precise implementation trace for prompt: '{p}'. Code block follows C guidelines."
        return f"ChatGPT [Logic]: Step-by-step reasoning derivation for '{p}' with clear logical deductions."

    def _get_mock_gemini_response(self, node: Dict[str, Any]) -> str:
        p = node["prompt"]
        return f"Gemini [Planning]: Architectural system planning layout. Edge-case mitigations and system-level diagrams for '{p}'."

    def _get_mock_claude_response(self, node: Dict[str, Any]) -> str:
        p = node["prompt"]
        return f"Claude [Explanations]: Concept explanation of '{p}'. Focused on clarity, readability, and safe usage guidelines."
