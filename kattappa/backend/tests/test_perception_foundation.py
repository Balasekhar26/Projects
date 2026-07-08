"""Unit tests for Program 18.0: Multimodal Perception Foundation.

Validates image ingestion, OCR grouping, container screen graphs, element grounding,
vision routing, popup analysis, and REST API router endpoints.
"""
from __future__ import annotations

import io
import json
import pytest
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient
from backend.main import app
from backend.core.perception.perception_frame import PerceptionFrame
from backend.core.perception.image_ingestion import ImageIngestion
from backend.core.perception.ocr_engine import OCREngine
from backend.core.perception.screen_graph import ScreenGraph
from backend.core.perception.ui_grounder import UIGrounder
from backend.core.perception.vision_router import VisionRouter
from backend.core.perception.screenshot_analyzer import ScreenshotAnalyzer


# ── 1. Image Ingestion & Representation Tests ─────────────────────────────────

class TestImageIngestion:
    def test_perception_frame_serialization(self):
        frame = PerceptionFrame(source="test_src", image_bytes=b"123", workspace_id="ws_01")
        data = frame.to_dict()
        assert data["frame_id"].startswith("frm_")
        assert data["source"] == "test_src"
        assert data["image_size_bytes"] == 3
        assert data["workspace_id"] == "ws_01"

    def test_generate_mock_frame(self):
        frame = ImageIngestion.generate_mock_frame("debug_tag")
        assert frame.source == "mock"
        assert frame.metadata["width"] == 100
        assert frame.metadata["height"] == 100
        assert frame.metadata["tag"] == "debug_tag"
        assert len(frame.image_bytes) > 0


# ── 2. OCR Engine Parsing ─────────────────────────────────────────────────────

class TestOCREngine:
    def test_extract_text_regions_mock(self):
        # Mock TSV data returned by pytesseract image_to_data
        tsv_output = (
            "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext\n"
            "5\t1\t1\t1\t1\t1\t50\t100\t80\t25\t96.5\tLogin\n"
            "5\t1\t1\t1\t1\t2\t140\t100\t120\t25\t94.0\tScreen\n"
            "5\t1\t2\t1\t1\t1\t50\t200\t100\t30\t-1\t\n"  # should be ignored
            "5\t1\t2\t1\t1\t2\t60\t200\t90\t30\t85.0\tSubmit\n"
        )

        with patch("pytesseract.image_to_data", return_value=tsv_output):
            mock_image = ImageIngestion.generate_mock_frame().image_bytes
            regions = OCREngine.extract_text_regions(mock_image)
            
            assert len(regions) == 3
            assert regions[0]["text"] == "Login"
            assert regions[0]["x"] == 50
            assert regions[0]["y"] == 100
            assert regions[0]["w"] == 80
            assert regions[0]["h"] == 25

            assert regions[2]["text"] == "Submit"
            assert regions[2]["x"] == 60
            assert regions[2]["y"] == 200


# ── 3. Screen Graph Line & Container Layouts ──────────────────────────────────

class TestScreenGraph:
    def test_screen_graph_word_grouping(self):
        # Two words horizontally close to each other should group into "Login Screen"
        regions = [
            {"text": "Login", "x": 50, "y": 100, "w": 40, "h": 20, "confidence": 95.0},
            {"text": "Screen", "x": 95, "y": 100, "w": 50, "h": 20, "confidence": 95.0},
            {"text": "Submit", "x": 50, "y": 200, "w": 50, "h": 20, "confidence": 90.0},
        ]
        
        graph = ScreenGraph(regions)
        nodes = graph.text_nodes
        
        # Should have clustered "Login" + "Screen" into 1 node, and "Submit" as another
        assert len(nodes) == 2
        
        # Verify merged node fields
        merged = next(n for n in nodes if "Login" in n["text"])
        assert merged["text"] == "Login Screen"
        assert merged["x"] == 50
        assert merged["y"] == 100
        assert merged["w"] == 95  # 50 + 40 + gap (which ends at 95+50=145 -> width 95)
        assert merged["words_count"] == 2

    def test_container_generation(self):
        # Elements at x=50, x=55, x=60 belong to same rounded column 50
        regions = [
            {"text": "A", "x": 50, "y": 100, "w": 10, "h": 10, "confidence": 90.0},
            {"text": "B", "x": 55, "y": 150, "w": 10, "h": 10, "confidence": 90.0},
            {"text": "C", "x": 500, "y": 100, "w": 10, "h": 10, "confidence": 90.0},
        ]
        graph = ScreenGraph(regions)
        assert len(graph.containers) == 2  # column 50 and column 500


# ── 4. UI Element Grounding ───────────────────────────────────────────────────

