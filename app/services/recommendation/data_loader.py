"""
Data loader: query MongoDB (sync) and return data structures
ready for feature engineering and LightFM Dataset building.

All functions here use the sync PyMongo handle obtained from
Motor's underlying client (via get_sync_db) because they run
inside background threads (scheduler / manual retrain), not
inside the async FastAPI event-loop.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from app.core.config import settings
from app.core.database import get_sync_db

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# Interactions
# ═══════════════════════════════════════════════════════════════════════════════

WEIGHT_MAP: dict[str, float] = {
    "VIEW": settings.WEIGHT_VIEW,
    "SAVE": settings.WEIGHT_SAVE,
    "APPLY": settings.WEIGHT_APPLY,
}


def load_interactions(
    days: int | None = None,
    since: datetime | None = None,
) -> tuple[list[tuple[str, str, float]], set[str], set[str], dict[str, set[str]], dict[str, set[str]]]:
    """
    Load interactions from MongoDB.

    Returns:
        - weighted_interactions: list of (user_id, job_id, weight)
        - user_ids: set of all user ids that have interactions
        - job_ids:  set of all job ids that have been interacted with
        - applied_jobs: dict mapping user_id -> set of job_ids they APPLYed
        - saved_jobs:   dict mapping user_id -> set of job_ids they SAVEd
    """
    db = get_sync_db()
    collection = db[settings.INTERACTIONS_COLLECTION]

    if since is None:
        d = days or settings.INTERACTION_DAYS
        since = datetime.now(timezone.utc) - timedelta(days=d)

    query = {"createdAt": {"$gte": since}}
    cursor = collection.find(query, {"userId": 1, "jobId": 1, "type": 1})

    # Accumulate weights per (user, job) pair
    pair_weights: dict[tuple[str, str], float] = defaultdict(float)
    user_ids: set[str] = set()
    job_ids: set[str] = set()
    applied_jobs: dict[str, set[str]] = defaultdict(set)
    saved_jobs: dict[str, set[str]] = defaultdict(set)

    count = 0
    for doc in cursor:
        uid = str(doc["userId"])
        jid = str(doc["jobId"])
        itype = doc.get("type", "VIEW")
        weight = WEIGHT_MAP.get(itype, 1.0)

        pair_weights[(uid, jid)] += weight
        user_ids.add(uid)
        job_ids.add(jid)
        count += 1

        if itype == "APPLY":
            applied_jobs[uid].add(jid)
        elif itype == "SAVE":
            saved_jobs[uid].add(jid)

    weighted = [(uid, jid, w) for (uid, jid), w in pair_weights.items()]
    logger.info(
        "Loaded %d raw interactions → %d unique (user, job) pairs, "
        "%d users, %d jobs",
        count, len(weighted), len(user_ids), len(job_ids),
    )
    return weighted, user_ids, job_ids, dict(applied_jobs), dict(saved_jobs)


def load_interactions_since(since: datetime):
    """Convenience for partial updates — load interactions since a timestamp."""
    return load_interactions(since=since)


# ═══════════════════════════════════════════════════════════════════════════════
# Jobs
# ═══════════════════════════════════════════════════════════════════════════════

def load_active_jobs() -> list[dict[str, Any]]:
    """Load all ACTIVE jobs from MongoDB."""
    db = get_sync_db()
    collection = db[settings.JOBS_COLLECTION]

    projection = {
        "title": 1,
        "category": 1,
        "type": 1,
        "workType": 1,
        "experience": 1,
        "area": 1,
        "skills": 1,
        "location.province": 1,
        "minSalary": 1,
        "maxSalary": 1,
        "status": 1,
    }

    jobs = list(collection.find({"status": "ACTIVE"}, projection))
    logger.info("Loaded %d active jobs", len(jobs))
    return jobs


# ═══════════════════════════════════════════════════════════════════════════════
# Candidates
# ═══════════════════════════════════════════════════════════════════════════════

def load_candidates(
    user_ids: set[str] | None = None,
    include_onboarded: bool = True,
) -> list[dict[str, Any]]:
    """
    Load candidate profiles from MongoDB.

    Args:
        user_ids: If provided, load only these users. If None, load all.
        include_onboarded: If True (full retrain), also load all onboarded
            users even if not in user_ids.
    """
    db = get_sync_db()
    collection = db[settings.CANDIDATES_COLLECTION]

    projection = {
        "userId": 1,
        "skills": 1,
        "preferredCategories": 1,
        "preferredLocations": 1,
        "workPreferences": 1,
        "expectedSalary": 1,
        "onboardingCompleted": 1,
    }

    if user_ids is not None:
        from bson import ObjectId

        oid_list = []
        for uid in user_ids:
            try:
                oid_list.append(ObjectId(uid))
            except Exception:
                pass

        conditions = [{"userId": {"$in": oid_list}}]
        if include_onboarded:
            conditions.append({"onboardingCompleted": True})
        query = {"$or": conditions}
    else:
        query = {}

    candidates = list(collection.find(query, projection))
    logger.info("Loaded %d candidate profiles", len(candidates))
    return candidates


# ═══════════════════════════════════════════════════════════════════════════════
# Popular jobs fallback
# ═══════════════════════════════════════════════════════════════════════════════

def get_popular_job_ids(limit: int = 20) -> list[str]:
    """
    Get the most interacted-with active jobs in the last N days.
    Used as a fallback for users with no profile data.
    """
    db = get_sync_db()
    since = datetime.now(timezone.utc) - \
        timedelta(days=settings.INTERACTION_DAYS)

    pipeline = [
        {"$match": {"createdAt": {"$gte": since}}},
        {
            "$group": {
                "_id": "$jobId",
                "score": {
                    "$sum": {
                        "$switch": {
                            "branches": [
                                {"case": {
                                    "$eq": ["$type", "APPLY"]}, "then": 5.0},
                                {"case": {
                                    "$eq": ["$type", "SAVE"]}, "then": 2.5},
                            ],
                            "default": 1.0,
                        }
                    }
                },
            }
        },
        {"$sort": {"score": -1}},
        {"$limit": limit},
    ]

    results = list(db[settings.INTERACTIONS_COLLECTION].aggregate(pipeline))
    return [str(r["_id"]) for r in results]
