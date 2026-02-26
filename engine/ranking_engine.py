import logging
from typing import Any, Dict, List, Tuple
from rapidfuzz import fuzz
import numpy as np

log = logging.getLogger("RankingEngine")

class RankingEngine:
    """
    Multi-Factor Ranking Engine for UI elements.
    Calculates a weighted score based on fuzzy text matching, OCR confidence, 
    geometry, and historical performance.
    """

    def __init__(self, weights: Dict[str, float] = None):
        self.weights = weights or {
            "fuzzy": 0.4,
            "ocr": 0.2,
            "geometry": 0.2,
            "memory": 0.2
        }

    def rank_candidates(
        self,
        target_text: str,
        candidates: List[Dict[str, Any]],
        memory_stats: Dict[str, float] = None
    ) -> List[Dict[str, Any]]:
        """
        Rank OCR results based on multiple heuristics.
        """
        ranked = []
        target_norm = target_text.lower().strip()

        for cand in candidates:
            cand_text = cand.get("text", "").lower().strip()
            
            # 1. Fuzzy Score (0.0 - 1.0)
            fuzzy_score = fuzz.token_set_ratio(target_norm, cand_text) / 100.0
            
            # 2. OCR Confidence (0.0 - 1.0)
            ocr_conf = cand.get("confidence", 0.0)
            
            # 3. Geometry Score (0.0 - 1.0)
            # Favor elements that look like buttons (reasonable aspect ratio and area)
            box = cand.get("box", [0, 0, 0, 0])
            width = box[2] - box[0]
            height = box[3] - box[1]
            area = width * height
            
            # Simple heuristic: favor area between 500 and 50000 pixels
            geometry_score = min(1.0, area / 2000.0) if area < 2000 else 1.0
            if width > 0 and height > 0:
                aspect_ratio = width / height
                if 1.5 < aspect_ratio < 10: # Likely a button or label
                    geometry_score *= 1.0
                else:
                    geometry_score *= 0.7
            
            # 4. Memory Weight (0.0 - 1.0)
            memory_weight = memory_stats.get(cand_text, 0.5) if memory_stats else 0.5

            # Final blended score
            final_score = (
                self.weights["fuzzy"] * fuzzy_score +
                self.weights["ocr"] * ocr_conf +
                self.weights["geometry"] * geometry_score +
                self.weights["memory"] * memory_weight
            )

            result = {
                **cand,
                "ranking_details": {
                    "fuzzy": round(fuzzy_score, 3),
                    "ocr": round(ocr_conf, 3),
                    "geometry": round(geometry_score, 3),
                    "memory": round(memory_weight, 3),
                    "final": round(final_score, 3)
                }
            }
            ranked.append(result)

        # Sort by final score descending
        ranked.sort(key=lambda x: x["ranking_details"]["final"], reverse=True)
        
        # Log top 3 for visibility
        for i, r in enumerate(ranked[:3]):
            details = r["ranking_details"]
            log.debug(f"Rank #{i+1}: '{r['text']}' -> Score: {details['final']} (F:{details['fuzzy']} O:{details['ocr']} G:{details['geometry']} M:{details['memory']})")

        return ranked
