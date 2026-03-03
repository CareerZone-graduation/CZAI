# CareerZoneAI — AI Interview Spec

> **Version:** 1.0 | **Date:** 2026-03-02

---

## 1. Tổng quan

Module AI Interview cung cấp trải nghiệm phỏng vấn thực tế với:
- **AI Interviewer** (GPT-4o via GitHub Models) hỏi đáp bằng tiếng Việt
- **TTS** (ElevenLabs) → stream audio PCM16 real-time
- **STT** (AssemblyAI) → chuyển giọng nói user thành text
- **Simli AI Avatar** (WebRTC) hoặc **Live2D** làm mặt người phỏng vấn

---

## 2. Luồng phỏng vấn (Interview Flow)

```
User (Client)                  Node.js              CareerZoneAI
     │                            │                       │
     │── Bắt đầu phỏng vấn ──────►│                       │
     │                            │─── POST /chat ────────►│
     │                            │  { isStart: true,      │
     │                            │    sessionId, topic }  │
     │                            │                        ├─ LLM: tạo lời chào
     │                            │                        ├─ ElevenLabs: stream PCM16
     │◄── Audio stream ───────────│◄── StreamingResponse ──┤
     │    + X-AI-Response header  │                        │
     │                            │                        │
     │── Người dùng nói ─────────►│                        │
     │                            │─── POST /transcribe ──►│
     │                            │    { audioData: base64}│
     │                            │◄── { text: "..." } ────┤
     │                            │                        │
     │                            │─── POST /chat ────────►│
     │                            │  { sessionId,          │
     │                            │    message: "..." }    │
     │                            │◄── Audio stream ───────┤
     │◄── Audio stream ───────────│                        │
     │                            │                        │
     │── Kết thúc ───────────────►│                        │
     │                            │─── POST /end ─────────►│
     │                            │◄── { status: success}──┤
```

---

## 3. Session Management

- Mỗi phiên phỏng vấn được định danh bằng **`sessionId`** (UUID)
- Chat history được lưu **in-memory** trong `interview_sessions: dict[sessionId, list]`
- Topic của session lưu trong `interview_topics: dict[sessionId, topic]`
- Session **không persistent** — restart service = mất hết sessions
- Gọi `POST /end` để xóa session và giải phóng memory

> ⚠️ **Limitation hiện tại:** Không có TTL tự động cho session — cần gọi `/end` explicit hoặc xử lý cleanup.

---

## 4. LLM Prompt Architecture

### 4.1 System Prompt Structure

```
[Base Prompt]
Bạn là CareerZoneAI, AI phỏng vấn viên...
QUY TẮC: ngắn gọn, không markdown, dùng [emotion tags]...

[Topic Section] (nếu có topic)
CHỦ ĐỀ: <topic>
LUỒNG: Chào → Kiến thức cơ bản → Kinh nghiệm → Dự án → Thách thức → Kết thúc

[Start Instruction] (nếu isStart=true)
Prompt: "Hãy bắt đầu cuộc phỏng vấn về chủ đề..."
```

### 4.2 Emotion tags

AI sử dụng tags tiếng Anh để biểu đạt cảm xúc (ElevenLabs render thành giọng):

| Tag           | Ý nghĩa       |
|---------------|---------------|
| `[hihi]`      | Vui vẻ nhẹ   |
| `[haha]`      | Cười vui      |
| `[laughs]`    | Cười          |
| `[sighs]`     | Thở dài       |
| `[chuckles]`  | Cười khúc khích |
| `[gasps]`     | Ngạc nhiên    |

### 4.3 LLM Config

| Param         | Value         |
|---------------|---------------|
| Model         | `gpt-4o`      |
| Base URL      | `https://models.github.ai/inference` |
| Temperature   | `1.0`         |
| Top-p         | `1.0`         |
| Auth          | `GITHUB_TOKEN` |

---

## 5. TTS — ElevenLabs

### 5.1 Chọn Voice

| `avatarType` | Voice ID               | Voice Name  |
|--------------|------------------------|-------------|
| `"simli"`    | `EXAVITQu4vr4xnSDxMaL` | Sarah       |
| `"live2d"` (default) | `pNInz6obpgDQGcFmaJgB` | Adam  |

### 5.2 Streaming Config

```
POST https://api.elevenlabs.io/v1/text-to-speech/{voice_id}/stream
  ?output_format=pcm_16000

Payload:
  model_id: "eleven_v3"
  stability: 0.5
  similarity_boost: 0.75

Output: raw PCM16 bytes (16000 Hz, 16-bit signed, mono)
```

### 5.3 Simli Integration

Simli AI nhận raw **PCM16 bytes** qua WebRTC DataChannel — đó là lý do `/chat` stream PCM16 trực tiếp thay vì MP3.

- Session token cần: `audioInputFormat: "pcm16"`
- Model: `"artalk"`
- Handle silence: `true`

---

## 6. STT — AssemblyAI

### 6.1 Luồng transcription

```
1. Client gửi audio dạng base64 (POST /transcribe)
2. Decode base64 → bytes
3. Validate: len(audio_bytes) >= 5000 (tránh audio quá ngắn)
4. Upload lên AssemblyAI → lấy upload_url
5. Submit transcription job: language_code = "vi" (tiếng Việt)
6. Poll status mỗi 500ms (tối đa 60 lần = 30 giây)
7. Trả về text đã transcribe
```

### 6.2 Error cases

| Condition                    | HTTP Code | Message                       |
|-----------------------------|-----------|-------------------------------|
| Base64 không hợp lệ         | 500       | Invalid base64 audio data     |
| Audio < 5000 bytes          | 400       | Audio too short...            |
| AssemblyAI trả lỗi          | 500       | Transcription failed          |
| Timeout sau 30 giây         | 500       | Transcription timeout         |

---

## 7. Simli Avatar — WebRTC Flow

```
Client                    CareerZoneAI              Simli AI
  │── POST /simli/get-session-token ──────────────────►│
  │     { faceId, maxSessionLength: 3600 }             │
  │◄── { token, ... } ◄──────────────────────────────  │
  │                                                     │
  │── GET /simli/get-ice-servers ─────────────────────►│
  │◄── { iceServers: [...] } ◄────────────────────────  │
  │                                                     │
  ├── Tạo WebRTC PeerConnection với ICE servers ────────┤
  ├── Gửi PCM16 audio chunks qua DataChannel ──────────►│
  └── Nhận video stream từ avatar ◄───────────────────  │
```

---

## 8. Spec: Cải tiến đề xuất

| ID       | Feature                              | Priority |
|----------|--------------------------------------|----------|
| INT-001  | TTL tự động cho interview sessions   | Medium   |
| INT-002  | Persist session vào Redis            | Low      |
| INT-003  | Streaming LLM (word-by-word)         | High     |
| INT-004  | Đánh giá ứng viên sau phỏng vấn      | High     |
| INT-005  | Upload recording lên Cloudinary      | Medium   |
