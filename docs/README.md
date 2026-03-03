# CareerZoneAI — Documentation Index

> AI Backend microservice (Python/FastAPI) cho hệ thống CareerZone.

---

## Tài liệu

| Tài liệu                                              | Mô tả                                                  |
|------------------------------------------------------|--------------------------------------------------------|
| [architecture.md](./architecture.md)                 | Kiến trúc tổng thể, layer stack, lifespan, concurrency |
| [api-spec.md](./api-spec.md)                         | Full API specification — tất cả endpoints              |
| [interview-spec.md](./interview-spec.md)             | AI Interview flow, LLM prompt, TTS/STT, Simli avatar   |
| [recommendation-spec.md](./recommendation-spec.md)  | LightFM engine, feature namespace, training pipeline   |
| [data-models.md](./data-models.md)                  | Pydantic schemas, MongoDB documents, env vars          |

---

## Quick Start

```bash
# Cài dependencies
pip install -r requirements.txt

# Tạo .env từ template
cp .env.example .env  # điền API keys

# Chạy dev server
uvicorn app.main:app --reload
# → http://localhost:8000
# → http://localhost:8000/docs  (Swagger UI)
# → http://localhost:8000/redoc (ReDoc)
```

---

## Domain Map

```
/api/v1/
 ├── /chat            POST   AI interview – stream PCM16 audio
 ├── /tts             POST   Text-to-speech
 ├── /transcribe      POST   Speech-to-text (AssemblyAI)
 ├── /end             POST   Kết thúc phiên phỏng vấn
 │
 ├── /simli/
 │    ├── /get-session-token   POST  Simli session token
 │    └── /get-ice-servers     GET   WebRTC ICE servers
 │
 ├── /embeddings/
 │    ├── /query-embedding     POST  Gemini text embedding  🔒
 │    └── /similar-jobs        POST  MongoDB $vectorSearch  🔒
 │
 ├── /interactions             POST  Ghi tương tác user-job  🔒
 ├── /recommendations/{id}     GET   Gợi ý việc làm         🔒
 ├── /retrain                  POST  Trigger full retrain   🔒
 ├── /partial-update           POST  Incremental update     🔒
 └── /health                   GET   Model status           🔒

🔒 = Yêu cầu header X-Internal-Secret
```
