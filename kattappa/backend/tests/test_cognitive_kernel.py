"""Tests for the upgraded Cognitive Kernel implementation."""

from __future__ import annotations

import pytest
import time
from typing import Dict, List, Any

from backend.core.cognitive_kernel import (
    CognitiveKernel,
    CognitiveService,
    ServiceStatus,
    MemoryService,
    GoalService,
    EventService,
)


class DummyService(CognitiveService):
    def __init__(self, name: str, dependencies: List[str] | None = None) -> None:
        super().__init__(name, dependencies)
        self.init_calls = 0
        self.shutdown_calls = 0
        self.init_order_log: List[str] = []
        self.shutdown_order_log: List[str] = []

    def initialize(self) -> None:
        self.init_calls += 1
        self.set_status(ServiceStatus.ACTIVE)
        if hasattr(self.kernel, "_init_log"):
            self.kernel._init_log.append(self.name)

    def shutdown(self) -> None:
        self.shutdown_calls += 1
        self.set_status(ServiceStatus.INACTIVE)
        if hasattr(self.kernel, "_shutdown_log"):
            self.kernel._shutdown_log.append(self.name)


class IsolatedKernel(CognitiveKernel):
    def __new__(cls):
        import threading
        obj = super(CognitiveKernel, cls).__new__(cls)
        obj._services = {}
        obj._services_lock = threading.RLock()
        obj._is_running = False
        return obj

    def __init__(self) -> None:
        pass


def test_service_registration_and_discovery():
    kernel = CognitiveKernel()
    
    # Register a new dummy service
    dummy = DummyService("test_dummy")
    kernel.register_service(dummy)
    
    assert kernel.get_service("test_dummy") is dummy
    assert dummy.kernel is kernel
    assert dummy.status == ServiceStatus.ACTIVE  # initialized immediately because kernel is running
    
    # Deregister it
    removed = kernel.deregister_service("test_dummy")
    assert removed is dummy
    assert dummy.status == ServiceStatus.INACTIVE
    
    with pytest.raises(RuntimeError):
        kernel.get_service("test_dummy")


def test_topological_lifecycle_management():
    kernel = IsolatedKernel()
    kernel._init_log = []
    kernel._shutdown_log = []
    
    # Setup dependency graph: c -> b -> a
    svc_a = DummyService("svc_a")
    svc_b = DummyService("svc_b", dependencies=["svc_a"])
    svc_c = DummyService("svc_c", dependencies=["svc_b"])
    
    # Register in non-topological order
    kernel.register_service(svc_c)
    kernel.register_service(svc_a)
    kernel.register_service(svc_b)
    
    # Start all
    kernel.initialize_all()
    
    # Initialization order must be svc_a -> svc_b -> svc_c
    assert kernel._init_log == ["svc_a", "svc_b", "svc_c"]
    assert svc_a.status == ServiceStatus.ACTIVE
    assert svc_b.status == ServiceStatus.ACTIVE
    assert svc_c.status == ServiceStatus.ACTIVE
    
    # Shutdown all
    kernel.shutdown_all()
    
    # Shutdown order must be reverse: svc_c -> svc_b -> svc_a
    assert kernel._shutdown_log == ["svc_c", "svc_b", "svc_a"]
    assert svc_a.status == ServiceStatus.INACTIVE
    assert svc_b.status == ServiceStatus.INACTIVE
    assert svc_c.status == ServiceStatus.INACTIVE


def test_circular_dependency_detection():
    kernel = IsolatedKernel()
    
    # Circular dependency: a -> b -> a
    svc_a = DummyService("svc_a", dependencies=["svc_b"])
    svc_b = DummyService("svc_b", dependencies=["svc_a"])
    
    kernel.register_service(svc_a)
    kernel.register_service(svc_b)
    
    with pytest.raises(ValueError, match="Cyclic dependency detected"):
        kernel.initialize_all()


def test_hot_swapping():
    kernel = CognitiveKernel()
    
    # Register Version 1
    v1 = DummyService("swappable_svc")
    kernel.register_service(v1)
    assert kernel.get_service("swappable_svc") is v1
    assert v1.status == ServiceStatus.ACTIVE
    
    # Swap to Version 2
    v2 = DummyService("swappable_svc")
    kernel.hot_swap_service("swappable_svc", v2)
    
    # Verify Version 1 is shut down and unregistered
    assert v1.status == ServiceStatus.INACTIVE
    assert v1.shutdown_calls == 1
    
    # Verify Version 2 is registered and initialized
    assert kernel.get_service("swappable_svc") is v2
    assert v2.status == ServiceStatus.ACTIVE
    assert v2.init_calls == 1
    
    # Cleanup
    kernel.deregister_service("swappable_svc")


def test_health_check_aggregation():
    kernel = IsolatedKernel()
    
    svc_1 = DummyService("svc_1")
    svc_2 = DummyService("svc_2")
    
    kernel.register_service(svc_1)
    kernel.register_service(svc_2)
    kernel.initialize_all()
    
    # Initially healthy
    report = kernel.get_health_report()
    assert report["healthy"] is True
    assert report["services"]["svc_1"]["healthy"] is True
    assert report["services"]["svc_2"]["healthy"] is True
    
    # Degrade svc_2
    svc_2.set_status(ServiceStatus.DEGRADED, "API connection lost")
    report_degraded = kernel.get_health_report()
    assert report_degraded["services"]["svc_2"]["healthy"] is False
    assert report_degraded["healthy"] is False  # Because svc_2 is unhealthy


def test_bus_delegation_routing():
    kernel = CognitiveKernel()
    
    # Test Events publish / subscribe routing
    events_triggered = []
    kernel.events.subscribe("kernel_test_topic", lambda payload: events_triggered.append(payload))
    
    kernel.events.publish("agent_test", "kernel_test_topic", {"status": "ok"})
    
    # Allow async Blackboard delivery
    time.sleep(0.1)
    
    assert len(events_triggered) == 1
    assert events_triggered[0]["payload"]["status"] == "ok"
