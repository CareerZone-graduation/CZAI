# GitHub Copilot Instructions for CZAI

## Project Overview

CareerZoneAI (CZAI) is a FastAPI-based backend that powers an AI-driven mock interview platform. It integrates several external services for voice synthesis, speech recognition, AI conversation, and avatar generation.

## Tech Stack

- **Framework:** FastAPI (Python 3.10+)
- **AI / LLM:** GitHub Models (`gpt-4o`) via OpenAI-compatible client (`app/services/llm_service.py`)
- **Text-to-Speech:** ElevenLabs (`app/services/tts_service.py`)
- **Speech-to-Text:** AssemblyAI (`app/services/stt_service.py`)
- **Avatar:** Simli API (`app/api/v1/endpoints/simli.py`)
- **Media Storage:** Cloudinary (`app/services/cloudinary_service.py`)
- **Database:** MongoDB via PyMongo (`app/core/database.py`)
- **Embeddings / Similarity:** Custom embedding service (`app/api/v1/endpoints/embedding.py`, `app/api/v1/endpoints/similar_jobs.py`)
- **Config:** `pydantic-settings` with `.env` file (`app/core/config.py`)

## Project Structure

```
app/
├── main.py              # FastAPI app entry point, CORS middleware, router registration
├── core/
│   ├── config.py        # Settings loaded from environment variables
│   └── database.py      # MongoDB connection
├── api/v1/
│   ├── router.py        # Aggregates all API routers
│   └── endpoints/
│       ├── interview.py    # Interview chat endpoints
│       ├── simli.py        # Simli avatar endpoints
│       ├── embedding.py    # Embedding creation endpoints
│       └── similar_jobs.py # Job similarity search endpoints
├── models/
│   ├── chat.py          # Pydantic models for chat/interview
│   └── embedding.py     # Pydantic models for embeddings
└── services/
    ├── llm_service.py       # LLM conversation logic (GitHub Models / GPT-4o)
    ├── tts_service.py       # Text-to-Speech via ElevenLabs
    ├── stt_service.py       # Speech-to-Text via AssemblyAI
    └── cloudinary_service.py # Media upload/management
```

## Coding Conventions

- Use **async/await** for all FastAPI route handlers and I/O-bound service calls.
- Use **Pydantic models** (defined in `app/models/`) for all request and response bodies.
- Place business logic in `app/services/`, keeping endpoint files thin (routing only).
- Read all configuration from `app.core.config.settings`; never hardcode secrets or API keys.
- Add new API routes in `app/api/v1/endpoints/`, then register them in `app/api/v1/router.py`.
- Follow existing naming conventions: snake_case for files, functions, and variables.
- Keep responses concise and in Vietnamese where the product is consumer-facing.

## Environment Variables

All required variables are defined in `app/core/config.py`. Copy `.env.example` to `.env` and populate the values before running locally:

| Variable | Purpose |
|---|---|
| `GITHUB_TOKEN` | GitHub Models API key for LLM |
| `ELEVENLABS_API_KEY` | ElevenLabs TTS |
| `ASSEMBLYAI_API_KEY` | AssemblyAI STT |
| `SIMLI_API_KEY` | Simli avatar API |
| `GEMINI_API_KEY` | Google Gemini (reserved) |
| `MONGO_URI` | MongoDB connection string |
| `CLOUDINARY_CLOUD_NAME` | Cloudinary cloud name |
| `CLOUDINARY_API_KEY` | Cloudinary API key |
| `CLOUDINARY_API_SECRET` | Cloudinary API secret |
| `INTERNAL_API_KEY` | Internal service authentication |

## Running Locally

```bash
python -m venv venv && source venv/bin/activate  # or .\venv\Scripts\Activate.ps1 on Windows
pip install -r requirements.txt
cp .env.example .env  # then fill in real values
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

API docs available at `http://localhost:8000/docs`.

## Key Patterns

- **Session management:** In-memory dictionaries (`interview_sessions`, `interview_topics`) in `llm_service.py` keyed by `session_id`.
- **Streaming audio:** TTS responses may be streamed; check existing endpoints for chunked response patterns.
- **CORS:** Configured in `main.py` to allow local development origins. Update `BACKEND_CORS_ORIGINS` in `config.py` for production.
