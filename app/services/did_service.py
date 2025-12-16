import httpx
from app.core.config import settings

AUTH_HEADER = {"Authorization": f"Basic {settings.DID_API_KEY}"}

async def create_stream():
    url = "https://api.d-id.com/talks/streams"
    payload = {
        # "source_url": "https://clips-presenters.d-id.com/amy/image.png"
        "source_url": "https://kenh14cdn.com/cPLqMkXoPs3Tkua5x0JnElZd2udVtV/Image/2015/03/updates/150330dep03-7ef68.jpg",
        "driver_url": "bank://lively", # Enable idle animation
        "config": {
            "stitch": True,
            "align": True
        }
    }
    async with httpx.AsyncClient() as client:
        res = await client.post(url, json=payload, headers=AUTH_HEADER)
        return res.json()

async def submit_sdp(stream_id: str, session_id: str, answer: dict):
    url = f"https://api.d-id.com/talks/streams/{stream_id}/sdp"
    payload = {
        "session_id": session_id,
        "answer": answer
    }
    async with httpx.AsyncClient() as client:
        res = await client.post(url, json=payload, headers=AUTH_HEADER)
        return res.json()

async def submit_ice(stream_id: str, session_id: str, candidate: dict, sdp_mid: str, sdp_m_line_index: int):
    url = f"https://api.d-id.com/talks/streams/{stream_id}/ice"
    payload = {
        "session_id": session_id,
        "candidate": candidate,
        "sdpMid": sdp_mid,
        "sdpMLineIndex": sdp_m_line_index
    }
    async with httpx.AsyncClient() as client:
        res = await client.post(url, json=payload, headers=AUTH_HEADER)
        return res.json()

async def speak(stream_id: str, session_id: str, text: str = None, audio_url: str = None):
    """
    Bắt buộc sử dụng audio_url để đảm bảo giọng nói nhất quán từ ElevenLabs (đã generate ở backend).
    Loại bỏ logic 'script type: text' để tránh D-ID dùng giọng mặc định hoặc config sai.
    """
    url = f"https://api.d-id.com/talks/streams/{stream_id}"
    
    if not audio_url:
        raise ValueError("audio_url is required. Please generate audio via TTS service first.")

    # Luôn sử dụng type: audio
    script_payload = {
        "type": "audio",
        "audio_url": audio_url
    }

    payload = {
        "session_id": session_id,
        "script": script_payload,
        "config": {
            "stitch": True
        }
    }
    
    async with httpx.AsyncClient() as client:
        res = await client.post(url, json=payload, headers=AUTH_HEADER)
        return res.json()

async def delete_stream(stream_id: str, session_id: str):
    url = f"https://api.d-id.com/talks/streams/{stream_id}"
    
    # D-ID yêu cầu gửi session_id trong body, ngay cả với method DELETE
    payload = {
        "session_id": session_id
    }
    
    # Sử dụng method="DELETE"
    async with httpx.AsyncClient() as client:
        # httpx.delete không hỗ trợ gửi json body trực tiếp ở một số phiên bản, 
        # nên dùng client.request để chắc chắn.
        res = await client.request("DELETE", url, json=payload, headers=AUTH_HEADER)
        
        # Kiểm tra nếu thành công (thường trả về 200 hoặc 204)
        if res.status_code == 204 or res.status_code == 200:
            return {"status": "success", "message": "Stream closed"}
        
        return res.json()
