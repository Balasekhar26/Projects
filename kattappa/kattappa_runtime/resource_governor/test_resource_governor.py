"""
Resource Governor Test Suite — Step 30
========================================

Verifies monitoring, budgeting, routing, optimization, life-cycle, storage safety,
and hierarchical compression.
"""

from __future__ import annotations

import os
import shutil
import time
import gzip
import json
import sqlite3
import pytest

from kattappa_runtime.resource_governor.schema import (
    GovernanceConfig,
    SubsystemBudget,
    SystemResourceMetrics,
    SubsystemStats,
)
from kattappa_runtime.resource_governor.monitor import ResourceMonitor
from kattappa_runtime.resource_governor.governor import ResourceGovernor
from kattappa_runtime.resource_governor.router import DifficultyEstimator, DynamicModelRouter
from kattappa_runtime.resource_governor.optimizer import ContextOptimizer
from kattappa_runtime.resource_governor.loader import LazyLoader, AgentLifecycleManager
from kattappa_runtime.resource_governor.storage import StorageManager, HierarchicalMemoryManager
from kattappa_runtime.resource_governor.engine import ResourceGovernorEngine


# Mocking resources to ensure reproducible metrics
class MockMonitor(ResourceMonitor):
    def __init__(self):
        super().__init__()
        self._mock_metrics = SystemResourceMetrics()

    def set_mock_metrics(self, metrics: SystemResourceMetrics):
        self._mock_metrics = metrics

    def get_metrics(self) -> SystemResourceMetrics:
        return self._mock_metrics


@pytest.fixture
def temp_dir(tmpdir):
    yield str(tmpdir)


def test_schema_initialization():
    """Test 1: Check schema configuration defaults."""
    config = GovernanceConfig()
    assert config.global_cpu_limit == 0.50
    assert config.global_ram_limit == 0.50
    assert config.thermal_throttling_temp_c == 85.0
    assert config.min_free_disk_space_bytes == 100 * 1024 * 1024 * 1024


def test_system_resource_metrics_fields():
    """Test 2: Check SystemResourceMetrics defaults."""
    metrics = SystemResourceMetrics()
    assert metrics.cpu_percent == 0.0
    assert metrics.ram_percent == 0.0
    assert metrics.temperature_c == 45.0
    assert metrics.battery_percent == 100.0


def test_monitor_initialization():
    """Test 3: Monitor initialization and forced polling."""
    monitor = ResourceMonitor(interval=0.5)
    monitor.force_poll()
    metrics = monitor.get_metrics()
    assert metrics.cpu_percent >= 0.0
    assert metrics.ram_percent > 0.0


def test_monitor_subsystem_stats():
    """Test 4: Verify setting and retrieving subsystem stats."""
    monitor = ResourceMonitor()
    stats = SubsystemStats(latency_ms=12.5, queue_length=3, active_agents=["planner_agent"])
    monitor.update_subsystem_stats("planner", stats)
    
    retrieved = monitor.get_subsystem_stats("planner")
    assert retrieved is not None
    assert retrieved.latency_ms == 12.5
    assert retrieved.queue_length == 3
    assert "planner_agent" in retrieved.active_agents


def test_governor_budget_permitted():
    """Test 5: Allow execution when estimated resources are within limits."""
    monitor = MockMonitor()
    monitor.set_mock_metrics(SystemResourceMetrics(cpu_percent=10.0, ram_percent=15.0))
    governor = ResourceGovernor(monitor)
    
    # Needs 5% CPU, 5% RAM -> total 15% CPU, 20% RAM (under 50% limit)
    assert governor.request_permission("planner", estimated_cpu=5.0, estimated_ram=5.0) is True


def test_governor_budget_denied():
    """Test 6: Deny execution when estimated resource exceeds subsystem budget allocation."""
    monitor = MockMonitor()
    monitor.set_mock_metrics(SystemResourceMetrics(cpu_percent=10.0, ram_percent=15.0))
    governor = ResourceGovernor(monitor)
    
    # Subsystem 'planner' has 10% CPU share of global limit (10% of 50% = 5.0 CPU)
    # Estimate of 8.0 CPU exceeds its budget of 5.0 CPU
    assert governor.request_permission("planner", estimated_cpu=8.0) is False


