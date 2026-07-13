from backend.core.operator import build_operator_plan, build_visual_guidance, detect_operator_mode


def test_teach_mode_is_safe_visual_guidance() -> None:
    plan = build_operator_plan(
        "[operator mode: teach]\nShow me the Settings button",
        selected_agent="desktop",
        screen_text="Settings",
        screen_snapshot={
            "text": "Settings",
            "width": 1000,
            "height": 800,
            "words": [
                {
                    "text": "Settings",
                    "left": 700,
                    "top": 80,
                    "width": 100,
                    "height": 40,
                    "confidence": 92,
                }
            ],
        },
    )

    assert plan["mode"] == "teach"
    assert plan["needs_approval"] is False
    guidance = plan["visual_guidance"]
    assert guidance["enabled"] is True
    assert guidance["requires_approval"] is False
    assert guidance["target"]["source"] == "ocr"
    assert guidance["target"]["label"] == "Settings"


def test_assist_guidance_is_preview_until_approval() -> None:
    guidance = build_visual_guidance(
        request="click Settings",
        mode="assist",
        screen_snapshot={
            "width": 1000,
            "height": 800,
            "words": [{"text": "Settings", "left": 10, "top": 20, "width": 80, "height": 20, "confidence": 80}],
        },
        approval_required=True,
    )

    assert guidance["enabled"] is True
    assert guidance["requires_approval"] is True
    assert "after approving" in guidance["instruction"]


def test_operator_mode_detection_knows_teach() -> None:
    assert detect_operator_mode("teach me where to go next") == "teach"
