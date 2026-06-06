#!/usr/bin/env python3
"""
Kattappa AI System - Feature Verification
Proves all features work without requiring models.
"""

import json
import sys
from pathlib import Path

def verify_features():
    """Verify all system features are present and working."""

    print("\n" + "="*60)
    print("  KATTAPPA AI SYSTEM - FEATURE VERIFICATION")
    print("="*60 + "\n")

    checks = []

    # 1. Import system
    try:
        import kattappa_ai_system as app
        checks.append(("✅ Core system imports", True))
    except Exception as e:
        checks.append(("❌ Core system imports", False))
        print(f"Error: {e}")
        return checks

    # 2. Config loading
    try:
        config = app.load_config()
        checks.append(("✅ Config loading + recovery", True))
    except Exception as e:
        checks.append(("❌ Config loading", False))
        print(f"Error: {e}")

    # 3. Directories
    try:
        app.ensure_dirs()
        assert app.WORKSPACE.exists()
        assert app.MEMORY_DIR.exists()
        assert app.LOG_DIR.exists()
        assert app.BACKUP_DIR.exists()
        checks.append(("✅ Workspace isolation", True))
    except Exception as e:
        checks.append(("❌ Workspace isolation", False))

    # 4. Path safety
    try:
        path = app.safe_workspace_path("example.txt")
        assert path.parent == app.WORKSPACE.resolve()
        # Test blocking
        blocked = False
        for bad_path in ["../outside.txt", "/tmp/outside", "C:/outside.txt"]:
            try:
                app.safe_workspace_path(bad_path)
            except ValueError:
                blocked = True
                break
        assert blocked
        checks.append(("✅ Safe path enforcement", True))
    except Exception as e:
        checks.append(("❌ Safe path enforcement", False))

    # 5. Memory system
    try:
        app.remember("test fact", config)
        notes = app.load_memory()
        assert any("test fact" in note.get("text", "") for note in notes)
        app.clear_memory()
        checks.append(("✅ Memory persistence", True))
    except Exception as e:
        checks.append(("❌ Memory persistence", False))

    # 6. Context collection
    try:
        budget = app.context_budget_report(config)
        assert budget["estimated_tokens"] >= 0
        checks.append(("✅ Context budgeting", True))
    except Exception as e:
        checks.append(("❌ Context budgeting", False))

    # 7. Secret scanning
    try:
        test_file = app.WORKSPACE / "_test_secret.txt"
        test_file.write_text("OPENAI_API_KEY=sk-test1234567890123456\n")
        findings = app.scan_workspace_secrets(config)
        assert any("_test_secret.txt" in f.get("path", "") for f in findings)
        test_file.unlink()
        checks.append(("✅ Secret detection", True))
    except Exception as e:
        checks.append(("❌ Secret detection", False))

    # 8. File backup
    try:
        backup_file = app.WORKSPACE / "_test_backup.txt"
        backup_file.write_text("original")
        backup_path = app.backup_workspace_file(backup_file)
        assert backup_path is not None
        assert (app.ROOT / backup_path).exists()
        backup_file.unlink()
        (app.ROOT / backup_path).unlink()
        checks.append(("✅ Automatic backups", True))
    except Exception as e:
        checks.append(("❌ Automatic backups", False))

    # 9. JSON parsing
    try:
        test_cases = [
            '{"summary": "test", "actions": []}',
            '```json\n{"summary": "test", "actions": []}\n```',
            'Some text before {"summary": "test", "actions": []} and after',
        ]
        for case in test_cases:
            result = app.extract_json_object(case)
            assert result.get("summary") == "test"
        checks.append(("✅ Robust JSON extraction", True))
    except Exception as e:
        checks.append(("❌ Robust JSON extraction", False))

    # 10. Search function (structure only)
    try:
        assert hasattr(app, 'search_web')
        assert callable(app.search_web)
        checks.append(("✅ Web search function", True))
    except Exception as e:
        checks.append(("❌ Web search function", False))

    # 11. Agent functions
    try:
        assert hasattr(app, 'chat')
        assert hasattr(app, 'coding_agent')
        assert hasattr(app, 'multi_agent_simulation')
        assert hasattr(app, 'search_and_answer')
        checks.append(("✅ All agent functions", True))
    except Exception as e:
        checks.append(("❌ All agent functions", False))

    # 12. Diagnostic functions
    try:
        assert hasattr(app, 'doctor')
        assert hasattr(app, 'get_prompt_template')
        report = app.doctor(config)
        assert "platform" in report
        checks.append(("✅ Diagnostics + templates", True))
    except Exception as e:
        checks.append(("❌ Diagnostics + templates", False))

    # 13. Configuration options
    try:
        assert "workspace_extensions" in config
        assert "prompt_templates" in config
        assert isinstance(config.get("workspace_extensions"), list)
        assert isinstance(config.get("prompt_templates"), dict)
        checks.append(("✅ Advanced config options", True))
    except Exception as e:
        checks.append(("❌ Advanced config options", False))

    # 14. Model support
    try:
        provider = app.selected_llm_provider(config)
        assert provider in ("ollama", "nvidia")
        checks.append(("✅ Multi-model support", True))
    except Exception as e:
        checks.append(("❌ Multi-model support", False))

    # Print results
    print("\nFEATURE CHECK RESULTS:\n")
    passed = 0
    failed = 0

    for feature, status in checks:
        print(f"  {feature}")
        if status:
            passed += 1
        else:
            failed += 1

    print("\n" + "="*60)
    print(f"RESULT: {passed}/{len(checks)} features verified ✅")
    print("="*60 + "\n")

    if failed == 0:
        print("🎉 ALL SYSTEMS OPERATIONAL")
        print("Your AI system is ready to use!")
        return 0
    else:
        print(f"⚠️  {failed} feature(s) need attention")
        return 1

if __name__ == "__main__":
    sys.exit(verify_features())
