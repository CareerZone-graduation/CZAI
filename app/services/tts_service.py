from app.core.config import settings
from fastapi.responses import StreamingResponse
from elevenlabs.client import AsyncElevenLabs

client = AsyncElevenLabs(api_key=settings.ELEVENLABS_API_KEY)


async def generate_audio(text: str) -> bytes:
    """
    Generates audio and returns the bytes. 
    Useful for saving to file and sending URL to D-ID.
    """
    print("Generating audio...: ", text)
    # client.text_to_speech.convert is an async generator, so we don't await the call itself
    audio_iterator = client.text_to_speech.convert(
        text=text,
        voice_id="pNInz6obpgDQGcFmaJgB",
        model_id="eleven_v3",
        output_format="mp3_44100_128"
    )
    
    audio_data = b""
    async for chunk in audio_iterator:
        audio_data += chunk
    return audio_data
