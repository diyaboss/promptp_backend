import time
import asyncio
from typing import Tuple
from app.core.config import settings
import uuid

class GenerationService:
    @staticmethod
    async def generate_image(prompt: str, seed: int, model: str, width: int, height: int) -> Tuple[str, int]:
        """
        Returns: (image_path, generation_time_ms)
        """
        start_time = time.time()
        
        if settings.GENERATION_MODE == "mock":
            # Simulate processing delay
            await asyncio.sleep(1.0)
            
            gen_time_ms = int((time.time() - start_time) * 1000)
            
            # Use a dummy placehold.co image for mock
            dummy_path = f"https://placehold.co/{width}x{height}/png?text=Mock+{uuid.uuid4().hex[:8]}"
            return dummy_path, gen_time_ms
            
        else:
            # Here we would connect to FLUX.1 or RunPod via a real HTTP client
            # For this phase, it's not fully implemented for non-mock.
            raise NotImplementedError("Real generation not yet implemented in Phase 1.")
