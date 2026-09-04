from app.core.config import settings

class StorageService:
    @staticmethod
    def upload_image(file_data: bytes, filename: str) -> str:
        """
        Uploads image and returns public URL/path.
        """
        if settings.STORAGE_MODE == "local":
            # For mock, we aren't doing actual file saving, just returning a path
            return f"/local-storage/{filename}"
        else:
            # Cloudflare R2 implementation via boto3
            raise NotImplementedError("R2 storage not implemented in Phase 1.")
            
    @staticmethod
    def get_image_url(path: str) -> str:
        if settings.STORAGE_MODE == "local":
            return path
        return f"{settings.CLOUDFLARE_R2_ENDPOINT}/{settings.CLOUDFLARE_R2_BUCKET}/{path}"

    @staticmethod
    def delete_image(path: str) -> bool:
        return True
