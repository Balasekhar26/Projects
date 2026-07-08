"""Human-In-The-Loop Approval Pipeline (Program 11.5).

Locks dangerous/destructive tool invocations until manual confirmation is received.
"""
from __future__ import annotations

import logging
import uuid
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class HumanApprovalPipeline:
    """Manages pending requests and manual confirmation overrides."""

    _instance: Optional[HumanApprovalPipeline] = None

    def __init__(self) -> None:
        # Maps request_id -> status ("pending", "approved", "rejected")
        self.requests: Dict[str, str] = {}

    @classmethod
    def get_instance(cls) -> HumanApprovalPipeline:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def create_request(self) -> str:
        """Registers a new pending approval lock, returning a unique request ID."""
        req_id = f"req_{uuid.uuid4().hex[:6]}"
        self.requests[req_id] = "pending"
        logger.info("Created human approval lock request: %s", req_id)
        return req_id

    def approve(self, request_id: str) -> None:
        if request_id in self.requests:
            self.requests[request_id] = "approved"
            logger.info("Human approval granted for request: %s", request_id)

    def reject(self, request_id: str) -> None:
        if request_id in self.requests:
            self.requests[request_id] = "rejected"
            logger.info("Human approval rejected for request: %s", request_id)

    def get_status(self, request_id: str) -> Optional[str]:
        return self.requests.get(request_id)
