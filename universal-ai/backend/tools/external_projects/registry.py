from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

PROJECTS_ROOT = Path(__file__).resolve().parents[4]
EXTERNAL_PROJECTS_ROOT = (
    PROJECTS_ROOT / "external-projects"
    if (PROJECTS_ROOT / "external-projects").exists()
    else PROJECTS_ROOT / "bin" / "external-projects"
)


@dataclass(frozen=True)
class ExternalProject:
    key: str
    name: str
    upstream_path: Path
    primary_local_project: Path
    purpose: str


EXTERNAL_PROJECTS: tuple[ExternalProject, ...] = (
    ExternalProject(
        key="wifi-csi",
        name="CSI-Sense-Zero",
        upstream_path=EXTERNAL_PROJECTS_ROOT / "CSI-Sense-Zero",
        primary_local_project=PROJECTS_ROOT / "dews",
        purpose="Wi-Fi CSI movement and activity sensing for safe sensor fusion.",
    ),
    ExternalProject(
        key="animal-meaning",
        name="BirdNET-Analyzer",
        upstream_path=EXTERNAL_PROJECTS_ROOT / "BirdNET-Analyzer",
        primary_local_project=PROJECTS_ROOT / "universal-translator",
        purpose="Animal/bioacoustic sound classification and meaning estimation.",
    ),
    ExternalProject(
        key="tiny-gpu",
        name="tiny-gpu",
        upstream_path=EXTERNAL_PROJECTS_ROOT / "tiny-gpu",
        primary_local_project=PROJECTS_ROOT / "pcb-doctor",
        purpose="SystemVerilog GPU learning lab and HDL debugging reference.",
    ),
    ExternalProject(
        key="kronos-finance",
        name="Kronos",
        upstream_path=EXTERNAL_PROJECTS_ROOT / "Kronos",
        primary_local_project=PROJECTS_ROOT / "universal-ai",
        purpose="Financial K-line/OHLCV foundation model reference for the Universal AI Finance Brain.",
    ),
)


def find_project(key: str) -> ExternalProject:
    for project in EXTERNAL_PROJECTS:
        if project.key == key:
            return project
    raise KeyError(f"Unknown external project: {key}")
