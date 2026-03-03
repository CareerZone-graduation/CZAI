"""
Model manager: quản lý vòng đời LightFM model —
training, partial updates, prediction, persistence.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any

import joblib
import numpy as np
from lightfm import LightFM
from lightfm.data import Dataset
from scipy.sparse import coo_matrix, csr_matrix

from app.core.config import settings
from app.services.recommendation.data_loader import (
    get_popular_job_ids,
    load_active_jobs,
    load_candidates,
    load_interactions,
    load_interactions_since,
)
from app.services.recommendation.feature_engineering import (
    build_item_feature_tuples,
    build_user_feature_tuples,
    collect_all_feature_names,
    extract_candidate_features,
)

logger = logging.getLogger(__name__)

_MODEL_FILE = "lightfm_model.joblib"
_DATASET_FILE = "lightfm_dataset.joblib"
_META_FILE = "lightfm_meta.joblib"
_MATRICES_FILE = "lightfm_matrices.joblib"


class RecommendationEngine:
    """Quản lý toàn bộ pipeline LightFM recommendation."""

    def __init__(self) -> None:
        self.model: LightFM | None = None
        self.dataset: Dataset | None = None
        self.interactions_matrix = None
        self.weights_matrix = None
        self.user_features_matrix = None
        self.item_features_matrix = None
        self.applied_jobs: dict[str, set[str]] = {}
        self.saved_jobs: dict[str, set[str]] = {}   # SAVE interactions
        self.active_job_ids: list[str] = []
        self.last_retrain_at: datetime | None = None
        self.last_partial_at: datetime | None = None

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _build_interactions(self, ds: Dataset, weighted_interactions):
        """Build interactions + weights matrices từ weighted data."""
        user_map, _, item_map, _ = ds.mapping()
        data = [
            (uid, jid, w)
            for uid, jid, w in weighted_interactions
            if uid in user_map and jid in item_map
        ]
        if data:
            return ds.build_interactions(data), len(data)

        n_u, n_i = ds.interactions_shape()
        empty = coo_matrix((n_u, n_i), dtype=np.float32)
        return (empty, empty), 0

    def _build_feature_matrices(self, ds: Dataset, jobs, candidates):
        """Build user & item feature matrices."""
        user_feat_tuples = build_user_feature_tuples(candidates)
        item_feat_tuples = build_item_feature_tuples(jobs)
        user_mat = ds.build_user_features(user_feat_tuples, normalize=True)
        item_mat = ds.build_item_features(item_feat_tuples, normalize=True)
        return user_mat, item_mat

    def _predict_scores(self, user_idx: int, item_map: dict) -> np.ndarray:
        """Predict scores cho 1 user trên tất cả items."""
        item_ids = np.arange(len(item_map), dtype=np.int32)
        return self.model.predict(
            user_ids=user_idx,
            item_ids=item_ids,
            user_features=self.user_features_matrix,
            item_features=self.item_features_matrix,
        )

    def _rank_results(
        self, scores: np.ndarray, item_map: dict,
        n: int, exclude_ids: set[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Sắp xếp scores → top-N results, chỉ lấy active jobs."""
        inv_map = {v: k for k, v in item_map.items()}
        active_set = set(self.active_job_ids)
        exclude = exclude_ids or set()

        results = []
        for idx in np.argsort(-scores):
            ext_id = inv_map.get(int(idx))
            if ext_id is None or ext_id not in active_set:
                continue
            if ext_id in exclude:
                continue
            results.append(
                {"jobId": ext_id, "score": round(float(scores[idx]), 4)})
            if len(results) >= n:
                break
        return results

    # ── Full retrain ──────────────────────────────────────────────────────────

    def full_retrain(self) -> dict[str, Any]:
        """Train model từ đầu với toàn bộ data."""
        t0 = time.time()
        logger.info("═══ Starting FULL RETRAIN ═══")

        # 1. Load data
        weighted, user_ids, job_ids, applied, saved = load_interactions()
        jobs = load_active_jobs()
        candidates = load_candidates(user_ids=user_ids, include_onboarded=True)

        if not jobs:
            logger.warning("No active jobs — skipping retrain.")
            return {"status": "skipped", "reason": "no_active_jobs"}

        all_job_ids = [str(j["_id"]) for j in jobs]
        all_user_ids = {str(c.get("userId", c.get("_id", "")))
                        for c in candidates}
        all_user_ids.update(user_ids)

        # 2. Build dataset + features
        user_feat_names, item_feat_names = collect_all_feature_names(
            jobs, candidates)

        ds = Dataset()
        ds.fit(
            users=all_user_ids,
            items=all_job_ids,
            user_features=user_feat_names,
            item_features=item_feat_names,
        )

        (interactions_mat, weights_mat), n_inter = self._build_interactions(ds, weighted)
        user_features_mat, item_features_mat = self._build_feature_matrices(
            ds, jobs, candidates)

        # 3. Train
        model = LightFM(
            no_components=settings.MODEL_NO_COMPONENTS,
            loss=settings.MODEL_LOSS,
            learning_rate=settings.MODEL_LEARNING_RATE,
            random_state=42,
        )
        model.fit(
            interactions_mat,
            user_features=user_features_mat,
            item_features=item_features_mat,
            sample_weight=weights_mat,
            epochs=settings.MODEL_EPOCHS,
            num_threads=settings.MODEL_NUM_THREADS,
        )

        # 4. Lưu state
        now = datetime.now(timezone.utc)
        self.model = model
        self.dataset = ds
        self.interactions_matrix = interactions_mat
        self.weights_matrix = weights_mat
        self.user_features_matrix = user_features_mat
        self.item_features_matrix = item_features_mat
        self.applied_jobs = applied
        self.saved_jobs = saved
        self.active_job_ids = all_job_ids
        self.last_retrain_at = now
        self.last_partial_at = now

        self._save_to_disk()

        elapsed = time.time() - t0
        stats = {
            "status": "success",
            "elapsed_seconds": round(elapsed, 2),
            "n_users": len(all_user_ids),
            "n_items": len(all_job_ids),
            "n_interactions": n_inter,
            "n_user_features": len(user_feat_names),
            "n_item_features": len(item_feat_names),
            "retrained_at": now.isoformat(),
        }
        logger.info("═══ FULL RETRAIN complete in %.2fs ═══ %s",
                    elapsed, stats)
        return stats

    # ── Partial update ────────────────────────────────────────────────────────

    def partial_update(self) -> dict[str, Any]:
        """
        Incremental update: CHỈ học interaction mới của User cũ và Job cũ đã biết.

        - Mỗi 30 phút (partial_update): fine-tune trên interaction của entity cũ.
          User/Job mới bị lờ đi — họ được _cold_start_predict phục vụ tạm.
        - 2:00 AM (full_retrain): chính thức kết nạp mọi entity mới vào model.
        """
        if not self.is_ready:
            logger.warning("No model loaded — running full retrain.")
            return self.full_retrain()

        since = self.last_partial_at or self.last_retrain_at
        if since is None:
            return self.full_retrain()

        t0 = time.time()
        logger.info("─── Starting PARTIAL UPDATE (since %s) ───", since)

        new_interactions, _, _, new_applied, new_saved = load_interactions_since(
            since)

        if not new_interactions:
            logger.info("No new interactions — skipping.")
            self.last_partial_at = datetime.now(timezone.utc)
            return {"status": "skipped", "reason": "no_new_data"}

        user_map, _, item_map, _ = self.dataset.mapping()
        valid_interactions = [
            (uid, jid, w) for uid, jid, w in new_interactions
            if uid in user_map and jid in item_map
        ]

        if not valid_interactions:
            logger.info(
                "All new interactions involve unknown entities — skipping fit_partial.")
            self.last_partial_at = datetime.now(timezone.utc)
            return {"status": "skipped", "reason": "only_new_entities_interactions"}

        (interactions_mat, weights_mat), n_valid = self._build_interactions(
            self.dataset, valid_interactions
        )

        # Enhance: Cộng dồn ma trận mới vào cumulative trước khi fit_partial.
        #
        # Nếu chỉ truyền interactions_mat (30 phút):
        #   WARP loss coi mọi ô = 0 trong ma trận là Negative sample.
        #   Toàn bộ interaction cũ (hôm qua, tuần trước) đều bằng 0 trong
        #   ma trận 30-phút → mô hình chủ động phạt (unlearn) chúng.
        #
        # Ví dụ thảm họa: User A APPLY Backend Python sáng nay (weight 5.0).
        #   Chiều VIEW DevOps → partial_update chỉ thấy DevOps > 0, còn
        #   Backend Python = 0 → LightFM bốc Backend Python làm Negative
        #   → đẩy score của Backend Python xuống dưới DevOps.
        #
        # Giải pháp: cộng dồn sparse matrix mới vào self.interactions_matrix
        #   (tích lũy từ full_retrain) trước khi fit_partial.
        cumul_interactions = (
            csr_matrix(self.interactions_matrix) + csr_matrix(interactions_mat)
        )
        # Dùng maximum cho weights: tránh inflate trọng số khi cùng 1 cặp
        # (user, job) xuất hiện nhiều lần trong khoảng partial window ngắn.
        # Ví dụ: VIEW (1.0) cũ + APPLY (5.0) mới → giữ 5.0, không cộng 6.0.
        cumul_weights = csr_matrix(self.weights_matrix).maximum(
            csr_matrix(weights_mat)
        )

        self.model.fit_partial(
            cumul_interactions.tocoo(),
            user_features=self.user_features_matrix,
            item_features=self.item_features_matrix,
            sample_weight=cumul_weights.tocoo(),
            epochs=settings.MODEL_PARTIAL_EPOCHS,
            num_threads=settings.MODEL_NUM_THREADS,
        )

        # Lưu lại cumulative để lần partial_update tiếp theo dùng tiếp.
        # Khi server restart, load_from_disk() sẽ rebuild từ toàn bộ DB
        # nên không cần persist 2 matrix này xuống disk.
        self.interactions_matrix = cumul_interactions
        self.weights_matrix = cumul_weights

        # Cập nhật applied_jobs và saved_jobs tăng dần
        for uid, jids in new_applied.items():
            if uid in user_map:
                self.applied_jobs.setdefault(uid, set()).update(jids)
        for uid, jids in new_saved.items():
            if uid in user_map:
                self.saved_jobs.setdefault(uid, set()).update(jids)

        self.last_partial_at = datetime.now(timezone.utc)
        self._save_to_disk()

        elapsed = time.time() - t0
        stats = {
            "status": "success",
            "elapsed_seconds": round(elapsed, 2),
            "total_new_interactions": len(new_interactions),
            "valid_interactions_trained": n_valid,
        }
        logger.info("─── PARTIAL UPDATE complete in %.2fs ─── %s",
                    elapsed, stats)
        return stats

    # ── Prediction ────────────────────────────────────────────────────────────

    def predict(
        self,
        user_id: str,
        n: int | None = None,
        exclude_applied: bool = True,
    ) -> tuple[list[dict[str, Any]], str]:
        """
        Top-N job recommendations cho 1 user.

        Returns:
            (results, source) với source là một trong:
              - "model"      : user có interaction, dùng collaborative filtering
              - "cold_start" : user có profile nhưng chưa interact, hoặc không
                               có trong dataset → dùng content-based / manual embedding
              - "popular"    : không có đủ thông tin → trả popular jobs
        """
        if n is None:
            n = settings.TOP_N

        if not self.is_ready:
            logger.warning("Model not loaded — returning popular jobs.")
            return self._popular_fallback(n)

        user_map, _, item_map, _ = self.dataset.mapping()

        # User chưa có trong model dataset → cold-start thủ công
        if user_id not in user_map:
            return self._cold_start_predict(user_id, n)

        # User trong model — kiểm tra có interaction không
        has_interaction = bool(self.applied_jobs.get(user_id))
        # applied_jobs chỉ track APPLY; kiểm tra thêm interactions_matrix
        if not has_interaction:
            _, _, item_map_check, _ = self.dataset.mapping()
            user_idx = user_map[user_id]
            from scipy.sparse import issparse
            mat = self.interactions_matrix
            if issparse(mat):
                row = mat.tocsr()[user_idx]
                has_interaction = row.nnz > 0
            else:
                has_interaction = bool(mat[user_idx].any())

        source = "model" if has_interaction else "cold_start"

        # Predict
        scores = self._predict_scores(user_map[user_id], item_map)

        # Exclude applied jobs nếu cần
        exclude = self.applied_jobs.get(
            user_id, set()) if exclude_applied else set()
        return self._rank_results(scores, item_map, n, exclude), source

    def _cold_start_predict(self, user_id: str, n: int) -> list[dict[str, Any]]:
        """
        Cold-start: user mới chưa có trong model.
        Tính user embedding thủ công từ profile features,
        rồi dot product với item embeddings để ra scores.

        ⚠️  LƯU Ý — CODE NÀY CÓ RỦI RO "FRAGILE":
        Toàn bộ phép tính bên dưới (mean embedding + dot product) chỉ đúng
        khi đồng thời thỏa 3 điều kiện sau:
          1. _build_feature_matrices() dùng normalize=True (hiện tại ở dòng ~78).
             Nếu đổi sang normalize=False, công thức đúng phải là .sum(axis=0),
             không phải .mean(axis=0) — sẽ sai im lặng, không có lỗi nào raise.
          2. model.user_embeddings / model.user_biases là internal attribute của
             LightFM. Thư viện không đảm bảo API ổn định cho các thuộc tính này;
             nếu thư viện cập nhật cấu trúc nội bộ, code sẽ vỡ.
          3. get_item_representations() cũng là semi-internal. Tương tự rủi ro trên.

        ✅  GIẢI PHÁP AN TOÀN HƠN (nếu cần refactor sau này):
        Xây csr_matrix 1 dòng với weight = 1/len(feat_indices) (replicate
        normalize=True) rồi gọi model.predict(user_ids=0, item_ids=...,
        user_features=new_user_sparse_matrix, item_features=...) trực tiếp —
        để LightFM tự xử lý toàn bộ phép tính nội bộ, không cần chạm vào
        user_embeddings hay get_item_representations().
        """
        logger.info("Cold-start prediction for user %s", user_id)

        candidates = load_candidates(
            user_ids={user_id}, include_onboarded=False)
        if not candidates:
            logger.info(
                "No profile for user %s — returning popular jobs", user_id)
            return self._popular_fallback(n)

        cand = candidates[0]
        cand_feats = extract_candidate_features(cand)
        if not cand_feats:
            return self._popular_fallback(n)

        _, user_feat_map, _, _ = self.dataset.mapping()

        feat_indices = []
        for feat in cand_feats:
            if feat in user_feat_map:
                feat_indices.append(user_feat_map[feat])

        if not feat_indices:
            logger.info("No matching features for user %s", user_id)
            return self._popular_fallback(n)

        # ⚠️  Chỉ đúng khi normalize=True (xem ghi chú trong docstring).
        # internal API
        feat_embeddings = self.model.user_embeddings[feat_indices]
        user_embedding = feat_embeddings.mean(axis=0)
        # internal API
        user_bias = self.model.user_biases[feat_indices].mean()

        _, _, item_map, _ = self.dataset.mapping()

        # ⚠️  get_item_representations() là semi-internal API của LightFM.
        item_embeddings = self.model.get_item_representations(
            self.item_features_matrix)
        item_biases = item_embeddings[0]
        item_vectors = item_embeddings[1]

        scores = item_vectors.dot(user_embedding) + user_bias + item_biases

        return self._rank_results(scores, item_map, n), "cold_start"

    def _popular_fallback(self, n: int) -> tuple[list[dict[str, Any]], str]:
        """Fallback: trả về popular jobs khi không predict được."""
        try:
            popular = get_popular_job_ids(limit=n)
            return [{"jobId": jid, "score": 0.0} for jid in popular], "popular"
        except Exception as e:
            logger.error("Failed to get popular jobs: %s", e)
            return [], "popular"

    def get_similar_items(
        self, job_id: str, n: int = 6, user_id: str | None = None,
    ) -> tuple[list[dict[str, Any]], str]:
        """
        Lấy các jobs tương tự dựa trên Item-Item CF.

        Sử dụng cosine similarity trên item embeddings từ LightFM.
        Vì model được train trên interaction data (VIEW/SAVE/APPLY) kết hợp
        content features, item embeddings encode collaborative signal:
        "người xem job A cũng thường xem job B".

        Args:
            job_id: Job đang xem (target)
            n:      Số lượng kết quả trả về
            user_id: (Optional) Nếu truyền vào, sẽ exclude jobs user đã interact
        """
        if not self.is_ready:
            logger.warning("Model not loaded — returning popular jobs for CF.")
            return self._popular_fallback(n)

        _, _, item_map, _ = self.dataset.mapping()
        if job_id not in item_map:
            logger.info(
                "Job %s not in model dataset — returning popular jobs for CF.", job_id)
            return self._popular_fallback(n)

        item_idx = item_map[job_id]

        # get_item_representations trả về (biases, embeddings)
        item_biases, item_embeddings = self.model.get_item_representations(
            self.item_features_matrix
        )

        target_embedding = item_embeddings[item_idx]
        target_norm = np.linalg.norm(target_embedding)

        if target_norm == 0:
            return self._popular_fallback(n)

        all_norms = np.linalg.norm(item_embeddings, axis=1)
        dot_products = item_embeddings.dot(target_embedding)

        # Cosine similarity (collaborative signal)
        cosine_similarities = np.zeros_like(dot_products)
        valid_mask = all_norms > 0
        cosine_similarities[valid_mask] = (
            dot_products[valid_mask] / (all_norms[valid_mask] * target_norm)
        )

        # Kết hợp item bias để ưu tiên jobs phổ biến hơn trong ranking.
        # bias phản ánh mức độ "intrinsic popularity" của item,
        # giúp tránh recommend jobs ít ai quan tâm dù embedding gần.
        # Normalize bias về [0, 1] rồi blend với cosine sim.
        bias_min = item_biases.min()
        bias_max = item_biases.max()
        if bias_max > bias_min:
            norm_biases = (item_biases - bias_min) / (bias_max - bias_min)
        else:
            norm_biases = np.zeros_like(item_biases)

        # 85% cosine similarity + 15% popularity bias
        combined_scores = 0.85 * cosine_similarities + 0.15 * norm_biases

        # Remove target job
        combined_scores[item_idx] = -2.0

        # Exclude jobs user đã tương tác (nếu có user_id)
        # Loại cả APPLY lẫn SAVE — user đã biết đến job này rồi.
        exclude_ids = {job_id}
        if user_id:
            exclude_ids.update(self.applied_jobs.get(user_id, set()))
            exclude_ids.update(self.saved_jobs.get(user_id, set()))

        results = self._rank_results(combined_scores, item_map, n, exclude_ids)
        return results, "model_cf"

    # ── Persistence ───────────────────────────────────────────────────────────

    def _save_to_disk(self) -> None:
        """Lưu model, dataset, metadata, và feature matrices xuống disk."""
        model_dir = settings.model_path
        model_dir.mkdir(parents=True, exist_ok=True)
        try:
            joblib.dump(self.model, model_dir / _MODEL_FILE)
            joblib.dump(self.dataset, model_dir / _DATASET_FILE)
            meta = {
                "active_job_ids": self.active_job_ids,
                "applied_jobs": {k: list(v) for k, v in self.applied_jobs.items()},
                "saved_jobs": {k: list(v) for k, v in self.saved_jobs.items()},
                "last_retrain_at": self.last_retrain_at,
                "last_partial_at": self.last_partial_at,
            }
            joblib.dump(meta, model_dir / _META_FILE)
            matrices = {
                "user_features_matrix": self.user_features_matrix,
                "item_features_matrix": self.item_features_matrix,
            }
            joblib.dump(matrices, model_dir / _MATRICES_FILE)
            logger.info("Model saved to %s", model_dir)
        except Exception as e:
            logger.error("Failed to save model: %s", e)

    def load_from_disk(self) -> bool:
        """Load model từ disk. Returns True nếu thành công."""
        model_dir = settings.model_path
        model_file = model_dir / _MODEL_FILE
        dataset_file = model_dir / _DATASET_FILE
        meta_file = model_dir / _META_FILE
        matrices_file = model_dir / _MATRICES_FILE

        if not model_file.exists() or not dataset_file.exists():
            logger.info("No saved model found at %s", model_dir)
            return False

        try:
            model = joblib.load(model_file)
            ds = joblib.load(dataset_file)
            meta = joblib.load(meta_file) if meta_file.exists() else {}

            if matrices_file.exists():
                matrices = joblib.load(matrices_file)
                user_features_mat = matrices["user_features_matrix"]
                item_features_mat = matrices["item_features_matrix"]
                logger.info("Loaded feature matrices from disk")
            else:
                logger.warning("Matrices file not found, rebuilding")
                jobs = load_active_jobs()
                candidates = load_candidates(include_onboarded=True)
                user_features_mat, item_features_mat = self._build_feature_matrices(
                    ds, jobs, candidates)

            all_interactions, _, _, applied, saved = load_interactions()
            (interactions_mat, weights_mat), _ = self._build_interactions(
                ds, all_interactions)

            self.model = model
            self.dataset = ds
            self.interactions_matrix = interactions_mat
            self.weights_matrix = weights_mat
            self.user_features_matrix = user_features_mat
            self.item_features_matrix = item_features_mat
            self.applied_jobs = applied
            self.saved_jobs = saved
            self.active_job_ids = meta.get("active_job_ids", [])
            self.last_retrain_at = meta.get("last_retrain_at")
            self.last_partial_at = meta.get("last_partial_at")

            logger.info("Model loaded from %s", model_dir)
            return True
        except Exception as e:
            logger.error("Failed to load model from disk: %s", e)
            return False

    # ── Status ────────────────────────────────────────────────────────────────

    @property
    def is_ready(self) -> bool:
        return self.model is not None and self.dataset is not None

    def get_status(self) -> dict[str, Any]:
        if not self.is_ready:
            return {"ready": False}
        user_map, _, item_map, _ = self.dataset.mapping()
        return {
            "ready": True,
            "n_users": len(user_map),
            "n_items": len(item_map),
            "n_active_jobs": len(self.active_job_ids),
            "last_retrain_at": self.last_retrain_at.isoformat() if self.last_retrain_at else None,
            "last_partial_at": self.last_partial_at.isoformat() if self.last_partial_at else None,
        }


# Singleton
engine = RecommendationEngine()
