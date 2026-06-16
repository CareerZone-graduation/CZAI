# CareerZoneAI – AI Backend (Python/FastAPI)

## Architecture

FastAPI app serving AI-powered features for CareerZone: **AI interview** and **personalized job recommendations (LightFM)**. API prefix `/api/v1` (set in `app/core/config.py`). This is a **companion microservice** — the main backend is Node.js/Express; this Python service handles AI/ML workloads.

### Layer structure

```
app/main.py                        → FastAPI app, CORS, lifespan (startup/shutdown), router mount
app/core/config.py                 → pydantic-settings Settings (all env vars)
app/core/database.py               → Single Motor client (async get_db + sync get_sync_db via .delegate)
app/api/v1/router.py               → Top-level APIRouter; sub-routers per domain
app/api/v1/endpoints/              → Route handlers (thin controllers)
app/services/                      → Business logic & external API wrappers
app/services/recommendation/       → LightFM recommendation engine (model_manager, feature_engineering, data_loader, scheduler, evaluator)
app/models/                        → Pydantic request/response schemas
app/utils/                         → Shared utilities (text normalization, skill synonyms, province mapping)
```

**Endpoints → Services → External APIs** is the standard data flow. Endpoints stay thin; heavy logic in `app/services/`.

### Key domains

| Domain | Endpoint prefix | Purpose |
|--------|----------------|---------|
| Interview | `/api/v1/chat`, `/tts`, `/transcribe`, `/end` | AI interview loop (LLM → TTS → stream to client) |
| Simli | `/api/v1/simli/` | Session tokens & ICE servers for Simli AI avatar |
| Embeddings | `/api/v1/embeddings/query-embedding` | Generate text embeddings via Gemini API |
| Similar Jobs | `/api/v1/embeddings/similar-jobs` | MongoDB Atlas `$vectorSearch` for job similarity |
| Recommendations | `/api/v1/recommendations/{user_id}` | Personalized job recommendations (LightFM hybrid model) |
| Interactions | `/api/v1/interactions` | Record user-job interactions (VIEW/SAVE/APPLY) for recommendation engine |
| Rec Admin | `/api/v1/retrain`, `/partial-update`, `/health` | Trigger retraining, check model status |

### Internal-only endpoints

- `/embeddings/query-embedding`, `/embeddings/similar-jobs` — protected by `X-Internal-Secret` header vs `settings.INTERNAL_API_KEY`
- `/interactions`, `/recommendations/*`, `/retrain`, `/partial-update` — called by Node.js backend, protected by same `X-Internal-Secret`

## Recommendation system (LightFM)

Hybrid collaborative filtering + content-based using **LightFM**. Lives in `app/services/recommendation/`.

### Key concepts
- **Shared feature namespace**: `skill:python`, `province:ho_chi_minh`, `salary:10m_15m`, `category:IT`, `worktype:REMOTE`, `contracttype:FULL_TIME`, `experience:SENIOR_LEVEL` — same tags used for both user features and job features, enabling cold-start handling
- **Weighted interactions**: `VIEW=1.0`, `SAVE=2.5`, `APPLY=5.0` (configurable in settings)
- **Scheduling**: APScheduler runs daily full retrain (2:00 AM) + partial `fit_partial` every 30 min
- **Cold-start**: New users get recommendations from profile features (manual embedding computation); fallback to popular jobs if no profile
- **Model persistence**: Saved via `joblib` to `./models/` directory (model, dataset, feature matrices, metadata)

### Module map
- `model_manager.py` — `RecommendationEngine` singleton: train, predict, cold-start, persistence
- `feature_engineering.py` — Extract/normalize features from jobs & candidates into shared namespace tags
- `data_loader.py` — MongoDB queries for interactions, jobs, candidates, popular jobs
- `scheduler.py` — APScheduler setup (full retrain + partial update cron jobs)
- `evaluator.py` — Offline evaluation (precision@K, recall@K, AUC, MRR, hit rate, coverage)
- `text_utils.py` — Skill synonym normalization, Vietnamese province mapping, salary bucketing (in `app/utils/`)

### MongoDB collections (recommendation)
- `jobs` — shared with Node.js backend (read-only)
- `candidateprofiles` — shared with Node.js backend (read-only)
- `interactions` — managed by this service: `{userId, jobId, type: "VIEW"|"SAVE"|"APPLY", createdAt}`

## External services & API keys

All keys loaded via `.env` → `pydantic-settings` in `app/core/config.py`:

