#!/usr/bin/env python3
"""
Kattappa Local AI System

Cross-platform, local-first AI system with:
- Ollama local models
- Chat mode
- Internet search mode
- Multi-agent simulation
- Workspace-limited coding agent
- Optional dependency installer

The coding agent can only read/write inside ./workspace.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import textwrap
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
WORKSPACE = ROOT / "workspace"
MEMORY_DIR = ROOT / "memory"
LOG_DIR = ROOT / "logs"
BACKUP_DIR = ROOT / "backups"
CONFIG_FILE = ROOT / "config.json"
MEMORY_FILE = MEMORY_DIR / "notes.json"
INSTALL_FLAG = ROOT / ".installed.flag"
LOCAL_DIR = ROOT / ".local"
LOCAL_BIN = ROOT / "bin"


DEFAULT_CONFIG: dict[str, Any] = {
    "llm_provider": "auto",
    "ollama_base_url": "http://localhost:11434",
    "models": {
        "assistant": "mistral",
        "coder": "mistral",
        "reviewer": "phi3",
        "search_summarizer": "mistral",
    },
    "nvidia_base_url": "https://integrate.api.nvidia.com",
    "nvidia_api_key_env": "NVIDIA_NIM_API_KEY",
    "nvidia_timeout_seconds": 180,
    "nvidia_max_tokens": 2048,
    "nvidia_models": {
        "assistant": "nvidia/llama-3.1-nemotron-nano-4b-v1_1",
        "coder": "openai/gpt-oss-20b",
        "reviewer": "nvidia/llama-3.1-nemotron-nano-4b-v1_1",
        "search_summarizer": "nvidia/llama-3.1-nemotron-nano-4b-v1_1",
    },
    "auto_pull_models": True,
    "optional_packages": ["duckduckgo-search", "ddgs"],
    "workspace_extensions": [
        ".py",
        ".js",
        ".ts",
        ".html",
        ".css",
        ".json",
        ".md",
        ".txt",
        ".c",
        ".cpp",
        ".h",
        ".java",
        ".rs",
        ".go",
        ".sh",
    ],
    "context_file_char_limit": 8_000,
    "workspace_max_file_bytes": 300_000,
    "secret_scan_max_file_bytes": 500_000,
    "backup_code_actions": True,
    "memory_max_notes": 50,
    "temperature": 0.2,
    "prompt_templates": {
        "assistant": "You are a helpful, safe, and trustworthy assistant. Answer clearly and avoid hallucinations.",
        "coder": "You are an expert coding assistant. Only edit workspace files and return valid JSON as instructed.",
        "reviewer": "You are a careful code reviewer. Identify flaws clearly and suggest concrete fixes.",
        "search_summarizer": "You are a search summarizer. Use search results to answer accurately, cite low-confidence findings, and note if the results are weak.",
    },
}


SYSTEM_SAFETY = """
You are running inside a local defensive AI workspace.
Never request destructive actions outside the workspace.
Never produce malware, credential theft, exploit deployment, persistence, evasion, or destructive code.
For coding tasks, prefer clear, maintainable files and explain what changed.
"""


CODER_PROTOCOL = """
You are the coding agent. You may edit only the user's workspace.
Return a single JSON object and nothing else.

Schema:
{
  "summary": "short explanation",
  "actions": [
    {"type": "write_file", "path": "relative/path.ext", "content": "full file content"},
    {"type": "delete_file", "path": "relative/path.ext"}
  ],
  "notes": ["optional note"]
}

