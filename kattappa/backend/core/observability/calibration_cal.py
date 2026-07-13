from __future__ import annotations

from typing import List, Dict, Any


def calculate_brier_score(predictions: List[float], outcomes: List[int]) -> float:
    """Calculates the Brier Score. Lower scores indicate better calibration (0.0 is perfect)."""
    if not predictions or not outcomes or len(predictions) != len(outcomes):
        return 0.0
    
    total = 0.0
    for p, o in zip(predictions, outcomes):
        total += (p - o) ** 2
    return round(total / len(predictions), 4)


def calculate_ece(predictions: List[float], outcomes: List[int], num_bins: int = 5) -> float:
    """Calculates the Expected Calibration Error (ECE) over N bins."""
    if not predictions or not outcomes or len(predictions) != len(outcomes):
        return 0.0

    n = len(predictions)
    ece = 0.0
    
    # Define bin bounds
    for i in range(num_bins):
        bin_lower = i / num_bins
        bin_upper = (i + 1) / num_bins
        
        # Gather items in current bin
        bin_predictions = []
        bin_outcomes = []
        for p, o in zip(predictions, outcomes):
            # Include upper bound for last bin
            if i == num_bins - 1:
                in_bin = bin_lower <= p <= bin_upper
            else:
                in_bin = bin_lower <= p < bin_upper
                
            if in_bin:
                bin_predictions.append(p)
                bin_outcomes.append(o)
                
        bin_size = len(bin_predictions)
        if bin_size > 0:
            bin_accuracy = sum(bin_outcomes) / bin_size
            bin_confidence = sum(bin_predictions) / bin_size
            ece += (bin_size / n) * abs(bin_accuracy - bin_confidence)
            
    return round(ece, 4)


def compile_calibration_report(calibrations: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Compiles Expected Calibration Error, Brier Score, and confidence histogram data."""
    if not calibrations:
        return {
            "total_records": 0,
            "brier_score": 0.0,
            "ece": 0.0,
            "histogram": {
                "0.0-0.2": {"count": 0, "avg_confidence": 0.0, "avg_accuracy": 0.0},
                "0.2-0.4": {"count": 0, "avg_confidence": 0.0, "avg_accuracy": 0.0},
                "0.4-0.6": {"count": 0, "avg_confidence": 0.0, "avg_accuracy": 0.0},
                "0.6-0.8": {"count": 0, "avg_confidence": 0.0, "avg_accuracy": 0.0},
                "0.8-1.0": {"count": 0, "avg_confidence": 0.0, "avg_accuracy": 0.0},
            }
        }

    predictions = [float(c["predicted_confidence"]) for c in calibrations]
    outcomes = [int(c["actual_result"]) for c in calibrations]
    
    brier = calculate_brier_score(predictions, outcomes)
    ece = calculate_ece(predictions, outcomes, num_bins=5)
    
    # Build histogram details
    histogram = {}
    num_bins = 5
    for i in range(num_bins):
        bin_lower = i / num_bins
        bin_upper = (i + 1) / num_bins
        bin_label = f"{bin_lower:.1f}-{bin_upper:.1f}"
        
        bin_preds = []
        bin_outs = []
        for p, o in zip(predictions, outcomes):
            if i == num_bins - 1:
                in_bin = bin_lower <= p <= bin_upper
            else:
                in_bin = bin_lower <= p < bin_upper
                
            if in_bin:
                bin_preds.append(p)
                bin_outs.append(o)
                
        count = len(bin_preds)
        histogram[bin_label] = {
            "count": count,
            "avg_confidence": round(sum(bin_preds) / count, 4) if count > 0 else 0.0,
            "avg_accuracy": round(sum(bin_outs) / count, 4) if count > 0 else 0.0,
        }
        
    return {
        "total_records": len(calibrations),
        "brier_score": brier,
        "ece": ece,
        "histogram": histogram,
    }