def test_governor_global_cpu_exceeded():
    """Test 7: Deny execution when system CPU is already at limit."""
    monitor = MockMonitor()
    monitor.set_mock_metrics(SystemResourceMetrics(cpu_percent=48.0))
    governor = ResourceGovernor(monitor)
    
    # Adding 5% CPU would push total to 53% (exceeds global 50% limit)
    assert governor.request_permission("planner", estimated_cpu=5.0) is False


def test_governor_global_ram_exceeded():
    """Test 8: Deny execution when system RAM is at limit."""
    monitor = MockMonitor()
    monitor.set_mock_metrics(SystemResourceMetrics(ram_percent=49.0))
    governor = ResourceGovernor(monitor)
    
    assert governor.request_permission("planner", estimated_ram=2.0) is False


def test_governor_global_gpu_exceeded():
    """Test 9: Deny execution when system GPU utilization is at limit."""
    monitor = MockMonitor()
    monitor.set_mock_metrics(SystemResourceMetrics(gpu_percent=49.0))
    governor = ResourceGovernor(monitor)
    
    assert governor.request_permission("planner", estimated_gpu=3.0) is False


def test_governor_disk_io_limit():
    """Test 10: Deny execution under heavy sustained Disk I/O."""
    monitor = MockMonitor()
    # 60 MB/s exceeds config limit of 50 MB/s
    monitor.set_mock_metrics(SystemResourceMetrics(disk_io_read_bytes_sec=65.0 * 1024 * 1024))
    governor = ResourceGovernor(monitor)
    
    assert governor.request_permission("planner") is False


def test_governor_net_io_limit():
    """Test 11: Deny execution under heavy sustained Network I/O."""
    monitor = MockMonitor()
    # 12 MB/s exceeds config limit of 10 MB/s
    monitor.set_mock_metrics(SystemResourceMetrics(net_io_recv_bytes_sec=12.0 * 1024 * 1024))
    governor = ResourceGovernor(monitor)
    
    assert governor.request_permission("planner") is False


def test_thermal_governor_worker_scaling():
    """Test 12: Worker count adapts dynamically to thermal load."""
    monitor = MockMonitor()
    governor = ResourceGovernor(monitor)
    
    # 1. Normal temp (45C) -> keep default workers
    monitor.set_mock_metrics(SystemResourceMetrics(temperature_c=45.0))
    assert governor.get_max_workers(8) == 8
    
    # 2. Warm temp (78C) -> cut workers in half
    monitor.set_mock_metrics(SystemResourceMetrics(temperature_c=78.0))
    assert governor.get_max_workers(8) == 4
    
    # 3. Critical temp (86C) -> enforce single worker
    monitor.set_mock_metrics(SystemResourceMetrics(temperature_c=86.0))
    assert governor.get_max_workers(8) == 1


def test_training_governor_healthy_state():
    """Test 13: Training governor suggests no changes under normal load."""
    monitor = MockMonitor()
    governor = ResourceGovernor(monitor)
    
    recs = governor.project_training_step(
        current_step=100,
        current_ram_percent=20.0,
        current_gpu_memory_gb=2.0,
        batch_size=8,
        grad_accum_steps=1
    )
    
    assert recs["should_reduce_batch"] is False
    assert recs["should_clear_cache"] is False


def test_training_governor_pressure_state():
    """Test 14: Clears caches and garbage collects under moderate load."""
    monitor = MockMonitor()
    governor = ResourceGovernor(monitor)
    
    # Limit is 50%. 46% is approaching.
    recs = governor.project_training_step(
        current_step=100,
        current_ram_percent=46.0,
        current_gpu_memory_gb=2.0,
        batch_size=8,
        grad_accum_steps=1
    )
    
    assert recs["should_clear_cache"] is True
    assert recs["should_gc"] is True
    assert recs["should_reduce_batch"] is False


def test_training_governor_critical_state():
    """Test 15: Triggers batch reduction and checkpoint delays under limit violations."""
    monitor = MockMonitor()
    governor = ResourceGovernor(monitor)
    
    # Exceeds 50% RAM limit
    recs = governor.project_training_step(
        current_step=100,
        current_ram_percent=52.0,
        current_gpu_memory_gb=2.0,
        batch_size=8,
        grad_accum_steps=1
    )
    
    assert recs["should_reduce_batch"] is True
    assert recs["should_increase_accum"] is True
    assert recs["should_delay_checkpoint"] is True


