from backend.core.self_model.capability_registry import CapabilityRegistry
from backend.core.self_model.confidence_engine import ConfidenceEngine
from backend.core.self_model.uncertainty_estimator import UncertaintyEstimator

class SelfModelEngine:
    def __init__(self):
        self.registry = CapabilityRegistry()
        self.confidence_engine = ConfidenceEngine()
        self.uncertainty_estimator = UncertaintyEstimator()

    def evaluate_task_safety_and_confidence(
        self, 
        task_id: str, 
        command: str, 
        vision_confidence: float = 1.0, 
        ocr_confidence: float = 1.0
    ) -> dict:
        """Evaluates command support, confidence history metrics, and reviews approval locks."""
        supported = self.registry.is_command_supported(command)
        conf = self.confidence_engine.calculate_confidence(task_id)
        
        uncertainty = self.uncertainty_estimator.estimate_uncertainty(vision_confidence, ocr_confidence)
        approval_gate = self.uncertainty_estimator.requires_human_approval(uncertainty) or (not supported)
        
        return {
            "supported": supported,
            "confidence": conf,
            "uncertainty": uncertainty,
            "requires_human_approval": approval_gate
        }
