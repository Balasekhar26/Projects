"""Unit tests for Program 19.1: Visual Action Grounding Layer.

Validates coordinate execution dispatches, scroll searching paging iterations,
element trackers, viewport mappings, spatial occlusions, and grounding validators.
"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch

from backend.core.perception.coordinate_executor import CoordinateExecutor
from backend.core.perception.viewport_mapper import ViewportMapper
from backend.core.perception.element_tracker import ElementTracker
from backend.core.perception.scroll_search import ScrollSearch
from backend.core.perception.occlusion_detector import OcclusionDetector
from backend.core.perception.grounding_validator import GroundingValidator
from backend.core.perception.screen_graph import ScreenGraph


# ── 1. Coordinate Executor Checks ─────────────────────────────────────────────

class TestCoordinateExecutor:
    @patch("pyautogui.size", return_value=(1920, 1080))
    @patch("pyautogui.moveTo")
    @patch("pyautogui.click")
    def test_execute_click_in_bounds(self, mock_click, mock_move, mock_size):
        res = CoordinateExecutor.execute_click(500, 300, button="left")
        assert res["success"] is True
        mock_move.assert_called_once_with(500, 300, duration=0.2)
        mock_click.assert_called_once_with(500, 300, button="left", clicks=1)

    @patch("pyautogui.size", return_value=(1920, 1080))
    def test_execute_click_out_of_bounds(self, mock_size):
        res = CoordinateExecutor.execute_click(2000, 300)
        assert res["success"] is False
        assert "out of screen boundaries" in res["error"]

    @patch("pyautogui.write")
    def test_execute_typing(self, mock_write):
        res = CoordinateExecutor.execute_typing("hello")
        assert res["success"] is True
        mock_write.assert_called_once_with("hello", interval=0.01)


# ── 2. Viewport Mapper Checks ─────────────────────────────────────────────────

class TestViewportMapper:
    def test_local_to_absolute_conversion(self):
        bounds = {"x": 100, "y": 200, "width": 800, "height": 600}
        
        # Inside bounds
        ax, ay = ViewportMapper.local_to_absolute(50, 60, bounds)
        assert ax == 150
        assert ay == 260

        # Capped outside bounds
        ax_capped, ay_capped = ViewportMapper.local_to_absolute(900, 700, bounds)
        assert ax_capped == 900  # Capped at wx + ww = 100 + 800
        assert ay_capped == 800  # Capped at wy + wh = 200 + 600


# ── 3. Element Tracker Checks ──────────────────────────────────────────────────

class TestElementTracker:
    def test_reacquire_exact_text(self):
        regions = [{"text": "Register", "x": 100, "y": 150, "w": 40, "h": 20, "confidence": 99.0}]
        graph = ScreenGraph(regions)

        last_known = (95, 145, 40, 20)
        res = ElementTracker.reacquire_element("Register", last_known, graph)
        assert res["success"] is True
        assert res["center"] == (120, 160)
        assert res["shifted"] is False

    def test_reacquire_shifted_text(self):
        regions = [{"text": "Register", "x": 200, "y": 250, "w": 40, "h": 20, "confidence": 99.0}]
        graph = ScreenGraph(regions)

        last_known = (95, 145, 40, 20)
        res = ElementTracker.reacquire_element("Register", last_known, graph)
        assert res["success"] is True
        assert res["center"] == (220, 260)
        assert res["shifted"] is True

    def test_proximity_fallback(self):
        # Target text "Register" is missing in current screen graph, but we have old box
        regions = [{"text": "Submit Button", "x": 110, "y": 150, "w": 40, "h": 20, "confidence": 99.0}]
        graph = ScreenGraph(regions)

        last_known = (100, 150, 40, 20)
        # Reacquire should find the closest node ("Submit Button")
        res = ElementTracker.reacquire_element("Register", last_known, graph)
        assert res["success"] is True
        assert res["center"] == (130, 160)
        assert res["shifted"] is True


# ── 4. Scroll Search Checks ───────────────────────────────────────────────────

class TestScrollSearch:
    @patch("pyautogui.scroll")
    def test_scroll_search_success(self, mock_scroll):
        # 1st capture: Element not present
        # 2nd capture: Element present
        layouts = [
            ScreenGraph([{"text": "Submit", "x": 10, "y": 20, "w": 10, "h": 10, "confidence": 90.0}]),
            ScreenGraph([
                {"text": "Submit", "x": 10, "y": 20, "w": 10, "h": 10, "confidence": 90.0},
                {"text": "Next Page", "x": 500, "y": 500, "w": 40, "h": 10, "confidence": 90.0}
            ])
        ]
        capture_idx = 0

        def mock_capture():
            nonlocal capture_idx
            graph = layouts[capture_idx]
            capture_idx += 1
            return graph

        res = ScrollSearch.search_for_element("Next Page", mock_capture, max_scrolls=2, scroll_amount=-200)
        assert res["success"] is True
        assert res["scrolls_count"] == 1
        assert res["node"]["text"] == "Next Page"
        mock_scroll.assert_called_once_with(-200)


# ── 5. Occlusion Detector Checks ──────────────────────────────────────────────

class TestOcclusionDetector:
    def test_detects_blockage_outside_modal(self):
        # Represents an active modal alert box in layout graph columns (column 300 is treated as modal)
        regions = [
            {"text": "Cancel Button", "x": 310, "y": 320, "w": 40, "h": 10, "confidence": 95.0},
        ]
        graph = ScreenGraph(regions)

        # Click at (10, 10) is outside modal region (which covers col 300) -> Occluded!
        res = OcclusionDetector.is_occluded(10, 10, graph)
        assert res["occluded"] is True
        assert "hidden behind a blocking modal" in res["reason"]

    def test_allows_click_inside_modal(self):
        regions = [
            {"text": "Cancel Button", "x": 310, "y": 320, "w": 40, "h": 10, "confidence": 95.0},
        ]
        graph = ScreenGraph(regions)

        # Click at (320, 325) is inside modal limits -> Not occluded!
        res = OcclusionDetector.is_occluded(320, 325, graph)
        assert res["occluded"] is False


# ── 6. Grounding Validator Checks ─────────────────────────────────────────────

class TestGroundingValidator:
    def test_click_validated_in_bounds(self):
        bbox = (100, 200, 50, 30)
        res = GroundingValidator.validate_grounding_click((120, 215), bbox)
        assert res["success"] is True

    def test_click_failed_out_of_bounds(self):
        bbox = (100, 200, 50, 30)
        res = GroundingValidator.validate_grounding_click((50, 50), bbox)
        assert res["success"] is False