- **LLM**: OpenAI SDK pointed at **GitHub Models** (`models.github.ai/inference`, model `gpt-4o`), keyed by `GITHUB_TOKEN`
- **TTS**: ElevenLabs (direct REST streaming in `interview.py` + SDK in `tts_service.py`)
- **STT**: AssemblyAI (upload → transcribe → poll in `stt_service.py`)
- **Avatar**: Simli AI (`simli.py` proxies token requests)
- **Embeddings**: Google Gemini Embedding API (`gemini-embedding-001`)
- **Storage**: Cloudinary (audio upload as `video` resource type)
- **Database**: MongoDB — single Motor client; async `get_db()` for endpoints, sync `get_sync_db()` (via Motor's `.delegate`) for background training threads
- **Recommendation ML**: LightFM (in-process, no external API)

## Conventions

- **Language**: Comments, prompts, and AI responses in **Vietnamese**. Keep user-facing strings in Vietnamese.
- **Request/response models**: `app/models/` with **camelCase** Pydantic fields matching JS frontend: `sessionId`, `isStart`, `audioData`, `userId`, `jobId`.
- **Async**: Endpoints are `async def`. Use `httpx.AsyncClient` for HTTP; blocking calls (Cloudinary, LightFM training) wrapped with `run_in_executor`. Use Motor (async) for DB in endpoints; background training threads use `get_sync_db()` (Motor's underlying PyMongo via `.delegate`).
- **Session state**: Interview chat history in-memory dict keyed by `sessionId` (not persistent).
- **Streaming**: `/chat` returns `StreamingResponse` of PCM16 audio with AI text in URL-encoded `X-AI-Response` header.
- **Error handling**: `HTTPException` with `400` for client errors, `5xx` for server/upstream failures.
- **Lifespan**: `app/main.py` uses FastAPI `lifespan` context manager for startup (connect Motor, load/train model, start scheduler) and shutdown (stop scheduler, close Motor).
- **Text normalization**: Free-text fields (skills, provinces, salary) are normalized via `app/utils/text_utils.py` — skill synonyms (`"ReactJS"` → `"react"`), province aliases (`"TP.HCM"` → `"ho_chi_minh"`), salary bucketing (`15M VND` → `"10m_15m"`).

## Development

```bash
# Activate venv & run
.venv\Scripts\Activate.ps1          # Windows
uvicorn app.main:app --reload       # Runs on :8000
```

- No test suite currently. When adding tests, use `pytest` + `httpx` (`TestClient`).
- Docs at `/docs` (Swagger) and `/redoc`.
- Docker: `docker build -t czai . && docker run -p 8000:8000 --env-file .env czai`
- Model artifacts saved to `./models/` — gitignored, rebuilt on first startup if missing.

## Adding new features

1. **New endpoint**: Create file in `app/api/v1/endpoints/`, define Pydantic models in `app/models/`, register sub-router in `app/api/v1/router.py`.
2. **New external service**: Add API key to `Settings` in `config.py`, create service module in `app/services/`, call from endpoint.
3. **New env var**: Add field to `Settings` class — pydantic-settings auto-loads from `.env`.
4. **New recommendation feature**: Add to shared namespace in `feature_engineering.py`, update `text_utils.py` if normalization needed. Model will pick it up on next retrain.

## Integration plan: RECOMMEND_SYS → this workspace

Merging the standalone `RECOMMEND_SYS/` project into this codebase following existing conventions:

### File mapping

| RECOMMEND_SYS source | Target in this workspace | Action |
|---|---|---|
| `app/config.py` | `app/core/config.py` | Merge recommendation settings into existing `Settings` class |
| `app/db/mongodb.py` | `app/core/database.py` | Single Motor client: `get_db()` (async) + `get_sync_db()` (via delegate) |
| `app/api/routes.py` | `app/api/v1/endpoints/recommendation.py` | New endpoint file, register in `router.py` |
| `app/api/schemas.py` | `app/models/recommendation.py` | New Pydantic models file |
| `app/core/model_manager.py` | `app/services/recommendation/model_manager.py` | Move as-is into recommendation service package |
| `app/core/feature_engineering.py` | `app/services/recommendation/feature_engineering.py` | Move as-is |
| `app/core/data_loader.py` | `app/services/recommendation/data_loader.py` | Move as-is, update DB imports |
| `app/core/scheduler.py` | `app/services/recommendation/scheduler.py` | Move as-is |
| `app/core/evaluator.py` | `app/services/recommendation/evaluator.py` | Move as-is |
| `app/utils/text_utils.py` | `app/utils/text_utils.py` | New utils package |
| `app/main.py` (lifespan) | `app/main.py` | Merge lifespan hooks (DB connect, model load, scheduler start/stop) |
| `requirements.txt` | `requirements.txt` | Add: `lightfm-next`, `numpy`, `scipy`, `motor`, `apscheduler`, `joblib`, `unidecode` |
| `.env.example` | `.env` | Add recommendation env vars (`MODEL_DIR`, `RETRAIN_HOUR`, etc.) |

### Step-by-step integration order

1. **Dependencies**: Add new packages to `requirements.txt` and `pip install`
2. **Utils**: Create `app/utils/__init__.py` + `app/utils/text_utils.py`
3. **Config**: Merge recommendation settings into `app/core/config.py` `Settings` class
4. **Database**: Single Motor client in `app/core/database.py` — async `get_db()` for endpoints, sync `get_sync_db()` via Motor's `.delegate` for training threads
5. **Services**: Create `app/services/recommendation/` package — move `data_loader`, `feature_engineering`, `model_manager`, `scheduler`, `evaluator`; update all internal imports to use `app.core.config`, `app.core.database`, `app.utils.text_utils`
6. **Models**: Create `app/models/recommendation.py` with Pydantic schemas
7. **Endpoints**: Create `app/api/v1/endpoints/recommendation.py`, register in `router.py` with prefix `/recommendations` or similar
8. **Lifespan**: Update `app/main.py` to use FastAPI `lifespan` — add Motor connect/disconnect, model init, scheduler start/stop
9. **Dockerfile**: Ensure `models/` dir is created; add to `.dockerignore` if needed
10. **Test**: Verify `/docs` shows new endpoints, health check returns model status