def test_difficulty_estimator_simple():
    """Test 16: Check simple query classification."""
    estimator = DifficultyEstimator()
    assert estimator.estimate_difficulty("Hello, what is your name?") == "simple"


def test_difficulty_estimator_coding():
    """Test 17: Check coding query classification."""
    estimator = DifficultyEstimator()
    assert estimator.estimate_difficulty("Write a python script to parse logs") == "medium"


def test_difficulty_estimator_complex():
    """Test 18: Check complex query classification."""
    estimator = DifficultyEstimator()
    assert estimator.estimate_difficulty("Optimize this database query and explain how it improves latency") == "complex"


def test_dynamic_router_simple():
    """Test 19: Simple queries route to tiny model."""
    monitor = MockMonitor()
    monitor.set_mock_metrics(SystemResourceMetrics(ram_percent=20.0))
    governor = ResourceGovernor(monitor)
    router = DynamicModelRouter(governor)
    
    assert router.route("Hello there") == "tiny"


def test_dynamic_router_medium_load():
    """Test 20: Medium query under healthy vs high RAM loads."""
    monitor = MockMonitor()
    governor = ResourceGovernor(monitor)
    router = DynamicModelRouter(governor)
    
    # Healthy RAM (20%) -> routes to medium
    monitor.set_mock_metrics(SystemResourceMetrics(ram_percent=20.0))
    assert router.route("Write a code implementation of a stack") == "medium"
    
    # High RAM (55%) -> routes to tiny fallback
    monitor.set_mock_metrics(SystemResourceMetrics(ram_percent=55.0))
    assert router.route("Write a code implementation of a stack") == "tiny"


def test_dynamic_router_complex_load():
    """Test 21: Complex query under cold vs warm vs high RAM loads."""
    monitor = MockMonitor()
    governor = ResourceGovernor(monitor)
    router = DynamicModelRouter(governor)
    
    # Healthy & Cool -> routes to large
    monitor.set_mock_metrics(
        SystemResourceMetrics(ram_percent=20.0, temperature_c=60.0)
    )
    assert router.route("Compare performance of Postgres vs MySQL and design a schema") == "large"
    
    # Healthy RAM but Hot Temp (78C) -> falls back to medium
    monitor.set_mock_metrics(
        SystemResourceMetrics(ram_percent=20.0, temperature_c=78.0)
    )
    assert router.route("Compare performance of Postgres vs MySQL and design a schema") == "medium"


def test_context_optimizer_token_estimation():
    """Test 22: ContextOptimizer estimates tokens reliably."""
    monitor = MockMonitor()
    governor = ResourceGovernor(monitor)
    optimizer = ContextOptimizer(governor)
    
    text = "Kattappa is a cognitive AI system."
    tokens = optimizer.estimate_tokens(text)
    assert tokens > 0
    assert tokens <= len(text)


def test_context_optimizer_simple_pruning():
    """Test 23: Truncates simple context window to around 800 tokens."""
    monitor = MockMonitor()
    monitor.set_mock_metrics(SystemResourceMetrics(ram_percent=20.0))
    governor = ResourceGovernor(monitor)
    optimizer = ContextOptimizer(governor)
    
    history = [{"role": "user", "content": "hello " * 300}]
    docs = ["doc text " * 300]
    
    opt = optimizer.optimize_context("hi", history, docs)
    assert opt["context_limit"] == 800
    assert opt["tokens_used"] <= 800


def test_context_optimizer_document_cropping():
    """Test 24: Crops raw documents if they overrun budget."""
    monitor = MockMonitor()
    monitor.set_mock_metrics(SystemResourceMetrics(ram_percent=20.0))
    governor = ResourceGovernor(monitor)
    optimizer = ContextOptimizer(governor)
    
    # Large document that will overrun the docs allocation
    docs = ["data " * 1000]
    opt = optimizer.optimize_context("Write code to sort an array", [], docs)
    
    assert opt["tokens_used"] <= opt["context_limit"]
    assert len(opt["optimized_documents"]) == 1
    assert opt["optimized_documents"][0].endswith("... [cropped]")


