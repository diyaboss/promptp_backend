from typing import List, Tuple
from app.core.config import settings

class ScoringService:
    @staticmethod
    def score_submission(target_image: str, submitted_image: str) -> float:
        """
        Scores the submission against the target image.
        Returns a float between 0 and 1.
        """
        if settings.SCORING_MODE == "mock":
            # Deterministic mock score based on string lengths just to have something consistent
            base = len(submitted_image) % 100
            return float(base) / 100.0
            
        else:
            # CLIP implementation goes here
            raise NotImplementedError("Real CLIP scoring not yet implemented in Phase 1.")

    @staticmethod
    def score_batch(target_embedding: list, submitted_images: List[str]) -> List[float]:
        # Batch scoring placeholder
        return [0.5 for _ in submitted_images]
