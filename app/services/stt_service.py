import asyncio
import base64
import httpx
from app.core.config import settings

async def transcribe_audio(audio_data_base64: str) -> str:
    # 1. Decode base64
    try:
        audio_bytes = base64.b64decode(audio_data_base64)
    except Exception:
        raise Exception("Invalid base64 audio data")

    if len(audio_bytes) < 5000:
        raise Exception("Audio too short. Please speak for at least 2-3 seconds.")

    headers = {
        "Authorization": settings.ASSEMBLYAI_API_KEY
    }

    async with httpx.AsyncClient() as client:
        # 2. Upload
        upload_response = await client.post(
            "https://api.assemblyai.com/v2/upload",
            content=audio_bytes,
            headers=headers
        )
        upload_response.raise_for_status()
        upload_url = upload_response.json()["upload_url"]

        # 3. Transcribe
        transcript_response = await client.post(
            "https://api.assemblyai.com/v2/transcript",
            json={"audio_url": upload_url, "language_code": "vi"},
            headers=headers
        )
        transcript_response.raise_for_status()
        transcript_id = transcript_response.json()["id"]

        # 4. Poll
        max_attempts = 60
        for _ in range(max_attempts):
            poll_response = await client.get(
                f"https://api.assemblyai.com/v2/transcript/{transcript_id}",
                headers=headers
            )
            poll_response.raise_for_status()
            result = poll_response.json()

            if result["status"] == "completed":
                return result["text"] or ""
            elif result["status"] == "error":
                raise Exception(f"Transcription failed: {result['error']}")
            
            await asyncio.sleep(0.5)
        
        raise Exception("Transcription timeout")
