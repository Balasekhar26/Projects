"""Planner Analytics Compiler (Program 28.0).

Aggregates execution spans to generate comprehensive statistics on token
consumption, tool latency profiles, and exception/failure distributions.
"""
from __future__ import annotations

from typing import Any, Dict, List
from backend.core.observability.telemetry import Span


class PlannerAnalytics:
    """Computes high-level aggregated operational metrics from trace span profiles."""

    @classmethod
    def compile(cls, spans: List[Span]) -> Dict[str, Any]:
        """Summarizes structural, monetary, performance, and failure profiles.

        Analyzes metadata tags for token usage, groups tool calls to compute
        latencies, and categorizes errors.
        """
        total_input_tokens = 0
        total_output_tokens = 0

        tool_metrics: Dict[str, Dict[str, Any]] = {}
        failures: Dict[str, int] = {}
        total_runs = 0
        successful_runs = 0

        for span in spans:
            # Aggregate token metrics from metadata parameters
            total_input_tokens += int(span.metadata.get("input_tokens", 0))
            total_output_tokens += int(span.metadata.get("output_tokens", 0))

            # Run success tracking (e.g. on higher level scheduler / planner spans)
            if "planner" in span.name.lower() or "agent" in span.name.lower() or "runtime" in span.name.lower():
                total_runs += 1
                if span.status == "success":
                    successful_runs += 1

            # Accumulate tool specific run-times
            is_tool = span.metadata.get("is_tool", False) or "tool" in span.name.lower()
            if is_tool:
                tool_name = span.metadata.get("tool", span.name)
                metrics = tool_metrics.setdefault(
                    tool_name,
                    {
                        "calls": 0,
                        "total_duration": 0.0,
                        "errors": 0,
                    },
                )
                metrics["calls"] += 1
                metrics["total_duration"] += span.duration
                if span.status == "error":
                    metrics["errors"] += 1

            # Categorize failure occurrences
            if span.status == "error":
                exc = span.metadata.get("exception_type", "UnknownError")
                failures[exc] = failures.get(exc, 0) + 1

        # Calculate averages for tool latencies
        processed_tools: Dict[str, Dict[str, Any]] = {}
        for tool_name, data in tool_metrics.items():
            calls = data["calls"]
            processed_tools[tool_name] = {
                "calls": calls,
                "avg_latency_ms": round((data["total_duration"] / calls) * 1000.0, 2) if calls > 0 else 0.0,
                "error_rate": round(data["errors"] / calls, 4) if calls > 0 else 0.0,
            }

        success_rate = successful_runs / total_runs if total_runs > 0 else 1.0

        return {
            "tokens": {
                "input": total_input_tokens,
                "output": total_output_tokens,
                "total": total_input_tokens + total_output_tokens,
            },
            "performance": {
                "total_runs": total_runs,
                "success_rate": round(success_rate, 4),
            },
            "tools": processed_tools,
            "failures": failures,
        }
