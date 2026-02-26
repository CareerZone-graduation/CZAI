from pymongo import MongoClient
from app.core.config import settings

_client = None

def get_db():
    """Get MongoDB database connection (lazy singleton)"""
    global _client
    if _client is None:
        _client = MongoClient(settings.MONGO_URI)
    return _client.get_default_database()
