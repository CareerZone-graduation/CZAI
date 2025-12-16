from app.core.config import settings
from fastapi.responses import StreamingResponse
from elevenlabs.client import AsyncElevenLabs

client = AsyncElevenLabs(api_key=settings.ELEVENLABS_API_KEY)

async def stream_audio_from_text(text: str):
    # async def audio_generator():
    #     # Use stream=True to get an async iterator
    #     stream = await client.text_to_speech.convert(
    #         text=text,
    #         voice_id=settings.ELEVENLABS_VOICE_ID,
    #         model_id="eleven_v3", # User requested this model in the snippet, changing back from eleven_v3 to match snippet instruction precisely or I should use eleven_v3? 
    #         output_format="mp3_44100_128"
    #     )
        
    #     # In the new SDK, convert might return bytes if stream=False (default).
    #     # We need to stream.
    #     # PLEASE NOTE: The user's snippet didn't use stream=True, but we usually want streaming for TTS endpoints.
    #     # However, `client.text_to_speech.convert` implementation varies.
    #     # If I look at the library source (simulated), typical usage for streaming is explicit stream=True.
    #     # But wait, AsyncElevenLabs `convert` might not return a stream object directly unless `stream=True` is passed?
    #     # Wait, if I look at Step 95 snippet again: `audio = ...` then `play(audio)`.
    #     # `play` works with bytes or generator.
    #     # If I want `StreamingResponse`, I should return a generator.
    #     # I will use `stream=True`.
    #     pass


    async def audio_generator():
         audio_stream = await client.text_to_speech.convert(
             text=text,
             voice_id=settings.ELEVENLABS_VOICE_ID,
             model_id="eleven_v3",
             output_format="mp3_44100_128",
             # stream=True # If I enable this, I must iterate.
         )
         # If audio_stream is bytes (default):
         yield audio_stream

    return StreamingResponse(audio_generator(), media_type="audio/mpeg")

async def generate_audio(text: str) -> bytes:
    """
    Generates audio and returns the bytes. 
    Useful for saving to file and sending URL to D-ID.
    """
    print("Generating audio...: ", text)
    # client.text_to_speech.convert is an async generator, so we don't await the call itself
    audio_iterator = client.text_to_speech.convert(
        text=text,
        voice_id=settings.ELEVENLABS_VOICE_ID,
        model_id="eleven_v3",
        output_format="mp3_44100_128"
    )
    
    audio_data = b""
    async for chunk in audio_iterator:
        audio_data += chunk
    return audio_data
