from typing import List, Tuple
from app.core.config import settings

class ScoringService:
    @staticmethod
    def score_submission(target_image: str, submitted_image: str) -> float:
        """
        Calculates the similarity score between a target image and the user's submitted image.
        
        In 'mock' mode, returns a deterministic dummy score. In 'real' mode, this will
        use CLIP to generate embeddings for both images and calculate their cosine similarity.
        
        Args:
            target_image (str): Path or URL of the target image.
            submitted_image (str): Path or URL of the user's generated image.
            
        Returns:
            float: Similarity score between 0.0 and 1.0.
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
        """
        Efficiently scores a batch of submitted images against a pre-computed target embedding.
        
        This will be used for batch evaluation if needed.
        """
        return [0.5 for _ in submitted_images]
