from pydantic import BaseModel
from typing import Optional

class ChatRequest(BaseModel):
    sessionId: str
    message: str = ""
    isStart: bool = False
    topic: Optional[str] = None  # Interview topic for focused questions
    avatarType: Optional[str] = "live2d"

class TTSRequest(BaseModel):
    text: str

class EndInterviewRequest(BaseModel):
    sessionId: str

class TranscribeRequest(BaseModel):
    audioData: str

class SimliSessionRequest(BaseModel):
    faceId: str
    maxSessionLength: int = 3600
