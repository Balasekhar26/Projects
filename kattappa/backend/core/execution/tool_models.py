"""Tool Definition and Execution Result Data Models (Program 11).

Standardizes schema parameters for tools execution.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional



@dataclass
class ToolDefinition:
    """Canonical model describing tool constraints and required validations."""
    name: str
    version: str
    description: str
    input_schema: Dict[str, Any] = field(default_factory=dict)
    output_schema: Dict[str, Any] = field(default_factory=dict)
    required_permissions: List[str] = field(default_factory=list)
    timeout: float = 10.0  # seconds
    retries: int = 2
    capabilities: List[str] = field(default_factory=list)
    # The actual executable python logic hook
    func: Callable[..., Any] = field(default=lambda **kwargs: {})


@dataclass
class ToolResult:
    """Canonical model for tool execution outputs."""
    tool_name: str
    status: str  # "ok" or "failed"
    data: Any = None
    error: Optional[str] = None
    execution_time: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)
