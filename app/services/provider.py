import asyncio
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional

from app.core.config import settings


@dataclass
class GenerateRequest:
    """Request payload for image generation providers."""
    prompt: str
    seed: int
    model: str
    width: int
    height: int
    generation_id: str


@dataclass
class GenerateResult:
    """
    Result from an image generation provider.

    Attributes:
        status: One of 'complete', 'failed', 'processing'.
        image_url: URL/path of the generated image (set on completion).
        provider_job_id: External job ID for async tracking.
        error_message: Human-readable error description on failure.
        generation_time_ms: Wall-clock generation time in milliseconds.
    """
    status: str  # "complete" | "failed" | "processing"
    image_url: Optional[str] = None
    provider_job_id: Optional[str] = None
    error_message: Optional[str] = None
    generation_time_ms: Optional[int] = None


class ImageProviderBase(ABC):
    """
    Abstract interface for image generation providers.

    Role 4 implements a concrete subclass (e.g. FluxImageProvider)
    that connects to FLUX Schnell/Klein via API. Role 3 provides
    MockImageProvider for local development and testing.
    """

    @abstractmethod
    async def generate(self, request: GenerateRequest) -> GenerateResult:
        """
        Start or complete an image generation.

        Depending on the provider, this may block until the image is ready
        (synchronous providers) or return immediately with status='processing'
        and a provider_job_id for polling.
        """
        ...

    @abstractmethod
    async def check_status(self, provider_job_id: str) -> GenerateResult:
        """
        Poll for the completion status of an asynchronous generation job.

        Only relevant for providers that return status='processing' from generate().
        """
        ...


class MockImageProvider(ImageProviderBase):
    """
    Mock provider for local development and testing.

    Returns placeholder images from placehold.co after a short simulated delay.
    """

    async def generate(self, request: GenerateRequest) -> GenerateResult:
        start_time = time.time()
        # Simulate network/GPU latency
        await asyncio.sleep(0.5)
        gen_time_ms = int((time.time() - start_time) * 1000)

        dummy_url = (
            f"https://placehold.co/{request.width}x{request.height}"
            f"/png?text=Mock+{uuid.uuid4().hex[:8]}"
        )
        return GenerateResult(
            status="complete",
            image_url=dummy_url,
            generation_time_ms=gen_time_ms,
            provider_job_id=f"mock-{uuid.uuid4().hex[:8]}",
        )

    async def check_status(self, provider_job_id: str) -> GenerateResult:
        # Mock jobs always complete instantly
        return GenerateResult(status="complete")


def get_image_provider() -> ImageProviderBase:
    """
    Factory function that returns the appropriate image provider
    based on the GENERATION_MODE configuration setting.

    - 'mock': Returns MockImageProvider (default for development).
    - Any other value: Raises NotImplementedError (Role 4 boundary).
    """
    if settings.GENERATION_MODE == "mock":
        return MockImageProvider()
    raise NotImplementedError(
        f"Image provider for GENERATION_MODE='{settings.GENERATION_MODE}' "
        f"is not implemented. This is the boundary for Role 4."
    )
