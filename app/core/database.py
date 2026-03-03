from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from app.core.config import settings

# ── Single Motor client (provides both async & sync access) ──────────────────
_client: AsyncIOMotorClient | None = None
_db: AsyncIOMotorDatabase | None = None


async def connect_db() -> AsyncIOMotorDatabase:
    """Create / return the async Motor database connection."""
    global _client, _db
    if _client is None:
        _client = AsyncIOMotorClient(settings.MONGO_URI)
        _db = _client[settings.MONGO_DB_NAME]
    return _db


async def close_db() -> None:
    """Close the Motor client (also closes underlying sync PyMongo)."""
    global _client, _db
    if _client is not None:
        _client.close()
        _client = None
        _db = None


def get_db() -> AsyncIOMotorDatabase:
    """Return the async Motor database handle (must call connect_db first)."""
    if _db is None:
        raise RuntimeError("DB not connected. Call connect_db() first.")
    return _db


def get_sync_db():
    """Return sync PyMongo database from Motor's underlying client.

    Used ONLY by recommendation training threads (data_loader, model_manager)
    where async is not available. Motor wraps PyMongo internally —
    `client.delegate` exposes the underlying pymongo.MongoClient.
    """
    if _client is None:
        raise RuntimeError("DB not connected. Call connect_db() first.")
    return _client.delegate[settings.MONGO_DB_NAME]