def test_context_optimizer_ram_pressure():
    """Test 25: Drops context budget even further under system RAM pressure."""
    monitor = MockMonitor()
    governor = ResourceGovernor(monitor)
    optimizer = ContextOptimizer(governor)
    
    # 1. Healthy RAM
    monitor.set_mock_metrics(SystemResourceMetrics(ram_percent=20.0))
    opt_healthy = optimizer.optimize_context("hi", [], [])
    
    # 2. Heavy RAM (55%)
    monitor.set_mock_metrics(SystemResourceMetrics(ram_percent=55.0))
    opt_heavy = optimizer.optimize_context("hi", [], [])
    
    assert opt_heavy["context_limit"] < opt_healthy["context_limit"]


def test_lazy_loader_load():
    """Test 26: Lazy loads a mapped module successfully."""
    monitor = MockMonitor()
    monitor.set_mock_metrics(SystemResourceMetrics(ram_percent=20.0))
    governor = ResourceGovernor(monitor)
    loader = LazyLoader(governor)
    
    # Load knowledge graph engine
    module = loader.load_subsystem("knowledge_graph")
    assert module is not None
    assert "knowledge_graph" in loader.loaded_subsystems


def test_lazy_loader_denied_on_ram():
    """Test 27: Blocks loading if RAM exceeds budget limit."""
    monitor = MockMonitor()
    monitor.set_mock_metrics(SystemResourceMetrics(ram_percent=55.0))
    governor = ResourceGovernor(monitor)
    loader = LazyLoader(governor)
    
    with pytest.raises(RuntimeError):
        loader.load_subsystem("knowledge_graph")


def test_agent_lifecycle_sleep_wake():
    """Test 28: Agent states update on sleep/wake calls."""
    monitor = MockMonitor()
    governor = ResourceGovernor(monitor)
    manager = AgentLifecycleManager(governor)
    
    manager.register_agent("researcher")
    assert "researcher" in manager.get_sleeping_agents()
    
    manager.wake_agent("researcher")
    assert "researcher" in manager.get_active_agents()
    assert "researcher" not in manager.get_sleeping_agents()
    
    manager.sleep_agent("researcher")
    assert "researcher" in manager.get_sleeping_agents()


def test_agent_lifecycle_inactivity():
    """Test 29: Agents sleep automatically after inactivity timeout."""
    monitor = MockMonitor()
    governor = ResourceGovernor(monitor)
    manager = AgentLifecycleManager(governor)
    
    manager.wake_agent("planner")
    # Fake backdate last active time
    manager.last_active_time["planner"] = time.time() - 15.0
    
    manager.check_inactivity_and_sleep(inactivity_timeout=10.0)
    assert "planner" in manager.get_sleeping_agents()


def test_storage_manager_disk_space_healthy(temp_dir):
    """Test 30: Check health assessment when space is plentiful."""
    monitor = MockMonitor()
    governor = ResourceGovernor(monitor)
    # Configure tiny limits for testing
    governor.config.min_free_disk_space_bytes = 1000
    governor.config.min_free_disk_space_ratio = 0.01
    
    manager = StorageManager(governor, base_dir=temp_dir)
    manager.get_disk_usage = lambda: {
        "total": 100 * 1024 * 1024, # 100 MB
        "used": 10 * 1024 * 1024,   # 10 MB
        "free": 90 * 1024 * 1024,   # 90 MB
    }
    res = manager.check_disk_space()
    
    assert res["is_healthy"] is True
    assert res["deficit_bytes"] == 0


def test_storage_manager_disk_space_unhealthy(temp_dir):
    """Test 31: Detect deficit when space requirements are high."""
    monitor = MockMonitor()
    governor = ResourceGovernor(monitor)
    # Ask for 10 Terabytes free
    governor.config.min_free_disk_space_bytes = 10 * 1024 ** 4
    
    manager = StorageManager(governor, base_dir=temp_dir)
    manager.get_disk_usage = lambda: {
        "total": 100 * 1024 * 1024, # 100 MB
        "used": 90 * 1024 * 1024,   # 90 MB
        "free": 10 * 1024 * 1024,   # 10 MB
    }
    res = manager.check_disk_space()
    
    assert res["is_healthy"] is False
    assert res["deficit_bytes"] > 0


