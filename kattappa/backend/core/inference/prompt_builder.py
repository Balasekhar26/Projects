"""Context and Prompt Builder (Program 10).

Aggregates system context variables, policies, and prompts into unified formats.
"""
from __future__ import annotations

from typing import Dict, List, Optional


class PromptBuilder:
    """Compiles clean, provider-agnostic prompt templates."""

    @staticmethod
    def compile_prompt(
        system_instruction: str,
        user_query: str,
        policies: Optional[List[str]] = None,
    ) -> str:
        """Combines rules, developer instructions, and variables into a single text payload."""
        sections = []
        
        if system_instruction:
            sections.append(f"System: {system_instruction}")

        if policies:
            sections.append("Policies:\n" + "\n".join(f"- {p}" for p in policies))

        sections.append(f"User: {user_query}")
        
        return "\n\n".join(sections)
