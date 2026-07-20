"""Cognitive Kernel — Phase 5A / K18.5.

Acts as the central coordination substrate for Kattappa, managing the lifecycles,
health states, dependency injection, and hot-swapping of all major cognitive systems
while decoupling their direct cross-module communications via abstract buses.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Dict, List, Optional, Callable, Set

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Service Lifecycle Enums & Base Class
# ---------------------------------------------------------------------------

class ServiceStatus:
    INACTIVE = "inactive"
    INITIALIZING = "initializing"
    ACTIVE = "active"
    DEGRADED = "degraded"
    FAILED = "failed"
    SHUTTING_DOWN = "shutting_down"


class CognitiveService:
    """Base class for all cognitive subsystems managed by the CognitiveKernel."""

    def __init__(self, name: str, dependencies: Optional[List[str]] = None) -> None:
        self._name = name
        self._dependencies = dependencies or []
        self._status = ServiceStatus.INACTIVE
        self._error: Optional[str] = None
        self._kernel: Optional[CognitiveKernel] = None
        self._last_health_check_time: float = 0.0

    @property
    def name(self) -> str:
        return self._name

    @property
    def dependencies(self) -> List[str]:
        return self._dependencies

    @property
    def status(self) -> str:
        return self._status

    @property
    def error(self) -> Optional[str]:
        return self._error

    @property
    def kernel(self) -> CognitiveKernel:
        if self._kernel is None:
            raise RuntimeError(f"Service {self._name!r} has not been registered with a kernel.")
        return self._kernel

    def set_status(self, status: str, error: Optional[str] = None) -> None:
        self._status = status
        self._error = error

    def set_kernel(self, kernel: CognitiveKernel) -> None:
        self._kernel = kernel

    def initialize(self) -> None:
        """Lifecycle hook called during kernel start or registration."""
        self.set_status(ServiceStatus.ACTIVE)

    def shutdown(self) -> None:
        """Lifecycle hook called during kernel shutdown or deregistration."""
        self.set_status(ServiceStatus.INACTIVE)

    def health_check(self) -> Dict[str, Any]:
        """Runs diagnostics on the service to evaluate current health status."""
        self._last_health_check_time = time.time()
        return {
            "status": self._status,
            "error": self._error,
            "healthy": self._status in (ServiceStatus.ACTIVE, ServiceStatus.INACTIVE),
            "timestamp": self._last_health_check_time
        }


# ---------------------------------------------------------------------------
# Default Subsystem Services
# ---------------------------------------------------------------------------

class MemoryService(CognitiveService):
    """Bridges calls to the unified memory bus."""

    def __init__(self) -> None:
        super().__init__("memory")

    def read(
        self,
        query: str,
        memory_types: Optional[List[str]] = None,
        session_id: Optional[str] = None,
        limit: int = 10,
    ) -> List[Any]:
        from backend.core.cognitive_memory_bus import MEMORY_BUS
        return MEMORY_BUS.read(
            query, memory_types=memory_types, session_id=session_id, limit=limit
        )

    def write(
        self,
        memory_type: str,
        data: Dict[str, Any],
        confidence: float = 1.0,
        verified: bool = False,
    ) -> Any:
        from backend.core.cognitive_memory_bus import MEMORY_BUS
        return MEMORY_BUS.write(
            memory_type, data, confidence=confidence, verified=verified
        )


class GoalService(CognitiveService):
    """Bridges calls to the goal hierarchy and task store."""

    def __init__(self) -> None:
        super().__init__("goals")

    def add_goal(
        self,
        node_id: str,
        parent_id: Optional[str],
        level: Any,
        title: str,
        description: Optional[str] = None,
        status: str = "PROPOSED",
        progress: float = 0.0,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        from backend.core.goal_hierarchy import GoalHierarchy
        node = GoalHierarchy.add_node(
            node_id=node_id,
            parent_id=parent_id,
            level=level,
            title=title,
            description=description,
            status=status,
            progress=progress,
            metadata=metadata,
        )
        return node.id

    def update_status(
        self, node_id: str, status: str, progress: Optional[float] = None
    ) -> bool:
        from backend.core.goal_hierarchy import GoalHierarchy
        db = GoalHierarchy()
        return db.update_node(node_id, status=status, progress=progress)

    def get_progress(self, node_id: str) -> float:
        from backend.core.goal_hierarchy import GoalHierarchy
        node = GoalHierarchy.get_node(node_id)
        if node:
            return node.progress
        return 0.0


class EventService(CognitiveService):
    """Bridges event publishing/subscribing to the Blackboard structure."""

    def __init__(self) -> None:
        super().__init__("events")

    def publish(
        self,
        publisher: str,
        topic: str,
        payload: Dict[str, Any],
        confidence: float = 1.0,
    ) -> str:
        from backend.core.blackboard import BLACKBOARD
        post = BLACKBOARD.publish(publisher, topic, payload, confidence=confidence)
        return post.post_id

    def subscribe(self, topic: str, callback: Callable[[Dict[str, Any]], None]) -> None:
        from backend.core.blackboard import BLACKBOARD
        BLACKBOARD.subscribe(topic, lambda post: callback(post.to_dict()))


class ContextService(CognitiveService):
    """Assembles rich context packages for execution loops."""

    def __init__(self) -> None:
        super().__init__("context", dependencies=["memory"])

    def build_context(self, session_id: str, query: str) -> Dict[str, Any]:
        from backend.core.context_manager import ContextManager
        return ContextManager.build_execution_context(session_id, query)


class ToolService(CognitiveService):
    """Manages executing external tools and tracking their success/reliability."""

    def __init__(self) -> None:
        super().__init__("tools")

    def execute(self, tool_name: str, args: Dict[str, Any]) -> Any:
        from backend.core.tool_reliability import ToolReliabilityTracker

        success = True
        error_msg = None
        latency = 0.05
        try:
            if tool_name == "calculator":
                val = eval(str(args.get("expr", "0")))
                return {"result": val}
            return {"result": f"Executed tool {tool_name} successfully"}
        except Exception as e:
            success = False
            error_msg = str(e)
            raise e
        finally:
            try:
                ToolReliabilityTracker.record_invocation(
                    tool_name, success, latency, error_msg
                )
            except Exception:
                pass


class AgentService(CognitiveService):
    """Maintains definitions and routing paths for specialized agent nodes."""

    def __init__(self) -> None:
        super().__init__("agents", dependencies=["goals", "events"])

    def get_agent(self, agent_name: str) -> Any:
        from backend.core.orchestrator.registry import ORCHESTRATOR_REGISTRY
        return ORCHESTRATOR_REGISTRY.get(agent_name)

    def schedule_task(self, task: Any, context: Any) -> Any:
        from backend.core.orchestrator.scheduler import TaskScheduler
        scheduler = TaskScheduler()
        return scheduler._execute_task(task, "direct-kernel-task", context)


class ExecutiveControllerService(CognitiveService):
    """Submits top-level cognitive loop tasks to the executive controller."""

    def __init__(self) -> None:
        super().__init__("executive", dependencies=["memory", "goals", "events"])

    @property
    def controller(self) -> Any:
        from backend.core.cos.executive_controller import CONTROLLER
        return CONTROLLER


class LedgerService(CognitiveService):
    """Coordinates audits and writes to structural SQLite ledger tables."""

    def __init__(self) -> None:
        super().__init__("ledger")
        self._store: Optional[Any] = None

    def initialize(self) -> None:
        from backend.core.config import load_config
        from backend.core.ledger.stores.sqlite_store import SQLiteLedgerStore
        from backend.core.governance.identity_registry import bootstrap_default_principals

        config = load_config()
        config.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        db_path = config.sqlite_path.parent / "ledger.db"

        self._store = SQLiteLedgerStore(str(db_path))
        bootstrap_default_principals(self._store)
        self.set_status(ServiceStatus.ACTIVE)

    def shutdown(self) -> None:
        self._store = None
        self.set_status(ServiceStatus.INACTIVE)

    @property
    def store(self) -> Any:
        if self._store is None:
            raise RuntimeError("Ledger store is not initialized.")
        return self._store

    @store.setter
    def store(self, value: Any) -> None:
        self._store = value


# ---------------------------------------------------------------------------
# Decoupled Bus Implementations (Delegating to registered Services)
# ---------------------------------------------------------------------------

class MemoryBus:
    def __init__(self, kernel: CognitiveKernel) -> None:
        self._kernel = kernel

    def read(
        self,
        query: str,
        memory_types: Optional[List[str]] = None,
        session_id: Optional[str] = None,
        limit: int = 10,
    ) -> List[Any]:
        service: MemoryService = self._kernel.get_service("memory")
        return service.read(query, memory_types, session_id, limit)

    def write(
        self,
        memory_type: str,
        data: Dict[str, Any],
        confidence: float = 1.0,
        verified: bool = False,
    ) -> Any:
        service: MemoryService = self._kernel.get_service("memory")
        return service.write(memory_type, data, confidence, verified)


class GoalBus:
    def __init__(self, kernel: CognitiveKernel) -> None:
        self._kernel = kernel

    def add_goal(
        self,
        node_id: str,
        parent_id: Optional[str],
        level: Any,
        title: str,
        description: Optional[str] = None,
        status: str = "PROPOSED",
        progress: float = 0.0,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        service: GoalService = self._kernel.get_service("goals")
        return service.add_goal(
            node_id, parent_id, level, title, description, status, progress, metadata
        )

    def update_status(
        self, node_id: str, status: str, progress: Optional[float] = None
    ) -> bool:
        service: GoalService = self._kernel.get_service("goals")
        return service.update_status(node_id, status, progress)

    def get_progress(self, node_id: str) -> float:
        service: GoalService = self._kernel.get_service("goals")
        return service.get_progress(node_id)


class EventBus:
    def __init__(self, kernel: CognitiveKernel) -> None:
        self._kernel = kernel

    def publish(
        self,
        publisher: str,
        topic: str,
        payload: Dict[str, Any],
        confidence: float = 1.0,
    ) -> str:
        service: EventService = self._kernel.get_service("events")
        return service.publish(publisher, topic, payload, confidence=confidence)

    def subscribe(self, topic: str, callback: Callable[[Dict[str, Any]], None]) -> None:
        service: EventService = self._kernel.get_service("events")
        service.subscribe(topic, callback)


class ContextBus:
    def __init__(self, kernel: CognitiveKernel) -> None:
        self._kernel = kernel

    def build_context(self, session_id: str, query: str) -> Dict[str, Any]:
        service: ContextService = self._kernel.get_service("context")
        return service.build_context(session_id, query)


class ToolBus:
    def __init__(self, kernel: CognitiveKernel) -> None:
        self._kernel = kernel

    def execute(self, tool_name: str, args: Dict[str, Any]) -> Any:
        service: ToolService = self._kernel.get_service("tools")
        return service.execute(tool_name, args)


class AgentBus:
    def __init__(self, kernel: CognitiveKernel) -> None:
        self._kernel = kernel

    def get_agent(self, agent_name: str) -> Any:
        service: AgentService = self._kernel.get_service("agents")
        return service.get_agent(agent_name)

    def schedule_task(self, task: Any, context: Any) -> Any:
        service: AgentService = self._kernel.get_service("agents")
        return service.schedule_task(task, context)


# ---------------------------------------------------------------------------
# CognitiveKernel Coordinator
# ---------------------------------------------------------------------------

class CognitiveKernel:
    """The central Microkernel coordinating lifecycles and communications of Kattappa."""

    _instance: Optional[CognitiveKernel] = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs) -> CognitiveKernel:
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
            return cls._instance

    def __init__(self) -> None:
        if hasattr(self, "_initialized"):
            return

        self._services: Dict[str, CognitiveService] = {}
        self._services_lock = threading.RLock()
        self._is_running = False

        # Expose standard buses
        self.memory = MemoryBus(self)
        self.goals = GoalBus(self)
        self.events = EventBus(self)
        self.context = ContextBus(self)
        self.tools = ToolBus(self)
        self.agents = AgentBus(self)

        # Register default subsystems
        self.register_service(MemoryService())
        self.register_service(GoalService())
        self.register_service(EventService())
        self.register_service(ContextService())
        self.register_service(ToolService())
        self.register_service(AgentService())
        self.register_service(ExecutiveControllerService())
        self.register_service(LedgerService())
        from backend.core.meta_executive import MetaExecutiveService
        self.register_service(MetaExecutiveService())
        from backend.core.simulation_engine import SimulationService
        self.register_service(SimulationService())

        # Automatically start default services
        self.initialize_all()

        self._initialized = True

    # ── Service Discovery & Registration ───────────────────────────────────

    def register_service(self, service: CognitiveService) -> None:
        """Register a service with the microkernel, injecting a kernel reference."""
        with self._services_lock:
            if service.name in self._services:
                raise ValueError(f"Service {service.name!r} is already registered. Use hot_swap_service to replace.")
            service.set_kernel(self)
            self._services[service.name] = service
            logger.info(f"Registered service: {service.name!r}")
            # If the kernel is already running, immediately initialize the late registration
            if self._is_running:
                try:
                    service.initialize()
                except Exception as e:
                    service.set_status(ServiceStatus.FAILED, str(e))
                    logger.error(f"Failed to initialize late-registered service {service.name!r}: {e}")

    def deregister_service(self, name: str) -> Optional[CognitiveService]:
        """Stop and remove a service from the kernel registry."""
        with self._services_lock:
            service = self._services.pop(name, None)
            if service:
                try:
                    service.shutdown()
                except Exception as e:
                    logger.error(f"Error during deregistration shutdown of service {name!r}: {e}")
                logger.info(f"Deregistered service: {name!r}")
                return service
            return None

    def get_service(self, name: str) -> Any:
        """Retrieve a registered service instance by name."""
        with self._services_lock:
            service = self._services.get(name)
            if not service:
                raise RuntimeError(f"Service {name!r} not registered with CognitiveKernel.")
            return service

    def hot_swap_service(self, name: str, new_service: CognitiveService) -> None:
        """Replace a running service with a new instance, executing safe transition lifecycle."""
        if new_service.name != name:
            raise ValueError(f"New service name {new_service.name!r} must match swap target name {name!r}")

        with self._services_lock:
            logger.info(f"Hot-swapping service: {name!r}")
            old_service = self.deregister_service(name)
            try:
                self.register_service(new_service)
            except Exception as e:
                # Rollback to old service if registration fails
                if old_service:
                    self.register_service(old_service)
                raise RuntimeError(f"Hot-swap failed during registration: {e}") from e

    # ── Lifecycle Management ───────────────────────────────────────────────

    def initialize_all(self) -> None:
        """Initialize all registered services in topological dependency order."""
        with self._services_lock:
            if self._is_running:
                return

            order = self._topological_sort()
            logger.info(f"Initializing services in order: {order}")

            for name in order:
                service = self._services[name]
                try:
                    service.initialize()
                except Exception as e:
                    service.set_status(ServiceStatus.FAILED, str(e))
                    logger.critical(f"Failed to initialize service {name!r}: {e}", exc_info=True)

            self._is_running = True

    def shutdown_all(self) -> None:
        """Shutdown all active services in reverse topological dependency order."""
        with self._services_lock:
            if not self._is_running:
                return

            order = list(reversed(self._topological_sort()))
            logger.info(f"Shutting down services in order: {order}")

            for name in order:
                service = self._services[name]
                try:
                    service.shutdown()
                except Exception as e:
                    logger.error(f"Error shutting down service {name!r}: {e}", exc_info=True)

            self._is_running = False

    def _topological_sort(self) -> List[str]:
        """Resolves dependencies topologically using Kahn's algorithm."""
        in_degree = {name: 0 for name in self._services}
        adj: Dict[str, List[str]] = {name: [] for name in self._services}

        for name, svc in self._services.items():
            for dep in svc.dependencies:
                if dep in self._services:
                    adj[dep].append(name)
                    in_degree[name] += 1
                else:
                    logger.warning(
                        f"Service {name!r} depends on {dep!r}, which is not registered in the kernel."
                    )

        # Queue for services with no unresolved dependencies
        queue = [name for name, deg in in_degree.items() if deg == 0]
        order: List[str] = []

        while queue:
            curr = queue.pop(0)
            order.append(curr)
            for neighbor in adj[curr]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        if len(order) != len(self._services):
            cyclic_elements = [name for name, deg in in_degree.items() if deg > 0]
            raise ValueError(f"Cyclic dependency detected among services: {cyclic_elements}")

        return order

    # ── Health Monitoring ──────────────────────────────────────────────────

    def get_health_report(self) -> Dict[str, Any]:
        """Checks and returns a status summary of all registered services."""
        with self._services_lock:
            report: Dict[str, Any] = {}
            all_healthy = True
            for name, svc in self._services.items():
                try:
                    res = svc.health_check()
                    report[name] = res
                    if not res.get("healthy", False):
                        all_healthy = False
                except Exception as e:
                    all_healthy = False
                    report[name] = {
                        "status": ServiceStatus.FAILED,
                        "error": f"Health check failed: {e}",
                        "healthy": False,
                        "timestamp": time.time()
                    }
            return {
                "healthy": all_healthy,
                "timestamp": time.time(),
                "services": report
            }

    # ── Dynamic Backwards Compatibility Attributes ─────────────────────────

    @property
    def executive(self) -> Any:
        service: ExecutiveControllerService = self.get_service("executive")
        return service.controller

    @property
    def ledger(self) -> Any:
        service: LedgerService = self.get_service("ledger")
        return service.store

    @ledger.setter
    def ledger(self, store: Any) -> None:
        service: LedgerService = self.get_service("ledger")
        service.store = store

    @property
    def meta_executive(self) -> Any:
        service = self.get_service("meta_executive")
        return service.executive

    @property
    def simulation(self) -> Any:
        service = self.get_service("simulation")
        return service.engine


# Global Kernel Singleton reference
KERNEL = CognitiveKernel()
