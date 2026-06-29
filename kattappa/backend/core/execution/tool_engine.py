"""Master Tool Execution Engine Coordinator (Program 11).

Orchestrates capability matchings, permission verifications, isolated sandbox runs,
timeout interrupts, retry backoffs, output validators, and audit logs.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

from backend.core.execution.tool_models import ToolDefinition, ToolResult
from backend.core.execution.registry import ToolRegistry
from backend.core.execution.capability_matcher import ToolCapabilityMatcher
from backend.core.execution.dispatcher import ToolDispatcher
from backend.core.execution.executor import ToolExecutor
from backend.core.execution.validator import ToolResultValidator
from backend.core.execution.permissions import PermissionManager
from backend.core.execution.sandbox import SandboxEnvironment
from backend.core.execution.audit import AuditLogger
from backend.core.execution.circuit_breaker import ToolCircuitBreaker
from backend.core.execution.approval import HumanApprovalPipeline
from backend.core.execution.cancellation import CancellationToken


logger = logging.getLogger(__name__)


class ToolEngine:
    """Master controller managing the Kattappa execution and tool platform pipeline."""

    _instance: Optional[ToolEngine] = None

    def __init__(self) -> None:
        self.registry = ToolRegistry.get_instance()
        self.matcher = ToolCapabilityMatcher(self.registry)
        self.permissions = PermissionManager.get_instance()
        self.sandbox = SandboxEnvironment()
        self.audit = AuditLogger.get_instance()
        self.circuit_breaker = ToolCircuitBreaker.get_instance()
        self.approval = HumanApprovalPipeline.get_instance()

        
        self.executor = ToolExecutor(self.registry, self.permissions)
        self.dispatcher = ToolDispatcher(self.executor)

    @classmethod
    def get_instance(cls) -> ToolEngine:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def execute(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        cancellation_token: Optional[CancellationToken] = None,
    ) -> ToolResult:
        """Runs the tool validation and invocation pipeline inside the sandbox environment."""
        start_time = time.time()

        # 0. Check cancellation token
        if cancellation_token and cancellation_token.is_cancelled():
            res = ToolResult(
                tool_name=tool_name,
                status="failed",
                error="Task execution aborted by cancellation token.",
            )
            self.audit.log_result(res, arguments)
            return res

        # 0.5 Check Circuit Breaker availability
        if not self.circuit_breaker.is_available(tool_name):
            res = ToolResult(
                tool_name=tool_name,
                status="failed",
                error="Circuit breaker is OPEN. Executions temporarily disabled.",
            )
            self.audit.log_result(res, arguments)
            return res
        
        # 1. Fetch tool definition
        tool = self.registry.get_tool(tool_name)
        if not tool:
            res = ToolResult(
                tool_name=tool_name,
                status="failed",
                error=f"Tool '{tool_name}' not registered.",
            )
            self.audit.log_result(res, arguments)
            return res

        # 1.5 Check Human Approval gate
        if "require_approval" in tool.required_permissions:
            req_id = arguments.get("request_id")
            if not req_id:
                # Trigger pending approval request lock
                new_id = self.approval.create_request()
                res = ToolResult(
                    tool_name=tool_name,
                    status="failed",
                    error=f"Pending human approval confirmation. Request ID: {new_id}",
                    metadata={"request_id": new_id, "requires_approval": True},
                )
                self.audit.log_result(res, arguments)
                return res
            else:
                status = self.approval.get_status(req_id)
                if status == "pending":
                    res = ToolResult(
                        tool_name=tool_name,
                        status="failed",
                        error=f"Pending human approval confirmation. Request ID: {req_id}",
                        metadata={"request_id": req_id, "requires_approval": True},
                    )
                    self.audit.log_result(res, arguments)
                    return res
                elif status == "rejected":
                    res = ToolResult(
                        tool_name=tool_name,
                        status="failed",
                        error=f"Human approval rejected for request: {req_id}",
                        metadata={"request_id": req_id, "requires_approval": True},
                    )
                    self.audit.log_result(res, arguments)
                    return res
                # If approved, proceed!

        # 2. Verify permissions
        if not self.permissions.verify_permissions(tool):
            res = ToolResult(
                tool_name=tool_name,
                status="failed",
                error=f"Authorization preflight check failed. Permission denied for: {tool.name}",
            )
            self.audit.log_result(res, arguments)
            return res

        # 3. Validate input schema conformance before execution
        if tool.input_schema:
            is_input_valid = ToolResultValidator.validate(arguments, tool.input_schema)
            if not is_input_valid:
                res = ToolResult(
                    tool_name=tool_name,
                    status="failed",
                    error="Arguments failed input schema validation rules.",
                )
                self.audit.log_result(res, arguments)
                return res

        # 4. Run execution inside isolated SandboxEnvironment wrapper
        try:
            # Invokes executor logic inside sandbox bounds
            raw_res = self.sandbox.run_isolated(
                self.executor.execute_tool,
                name=tool_name,
                args=arguments,
            )
            
            # 5. Validate output schema conformance
            if raw_res.status == "ok" and tool.output_schema:
                is_valid = ToolResultValidator.validate(raw_res.data, tool.output_schema)
                if not is_valid:
                    raw_res.status = "failed"
                    raw_res.error = "Result failed output schema validation rules."
                    raw_res.data = None

            raw_res.execution_time = time.time() - start_time
            
            # Record circuit outcomes
            if raw_res.status == "ok":
                self.circuit_breaker.record_success(tool_name)
            else:
                self.circuit_breaker.record_failure(tool_name)

            self.audit.log_result(raw_res, arguments)
            return raw_res



        except Exception as exc:
            self.circuit_breaker.record_failure(tool_name)
            res = ToolResult(
                tool_name=tool_name,
                status="failed",
                error=str(exc),
                execution_time=time.time() - start_time,
            )
            self.audit.log_result(res, arguments)
            return res
