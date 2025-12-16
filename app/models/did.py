from pydantic import BaseModel
from typing import Optional, Any

class SDPRequest(BaseModel):
    streamId: str
    sessionId: str
    sdpType: str
    sdpSdp: str

class ICERequest(BaseModel):
    streamId: str
    sessionId: str
    candidate: str
    sdpMid: str
    sdpMLineIndex: int

class SpeakRequest(BaseModel):
    streamId: str
    sessionId: str
    text: str

class CloseStreamRequest(BaseModel):
    streamId: str
    sessionId: str