def test_storage_manager_cleanup_tmp(temp_dir):
    """Test 32: Cleans temp directory during cleanup."""
    monitor = MockMonitor()
    governor = ResourceGovernor(monitor)
    manager = StorageManager(governor, base_dir=temp_dir)
    
    # Create temp files
    tmp_path = os.path.join(temp_dir, "tmp")
    os.makedirs(tmp_path, exist_ok=True)
    with open(os.path.join(tmp_path, "file.txt"), "w") as f:
        f.write("hello")
        
    actions = manager.run_cleanup_cycle()
    assert any("tmp/" in act for act in actions)
    assert len(os.listdir(tmp_path)) == 0


def test_storage_manager_cleanup_checkpoint_pruning(temp_dir):
    """Test 33: Prunes oldest checkpoints when count exceeds 3."""
    monitor = MockMonitor()
    governor = ResourceGovernor(monitor)
    manager = StorageManager(governor, base_dir=temp_dir)
    
    ckpt_dir = os.path.join(temp_dir, "kattappa_native", "checkpoints", "alpha")
    os.makedirs(ckpt_dir, exist_ok=True)
    
    # Create 5 fake checkpoints with staggered mod times
    for i in range(5):
        path = os.path.join(ckpt_dir, f"checkpoint_step_000{i}00.pt")
        with open(path, "w") as f:
            f.write("weights")
        # Shift modification time back
        os.utime(path, (time.time() - (5 - i) * 10, time.time() - (5 - i) * 10))
        
    actions = manager.run_cleanup_cycle()
    assert any("checkpoints" in act for act in actions)
    
    remaining = os.listdir(ckpt_dir)
    assert len(remaining) == 3
    # Check that older 0 and 1 were pruned
    assert "checkpoint_step_000000.pt" not in remaining
    assert "checkpoint_step_000100.pt" not in remaining
    # Keepers
    assert "checkpoint_step_000400.pt" in remaining


def test_storage_manager_rotate_logs(temp_dir):
    """Test 34: Rotates log files exceeding size threshold."""
    monitor = MockMonitor()
    governor = ResourceGovernor(monitor)
    manager = StorageManager(governor, base_dir=temp_dir)
    
    log_path = os.path.join(temp_dir, "pretrain.log")
    with open(log_path, "w") as f:
        # Write > 10MB of data
        f.write("large log data\n" * 1000000)
        
    actions = manager.run_cleanup_cycle()
    assert any("pretrain.log" in act for act in actions)
    assert os.path.exists(log_path + ".gz")
    assert os.path.getsize(log_path) == 0


def test_hierarchical_memory_eviction(temp_dir):
    """Test 35: Evicts low-importance records from RAM (Hot) to SQLite (Warm)."""
    db_path = os.path.join(temp_dir, "test_warm.db")
    archive_dir = os.path.join(temp_dir, "test_cold")
    
    hmm = HierarchicalMemoryManager(db_path=db_path, archive_dir=archive_dir)
    
    # Create 15 records
    hot = []
    for i in range(15):
        hot.append({
            "id": f"rec_{i}",
            "timestamp": f"2026-06-26T12:00:0{i}Z",
            "subsystem": "planner",
            "importance": float(i) / 15.0,  # record 0 is least important, 14 is most
            "content": f"msg {i}"
        })
        
    # Compress tier, max size = 10
    remaining_hot = hmm.compress_memory_tier(hot, max_hot_size=10)
    
    assert len(remaining_hot) == 10
    # The remaining hot records should be the 10 most important ones (5 to 14)
    ids_remaining = [r["id"] for r in remaining_hot]
    assert "rec_0" not in ids_remaining
    assert "rec_4" not in ids_remaining
    assert "rec_14" in ids_remaining

    # Evicted 0 through 4 should now be stored in SQLite Warm database
    rec_evicted = hmm.retrieve_record("rec_0")
    assert rec_evicted is not None
    assert rec_evicted["content"] == "msg 0"