Rules:
- Paths must be relative.
- Do not use absolute paths.
- Do not use .. path traversal.
- For edits, provide complete replacement file content.
- If you need to inspect files first, return no actions and explain which files should be read.
"""


@dataclass
class AgentResponse:
    agent: str
    model: str
    content: str


def ensure_dirs() -> None:
    WORKSPACE.mkdir(parents=True, exist_ok=True)
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)


def load_config() -> dict[str, Any]:
    ensure_dirs()
    if not CONFIG_FILE.exists():
        CONFIG_FILE.write_text(json.dumps(DEFAULT_CONFIG, indent=2) + "\n", encoding="utf-8")
    try:
        config = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        backup_path = CONFIG_FILE.with_suffix(".json.bak")
        CONFIG_FILE.rename(backup_path)
        print(f"Invalid config.json detected; backed up to {backup_path}. Restoring defaults.")
        CONFIG_FILE.write_text(json.dumps(DEFAULT_CONFIG, indent=2) + "\n", encoding="utf-8")
        config = {}
    merged = dict(DEFAULT_CONFIG)
    merged.update(config if isinstance(config, dict) else {})
    merged["models"] = {
        **DEFAULT_CONFIG["models"],
        **(config.get("models", {}) if isinstance(config, dict) else {}),
    }
    merged["workspace_extensions"] = [
        *DEFAULT_CONFIG["workspace_extensions"],
        *([str(x) for x in config.get("workspace_extensions", [])] if isinstance(config, dict) else []),
    ]
    prompt_templates = config.get("prompt_templates", {}) if isinstance(config, dict) else {}
    if not isinstance(prompt_templates, dict):
        prompt_templates = {}
    merged["prompt_templates"] = {
        **DEFAULT_CONFIG["prompt_templates"],
        **prompt_templates,
    }
    nvidia_models = config.get("nvidia_models", {}) if isinstance(config, dict) else {}
    if not isinstance(nvidia_models, dict):
        nvidia_models = {}
    merged["nvidia_models"] = {
        **DEFAULT_CONFIG["nvidia_models"],
        **nvidia_models,
    }
    return merged


def get_prompt_template(config: dict[str, Any], role: str, fallback: str) -> str:
    prompts = config.get("prompt_templates", {})
    if not isinstance(prompts, dict):
        prompts = {}
    return str(prompts.get(role, prompts.get("assistant", fallback)))


def log_event(event: str, payload: dict[str, Any]) -> None:
    ensure_dirs()
    item = {"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "event": event, **payload}
    with (LOG_DIR / "events.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(item, sort_keys=True) + "\n")


def load_memory() -> list[dict[str, str]]:
    ensure_dirs()
    if not MEMORY_FILE.exists():
        return []
    try:
        data = json.loads(MEMORY_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []
    if not isinstance(data, list):
        return []
    notes: list[dict[str, str]] = []
    for item in data:
        if isinstance(item, dict) and str(item.get("text", "")).strip():
            notes.append(
                {
                    "ts": str(item.get("ts", "")),
                    "text": str(item.get("text", "")).strip(),
                }
            )
    return notes


def save_memory(notes: list[dict[str, str]], config: dict[str, Any]) -> None:
    ensure_dirs()
    max_notes = max(1, int(config.get("memory_max_notes", 50)))
    MEMORY_FILE.write_text(json.dumps(notes[-max_notes:], indent=2) + "\n", encoding="utf-8")


def remember(text: str, config: dict[str, Any]) -> str:
    note = text.strip()
    if not note:
        return "Nothing to remember."
    notes = load_memory()
    notes.append({"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "text": note})
    save_memory(notes, config)
    return "Saved to memory."


def clear_memory() -> str:
    ensure_dirs()
    if MEMORY_FILE.exists():
        MEMORY_FILE.unlink()
    return "Memory cleared."


def memory_context() -> str:
    notes = load_memory()
    if not notes:
        return ""
    lines = ["Useful saved memory:"]
    for note in notes[-12:]:
        prefix = f"- {note['ts']}: " if note.get("ts") else "- "
        lines.append(prefix + note["text"])
    return "\n".join(lines)


def run_cmd(cmd: list[str] | str, check: bool = False, shell: bool = False) -> subprocess.CompletedProcess[str]:
    print(f"$ {cmd if isinstance(cmd, str) else ' '.join(cmd)}")
    capture_output = check
    result = subprocess.run(cmd, text=True, capture_output=capture_output, check=False, shell=shell)
    if check and result.returncode != 0:
        if result.stdout:
            print(result.stdout)
        if result.stderr:
            print(result.stderr)
        raise subprocess.CalledProcessError(result.returncode, cmd, output=result.stdout, stderr=result.stderr)
    return result


def command_exists(name: str) -> bool:
    return executable_path(name) is not None


def executable_path(name: str) -> str | None:
    if platform.system().lower() == "windows":
        local_candidates = (LOCAL_BIN / f"{name}.exe",)
    else:
        local_candidates = (LOCAL_BIN / name,)
    for candidate in local_candidates:
        if candidate.exists():
            return str(candidate)
    return shutil.which(name)


def install_optional_packages(config: dict[str, Any]) -> None:
    packages = config.get("optional_packages", [])
    if not packages:
        return
    try:
        subprocess.run([sys.executable, "-m", "pip", "--version"], check=True, capture_output=True)
    except Exception:
        print("pip is not available; skipping optional Python packages.")
        return

    for package in packages:
        module_name = package.split("[", 1)[0].replace("-", "_")
        if package_available(module_name):
            continue
        print(f"Installing optional package: {package}")
        try:
            run_cmd([sys.executable, "-m", "pip", "install", package], check=True)
        except subprocess.CalledProcessError:
            print(f"Failed to install optional package: {package}")


def install_ollama_if_possible() -> None:
    if command_exists("ollama"):
        return

    system = platform.system().lower()
    print("Ollama is not installed or not in PATH.")

    if system == "darwin" and command_exists("curl") and command_exists("unzip"):
        if install_ollama_macos_local():
            return
        print("Local macOS Ollama install did not complete.")
    elif system == "linux" and command_exists("curl"):
        print("Attempting official Ollama install script.")
        result = subprocess.run(
            "curl -fsSL https://ollama.com/install.sh | sh",
            shell=True,
            text=True,
            check=False,
        )
        if result.returncode == 0:
            return
        print("Automatic Ollama install did not complete.")
    elif system == "windows":
        print("On Windows, run PowerShell as your user and execute:")
        print("irm https://ollama.com/install.ps1 | iex")
    else:
        print("Could not attempt Ollama install on this platform.")


def install_ollama_macos_local() -> bool:
    """Install Ollama under this project folder without sudo or /usr/local/bin."""
    LOCAL_DIR.mkdir(parents=True, exist_ok=True)
    LOCAL_BIN.mkdir(parents=True, exist_ok=True)
    zip_path = LOCAL_DIR / "Ollama-darwin.zip"
    app_parent = LOCAL_DIR / "ollama-app"
    app_path = app_parent / "Ollama.app"
    ollama_cli = app_path / "Contents" / "Resources" / "ollama"
    link_path = LOCAL_BIN / "ollama"

    print("Downloading Ollama for macOS into the project folder.")
    result = subprocess.run(
        [
            str(executable_path("curl") or "curl"),
            "--fail",
            "--location",
            "--show-error",
            "-o",
            str(zip_path),
            "https://ollama.com/download/Ollama-darwin.zip",
        ],
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return False

    if app_parent.exists():
        shutil.rmtree(app_parent)
    app_parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        [str(executable_path("unzip") or "unzip"), "-q", str(zip_path), "-d", str(app_parent)],
        text=True,
        check=False,
    )
    if result.returncode != 0 or not ollama_cli.exists():
        return False

    if link_path.exists() or link_path.is_symlink():
        link_path.unlink()
    try:
        link_path.symlink_to(ollama_cli)
    except OSError:
        shutil.copy2(ollama_cli, link_path)
    link_path.chmod(0o755)
    print(f"Installed local Ollama CLI: {link_path}")
    return True


def ollama_url(config: dict[str, Any], path: str) -> str:
    return config["ollama_base_url"].rstrip("/") + path


def http_json(url: str, payload: dict[str, Any] | None = None, timeout: int = 120) -> dict[str, Any]:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="GET" if payload is None else "POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw = response.read().decode("utf-8")
    return json.loads(raw) if raw else {}


def http_json_with_headers(
    url: str,
    payload: dict[str, Any],
    headers: dict[str, str],
    timeout: int = 120,
) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", **headers},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw = response.read().decode("utf-8")
    return json.loads(raw) if raw else {}


def ollama_available(config: dict[str, Any]) -> bool:
    try:
        http_json(ollama_url(config, "/api/tags"), timeout=5)
        return True
    except Exception:
        return False


def start_ollama_background() -> None:
    ollama = executable_path("ollama")
    if not ollama:
        return
    try:
        subprocess.Popen(
            [ollama, "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        time.sleep(2)
    except Exception:
        pass


def installed_models(config: dict[str, Any]) -> set[str]:
    try:
        data = http_json(ollama_url(config, "/api/tags"), timeout=10)
    except Exception:
        return set()
    names = set()
    for model in data.get("models", []):
        name = model.get("name")
        if name:
            names.add(name)
            names.add(name.split(":", 1)[0])
    return names


def pull_model(config: dict[str, Any], model: str) -> None:
    print(f"Pulling model: {model}")
    payload = {"name": model, "stream": False}
    try:
        http_json(ollama_url(config, "/api/pull"), payload, timeout=3600)
    except Exception as exc:
        print(f"Could not pull {model}: {exc}")


def ensure_models(config: dict[str, Any]) -> None:
    if selected_llm_provider(config) == "nvidia":
        return
    if not config.get("auto_pull_models", True):
        return
    if not ollama_available(config):
        print("Ollama server is not available; skipping model pull.")
        return

    have = installed_models(config)
    wanted = sorted(set(config["models"].values()))
    for model in wanted:
        if model not in have:
            pull_model(config, model)


def ollama_chat(config: dict[str, Any], model: str, messages: list[dict[str, str]]) -> str:
    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
        "options": {"temperature": config.get("temperature", 0.2)},
    }
    try:
        data = http_json(ollama_url(config, "/api/chat"), payload, timeout=3600)
        return data.get("message", {}).get("content", "").strip()
    except urllib.error.URLError as exc:
        return f"Ollama connection failed: {exc}. Start Ollama and try again."
    except Exception as exc:
        return f"Ollama request failed: {exc}"


def nvidia_api_key(config: dict[str, Any]) -> str:
    env_name = str(config.get("nvidia_api_key_env", "NVIDIA_NIM_API_KEY"))
    return os.getenv(env_name, "") or os.getenv("NVIDIA_API_KEY", "")


def nvidia_available(config: dict[str, Any]) -> bool:
    return bool(nvidia_api_key(config).strip())


def selected_llm_provider(config: dict[str, Any]) -> str:
    provider = str(config.get("llm_provider", "auto")).strip().lower()
    if provider in {"nvidia", "ollama"}:
        return provider
    if nvidia_available(config):
        return "nvidia"
    return "ollama"


def nvidia_model_for_role(config: dict[str, Any], role: str) -> str:
    models = config.get("nvidia_models", {})
    if not isinstance(models, dict):
        return DEFAULT_CONFIG["nvidia_models"]["assistant"]
    return str(models.get(role) or models.get("assistant") or DEFAULT_CONFIG["nvidia_models"]["assistant"])


def ollama_model_for_role(config: dict[str, Any], role: str) -> str:
    models = config.get("models", {})
    if not isinstance(models, dict):
        return DEFAULT_CONFIG["models"]["assistant"]
    return str(models.get(role) or models.get("assistant") or DEFAULT_CONFIG["models"]["assistant"])


def nvidia_chat(config: dict[str, Any], model: str, messages: list[dict[str, str]]) -> str:
    api_key = nvidia_api_key(config).strip()
    if not api_key:
        return "NVIDIA_NIM_API_KEY is not configured."

    base_url = str(config.get("nvidia_base_url", "https://integrate.api.nvidia.com")).rstrip("/")
    payload = {
        "model": model,
        "messages": messages,
        "temperature": config.get("temperature", 0.2),
        "max_tokens": int(config.get("nvidia_max_tokens", 2048)),
        "stream": False,
    }
    try:
        data = http_json_with_headers(
            f"{base_url}/v1/chat/completions",
            payload,
            {"Authorization": f"Bearer {api_key}"},
            timeout=int(config.get("nvidia_timeout_seconds", 180)),
        )
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        return f"NVIDIA NIM request failed: HTTP {exc.code} {error_body}"
    except urllib.error.URLError as exc:
        return f"NVIDIA NIM connection failed: {exc}"
    except Exception as exc:
        return f"NVIDIA NIM request failed: {exc}"

    choices = data.get("choices") or [{}]
    content = choices[0].get("message", {}).get("content", "")
    return str(content).strip()


def llm_chat(config: dict[str, Any], role: str, messages: list[dict[str, str]]) -> tuple[str, str]:
    provider = selected_llm_provider(config)
    system_prompt = get_prompt_template(config, role, SYSTEM_SAFETY)
    if messages and isinstance(messages, list) and messages[0].get("role") == "system":
        messages[0]["content"] = f"{SYSTEM_SAFETY}\n{system_prompt}"
    else:
        messages.insert(0, {"role": "system", "content": f"{SYSTEM_SAFETY}\n{system_prompt}"})

    if provider == "nvidia":
        model = nvidia_model_for_role(config, role)
        content = nvidia_chat(config, model, messages)
        if str(config.get("llm_provider", "auto")).strip().lower() == "auto" and content.startswith("NVIDIA NIM"):
            fallback_model = ollama_model_for_role(config, role)
            return f"ollama:{fallback_model}", ollama_chat(config, fallback_model, messages)
        return f"nvidia:{model}", content

    model = ollama_model_for_role(config, role)
    return f"ollama:{model}", ollama_chat(config, model, messages)


def llm_available(config: dict[str, Any]) -> bool:
    return nvidia_available(config) or ollama_available(config)


def safe_workspace_path(relative_path: str) -> Path:
    cleaned = relative_path.strip().replace("\\", "/")
    if not cleaned or cleaned.startswith("/") or re.match(r"^[A-Za-z]:/", cleaned):
        raise ValueError("path must be relative to workspace")
    target = (WORKSPACE / cleaned).resolve()
    workspace_root = WORKSPACE.resolve()
    if target != workspace_root and workspace_root not in target.parents:
        raise ValueError("path escapes workspace")
    return target


def workspace_tree(max_entries: int = 120) -> str:
    ensure_dirs()
    lines: list[str] = []
    for path in sorted(WORKSPACE.rglob("*")):
        if len(lines) >= max_entries:
            lines.append("... truncated ...")
            break
        rel = path.relative_to(WORKSPACE)
        if any(part.startswith(".") for part in rel.parts):
            continue
        suffix = "/" if path.is_dir() else ""
        lines.append(f"{rel}{suffix}")
    return "\n".join(lines) if lines else "(workspace is empty)"


def read_workspace_file(path_text: str, config: dict[str, Any]) -> str:
    path = safe_workspace_path(path_text)
    max_bytes = int(config.get("workspace_max_file_bytes", 300_000))
    if not path.exists():
        return f"File not found: {path_text}"
    if not path.is_file():
        return f"Not a file: {path_text}"
    data = path.read_bytes()
    if len(data) > max_bytes:
        data = data[:max_bytes]
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("utf-8", errors="replace")


def collect_workspace_context(config: dict[str, Any]) -> str:
    lines = ["Workspace tree:", workspace_tree(), ""]
    file_char_limit = int(config.get("context_file_char_limit", 8_000))
    allowed_extensions = set(str(ext).lower() for ext in config.get("workspace_extensions", DEFAULT_CONFIG["workspace_extensions"]))
    for path in sorted(WORKSPACE.rglob("*")):
        if not path.is_file():
            continue
        if any(part.startswith(".") for part in path.relative_to(WORKSPACE).parts):
            continue
        rel = path.relative_to(WORKSPACE).as_posix()
        if path.stat().st_size > int(config.get("workspace_max_file_bytes", 300_000)):
            continue
        if path.suffix.lower() not in allowed_extensions:
            continue
        content = read_workspace_file(rel, config)
        lines.append(f"--- file: {rel} ---")
        lines.append(content[:file_char_limit])
        lines.append("")
    return "\n".join(lines)


def estimate_tokens(text: str) -> int:
    if not text:
        return 0
    return max(1, (len(text) + 3) // 4)


def context_budget_report(config: dict[str, Any]) -> dict[str, Any]:
    context = collect_workspace_context(config)
    files = [path for path in WORKSPACE.rglob("*") if path.is_file()]
    included_markers = context.count("--- file:")
    return {
        "workspace_files_total": len(files),
        "workspace_files_included": included_markers,
        "context_characters": len(context),
        "estimated_tokens": estimate_tokens(context),
        "max_file_bytes": int(config.get("workspace_max_file_bytes", 300_000)),
        "per_file_character_limit": int(config.get("context_file_char_limit", 8_000)),
    }


SECRET_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("private_key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("openai_key", re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b")),
    ("anthropic_key", re.compile(r"\bsk-ant-[A-Za-z0-9_-]{20,}\b")),
    ("nvidia_key", re.compile(r"\bnvapi-[A-Za-z0-9_-]{20,}\b")),
    ("github_token", re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{20,}\b")),
    ("aws_access_key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    (
        "generic_secret_assignment",
        re.compile(
            r"(?i)\b(api[_-]?key|secret|token|password)\b\s*[:=]\s*['\"]?[^'\"\s]{12,}"
        ),
    ),
]


def mask_secret_text(text: str) -> str:
    masked = text
    token_re = re.compile(r"([A-Za-z0-9_./+=:-]{4})([A-Za-z0-9_./+=:-]{8,})([A-Za-z0-9_./+=:-]{4})")
    return token_re.sub(lambda match: f"{match.group(1)}...{match.group(3)}", masked)


def scan_workspace_secrets(config: dict[str, Any]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    max_bytes = int(config.get("secret_scan_max_file_bytes", 500_000))
    for path in sorted(WORKSPACE.rglob("*")):
        if not path.is_file() or path.name.startswith("."):
            continue
        if path.stat().st_size > max_bytes:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue
        except Exception:
            continue
        rel = path.relative_to(WORKSPACE).as_posix()
        for line_number, line in enumerate(text.splitlines(), start=1):
            for kind, pattern in SECRET_PATTERNS:
                if pattern.search(line):
                    findings.append(
                        {
                            "path": rel,
                            "line": line_number,
                            "kind": kind,
                            "snippet": mask_secret_text(line.strip())[:240],
                        }
                    )
                    break
    return findings


def _find_json_object_text(text: str) -> str | None:
    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    in_string = False
    escape = False
    for index, char in enumerate(text[start:], start=start):
        if char == "\\" and not escape:
            escape = True
            continue
        if char == '"' and not escape:
            in_string = not in_string
        if in_string:
            escape = False
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
        escape = False
    return None


def extract_json_object(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?", "", stripped).strip()
        stripped = re.sub(r"```$", "", stripped).strip()
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        pass
    json_text = _find_json_object_text(stripped)
    if not json_text:
        raise ValueError("No JSON object found in coder response")
    return json.loads(json_text)


def backup_workspace_file(path: Path) -> str | None:
    if not path.exists() or not path.is_file():
        return None
    timestamp = time.strftime("%Y%m%d-%H%M%S", time.localtime())
    rel = path.relative_to(WORKSPACE)
    backup_path = BACKUP_DIR / timestamp / rel
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, backup_path)
    return backup_path.relative_to(ROOT).as_posix()


def apply_coder_actions(plan: dict[str, Any], config: dict[str, Any]) -> list[str]:
    ensure_dirs()
    results: list[str] = []
    actions = plan.get("actions", [])
    if not isinstance(actions, list):
        raise ValueError("coder response actions must be a list")

    for action in actions:
        if not isinstance(action, dict):
            continue
        action_type = action.get("type")
        path_text = str(action.get("path", ""))
        path = safe_workspace_path(path_text)

        if action_type == "write_file":
            content = str(action.get("content", ""))
            if config.get("backup_code_actions", True):
                backup = backup_workspace_file(path)
                if backup:
                    results.append(f"backed up workspace/{path.relative_to(WORKSPACE).as_posix()} to {backup}")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            results.append(f"wrote workspace/{path.relative_to(WORKSPACE).as_posix()}")
        elif action_type == "delete_file":
            if path.exists() and path.is_file():
                if config.get("backup_code_actions", True):
                    backup = backup_workspace_file(path)
                    if backup:
                        results.append(f"backed up workspace/{path.relative_to(WORKSPACE).as_posix()} to {backup}")
                path.unlink()
                results.append(f"deleted workspace/{path.relative_to(WORKSPACE).as_posix()}")
            else:
                results.append(f"skipped missing file workspace/{path.relative_to(WORKSPACE).as_posix()}")
        else:
            results.append(f"ignored unknown action type: {action_type}")
    return results


def _format_search_results(results: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for i, item in enumerate(results, start=1):
        title = item.get("title") or item.get("text") or "(no title)"
        body = item.get("body") or item.get("snippet") or item.get("excerpt") or ""
        link = item.get("href") or item.get("url") or ""
        if body:
            lines.append(f"{i}. {title}: {body} {link}".strip())
        else:
            lines.append(f"{i}. {title} {link}".strip())
    return "\n".join(lines)


def search_web(query: str) -> str:
    try:
        try:
            from ddgs import DDGS  # type: ignore
        except Exception:
            from duckduckgo_search import DDGS  # type: ignore

        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=8))
        if results:
            return _format_search_results(results)
    except Exception:
        pass

    encoded = urllib.parse.urlencode({"q": query, "format": "json", "no_html": "1"})
    url = f"https://api.duckduckgo.com/?{encoded}"
    try:
        data = http_json(url, timeout=20)
    except Exception as exc:
        return f"Search failed: {exc}"
    parts: list[str] = []
    if data.get("AbstractText"):
        parts.append(data["AbstractText"])
    for topic in data.get("RelatedTopics", [])[:8]:
        if isinstance(topic, dict) and topic.get("Text"):
            parts.append(topic["Text"])
        elif isinstance(topic, dict) and isinstance(topic.get("Topics"), list):
            for subtopic in topic["Topics"][:2]:
                if isinstance(subtopic, dict) and subtopic.get("Text"):
                    parts.append(subtopic["Text"])
    return "\n".join(parts) if parts else "No search results found."


def chat(config: dict[str, Any], prompt: str) -> AgentResponse:
    memory = memory_context()
    user_prompt = f"{memory}\n\nUser prompt:\n{prompt}" if memory else prompt
    messages = [
        {"role": "system", "content": SYSTEM_SAFETY},
        {"role": "user", "content": user_prompt},
    ]
    model, content = llm_chat(config, "assistant", messages)
    return AgentResponse("assistant", model, content)


def search_and_answer(config: dict[str, Any], query: str) -> AgentResponse:
    info = search_web(query)
    memory = memory_context()
    prompt = (
        f"{memory}\n\n" if memory else ""
    ) + f"Search results:\n{info}\n\nAnswer the query clearly with caveats if results are weak.\nQuery: {query}"
    model, content = llm_chat(
        config,
        "search_summarizer",
        [
            {"role": "system", "content": SYSTEM_SAFETY},
            {"role": "user", "content": prompt},
        ],
    )
    return AgentResponse("search", model, content)


def multi_agent_simulation(config: dict[str, Any], task: str) -> list[AgentResponse]:
    memory = memory_context()
    task_with_memory = f"{memory}\n\nTask:\n{task}" if memory else task
    assistant_model, planner = llm_chat(
        config,
        "assistant",
        [
            {"role": "system", "content": SYSTEM_SAFETY + "\nYou are the planner agent."},
            {"role": "user", "content": f"Plan a solution for:\n{task_with_memory}"},
        ],
    )
    coder_model, builder = llm_chat(
        config,
        "coder",
        [
            {"role": "system", "content": SYSTEM_SAFETY + "\nYou are the builder agent."},
            {"role": "user", "content": f"Task:\n{task_with_memory}\n\nPlanner said:\n{planner}\n\nImprove or implement the idea conceptually."},
        ],
    )
    reviewer_model, review = llm_chat(
        config,
        "reviewer",
        [
            {"role": "system", "content": SYSTEM_SAFETY + "\nYou are the reviewer agent. Find flaws and fixes."},
            {"role": "user", "content": f"Task:\n{task_with_memory}\n\nPlanner:\n{planner}\n\nBuilder:\n{builder}\n\nReview this."},
        ],
    )
    final_model, final = llm_chat(
        config,
        "assistant",
        [
            {"role": "system", "content": SYSTEM_SAFETY + "\nYou are the final synthesizer."},
            {"role": "user", "content": f"Task:\n{task_with_memory}\n\nPlanner:\n{planner}\n\nBuilder:\n{builder}\n\nReviewer:\n{review}\n\nGive final answer."},
        ],
    )
    return [
        AgentResponse("planner", assistant_model, planner),
        AgentResponse("builder", coder_model, builder),
        AgentResponse("reviewer", reviewer_model, review),
        AgentResponse("final", final_model, final),
    ]


def coding_agent(config: dict[str, Any], task: str) -> tuple[AgentResponse, list[str], AgentResponse | None]:
    context = collect_workspace_context(config)
    memory = memory_context()
    prompt = f"{CODER_PROTOCOL}\n\n{memory}\n\nUser task:\n{task}\n\n{context}" if memory else f"{CODER_PROTOCOL}\n\nUser task:\n{task}\n\n{context}"
    model, response = llm_chat(
        config,
        "coder",
        [
            {"role": "system", "content": SYSTEM_SAFETY + "\n" + CODER_PROTOCOL},
            {"role": "user", "content": prompt},
        ],
    )
    coder_response = AgentResponse("coder", model, response)

    try:
        plan = extract_json_object(response)
        results = apply_coder_actions(plan, config)
    except Exception as exc:
        results = [f"No files changed: {exc}", "Raw coder response was printed for inspection."]
        return coder_response, results, None

    review_prompt = (
        f"Review this coding task and file actions. Be concise.\n"
        f"Task: {task}\n"
        f"Coder summary: {plan.get('summary', '')}\n"
        f"Actions applied: {results}\n"
        f"Workspace tree now:\n{workspace_tree()}"
    )
    reviewer_model, review = llm_chat(
        config,
        "reviewer",
        [
            {"role": "system", "content": SYSTEM_SAFETY + "\nYou are a code reviewer."},
            {"role": "user", "content": review_prompt},
        ],
    )
    return coder_response, results, AgentResponse("reviewer", reviewer_model, review)


def print_response(response: AgentResponse) -> None:
    print(f"\n[{response.agent} / {response.model}]\n{response.content}\n")


def package_available(module_name: str) -> bool:
    try:
        __import__(module_name)
        return True
    except Exception:
        return False


def doctor(config: dict[str, Any]) -> dict[str, Any]:
    provider = selected_llm_provider(config)
    ollama_ok = ollama_available(config)
    duckduckgo_package = package_available("ddgs") or package_available("duckduckgo_search")
    budget = context_budget_report(config)
    return {
        "platform": {
            "os": platform.platform(),
            "python": sys.version.split()[0],
            "executable": sys.executable,
        },
        "paths": {
            "project": str(ROOT),
            "workspace": str(WORKSPACE),
            "memory": str(MEMORY_DIR),
            "logs": str(LOG_DIR),
            "backups": str(BACKUP_DIR),
        },
        "provider": {
            "selected": provider,
            "nvidia_key_configured": nvidia_available(config),
            "ollama_command": executable_path("ollama") or "",
            "ollama_server_reachable": ollama_ok,
        },
        "models": {
            "configured_ollama": config.get("models", {}),
            "installed_ollama": sorted(installed_models(config)) if ollama_ok else [],
            "configured_nvidia": config.get("nvidia_models", {}),
        },
        "features": {
            "web_search_package": duckduckgo_package,
            "memory_notes": len(load_memory()),
            "context_estimated_tokens": budget["estimated_tokens"],
            "workspace_files": workspace_tree().splitlines()[:20],
        },
    }


def print_doctor(config: dict[str, Any]) -> None:
    print(json.dumps(doctor(config), indent=2))


def print_status(config: dict[str, Any]) -> None:
    provider = selected_llm_provider(config)
    print(json.dumps(
        {
            "provider": provider,
            "active_models": {
                "assistant": config["models"].get("assistant"),
                "coder": config["models"].get("coder"),
                "reviewer": config["models"].get("reviewer"),
                "search_summarizer": config["models"].get("search_summarizer"),
            },
            "workspace_files": len([p for p in WORKSPACE.rglob("*") if p.is_file() and not any(part.startswith(".") for part in p.relative_to(WORKSPACE).parts)]),
            "memory_notes": len(load_memory()),
        },
        indent=2,
    ))


def print_config(config: dict[str, Any]) -> None:
    print(json.dumps({
        "llm_provider": config.get("llm_provider"),
        "workspace_extensions": config.get("workspace_extensions"),
        "temperature": config.get("temperature"),
        "backup_code_actions": config.get("backup_code_actions"),
    }, indent=2))


def print_help() -> None:
    print(
        textwrap.dedent(
            """
            Commands:
              help                       Show this help
              exit                       Quit
              doctor                     Check Python, Ollama, models, search, paths
              models                     Show configured Ollama and NVIDIA models
              pull                       Pull configured Ollama models
              files                      List workspace files
              read: path/to/file         Read a workspace file
              budget                     Estimate workspace context size
              scan                       Scan workspace for likely secrets
              memory                     Show saved memory notes
              remember: fact             Save a persistent note for future prompts
              forget memory              Clear saved memory notes
              status                     Show current model/provider/workspace status
              config                     Show effective runtime configuration
              search: query              Search web and answer with local model
              code: task                 Let coding agent edit workspace files
              simulate: task             Run planner/builder/reviewer/final agents
              anything else              Normal chatbot mode

            Workspace:
              Put project files inside ./workspace
              The coding agent cannot read/write outside ./workspace
            """
        ).strip()
    )


def interactive_loop(config: dict[str, Any]) -> None:
    print("\nKATTAPPA AI SYSTEM READY")
    print(f"Project: {ROOT}")
    print(f"Workspace: {WORKSPACE}")
    print(f"LLM provider: {selected_llm_provider(config)}")
    print("Type 'help' for commands.\n")

    if not llm_available(config):
        print("No LLM provider is reachable.")
        print("Set NVIDIA_NIM_API_KEY for hosted NIM, or install/start Ollama and rerun.")
        print("Utility commands still work: help, doctor, files, read, budget, scan, memory, exit.\n")

    while True:
        try:
            task = input(">> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if not task:
            continue
        normalized = task.strip()
        lowered = normalized.lower()

        if lowered in {"exit", "quit", "q"}:
            return
        if lowered in {"help", "?"}:
            print_help()
            continue
        if lowered == "doctor":
            print_doctor(config)
            continue
        if lowered == "status":
            print_status(config)
            continue
        if lowered == "config":
            print_config(config)
            continue
        if lowered == "models":
            print(
                json.dumps(
                    {
                        "active_provider": selected_llm_provider(config),
                        "ollama": config["models"],
                        "nvidia": config["nvidia_models"],
                    },
                    indent=2,
                )
            )
            continue
        if lowered == "pull":
            ensure_models(config)
            continue
        if lowered == "files":
            print(workspace_tree())
            continue
        if lowered.startswith("read:") or lowered.startswith("read "):
            target = normalized.split(":", 1)[-1].strip() if ":" in normalized else normalized.split(" ", 1)[1].strip()
            print(read_workspace_file(target, config))
            continue
        if lowered == "budget":
            print(json.dumps(context_budget_report(config), indent=2))
            continue
        if lowered == "scan":
            findings = scan_workspace_secrets(config)
            if not findings:
                print("No likely secrets found in workspace.")
            else:
                print(json.dumps(findings, indent=2))
            continue
        if lowered == "memory":
            notes = load_memory()
            if not notes:
                print("No saved memory yet.")
            else:
                for note in notes:
                    ts = f"{note['ts']} " if note.get("ts") else ""
                    print(f"- {ts}{note['text']}")
            continue
        if lowered.startswith("remember:") or lowered.startswith("remember "):
            note = normalized.split(":", 1)[-1].strip() if ":" in normalized else normalized.split(" ", 1)[1].strip()
            print(remember(note, config))
            continue
        if lowered in {"forget memory", "clear memory"}:
            print(clear_memory())
            continue
        if lowered.startswith("search:") or lowered.startswith("search "):
            query = normalized.split(":", 1)[-1].strip() if ":" in normalized else normalized.split(" ", 1)[1].strip()
            response = search_and_answer(config, query)
            print_response(response)
            log_event("search", {"query": query, "model": response.model})
            continue
        if lowered.startswith("simulate:") or lowered.startswith("simulate "):
            task_text = normalized.split(":", 1)[-1].strip() if ":" in normalized else normalized.split(" ", 1)[1].strip()
            responses = multi_agent_simulation(config, task_text)
            for response in responses:
                print_response(response)
            log_event("simulate", {"task": task_text})
            continue
        if lowered.startswith("code:") or lowered.startswith("code "):
            task_text = normalized.split(":", 1)[-1].strip() if ":" in normalized else normalized.split(" ", 1)[1].strip()
            coder_response, results, review = coding_agent(config, task_text)
            print_response(coder_response)
            print("Applied actions:")
            for result in results:
                print(f"- {result}")
            if review:
                print_response(review)
            log_event("code", {"task": task_text, "results": results})
            continue

        response = chat(config, normalized)
        print_response(response)
        log_event("chat", {"task": normalized, "model": response.model})


def setup(config: dict[str, Any]) -> None:
    ensure_dirs()
    install_optional_packages(config)
    if selected_llm_provider(config) == "nvidia" and nvidia_available(config):
        INSTALL_FLAG.write_text(time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()) + "\n", encoding="utf-8")
        return
    install_ollama_if_possible()
    if command_exists("ollama") and not ollama_available(config):
        start_ollama_background()
    ensure_models(config)
    INSTALL_FLAG.write_text(time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Kattappa local multi-agent AI system")
    parser.add_argument("--setup", action="store_true", help="Run dependency/model setup")
    parser.add_argument("--no-setup", action="store_true", help="Skip first-run setup")
    parser.add_argument("--provider", choices=["auto", "ollama", "nvidia"], help="Override the configured LLM provider")
    parser.add_argument("--debug", action="store_true", help="Enable debug output for requests and command execution")
    parser.add_argument("--once", help="Run one prompt and exit")
    parser.add_argument("--code", help="Run one coding task and exit")
    parser.add_argument("--search", help="Run one web search answer and exit")
    parser.add_argument("--simulate", help="Run one multi-agent simulation and exit")
    parser.add_argument("--remember", help="Save one memory note and exit")
    parser.add_argument("--doctor", action="store_true", help="Print setup diagnostics and exit")
    parser.add_argument("--budget", action="store_true", help="Print workspace context budget and exit")
    parser.add_argument("--scan", action="store_true", help="Scan workspace for likely secrets and exit")
    args = parser.parse_args()

    config = load_config()
    if args.provider:
        config["llm_provider"] = args.provider
    if args.debug:
        print("DEBUG MODE ENABLED")
        config["debug"] = True

    utility_only = args.doctor or args.budget or args.scan
    if not utility_only and (args.setup or (not args.no_setup and not INSTALL_FLAG.exists())):
        setup(config)

    if args.doctor:
        print_doctor(config)
        return 0
    if args.budget:
        print(json.dumps(context_budget_report(config), indent=2))
        return 0
    if args.scan:
        findings = scan_workspace_secrets(config)
        if findings:
            print(json.dumps(findings, indent=2))
            return 1
        print("No likely secrets found in workspace.")
        return 0
    if args.remember:
        print(remember(args.remember, config))
        return 0
    if args.once:
        print_response(chat(config, args.once))
        return 0
    if args.search:
        print_response(search_and_answer(config, args.search))
        return 0
    if args.simulate:
        for response in multi_agent_simulation(config, args.simulate):
            print_response(response)
        return 0
    if args.code:
        coder_response, results, review = coding_agent(config, args.code)
        print_response(coder_response)
        for result in results:
            print(f"- {result}")
        if review:
            print_response(review)
        return 0

    interactive_loop(config)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