class TestUIGrounder:
    def test_exact_grounding(self):
        regions = [{"text": "Submit", "x": 100, "y": 200, "w": 50, "h": 20, "confidence": 99.0}]
        graph = ScreenGraph(regions)
        grounder = UIGrounder(graph)

        res = grounder.ground_target("click Submit")
        assert res["success"] is True
        assert res["text"] == "Submit"
        assert res["center"] == (125, 210)
        assert res["confidence"] == 1.0

    def test_fuzzy_substring_grounding(self):
        regions = [{"text": "Cancel Transaction", "x": 100, "y": 200, "w": 50, "h": 20, "confidence": 99.0}]
        graph = ScreenGraph(regions)
        grounder = UIGrounder(graph)

        res = grounder.ground_target("cancel")
        assert res["success"] is True
        assert res["text"] == "Cancel Transaction"
        assert res["confidence"] > 0.0


# ── 5. Vision Router ──────────────────────────────────────────────────────────

class TestVisionRouter:
    def test_router_text_only(self):
        res = VisionRouter.classify_and_route("Check logs for errors", {})
        assert res["requires_vision"] is False
        assert res["recommended_agent"] == "Planner"

    def test_router_requires_vision_payload(self):
        res = VisionRouter.classify_and_route("Analyze this picture", {"image_path": "logo.png"})
        assert res["requires_vision"] is True
        assert res["recommended_agent"] == "ToolExecutor"

    def test_router_browser_vision(self):
        res = VisionRouter.classify_and_route("click on register link on browser window", {})
        assert res["requires_vision"] is True
        assert res["recommended_agent"] == "Browser"


# ── 6. Popup & Anomaly Detection ──────────────────────────────────────────────

class TestScreenshotAnalyzer:
    def test_analyzer_detects_error_dialog(self):
        regions = [
            {"text": "An Exception Occurred", "x": 50, "y": 100, "w": 100, "h": 20, "confidence": 95.0},
            {"text": "Confirm Choice dialog", "x": 50, "y": 200, "w": 100, "h": 20, "confidence": 95.0},
        ]
        graph = ScreenGraph(regions)
        report = ScreenshotAnalyzer.inspect_layout(graph)

        assert report["popup_detected"] is True
        assert report["anomaly_detected"] is True
        assert "An Exception Occurred" in report["critical_errors"]


# ── 7. Endpoint Router API Tests ──────────────────────────────────────────────

class TestPerceptionAPI:
    def test_api_capture_and_ground_flow(self):
        client = TestClient(app)
        mock_frame = ImageIngestion.generate_mock_frame()
        mock_regions = [{"text": "Settings", "x": 800, "y": 20, "w": 60, "h": 20, "confidence": 98.0}]

        with patch("backend.api.v1.perception.ImageIngestion.capture_screenshot", return_value=mock_frame), \
             patch("backend.api.v1.perception.OCREngine.extract_text_regions", return_value=mock_regions):
            
            # 1. Trigger Screen Capture
            cap_resp = client.post("/api/v1/perception/capture")
            assert cap_resp.status_code == 200
            data = cap_resp.json()
            assert data["frame_id"].startswith("frm_")
            assert data["elements_count"] == 1

            # 2. Ground UI Element Query
            ground_resp = client.post("/api/v1/perception/ground", json={"query": "go to settings"})
            assert ground_resp.status_code == 200
            g_data = ground_resp.json()
            assert g_data["success"] is True
            assert g_data["text"] == "Settings"
            assert g_data["center"] == [830, 30]

    def test_api_ground_fails_without_capture(self):
        # Clearing context history to force empty state
        from backend.api.v1.perception import ACTIVE_PERCEPTION_CONTEXT
        ACTIVE_PERCEPTION_CONTEXT._history.clear()
        ACTIVE_PERCEPTION_CONTEXT._latest_graph = None

        client = TestClient(app)
        ground_resp = client.post("/api/v1/perception/ground", json={"query": "settings"})
        assert ground_resp.status_code == 400
        assert "Call /capture first" in ground_resp.json()["detail"]

    def test_api_ocr_base64(self):
        client = TestClient(app)
        mock_regions = [{"text": "Login", "x": 10, "y": 20, "w": 30, "h": 10, "confidence": 99.0}]
        
        with patch("backend.api.v1.perception.OCREngine.extract_text_regions", return_value=mock_regions):
            import base64
            fake_b64 = base64.b64encode(b"dummy_bytes").decode("utf-8")
            resp = client.post("/api/v1/perception/ocr", json={"image_base64": fake_b64})
            assert resp.status_code == 200
            data = resp.json()
            assert len(data["text_nodes"]) == 1
            assert data["text_nodes"][0]["text"] == "Login"

