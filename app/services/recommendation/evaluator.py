"""
Model evaluator: đánh giá chất lượng LightFM model (standalone).

Hai chế độ:
  1. **current** — load model đã train từ disk, đánh giá trên toàn bộ
     interactions hiện tại (train metrics, nhanh).
  2. **split**   — chia data theo random, train model mới trên tập train,
     đánh giá trên tập test (offline evaluation, chính xác hơn).

Metrics: Precision@K, Recall@K, AUC, MRR, Hit Rate@K, Coverage@K.

Usage:
  python -m app.services.recommendation.evaluator --mode current
  python -m app.services.recommendation.evaluator --mode split --test-ratio 0.2 --k 10
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import joblib
import numpy as np
from lightfm import LightFM
from lightfm.data import Dataset
from lightfm.evaluation import auc_score, precision_at_k, recall_at_k, reciprocal_rank
from scipy.sparse import coo_matrix, csr_matrix

from app.core.config import settings
from app.services.recommendation.data_loader import (
    load_active_jobs,
    load_candidates,
    load_interactions,
)
from app.services.recommendation.feature_engineering import (
    build_item_feature_tuples,
    build_user_feature_tuples,
    collect_all_feature_names,
)

logger = logging.getLogger(__name__)

DEFAULT_K = 10
DEFAULT_TEST_RATIO = 0.2

_MODEL_FILE = "lightfm_model.joblib"
_DATASET_FILE = "lightfm_dataset.joblib"
_META_FILE = "lightfm_meta.joblib"
_MATRICES_FILE = "lightfm_matrices.joblib"


def _safe_mean(arr: np.ndarray) -> float:
    """Tính mean, bỏ qua NaN/Inf, trả 0.0 nếu rỗng."""
    finite = arr[np.isfinite(arr)]
    return float(finite.mean()) if len(finite) > 0 else 0.0


def _load_model_from_disk(
    model_dir: Path | None = None,
) -> tuple[LightFM, Dataset, Any, Any] | None:
    """Load model + dataset + feature matrices từ disk."""
    model_dir = model_dir or settings.model_path
    model_file = model_dir / _MODEL_FILE
    dataset_file = model_dir / _DATASET_FILE
    matrices_file = model_dir / _MATRICES_FILE

    if not model_file.exists() or not dataset_file.exists():
        logger.error("Model files not found at %s", model_dir)
        return None

    model = joblib.load(model_file)
    ds = joblib.load(dataset_file)

    user_features_mat = None
    item_features_mat = None
    if matrices_file.exists():
        matrices = joblib.load(matrices_file)
        user_features_mat = matrices.get("user_features_matrix")
        item_features_mat = matrices.get("item_features_matrix")
    else:
        logger.warning("Matrices file not found — rebuilding from DB")
        jobs = load_active_jobs()
        candidates = load_candidates(include_onboarded=True)
        user_feat_tuples = build_user_feature_tuples(candidates)
        item_feat_tuples = build_item_feature_tuples(jobs)
        user_features_mat = ds.build_user_features(
            user_feat_tuples, normalize=False)
        item_features_mat = ds.build_item_features(
            item_feat_tuples, normalize=False)

    return model, ds, user_features_mat, item_features_mat


def _random_split_interactions(
    weighted_interactions: list[tuple[str, str, float]],
    test_ratio: float = DEFAULT_TEST_RATIO,
    seed: int = 42,
) -> tuple[list[tuple[str, str, float]], list[tuple[str, str, float]]]:
    """Random split per user, ensuring each user has ≥1 train interaction."""
    rng = np.random.RandomState(seed)

    user_interactions: dict[str, list[tuple[str, str, float]]] = {}
    for uid, jid, w in weighted_interactions:
        user_interactions.setdefault(uid, []).append((uid, jid, w))

    train_data: list[tuple[str, str, float]] = []
    test_data: list[tuple[str, str, float]] = []

    for uid, interactions in user_interactions.items():
        if len(interactions) <= 1:
            train_data.extend(interactions)
            continue

        n_test = max(1, int(len(interactions) * test_ratio))
        indices = rng.permutation(len(interactions))
        test_indices = set(indices[:n_test])

        for i, inter in enumerate(interactions):
            if i in test_indices:
                test_data.append(inter)
            else:
                train_data.append(inter)

    return train_data, test_data


def _compute_coverage(
    model: LightFM, test_interactions: csr_matrix,
    user_features, item_features, k: int, n_items: int,
) -> float:
    """Catalog coverage: % unique items trong top-K trên test users."""
    recommended_items: set[int] = set()
    test_csr = test_interactions.tocsr()

    for user_idx in range(test_csr.shape[0]):
        if test_csr[user_idx].nnz == 0:
            continue
        item_ids = np.arange(n_items, dtype=np.int32)
        scores = model.predict(
            user_ids=user_idx, item_ids=item_ids,
            user_features=user_features, item_features=item_features,
        )
        top_k = np.argsort(-scores)[:k]
        recommended_items.update(top_k.tolist())

    return len(recommended_items) / n_items if n_items > 0 else 0.0


def _compute_hit_rate(
    model: LightFM, train_interactions: csr_matrix,
    test_interactions: csr_matrix, user_features, item_features, k: int,
) -> float:
    """Hit Rate@K: % users có ít nhất 1 item đúng trong top-K."""
    test_csr = test_interactions.tocsr()
    train_csr = train_interactions.tocsr()
    n_items = test_csr.shape[1]
    hits = 0
    total = 0

    for user_idx in range(test_csr.shape[0]):
        if test_csr[user_idx].nnz == 0:
            continue
        total += 1

        item_ids = np.arange(n_items, dtype=np.int32)
        scores = model.predict(
            user_ids=user_idx, item_ids=item_ids,
            user_features=user_features, item_features=item_features,
        )
        train_items = set(train_csr[user_idx].indices)
        for idx in train_items:
            scores[idx] = -np.inf

        top_k = set(np.argsort(-scores)[:k].tolist())
        test_items = set(test_csr[user_idx].indices)
        if top_k & test_items:
            hits += 1

    return hits / total if total > 0 else 0.0


def evaluate_current_model(k: int = DEFAULT_K) -> dict[str, Any]:
    """Load model từ disk, đánh giá trên toàn bộ interactions (train metrics)."""
    t0 = time.time()
    logger.info("═══ Evaluating CURRENT model (k=%d) ═══", k)

    loaded = _load_model_from_disk()
    if loaded is None:
        return {"status": "error", "reason": "model_not_found"}

    model, ds, user_features_mat, item_features_mat = loaded

    weighted, _, _, _ = load_interactions()
    if not weighted:
        return {"status": "error", "reason": "no_interactions"}

    n_raw = len(weighted)
    user_id_map, _, item_id_map, _ = ds.mapping()
    data = [
        (uid, jid, w) for uid, jid, w in weighted
        if uid in user_id_map and jid in item_id_map
    ]
    if not data:
        return {"status": "error", "reason": "no_interactions_after_filtering"}

    n_filtered_out = n_raw - len(data)
    if n_filtered_out > 0:
        logger.warning(
            "Filtered out %d / %d interactions (user/job not in model dataset). "
            "This usually means new users/jobs appeared since last retrain, "
            "or jobs became inactive.",
            n_filtered_out, n_raw,
        )

    interactions_mat, _ = ds.build_interactions(data)
    n_inter = len(data)
    interactions_csr = interactions_mat.tocsr()

    prec = precision_at_k(
        model, interactions_csr,
        user_features=user_features_mat, item_features=item_features_mat,
        k=k, num_threads=settings.MODEL_NUM_THREADS,
    )
    rec = recall_at_k(
        model, interactions_csr,
        user_features=user_features_mat, item_features=item_features_mat,
        k=k, num_threads=settings.MODEL_NUM_THREADS,
    )
    auc = auc_score(
        model, interactions_csr,
        user_features=user_features_mat, item_features=item_features_mat,
        num_threads=settings.MODEL_NUM_THREADS,
    )
    rr = reciprocal_rank(
        model, interactions_csr,
        user_features=user_features_mat, item_features=item_features_mat,
        num_threads=settings.MODEL_NUM_THREADS,
    )

    elapsed = time.time() - t0
    metrics = {
        "status": "success",
        "mode": "current",
        "k": k,
        f"precision@{k}": round(_safe_mean(prec), 4),
        f"recall@{k}": round(_safe_mean(rec), 4),
        "auc": round(_safe_mean(auc), 4),
        "mrr": round(_safe_mean(rr), 4),
        "n_users_evaluated": int(np.sum(np.isfinite(prec))),
        "n_interactions": n_inter,
        "n_raw_interactions": n_raw,
        "n_filtered_out": n_filtered_out,
        "elapsed_seconds": round(elapsed, 2),
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
    }
    logger.info("═══ Current model evaluation complete ═══ %s", metrics)
    return metrics


def evaluate_train_test_split(
    test_ratio: float = DEFAULT_TEST_RATIO,
    k: int = DEFAULT_K,
) -> dict[str, Any]:
    """
    Offline evaluation: chia data → train/test → train model mới → đánh giá.
    Tạo model tạm — KHÔNG ảnh hưởng model đang chạy.
    """
    t0 = time.time()
    logger.info(
        "═══ Starting TRAIN/TEST evaluation (ratio=%.2f, k=%d) ═══",
        test_ratio, k,
    )

    weighted, user_ids, job_ids, _ = load_interactions()
    jobs = load_active_jobs()
    candidates = load_candidates(user_ids=user_ids, include_onboarded=True)

    if not weighted:
        return {"status": "skipped", "reason": "no_interactions", "elapsed_seconds": 0}
    if not jobs:
        return {"status": "skipped", "reason": "no_active_jobs", "elapsed_seconds": 0}

    train_data, test_data = _random_split_interactions(weighted, test_ratio)
    logger.info("Split: %d train, %d test interactions",
                len(train_data), len(test_data))

    if not test_data:
        return {
            "status": "skipped",
            "reason": "not_enough_data_for_split",
            "elapsed_seconds": round(time.time() - t0, 2),
        }

    all_job_ids = [str(j["_id"]) for j in jobs]
    all_user_ids = {str(c.get("userId", c.get("_id", ""))) for c in candidates}
    all_user_ids.update(user_ids)

    user_feat_names, item_feat_names = collect_all_feature_names(
        jobs, candidates)

    ds = Dataset()
    ds.fit(
        users=all_user_ids,
        items=all_job_ids,
        user_features=user_feat_names,
        item_features=item_feat_names,
    )

    known_job_ids = set(all_job_ids)
    known_user_ids = all_user_ids
    n_train_before = len(train_data)
    n_test_before = len(test_data)
    train_data = [
        (uid, jid, w) for uid, jid, w in train_data
        if uid in known_user_ids and jid in known_job_ids
    ]
    test_data = [
        (uid, jid, w) for uid, jid, w in test_data
        if uid in known_user_ids and jid in known_job_ids
    ]

    n_filtered = (n_train_before - len(train_data)) + (n_test_before - len(test_data))
    if n_filtered > 0:
        logger.warning(
            "Filtered out %d interactions referencing inactive/unknown jobs or users "
            "(train: %d→%d, test: %d→%d)",
            n_filtered,
            n_train_before, len(train_data),
            n_test_before, len(test_data),
        )

    if not test_data:
        return {
            "status": "skipped",
            "reason": "all_test_interactions_filtered_out",
            "elapsed_seconds": round(time.time() - t0, 2),
        }

    n_u, n_i = ds.interactions_shape()

    if train_data:
        train_mat, train_weights = ds.build_interactions(train_data)
    else:
        train_mat = coo_matrix((n_u, n_i), dtype=np.float32)
        train_weights = coo_matrix((n_u, n_i), dtype=np.float32)

    if test_data:
        test_mat, _ = ds.build_interactions(test_data)
    else:
        test_mat = coo_matrix((n_u, n_i), dtype=np.float32)

    user_feat_tuples = build_user_feature_tuples(candidates)
    item_feat_tuples = build_item_feature_tuples(jobs)
    # normalize=True to match production model (model_manager._build_feature_matrices)
    user_features_mat = ds.build_user_features(
        user_feat_tuples, normalize=True)
    item_features_mat = ds.build_item_features(
        item_feat_tuples, normalize=True)

    eval_model = LightFM(
        no_components=settings.MODEL_NO_COMPONENTS,
        loss=settings.MODEL_LOSS,
        learning_rate=settings.MODEL_LEARNING_RATE,
        random_state=42,
    )
    eval_model.fit(
        train_mat,
        user_features=user_features_mat,
        item_features=item_features_mat,
        sample_weight=train_weights,
        epochs=settings.MODEL_EPOCHS,
        num_threads=settings.MODEL_NUM_THREADS,
    )

    train_csr = train_mat.tocsr()
    test_csr = test_mat.tocsr()

    prec = precision_at_k(
        eval_model, test_csr, train_interactions=train_csr,
        user_features=user_features_mat, item_features=item_features_mat,
        k=k, num_threads=settings.MODEL_NUM_THREADS,
    )
    rec = recall_at_k(
        eval_model, test_csr, train_interactions=train_csr,
        user_features=user_features_mat, item_features=item_features_mat,
        k=k, num_threads=settings.MODEL_NUM_THREADS,
    )
    auc = auc_score(
        eval_model, test_csr, train_interactions=train_csr,
        user_features=user_features_mat, item_features=item_features_mat,
        num_threads=settings.MODEL_NUM_THREADS,
    )
    rr = reciprocal_rank(
        eval_model, test_csr, train_interactions=train_csr,
        user_features=user_features_mat, item_features=item_features_mat,
        num_threads=settings.MODEL_NUM_THREADS,
    )

    train_prec = precision_at_k(
        eval_model, train_csr,
        user_features=user_features_mat, item_features=item_features_mat,
        k=k, num_threads=settings.MODEL_NUM_THREADS,
    )
    train_auc = auc_score(
        eval_model, train_csr,
        user_features=user_features_mat, item_features=item_features_mat,
        num_threads=settings.MODEL_NUM_THREADS,
    )

    coverage = _compute_coverage(
        eval_model, test_csr,
        user_features=user_features_mat, item_features=item_features_mat,
        k=k, n_items=n_i,
    )
    hit_rate = _compute_hit_rate(
        eval_model, train_csr, test_csr,
        user_features=user_features_mat, item_features=item_features_mat,
        k=k,
    )

    elapsed = time.time() - t0
    metrics = {
        "status": "success",
        "mode": "train_test_split",
        "test_ratio": test_ratio,
        "k": k,
        "n_train_interactions": len(train_data),
        "n_test_interactions": len(test_data),
        "n_raw_interactions": len(weighted),
        "n_filtered_out": n_filtered,
        "n_users": len(all_user_ids),
        "n_items": len(all_job_ids),
        f"test_precision@{k}": round(_safe_mean(prec), 4),
        f"test_recall@{k}": round(_safe_mean(rec), 4),
        "test_auc": round(_safe_mean(auc), 4),
        "test_mrr": round(_safe_mean(rr), 4),
        f"test_hit_rate@{k}": round(hit_rate, 4),
        f"test_coverage@{k}": round(coverage, 4),
        f"train_precision@{k}": round(_safe_mean(train_prec), 4),
        "train_auc": round(_safe_mean(train_auc), 4),
        "elapsed_seconds": round(elapsed, 2),
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
    }

    logger.info("═══ EVALUATION complete in %.2fs ═══", elapsed)
    return metrics


if __name__ == "__main__":
    import argparse
    import asyncio
    import json

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    parser = argparse.ArgumentParser(description="Đánh giá LightFM model")
    parser.add_argument(
        "--mode",
        choices=["current", "split"],
        default="current",
        help="current = dùng model đã train; split = train/test split (default: current)",
    )
    parser.add_argument("--k", type=int, default=DEFAULT_K,
                        help=f"Top-K (default: {DEFAULT_K})")
    parser.add_argument("--test-ratio", type=float, default=DEFAULT_TEST_RATIO,
                        help=f"Tỉ lệ test khi dùng mode=split (default: {DEFAULT_TEST_RATIO})")
    args = parser.parse_args()

    from app.core.database import connect_db, close_db

    async def _main() -> None:
        await connect_db()
        try:
            if args.mode == "current":
                result = evaluate_current_model(k=args.k)
            else:
                result = evaluate_train_test_split(test_ratio=args.test_ratio, k=args.k)
            print(json.dumps(result, indent=2, ensure_ascii=False))
        finally:
            await close_db()

    asyncio.run(_main())
