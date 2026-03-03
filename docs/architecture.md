# CareerZoneAI — Kiến trúc hệ thống (Architecture Spec)

> **Version:** 1.0 | **Date:** 2026-03-02

## 1. Tổng quan

CareerZoneAI là một **AI microservice** viết bằng Python/FastAPI, đóng vai trò companion cho backend chính Node.js/Express của hệ thống CareerZone. Service này xử lý toàn bộ workload AI/ML:

| Tính năng                     | Module                          | Công nghệ                     |
|------------------------------|---------------------------------|-------------------------------|
| AI Interview (hỏi-đáp)        | `services/llm_service.py`       | OpenAI GPT-4o (GitHub Models) |
| Text-to-Speech                | `services/tts_service.py`       | ElevenLabs API                |
| Speech-to-Text                | `services/stt_service.py`       | AssemblyAI API                |
| AI Avatar session             | `endpoints/simli.py`            | Simli AI API                  |
| Vector embedding              | `endpoints/embedding.py`        | Gemini Embedding API          |
| Similar Jobs (vector search)  | `endpoints/similar_jobs.py`     | MongoDB Atlas $vectorSearch   |
| Personalized Recommendations  | `services/recommendation/`      | LightFM (Hybrid CF + CB)      |

---

## 2. Sơ đồ luồng dữ liệu (Data Flow)

```
Client (Browser/App)
       │
       ▼
Node.js Backend (main backend)
       │ calls with X-Internal-Secret header
       ▼
CareerZoneAI FastAPI (:8000)
  /api/v1/
    ├── /chat                → LLM Service → ElevenLabs TTS → StreamingResponse (PCM16)
    ├── /tts                 → ElevenLabs SDK
    ├── /transcribe          → AssemblyAI STT
    ├── /end                 → Clear in-memory session
    ├── /simli/              → Simli AI API (token + ICE)
    ├── /embeddings/
    │   ├── /query-embedding → Gemini Embedding API
    │   └── /similar-jobs    → MongoDB Atlas $vectorSearch
    ├── /recommendations/{id}→ LightFM Engine (in-process)
    ├── /interactions        → MongoDB write
    ├── /retrain             → LightFM full retrain (background thread)
    ├── /partial-update      → LightFM fit_partial (background thread)
    └── /health              → Model status
```

---

## 3. Layer Stack

```
app/main.py
  └── FastAPI app (lifespan: DB connect / model load / scheduler start)
       └── CORS Middleware
            └── api_router (prefix: /api/v1)
                 ├── endpoints/interview.py
                 ├── endpoints/simli.py
                 ├── endpoints/embedding.py
                 ├── endpoints/similar_jobs.py
                 └── endpoints/recommendation.py
                      │
                      ▼
app/services/
  ├── llm_service.py          (OpenAI/GitHub Models)
  ├── tts_service.py          (ElevenLabs SDK)
  ├── stt_service.py          (AssemblyAI REST)
  ├── cloudinary_service.py   (Cloudinary)
  └── recommendation/
       ├── model_manager.py   (RecommendationEngine singleton)
       ├── feature_engineering.py
       ├── data_loader.py
       ├── scheduler.py
       └── evaluator.py

app/core/
  ├── config.py               (pydantic-settings — đọc từ .env)
  └── database.py             (Motor client — async get_db + sync get_sync_db)

app/models/                   (Pydantic request/response schemas)
app/utils/
  └── text_utils.py           (skill normalization, province mapping, salary bucketing)
```

---

## 4. Startup Lifecycle

Khi service khởi động (FastAPI `lifespan` context manager):

1. **Connect MongoDB** — Motor async client (`connect_db()`)
2. **Ensure indexes** — `interactions` collection: `idx_user_job_type`, `idx_created_at`
3. **Load / train model** — chạy trong background thread (`ThreadPoolExecutor`):
   - Thử load từ disk (`./models/`)
   - Nếu không có → chạy `full_retrain()`
4. **Start APScheduler**:
   - Full retrain: hằng ngày lúc `RETRAIN_HOUR:RETRAIN_MINUTE` (mặc định 2:00 AM)
   - Partial update: mỗi `PARTIAL_UPDATE_INTERVAL_MINUTES` phút (mặc định 30 phút)

Khi shutdown:
1. Stop scheduler
2. Đóng Motor client

---

## 5. Chiến lược Async / Concurrency

| Loại task                    | Cơ chế                                    |
|-----------------------------|-------------------------------------------|
| HTTP endpoints               | `async def` + Motor async                |
| Gọi HTTP ra ngoài            | `httpx.AsyncClient`                      |
| LightFM training             | `loop.run_in_executor(ThreadPoolExecutor)` |
| DB trong training threads    | `get_sync_db()` (Motor `.delegate` → PyMongo sync) |
| APScheduler jobs             | `AsyncIOScheduler` + executor             |
| Cloudinary upload            | `run_in_executor`                        |

---

## 6. Bảo mật

| Endpoint group                     | Auth mechanism               |
|------------------------------------|------------------------------|
| `/interactions`, `/recommendations` | `X-Internal-Secret` header = `INTERNAL_API_KEY` |
| `/retrain`, `/partial-update`, `/health` | `X-Internal-Secret` header |
| `/embeddings/query-embedding`, `/embeddings/similar-jobs` | `X-Internal-Secret` header |
| `/chat`, `/tts`, `/transcribe`, `/end` | Không auth (gọi từ client qua Node.js proxy) |
| `/simli/*` | Không auth (public session token proxy) |

HTTP `403 Forbidden` khi secret sai hoặc thiếu.

---

## 7. Environment Variables

Xem chi tiết trong [data-models.md](./data-models.md#environment-variables).

---

## 8. External Service Dependencies

| Service          | SDK/Client                   | Mục đích                        |
|-----------------|------------------------------|----------------------------------|
| OpenAI/GitHub Models | `openai` Python SDK       | LLM cho AI interview             |
| ElevenLabs       | REST + `elevenlabs` SDK      | TTS cho interview                |
| AssemblyAI       | REST (`httpx`)               | STT / transcription              |
| Simli AI         | REST (`requests`)            | Avatar session token + ICE       |
| Google Gemini    | REST (`httpx`)               | Text embedding (1536-dim)        |
| MongoDB Atlas    | `motor` (async Motor)         | Database + $vectorSearch         |
| Cloudinary       | `cloudinary` SDK             | Audio storage                    |
| LightFM          | In-process Python lib        | Recommendation model             |
