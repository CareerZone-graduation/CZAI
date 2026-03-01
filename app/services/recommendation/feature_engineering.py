"""
Feature engineering: extract user-features and item-features for LightFM.

SHARED NAMESPACE strategy:
  - skill:xxx          — shared between user skills and job required skills
  - province:xxx       — shared between user preferred locations and job location
  - salary:xxx         — shared salary bucket
  - category:xxx       — shared between user preferred categories and job category
  - worktype:xxx       — shared between user work preferences and job work type
  - contracttype:xxx   — shared between user contract preferences and job type
  - experience:xxx     — shared between user experience level and job experience

This enables LightFM to learn that e.g. a user with skill:python is likely
to prefer jobs with skill:python — critical for cold-start scenarios.
"""

from __future__ import annotations

import logging
from typing import Any

from app.utils.text_utils import normalize_province, normalize_skill, salary_bucket

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# Item (Job) features
# ═══════════════════════════════════════════════════════════════════════════════

def extract_job_features(job: dict[str, Any]) -> list[str]:
    """
    Extract a list of feature tags from a single job document.

    Returns:
        List of feature strings, e.g. ["category:IT", "skill:python", ...]
    """
    features: list[str] = []

    # ── Category (enum) ──────────────────────────────────────────────────────
    cat = job.get("category")
    if cat:
        features.append(f"category:{cat}")

    # ── Job type / contract type (enum) ──────────────────────────────────────
    jtype = job.get("type")
    if jtype:
        features.append(f"contracttype:{jtype}")

    # ── Work type (enum) ─────────────────────────────────────────────────────
    wtype = job.get("workType")
    if wtype:
        features.append(f"worktype:{wtype}")

    # ── Experience level (enum) ──────────────────────────────────────────────
    exp = job.get("experience")
    if exp:
        features.append(f"experience:{exp}")

    # ── Area (enum, optional) ────────────────────────────────────────────────
    area = job.get("area")
    if area:
        features.append(f"area:{area}")

    # ── Skills (free-text list) ──────────────────────────────────────────────
    skills = job.get("skills") or []
    for raw_skill in skills:
        normed = normalize_skill(raw_skill)
        if normed:
            features.append(f"skill:{normed}")

    # ── Location/province (free-text) ────────────────────────────────────────
    location = job.get("location") or {}
    province = location.get("province", "")
    if province:
        normed_prov = normalize_province(province)
        if normed_prov:
            features.append(f"province:{normed_prov}")

    # ── Salary bucket ────────────────────────────────────────────────────────
    min_sal = _parse_decimal(job.get("minSalary"))
    max_sal = _parse_decimal(job.get("maxSalary"))
    if min_sal or max_sal:
        avg = 0.0
        if min_sal and max_sal:
            avg = (min_sal + max_sal) / 2
        elif min_sal:
            avg = min_sal
        elif max_sal:
            avg = max_sal
        bucket = salary_bucket(avg)
        features.append(f"salary:{bucket}")
    else:
        features.append("salary:negotiable")

    return features


# ═══════════════════════════════════════════════════════════════════════════════
# User (Candidate) features
# ═══════════════════════════════════════════════════════════════════════════════

def extract_candidate_features(candidate: dict[str, Any]) -> list[str]:
    """
    Extract a list of feature tags from a single candidate profile document.

    Returns:
        List of feature strings using the shared namespace.
    """
    features: list[str] = []

    # ── Skills (free-text) ───────────────────────────────────────────────────
    skills = candidate.get("skills") or []
    for skill_obj in skills:
        name = skill_obj.get("name", "") if isinstance(
            skill_obj, dict) else str(skill_obj)
        normed = normalize_skill(name)
        if normed:
            features.append(f"skill:{normed}")

    # ── Preferred categories (enum list) ─────────────────────────────────────
    pref_cats = candidate.get("preferredCategories") or []
    for cat in pref_cats:
        if cat:
            features.append(f"category:{cat}")

    # ── Preferred locations (free-text provinces) ────────────────────────────
    pref_locs = candidate.get("preferredLocations") or []
    for loc in pref_locs:
        province = loc.get("province", "") if isinstance(
            loc, dict) else str(loc)
        normed_prov = normalize_province(province)
        if normed_prov:
            features.append(f"province:{normed_prov}")

    # ── Work preferences ─────────────────────────────────────────────────────
    work_prefs = candidate.get("workPreferences") or {}

    work_types = work_prefs.get("workTypes") or []
    for wt in work_types:
        if wt:
            features.append(f"worktype:{wt}")

    contract_types = work_prefs.get("contractTypes") or []
    for ct in contract_types:
        if ct:
            features.append(f"contracttype:{ct}")

    exp_levels = work_prefs.get("experienceLevel") or []
    for el in exp_levels:
        if el:
            features.append(f"experience:{el}")

    # ── Expected salary ──────────────────────────────────────────────────────
    expected = candidate.get("expectedSalary") or {}
    min_sal = expected.get("min", 0) or 0
    max_sal = expected.get("max", 0) or 0
    if min_sal or max_sal:
        avg = 0.0
        if min_sal and max_sal:
            avg = (min_sal + max_sal) / 2
        elif min_sal:
            avg = min_sal
        elif max_sal:
            avg = max_sal
        bucket = salary_bucket(avg)
        features.append(f"salary:{bucket}")

    return features


# ═══════════════════════════════════════════════════════════════════════════════
# Helpers to collect all unique feature names (for Dataset.fit)
# ═══════════════════════════════════════════════════════════════════════════════

def collect_all_feature_names(
    jobs: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
) -> tuple[set[str], set[str]]:
    """
    Scan all jobs and candidates to collect the set of unique feature tags.

    Returns:
        (user_feature_names, item_feature_names) — each a set of strings.
    """
    user_feature_names: set[str] = set()
    item_feature_names: set[str] = set()

    for job in jobs:
        feats = extract_job_features(job)
        item_feature_names.update(feats)

    for cand in candidates:
        feats = extract_candidate_features(cand)
        user_feature_names.update(feats)

    logger.info(
        "Collected %d unique user features, %d unique item features",
        len(user_feature_names),
        len(item_feature_names),
    )
    return user_feature_names, item_feature_names


# ═══════════════════════════════════════════════════════════════════════════════
# Build feature tuples for Dataset.build_*_features()
# ═══════════════════════════════════════════════════════════════════════════════

def build_user_feature_tuples(
    candidates: list[dict[str, Any]],
    user_id_field: str = "userId",
) -> list[tuple[str, list[str]]]:
    """Build list of (user_id, [feature_list]) for Dataset.build_user_features()."""
    result = []
    for cand in candidates:
        uid = str(cand.get(user_id_field, cand.get("_id", "")))
        feats = extract_candidate_features(cand)
        if uid and feats:
            result.append((uid, feats))
    return result


def build_item_feature_tuples(
    jobs: list[dict[str, Any]],
) -> list[tuple[str, list[str]]]:
    """Build list of (item_id, [feature_list]) for Dataset.build_item_features()."""
    result = []
    for job in jobs:
        jid = str(job.get("_id", ""))
        feats = extract_job_features(job)
        if jid and feats:
            result.append((jid, feats))
    return result


# ═══════════════════════════════════════════════════════════════════════════════
# Internal helpers
# ═══════════════════════════════════════════════════════════════════════════════

def _parse_decimal(value) -> float | None:
    """Parse MongoDB Decimal128 or string salary values to float."""
    if value is None:
        return None
    try:
        return float(str(value))
    except (ValueError, TypeError):
        return None
