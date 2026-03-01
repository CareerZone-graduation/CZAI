from __future__ import annotations

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.database import close_db, connect_db
from app.services.recommendation.model_manager import engine
from app.services.recommendation.scheduler import start_scheduler, stop_scheduler

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

_startup_executor = ThreadPoolExecutor(
    max_workers=1, thread_name_prefix="startup")


def _init_model_sync() -> None:
    """Blocking init: load saved model or run initial full retrain."""
    loaded = engine.load_from_disk()
    if not loaded:
        logger.info("No persisted model — running initial full retrain …")
        result = engine.full_retrain()
        logger.info("Initial retrain result: %s", result)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage startup and shutdown for all subsystems."""
    # ── Startup ──────────────────────────────────────────────────────────
    logger.info("Starting CareerZoneAI …")

    # 1. Connect MongoDB (Motor)
    db = await connect_db()
    logger.info("MongoDB connected (Motor)")

    # 2. Ensure indexes on interactions collection
    try:
        await db[settings.INTERACTIONS_COLLECTION].create_index(
            [("userId", 1), ("jobId", 1), ("type", 1)],
            name="idx_user_job_type",
        )
        await db[settings.INTERACTIONS_COLLECTION].create_index(
            [("createdAt", 1)],
            name="idx_created_at",
        )
        logger.info("Interaction indexes ensured")
    except Exception as e:
        logger.warning("Could not create indexes: %s", e)

    # 3. Load / train recommendation model in background thread
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(_startup_executor, _init_model_sync)

    # 4. Start scheduler (daily retrain + periodic partial update)
    start_scheduler()

    logger.info("CareerZoneAI is READY")

    yield

    # ── Shutdown ─────────────────────────────────────────────────────────
    logger.info("Shutting down CareerZoneAI …")
    stop_scheduler()
    await close_db()
    logger.info("Shutdown complete")


app = FastAPI(title=settings.PROJECT_NAME, lifespan=lifespan)

# Cấu hình CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.BACKEND_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)

# Đăng ký Router
app.include_router(api_router, prefix=settings.API_PREFIX)


@app.get("/")
def root():
    return {"message": "Welcome to CareerZoneAI Python Backend"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