def test_hierarchical_memory_warm_to_cold_compression(temp_dir):
    """Test 36: Compresses old SQLite entries to Gzip Cold storage when count > 50."""
    db_path = os.path.join(temp_dir, "test_warm2.db")
    archive_dir = os.path.join(temp_dir, "test_cold2")
    
    hmm = HierarchicalMemoryManager(db_path=db_path, archive_dir=archive_dir)
    
    # Push 60 records through eviction so SQLite count exceeds 50 limit
    hot = []
    for i in range(60):
        hot.append({
            "id": f"rec_{i}",
            "timestamp": f"2026-06-26T12:00:{i:02d}Z",
            "subsystem": "planner",
            "importance": 0.1,  # all low importance
            "content": f"msg {i}"
        })
        
    # Trigger eviction to push them into SQLite. Max hot = 5.
    hmm.compress_memory_tier(hot, max_hot_size=5)
    
    # Check that a cold archive .json.gz file was created
    archives = os.listdir(archive_dir)
    assert len(archives) == 1
    assert archives[0].endswith(".json.gz")
    
    # Read the archive to verify
    archive_path = os.path.join(archive_dir, archives[0])
    with gzip.open(archive_path, "rt", encoding="utf-8") as f:
        data = json.load(f)
    assert len(data) == 30  # Archived exactly the oldest 30 records
    assert data[0]["id"] == "rec_0"


def test_engine_facade_start_stop():
    """Test 37: ResourceGovernorEngine facade starts/stops threads safely."""
    engine = ResourceGovernorEngine()
    engine.start()
    assert engine.monitor._thread is not None
    assert engine.monitor._thread.is_alive()
    
    engine.stop()
    assert engine.monitor._thread is None


def test_engine_facade_delegation():
    """Test 38: Engine facade properly routes delegation calls."""
    engine = ResourceGovernorEngine()
    
    # Mock monitor
    mock_mon = MockMonitor()
    mock_mon.set_mock_metrics(SystemResourceMetrics(ram_percent=20.0))
    engine.monitor = mock_mon
    engine.governor.monitor = mock_mon
    engine.router.governor = engine.governor
    engine.optimizer.governor = engine.governor
    
    # Delegate: request_permission
    assert engine.request_permission("planner", estimated_cpu=1.0) is True
    
    # Delegate: route_model
    assert engine.route_model("Simple hello") == "tiny"
    
    # Delegate: optimize_context
    opt = engine.optimize_context("Hello", [], [])
    assert opt["difficulty"] == "simple"
    
    # Delegate: lifecycle
    engine.register_agent("assistant")
    engine.wake_agent("assistant")
    assert "assistant" in engine.lifecycle.get_active_agents()


def test_difficulty_estimator_empty_query():
    """Test 39: Check empty query estimation."""
    estimator = DifficultyEstimator()
    assert estimator.estimate_difficulty("") == "simple"


def test_difficulty_estimator_edge_case_whitespace():
    """Test 40: Check whitespace only query estimation."""
    estimator = DifficultyEstimator()
    assert estimator.estimate_difficulty("    \n   ") == "simple"


def test_dynamic_router_extreme_ram_overload():
    """Test 41: Check router behavior when system is extremely overloaded."""
    monitor = MockMonitor()
    monitor.set_mock_metrics(SystemResourceMetrics(ram_percent=99.0))
    governor = ResourceGovernor(monitor)
    router = DynamicModelRouter(governor)
    assert router.route("Design a complex neural network topology") == "tiny"


def test_context_optimizer_empty_history():
    """Test 42: Optimize context with empty history and documents."""
    monitor = MockMonitor()
    governor = ResourceGovernor(monitor)
    optimizer = ContextOptimizer(governor)
    opt = optimizer.optimize_context("Hello", [], [], max_allowed_tokens=500)
    assert opt["tokens_used"] > 0
    assert opt["optimized_history"] == []
    assert opt["optimized_documents"] == []


