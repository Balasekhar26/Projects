#!/usr/bin/env python3
"""Fast smoke tests that do not require an LLM, Ollama, or internet."""

from __future__ import annotations

import json

import kattappa_ai_system as app


def main() -> int:
    config = app.load_config()
    app.ensure_dirs()

    assert app.ROOT.exists()
    assert app.WORKSPACE.exists()
    assert app.MEMORY_DIR.exists()
    assert app.LOG_DIR.exists()
    assert app.BACKUP_DIR.exists()

    inside = app.safe_workspace_path("example.txt")
    assert inside.parent == app.WORKSPACE.resolve()

    blocked_paths = ["../outside.txt", "/tmp/outside.txt", "C:/outside.txt"]
    for blocked in blocked_paths:
        try:
            app.safe_workspace_path(blocked)
        except ValueError:
            pass
        else:
            raise AssertionError(f"unsafe path was accepted: {blocked}")

    original_memory = app.MEMORY_FILE.read_text(encoding="utf-8") if app.MEMORY_FILE.exists() else None
    try:
        app.remember("smoke test memory note", config)
        assert app.load_memory()
        assert "smoke test memory note" in app.memory_context()
        assert app.clear_memory() == "Memory cleared."
    finally:
        if original_memory is None:
            if app.MEMORY_FILE.exists():
                app.MEMORY_FILE.unlink()
        else:
            app.MEMORY_FILE.write_text(original_memory, encoding="utf-8")

    budget = app.context_budget_report(config)
    assert budget["estimated_tokens"] >= 0
    assert budget["workspace_files_total"] >= 0

    smoke_file = app.WORKSPACE / "_smoke_secret_test.txt"
    backup_file = app.WORKSPACE / "_smoke_backup_test.txt"
    backup_path = None
    try:
        smoke_file.write_text("OPENAI_API_KEY=sk-test_12345678901234567890\n", encoding="utf-8")
        findings = app.scan_workspace_secrets(config)
        assert any(item["path"] == "_smoke_secret_test.txt" for item in findings)

        backup_file.write_text("before\n", encoding="utf-8")
        backup_path = app.backup_workspace_file(backup_file)
        assert backup_path
        assert (app.ROOT / backup_path).exists()
    finally:
        for path in (smoke_file, backup_file):
            if path.exists():
                path.unlink()
        if backup_path:
            created_backup = app.ROOT / backup_path
            if created_backup.exists():
                created_backup.unlink()
            try:
                created_backup.parent.rmdir()
            except OSError:
                pass

    report = app.doctor(config)
    assert report["paths"]["workspace"]
    assert "selected" in report["provider"]
    json.dumps(report)

    print("Smoke test passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
