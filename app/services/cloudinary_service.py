import cloudinary
import cloudinary.uploader
from app.core.config import settings
import asyncio

# Configure Cloudinary
cloudinary.config( 
  cloud_name = settings.CLOUDINARY_CLOUD_NAME, 
  api_key = settings.CLOUDINARY_API_KEY, 
  api_secret = settings.CLOUDINARY_API_SECRET,
  secure = True
)

async def upload_audio_bytes(audio_data: bytes, public_id: str = None) -> str:
    """
    Uploads audio bytes to Cloudinary and returns the secure URL.
    Run asynchronously to avoid blocking the main thread.
    """
    try:
        # Cloudinary upload is blocking, so run in executor
        loop = asyncio.get_event_loop()
        
        def _upload():
            return cloudinary.uploader.upload(
                audio_data, 
                resource_type="video", # Audio is treated as video resource type in Cloudinary usually, or 'auto'
                public_id=public_id,
                folder="ai-interview/audio",
                format="mp3"
            )

        result = await loop.run_in_executor(None, _upload)
        return result.get("secure_url")
        
    except Exception as e:
        print(f"Cloudinary upload error: {e}")
        raise e