def test_context_optimizer_large_history_pruning():
    """Test 43: Ensure older history is pruned first when it exceeds budget."""
    monitor = MockMonitor()
    governor = ResourceGovernor(monitor)
    optimizer = ContextOptimizer(governor)
    
    history = [
        {"role": "user", "content": "old message " * 100},
        {"role": "assistant", "content": "middle message " * 100},
        {"role": "user", "content": "latest message " * 10},
    ]
    opt = optimizer.optimize_context("hi", history, [], max_allowed_tokens=100)
    assert opt["tokens_used"] <= 100
    # The last message should be retained
    assert any("latest message" in msg["content"] for msg in opt["optimized_history"])


def test_lazy_loader_nonexistent_subsystem():
    """Test 44: Requesting an unknown subsystem should raise ValueError."""
    monitor = MockMonitor()
    governor = ResourceGovernor(monitor)
    loader = LazyLoader(governor)
    with pytest.raises(ValueError, match="Unknown lazy subsystem"):
        loader.load_subsystem("invalid_subsystem_name")


def test_agent_lifecycle_multiple_agents():
    """Test 45: Lifecycle manager can manage multiple agents independently."""
    monitor = MockMonitor()
    governor = ResourceGovernor(monitor)
    manager = AgentLifecycleManager(governor)
    
    manager.register_agent("agent_a")
    manager.register_agent("agent_b")
    
    manager.wake_agent("agent_a")
    assert "agent_a" in manager.get_active_agents()
    assert "agent_b" in manager.get_sleeping_agents()
    
    manager.wake_agent("agent_b")
    assert len(manager.get_active_agents()) == 2
    
    manager.sleep_agent("agent_a")
    assert "agent_a" in manager.get_sleeping_agents()
    assert "agent_b" in manager.get_active_agents()


def test_storage_manager_no_checkpoints_to_prune(temp_dir):
    """Test 46: Storage manager behaves correctly when checkpoints dir is empty."""
    monitor = MockMonitor()
    governor = ResourceGovernor(monitor)
    manager = StorageManager(governor, base_dir=temp_dir)
    
    ckpt_dir = os.path.join(temp_dir, "kattappa_native", "checkpoints", "alpha")
    os.makedirs(ckpt_dir, exist_ok=True)
    
    actions = manager.run_cleanup_cycle()
    # No checkpoint pruning action should be reported
    assert not any("pruned" in act.lower() for act in actions)


def test_hierarchical_memory_retrieve_nonexistent(temp_dir):
    """Test 47: Retrieve record returns None when id is not in SQLite."""
    db_path = os.path.join(temp_dir, "nonexistent.db")
    hmm = HierarchicalMemoryManager(db_path=db_path, archive_dir=os.path.join(temp_dir, "cold"))
    assert hmm.retrieve_record("missing_id") is None


def test_governor_subsystem_specific_allocation():
    """Test 48: Subsystem stats can be fetched and budgets respect custom stats."""
    monitor = MockMonitor()
    governor = ResourceGovernor(monitor)
    
    # Subsystem specific CPU limits are 10% of 50% = 5% CPU
    # Estimated 3% is allowed
    assert governor.request_permission("planner", estimated_cpu=3.0) is True
    # Estimated 6% is denied
    assert governor.request_permission("planner", estimated_cpu=6.0) is False


def test_governor_network_receive_limit_edge():
    """Test 49: Network check limits correctly enforce budget at border."""
    monitor = MockMonitor()
    # Setting exactly at limit
    monitor.set_mock_metrics(SystemResourceMetrics(net_io_recv_bytes_sec=10.0 * 1024 * 1024))
    governor = ResourceGovernor(monitor)
    # Under limit (or at limit) is allowed
    assert governor.request_permission("planner") is True
    
    # Over limit is denied
    monitor.set_mock_metrics(SystemResourceMetrics(net_io_recv_bytes_sec=10.1 * 1024 * 1024))
    assert governor.request_permission("planner") is False


def test_engine_facade_lazy_load_denied_exception():
    """Test 50: Facade handles and bubbles up loading exceptions under heavy RAM load."""
    engine = ResourceGovernorEngine()
    mock_mon = MockMonitor()
    mock_mon.set_mock_metrics(SystemResourceMetrics(ram_percent=60.0))
    engine.monitor = mock_mon
    engine.governor.monitor = mock_mon
    
    with pytest.raises(RuntimeError, match="blocked lazy load"):
        engine.load_subsystem("knowledge_graph")

