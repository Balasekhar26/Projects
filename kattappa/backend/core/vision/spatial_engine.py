from backend.core.vision.ui_element import UIElement

class SpatialRelationshipEngine:
    @classmethod
    def compute_spatial_relations(cls, elements: list[UIElement]) -> list[dict]:
        """Calculates relative directional layout relationships between UI elements from pixel boundaries."""
        relations = []
        
        for i, elem_a in enumerate(elements):
            x1_a, y1_a, x2_a, y2_a = elem_a.pixel_bbox
            w_a = x2_a - x1_a
            h_a = y2_a - y1_a
            cx_a = (x1_a + x2_a) / 2
            cy_a = (y1_a + y2_a) / 2
            
            for j, elem_b in enumerate(elements):
                if i == j:
                    continue
                x1_b, y1_b, x2_b, y2_b = elem_b.pixel_bbox
                w_b = x2_b - x1_b
                h_b = y2_b - y1_b
                cx_b = (x1_b + x2_b) / 2
                cy_b = (y1_b + y2_b) / 2
                
                # Compute intersections
                ix1 = max(x1_a, x1_b)
                iy1 = max(y1_a, y1_b)
                ix2 = min(x2_a, x2_b)
                iy2 = min(y2_a, y2_b)
                
                inter_area = 0
                if ix2 > ix1 and iy2 > iy1:
                    inter_area = (ix2 - ix1) * (iy2 - iy1)
                    
                area_b = w_b * h_b
                
                # 1. Check Containment and Overlap Ratios
                if area_b > 0:
                    containment_ratio = inter_area / area_b
                    if containment_ratio >= 0.90:
                        relations.append({
                            "source_id": elem_a.element_id,
                            "target_id": elem_b.element_id,
                            "predicate": "CONTAINS"
                        })
                        continue
                    elif 0.50 <= containment_ratio < 0.90:
                        relations.append({
                            "source_id": elem_a.element_id,
                            "target_id": elem_b.element_id,
                            "predicate": "PARTIALLY_CONTAINS"
                        })
                        continue
                    elif 0.10 <= containment_ratio < 0.50:
                        relations.append({
                            "source_id": elem_a.element_id,
                            "target_id": elem_b.element_id,
                            "predicate": "OVERLAPS"
                        })
                        continue
                
                # 2. Check ABOVE/BELOW with horizontal alignments
                # Horizontally aligned if center points are closer than the maximum width
                horiz_aligned = abs(cx_a - cx_b) < max(w_a, w_b)
                if horiz_aligned:
                    if y2_a <= y1_b:
                        relations.append({
                            "source_id": elem_a.element_id,
                            "target_id": elem_b.element_id,
                            "predicate": "ABOVE"
                        })
                    elif y1_a >= y2_b:
                        relations.append({
                            "source_id": elem_a.element_id,
                            "target_id": elem_b.element_id,
                            "predicate": "BELOW"
                        })
                        
                # 3. Check LEFT_OF/RIGHT_OF with vertical alignments
                vert_aligned = abs(cy_a - cy_b) < max(h_a, h_b)
                if vert_aligned:
                    if x2_a <= x1_b:
                        relations.append({
                            "source_id": elem_a.element_id,
                            "target_id": elem_b.element_id,
                            "predicate": "LEFT_OF"
                        })
                    elif x1_a >= x2_b:
                        relations.append({
                            "source_id": elem_a.element_id,
                            "target_id": elem_b.element_id,
                            "predicate": "RIGHT_OF"
                        })
                        
        return relations
