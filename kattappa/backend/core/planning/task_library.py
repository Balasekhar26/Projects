"""Decomposition Tasks Library for HTN Planning (Program 12.1).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class TaskDefinition:
    """Canonical model for HTN tasks, containing state transitions and cost vectors."""
    name: str
    is_primitive: bool
    preconditions: List[str] = field(default_factory=list)
    effects: List[str] = field(default_factory=list)
    negative_effects: List[str] = field(default_factory=list)
    cost_vector: Dict[str, float] = field(default_factory=dict)
    rule_id: Optional[str] = None
    estimated_duration: float = 1.0
    duration_variance: float = 0.1
    success_probability: float = 0.95
    # For Compound tasks: lists of subtask names to expand into
    subtasks: List[str] = field(default_factory=list)


class TaskLibrary:
    """Registry of compound and primitive tasks with task decomposition templates."""

    def __init__(self) -> None:
        self.tasks: Dict[str, TaskDefinition] = {}
        self._load_default_library()

    def register_task(self, task: TaskDefinition) -> None:
        self.tasks[task.name] = task

    def get_task(self, name: str) -> Optional[TaskDefinition]:
        return self.tasks.get(name)

    def _load_default_library(self) -> None:
        """Seeds the library with default planning templates and task definitions."""
        
        # 1. Primitive Tasks (leaf executions with preconditions and effects)
        self.register_task(TaskDefinition(
            name="VerifyHardware",
            is_primitive=True,
            preconditions=[],
            effects=["hardware_verified"],
            cost_vector={"cpu_seconds": 1.0},
            estimated_duration=2.0,
            success_probability=0.99,
            rule_id="rule_verify_hw_01"
        ))
        self.register_task(TaskDefinition(
            name="DownloadBinary",
            is_primitive=True,
            preconditions=["internet_available"],
            effects=["binary_downloaded"],
            cost_vector={"api_tokens": 1000.0, "dollars": 1.5},
            estimated_duration=10.0,
            success_probability=0.92,
            rule_id="rule_download_bin_01"
        ))
        self.register_task(TaskDefinition(
            name="ConfigureSettings",
            is_primitive=True,
            preconditions=["binary_downloaded"],
            effects=["settings_configured"],
            cost_vector={"cpu_seconds": 0.5},
            estimated_duration=3.0,
            success_probability=0.98,
            rule_id="rule_config_settings_01"
        ))
        self.register_task(TaskDefinition(
            name="RunDiagnostics",
            is_primitive=True,
            preconditions=["hardware_verified", "settings_configured"],
            effects=["diagnostics_passed"],
            cost_vector={"cpu_seconds": 2.0},
            estimated_duration=5.0,
            success_probability=0.95,
            rule_id="rule_run_diagnostics_01"
        ))
        self.register_task(TaskDefinition(
            name="GenerateReport",
            is_primitive=True,
            preconditions=["diagnostics_passed"],
            effects=["report_generated"],
            cost_vector={"cpu_seconds": 0.2},
            estimated_duration=1.5,
            success_probability=0.99,
            rule_id="rule_gen_report_01"
        ))


        # 2. Compound Tasks (hierarchical steps)
        # InstallSimulator decomposes to: DownloadBinary -> ConfigureSettings
        self.register_task(TaskDefinition(
            name="InstallSimulator",
            is_primitive=False,
            subtasks=["DownloadBinary", "ConfigureSettings"]
        ))

        # PrepareDemoSystem decomposes to: VerifyHardware -> InstallSimulator -> RunDiagnostics -> GenerateReport
        self.register_task(TaskDefinition(
            name="PrepareDemoSystem",
            is_primitive=False,
            subtasks=["VerifyHardware", "InstallSimulator", "RunDiagnostics", "GenerateReport"]
        ))
