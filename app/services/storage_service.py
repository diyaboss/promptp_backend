from app.core.config import settings

class StorageService:
    @staticmethod
    def upload_image(file_data: bytes, filename: str) -> str:
        """
        Uploads image data to the configured storage backend.
        
        In 'local' mock mode, it simply returns a dummy path without saving.
        In 'r2' mode, this will handle S3 API interactions to store the image on Cloudflare R2.
        
        Args:
            file_data (bytes): The raw image bytes.
            filename (str): The destination filename.
            
        Returns:
            str: The public URL or path where the image is accessible.
        """
        if settings.STORAGE_MODE == "local":
            # For mock, we aren't doing actual file saving, just returning a path
            return f"/local-storage/{filename}"
        else:
            # Cloudflare R2 implementation via boto3
            raise NotImplementedError("R2 storage not implemented in Phase 1.")
            
    @staticmethod
    def get_image_url(path: str) -> str:
        """
        Constructs the full public URL for a given image path.
        """
        if settings.STORAGE_MODE == "local":
            return path
        return f"{settings.CLOUDFLARE_R2_ENDPOINT}/{settings.CLOUDFLARE_R2_BUCKET}/{path}"

    @staticmethod
    def delete_image(path: str) -> bool:
        """
        Deletes an image from the storage backend.
        """
        return True
