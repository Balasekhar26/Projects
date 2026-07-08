"""Perception Router API (Program 18.0).

Exposes endpoints for screenshot capture, regional OCR analysis, and layout mapping.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from backend.core.perception.image_ingestion import ImageIngestion
from backend.core.perception.ocr_engine import OCREngine
from backend.core.perception.screen_graph import ScreenGraph
from backend.core.perception.ui_grounder import UIGrounder
from backend.core.perception.screenshot_analyzer import ScreenshotAnalyzer
from backend.core.perception.perception_context import PerceptionContext
from backend.core.perception import perception_events as pe

perception_router = APIRouter(prefix="/perception", tags=["Perception"])

# In-memory context singleton for the active workspace lifecycle
ACTIVE_PERCEPTION_CONTEXT = PerceptionContext()


class GroundingRequest(BaseModel):
    query: str = Field(..., description="Semantic target query, e.g. 'click Submit'")


class CaptureResponse(BaseModel):
    frame_id: str
    timestamp: float
    width: int
    height: int
    hash: str
    elements_count: int


@perception_router.post("/capture", response_model=CaptureResponse, summary="Capture current desktop screenshot")
def capture_screen() -> Dict[str, Any]:
    """Triggers high-frequency desktop screen capture, runs VAD/OCR parsing, and updates context."""
    try:
        frame = ImageIngestion.capture_screenshot()
        raw_words = OCREngine.extract_text_regions(frame.image_bytes)
        graph = ScreenGraph(raw_words)
        
        # Update sliding context history
        ACTIVE_PERCEPTION_CONTEXT.update_frame(frame, graph)

        # Emit audit logs
        pe.emit_frame_captured(frame.frame_id, frame.source, frame.metadata.get("hash", ""), len(frame.image_bytes))
        pe.emit_ocr_complete(frame.frame_id, len(raw_words), 95.0)

        # Scan for modal alerts/dialog popups
        analysis = ScreenshotAnalyzer.inspect_layout(graph)
        if analysis["anomaly_detected"]:
            pe.emit_anomaly_detected(frame.frame_id, analysis["critical_errors"])

        return {
            "frame_id": frame.frame_id,
            "timestamp": frame.timestamp,
            "width": frame.metadata.get("width", 100),
            "height": frame.metadata.get("height", 100),
            "hash": frame.metadata.get("hash", ""),
            "elements_count": len(graph.text_nodes)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Screen capture failed: {e}")


import base64


class OCRRequest(BaseModel):
    image_base64: str = Field(..., description="Base64 encoded image string")


@perception_router.post("/ocr", summary="Run OCR layout extraction on base64 image")
def extract_layout(request: OCRRequest) -> Dict[str, Any]:
    """Accepts base64 encoded image and returns parsed text nodes, containers, and coordinate bboxes."""
    try:
        content = base64.b64decode(request.image_base64)
        raw_words = OCREngine.extract_text_regions(content)
        graph = ScreenGraph(raw_words)
        return graph.to_dict()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"OCR layout parsing failed: {e}")


@perception_router.post("/ground", summary="Locate coordinate bounding box of semantic text query")
def ground_ui_element(request: GroundingRequest) -> Dict[str, Any]:
    """Matches text target against visible context elements and returns bounding box coordinates."""
    graph = ACTIVE_PERCEPTION_CONTEXT.get_latest_graph()
    if not graph:
        raise HTTPException(status_code=400, detail="No active perception frame captured. Call /capture first.")

    grounder = UIGrounder(graph)
    result = grounder.ground_target(request.query)

    if result["success"]:
        pe.emit_grounding_match(request.query, result["text"], result["confidence"], result["center"])

    return result
