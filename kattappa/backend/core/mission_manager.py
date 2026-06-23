from __future__ import annotations

import time
import uuid
from typing import Any

from backend.core.mission_memory import MissionMemory


class MissionManager:
    @classmethod
    def create_mission_from_goal(cls, title: str, description: str, project_name: str | None = None) -> dict[str, Any]:
        """Goal Engine: Converts a vague goal into structured execution stages and saves it."""
        title_lower = title.lower() + " " + description.lower()
        
        # Heuristic stage routing
        if any(w in title_lower for w in ["drone", "jammer", "pcb", "embedded", "chip", "sensor", "rf", "hardware"]):
            stages = ["Research", "Design", "Simulation", "Testing", "Documentation"]
        elif any(w in title_lower for w in ["website", "app", "database", "api", "code", "software", "web"]):
            stages = ["Requirements", "Architecture", "Implementation", "Testing", "Deployment"]
        else:
            stages = ["Research", "Plan", "Execute", "Verify", "Report"]

        mission = {
            "id": f"mis_{uuid.uuid4().hex[:8]}",
            "title": title,
            "description": description,
            "stages": stages,
            "current_stage": stages[0],
            "status": "running",
            "created_at": time.time(),
            "completed_at": None,
            "lessons_learned": [],
            "user_project": project_name or "General Initiative",
            "updated_at": time.time()
        }
        
        MissionMemory.add_mission(mission)
        return mission

    @classmethod
    def generate_long_horizon_plan(cls, goal: str) -> dict[str, Any]:
        """Long-Horizon Planning: Today, This Week, This Month, This Quarter planning engine."""
        goal_lower = goal.lower()
        if "embedded" in goal_lower or "engineer" in goal_lower:
            plan = {
                "goal": goal,
                "today": "Study STM32 register manuals & download datasheet",
                "this_week": "Write a bare-metal GPIO register blinky driver",
                "this_month": "STM32 Register Mastery: DMA, Interrupts, and Timer configurations",
                "this_quarter": {
                    "Month 1": "STM32 and peripheral register mastery",
                    "Month 2": "FreeRTOS task scheduling & priority inversion analysis",
                    "Month 3": "RF basics & SDR signal analysis",
                    "Month 4": "Altium PCB schematic layout & trace routing"
                }
            }
        else:
            plan = {
                "goal": goal,
                "today": "Define specifications & set up git repository",
                "this_week": "Develop functional skeleton & mock unit tests",
                "this_month": "Core software modules implementation and validation",
                "this_quarter": {
                    "Month 1": "Specifications & architecture setup",
                    "Month 2": "Core development and unit testing",
                    "Month 3": "Integration checks & security audits",
                    "Month 4": "Deployment & production optimization"
                }
            }
        return plan

    @classmethod
    def scan_for_strategic_projects(cls, discovery_text: str) -> dict[str, Any] | None:
        """Strategic Planning Engine: Automatically proposes embedded projects from new RF discoveries."""
        disc_lower = discovery_text.lower()
        if "new rf chipset" in disc_lower or "chipset released" in disc_lower:
            recommendation = {
                "project_title": "Low-cost jammer development",
                "details": "Integrate the newly discovered RF chipset to reduce BOM costs by 40%.",
                "confidence": 0.82,
                "priority": "Medium",
                "reason": "New chipset release lowers component costs significantly.",
                "created_at": time.time()
            }
            # Automatically spawn a running mission
            cls.create_mission_from_goal(
                title=recommendation["project_title"],
                description=recommendation["details"],
                project_name="Autonomous Strategic R&D"
            )
            return recommendation
        return None
