from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from backend.core.config import load_config


IGNORED_DIRS = {
    ".git",
    ".pytest_cache",
    ".venv",
    "__pycache__",
    "ai_system_env",
    "dist",
    "node_modules",
    "target",
}

LANGUAGE_BY_SUFFIX = {
    ".bat": "Batch",
    ".css": "CSS",
    ".html": "HTML",
    ".js": "JavaScript",
    ".json": "JSON",
    ".md": "Markdown",
    ".ps1": "PowerShell",
    ".py": "Python",
    ".rs": "Rust",
    ".toml": "TOML",
    ".ts": "TypeScript",
    ".tsx": "TypeScript React",
    ".vbs": "VBScript",
    ".yaml": "YAML",
    ".yml": "YAML",
}

IMPORTANT_FILES = {
    "run.exe": "Main Windows launcher",
    "setup.bat": "Main Windows setup",
    "backend/main.py": "FastAPI API and WebSocket chat",
    "backend/core/graph.py": "Agent graph orchestration",
    "backend/core/memory.py": "SQLite, Chroma, approvals, skills, chat history, long tasks",
    "backend/core/model_router.py": "Local Ollama model routing and fallback",
    "backend/core/project_indexer.py": "Local workspace intelligence index",
    "apps/desktop/src/App.tsx": "Desktop ChatGPT-like interface",
    "apps/desktop/src/styles.css": "Desktop UI styling",
    "apps/desktop/src-tauri/tauri.conf.json": "Desktop packaging config",
    "apps/desktop/scripts/build-tauri-with-msi.ps1": "MSI packaging recovery wrapper",
}


def build_project_index(limit: int = 220) -> dict[str, Any]:
    config = load_config()
    root = config.root
    files = _walk_files(root, limit=max(1, min(limit, 1000)))
    language_counts = Counter(file["language"] for file in files if file["language"] != "Other")
    role_counts = Counter(file["role"] for file in files)
    important = [
        {
            "path": path,
            "role": role,
            "exists": (root / path).exists(),
        }
        for path, role in IMPORTANT_FILES.items()
    ]
    scripts = _detect_scripts(root)
    tests = [file for file in files if "test" in file["path"].lower() or "tests" in file["path"].lower()][:25]
    return {
        "root": str(root),
        "files_indexed": len(files),
        "languages": [{"name": name, "count": count} for name, count in language_counts.most_common()],
        "roles": [{"name": name, "count": count} for name, count in role_counts.most_common()],
        "important_files": important,
        "scripts": scripts,
        "tests": tests,
        "files": files,
        "summary": _summary(root, files, language_counts, scripts),
    }


def search_project_index(query: str, limit: int = 30) -> dict[str, Any]:
    terms = _terms(query)
    index = build_project_index(limit=600)
    if not terms:
        return {"query": query, "items": index["files"][:limit], "summary": index["summary"]}
    scored: list[tuple[int, dict[str, Any]]] = []
    for file in index["files"]:
        haystack = f"{file['path']} {file['role']} {file['language']}".lower()
        score = sum(3 if term in file["path"].lower() else 1 for term in terms if term in haystack)
        if score:
            scored.append((score, file))
    scored.sort(key=lambda item: (-item[0], item[1]["path"]))
    return {
        "query": query,
        "items": [file for _, file in scored[: max(1, min(limit, 100))]],
        "summary": index["summary"],
    }


def _walk_files(root: Path, limit: int) -> list[dict[str, Any]]:
    files: list[dict[str, Any]] = []
    for path in root.rglob("*"):
        if len(files) >= limit:
            break
        if any(part in IGNORED_DIRS for part in path.parts):
            continue
        if not path.is_file():
            continue
        try:
            size = path.stat().st_size
        except OSError:
            continue
        if size > 2_000_000:
            continue
        rel = path.relative_to(root).as_posix()
        files.append(
            {
                "path": rel,
                "size": size,
                "language": LANGUAGE_BY_SUFFIX.get(path.suffix.lower(), "Other"),
                "role": _role_for(rel),
            }
        )
    return files


def _detect_scripts(root: Path) -> list[dict[str, str]]:
    scripts: list[dict[str, str]] = []
    package_json = root / "apps" / "desktop" / "package.json"
    if package_json.exists():
        scripts.append({"name": "desktop build", "command": "npm.cmd run build", "cwd": "apps/desktop"})
        scripts.append({"name": "desktop MSI", "command": "npm.cmd run tauri:build", "cwd": "apps/desktop"})
    if (root / "backend" / "tests" / "test_backend.py").exists():
        scripts.append({"name": "backend tests", "command": "ai_system_env\\Scripts\\python.exe -m pytest backend\\tests\\test_backend.py", "cwd": "."})
    if (root / "run.exe").exists():
        scripts.append({"name": "launch app", "command": "run.exe", "cwd": "."})
    return scripts


def _role_for(path: str) -> str:
    lower = path.lower()
    if lower.endswith((".bat", ".ps1", ".vbs")):
        return "launcher/script"
    if lower.startswith("backend/agents/"):
        return "agent"
    if lower.startswith("backend/core/"):
        return "backend core"
    if lower.startswith("backend/tests/"):
        return "backend test"
    if lower.startswith("backend/tools/"):
        return "tool adapter"
    if lower.startswith("apps/desktop/src-tauri/"):
        return "desktop shell"
    if lower.startswith("apps/desktop/src/"):
        return "desktop ui"
    if lower.endswith((".md", ".txt")):
        return "documentation"
    return "project file"


def _summary(root: Path, files: list[dict[str, Any]], languages: Counter[str], scripts: list[dict[str, str]]) -> str:
    top_languages = ", ".join(name for name, _ in languages.most_common(4)) or "mixed project files"
    return (
        f"Indexed {len(files)} files under {root}. Main languages: {top_languages}. "
        f"Known run/build commands: {len(scripts)}. This index is local-only and excludes generated dependency folders."
    )


def _terms(query: str) -> list[str]:
    terms: list[str] = []
    for raw in query.lower().split():
        term = "".join(ch for ch in raw if ch.isalnum() or ch in {"-", "_"})
        if len(term) >= 2 and term not in terms:
            terms.append(term)
    return terms[:10]
