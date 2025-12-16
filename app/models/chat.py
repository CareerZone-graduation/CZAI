from pydantic import BaseModel
from typing import Optional

class ChatRequest(BaseModel):
    sessionId: str
    message: str = ""
    isStart: bool = False
    topic: Optional[str] = None  # Interview topic for focused questions

class TTSRequest(BaseModel):
    text: str

class EndInterviewRequest(BaseModel):
    sessionId: str

class TranscribeRequest(BaseModel):
    audioData: str
