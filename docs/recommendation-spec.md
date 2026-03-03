# CareerZoneAI — Recommendation Engine Spec

> **Version:** 1.0 | **Date:** 2026-03-02

---

## 1. Tổng quan

Hệ thống gợi ý việc làm sử dụng **LightFM** — thuật toán hybrid kết hợp:
- **Collaborative Filtering (CF)**: học từ lịch sử tương tác user-job
- **Content-Based (CB)**: dùng features (skills, province, salary, ...) của user và job

### Điểm mạnh
- **Cold-start**: User/job mới không có interactions vẫn nhận được gợi ý từ features
- **Shared feature namespace**: cùng tag `skill:python` cho cả user và job → học correlation
- **Weighted interactions**: APPLY > SAVE > VIEW phản ánh mức độ nghiêm túc

---

## 2. Kiến trúc module

```
app/services/recommendation/
├── model_manager.py      — RecommendationEngine singleton (train/predict/persist)
├── feature_engineering.py — Extract features từ jobs & candidates
├── data_loader.py        — MongoDB queries (sync, chạy trong thread)
├── scheduler.py          — APScheduler (daily retrain + periodic partial update)
└── evaluator.py          — Offline metrics (precision@K, recall@K, AUC, MRR)
```

---

## 3. Feature Namespace

Tất cả features của user **và** job đều dùng chung một namespace, cho phép LightFM học correlation giữa user preference và job attribute.

| Prefix            | Source (User)                        | Source (Job)              | Example                  |
|-------------------|--------------------------------------|---------------------------|--------------------------|
| `skill:`          | `candidateprofiles.skills[].name`    | `jobs.skills[]`           | `skill:python`           |
| `province:`       | `candidateprofiles.preferredLocations[].province` | `jobs.location.province` | `province:ho_chi_minh`  |
| `salary:`         | *(không có — chỉ job)*               | `jobs.minSalary/maxSalary`| `salary:10m_15m`         |
| `category:`       | `candidateprofiles.preferredCategories[]` | `jobs.category`      | `category:IT`            |
| `worktype:`       | `candidateprofiles.workPreferences.workTypes[]` | `jobs.workType`  | `worktype:REMOTE`        |
| `contracttype:`   | `candidateprofiles.workPreferences.contractTypes[]` | `jobs.type`  | `contracttype:FULL_TIME` |
| `experience:`     | `candidateprofiles.workPreferences.experienceLevel[]` | `jobs.experience` | `experience:SENIOR_LEVEL` |
| `area:`           | *(không có)*                        | `jobs.area`               | `area:NORTH`             |

### 3.1 Normalization

Text free-form được normalize trước khi tạo feature tag:

| Loại     | Input example          | Normalized                | Hàm                    |
|----------|------------------------|---------------------------|------------------------|
| Skill    | `"ReactJS"`, `"React.js"` | `"react"`              | `normalize_skill()`    |
| Province | `"TP.HCM"`, `"Hồ Chí Minh"` | `"ho_chi_minh"`    | `normalize_province()` |
| Salary   | `15_000_000 VND avg`   | `"10m_15m"`               | `salary_bucket()`      |

**Salary buckets:**

| Range (VND/tháng)     | Bucket tag        |
|-----------------------|-------------------|
| < 5,000,000           | `under_5m`        |
| 5M – 10M              | `5m_10m`          |
| 10M – 15M             | `10m_15m`         |
| 15M – 20M             | `15m_20m`         |
| 20M – 30M             | `20m_30m`         |
| 30M – 50M             | `30m_50m`         |
| ≥ 50M                 | `above_50m`       |
| Không xác định        | `negotiable`      |

---

## 4. Interaction Weighting

| Interaction Type | Weight   | Lý do                              |
|-----------------|----------|------------------------------------|
| `VIEW`          | `1.0`    | Xem qua, thể hiện quan tâm nhẹ    |
| `SAVE`          | `2.5`    | Lưu lại, quan tâm cao hơn         |
| `APPLY`         | `5.0`    | Ứng tuyển — tín hiệu mạnh nhất    |

- Nhiều interactions cùng `(userId, jobId)` → **cộng dồn** weights
- Configurable qua env: `WEIGHT_VIEW`, `WEIGHT_SAVE`, `WEIGHT_APPLY`

---

## 5. Model Training Pipeline

### 5.1 Full Retrain

```
load_interactions(days=INTERACTION_DAYS)
    └── Lấy tất cả interactions trong N ngày gần nhất
         ↓
load_active_jobs()
    └── Lấy tất cả jobs có status ACTIVE
         ↓
load_candidates(user_ids, include_onboarded=True)
    └── Lấy profiles của users có interactions + users đã onboard
         ↓
collect_all_feature_names(jobs, candidates)
    └── Tổng hợp tất cả feature tags trong namespace chung
         ↓
Dataset.fit(users, items, user_features, item_features)
    └── Xây dựng LightFM Dataset mapping
         ↓
build_interactions() + build_user_features() + build_item_features()
    └── Tạo sparse matrices
         ↓
LightFM.fit(loss="warp", epochs=30, num_threads=4)
    └── Train model
         ↓
save_to_disk(./models/)
    └── Lưu model, dataset, matrices, metadata
```

### 5.2 Partial Update (`fit_partial`)

Chạy 30 phút/lần để cập nhật incremental:
```
load_interactions_since(last_partial_at)
    └── Chỉ lấy interactions mới nhất (valid = user+job đã biết)
         ↓
cumul_interactions = self.interactions_matrix + new_interactions_mat
cumul_weights      = self.weights_matrix.maximum(new_weights_mat)
    └── Cộng dồn vào cumulative từ full_retrain (giữ toàn bộ lịch sử)
         ↓
LightFM.fit_partial(cumul_interactions, epochs=5)
    └── Train trên ma trận tích lũy — tránh catastrophic forgetting
         ↓
self.interactions_matrix = cumul_interactions   # cập nhật state
save_to_disk()
```

> **⚠️ Tại sao phải dùng cumulative, không phải chỉ 30-phút?**
>
> WARP loss coi mọi ô `= 0` trong ma trận là **Negative sample**. Nếu chỉ
> truyền ma trận 30-phút, toàn bộ interactions cũ (hôm qua, tuần trước)
> đều thành `0` → LightFM sẽ **chủ động phạt (unlearn)** chúng.
>
> Ví dụ: User A APPLY Backend Python sáng nay (weight 5.0). Chiều VIEW
> DevOps → partial_update chỉ thấy DevOps > 0, còn Backend Python = 0
> → LightFM bốc Backend Python làm Negative → score Backend Python tụt
> xuống dưới DevOps. Hệ thống gợi ý sẽ "nhảy múa" nhiễu loạn sau mỗi
> 30 phút thay vì cải thiện.
>
> Dùng `maximum()` cho weights (không cộng): tránh inflate khi cùng một
> cặp `(user, job)` xuất hiện nhiều lần trong partial window ngắn.
> Ví dụ: VIEW (1.0) cũ + APPLY (5.0) mới → giữ 5.0, không cộng 6.0.

---

## 6. Prediction Logic

### 6.1 Known user (có interactions)

```python
user_idx = user_map[user_id]
scores = model.predict(user_ids=user_idx, item_ids=all_items,
                       user_features=user_mat, item_features=item_mat)
return top_N active jobs (exclude applied jobs)
```

### 6.2 Cold-start user (chưa có interactions)

```python
# Trích xuất candidate features từ MongoDB
cand_feats = extract_candidate_features(candidate)
feat_indices = [user_feat_map[f] for f in cand_feats if f in user_feat_map]

# Tính user embedding thủ công (mean của feature embeddings)
user_embedding = model.user_embeddings[feat_indices].mean(axis=0)
user_bias      = model.user_biases[feat_indices].mean()
item_biases, item_vectors = model.get_item_representations(item_features_matrix)
scores = item_vectors.dot(user_embedding) + user_bias + item_biases

return top_N active jobs
```

> **⚠️ Lưu ý kỹ thuật — code hiện tại có rủi ro fragile:**
>
> Cách tính thủ công trên chỉ đúng khi đồng thời thỏa 3 điều kiện:
> 1. `normalize=True` trong `_build_feature_matrices()` (hiện tại đang đúng)
>    — nếu đổi sang `False`, phải dùng `.sum()` thay `.mean()`, sai im lặng.
> 2. `model.user_embeddings` / `model.user_biases` là **internal attribute**
>    của LightFM, không có stability guarantee.
> 3. `get_item_representations()` là **semi-internal API**, tương tự rủi ro.
>
> **Giải pháp an toàn hơn (nếu refactor):** xây `csr_matrix` 1 dòng với
> `weight = 1/len(feat_indices)` rồi gọi `model.predict(user_ids=0, ...,
> user_features=new_user_sparse_matrix, item_features=...)` trực tiếp.

### 6.3 Fallback (không có profile)

```python
return get_popular_job_ids(n=TOP_N)
# Sorted by: số lượng interactions trong N ngày gần nhất
```

### 6.4 Filtering

- Chỉ trả về **active jobs** (`active_job_ids` được cập nhật lúc retrain)
- Loại bỏ jobs user đã **APPLY** (`applied_jobs[user_id]`)
- Loại bỏ jobs user đã **SAVE** (`saved_jobs[user_id]`) — user đã bookmark = đã biết
- Top **N** jobs (default `TOP_N=20`, configurable via env)

## 6b. Item-Item Collaborative Filtering (Similar Jobs)

> Endpoint: `GET /similar-jobs-cf/{job_id}?userId=...`
>
> Dùng trong trang chi tiết việc — gợi ý: *"việc làm mà người có cùng sở thích cũng quan tâm"

### Lý do khác Vector Search

| Đặc điểm | `/embeddings/similar-jobs` (Vector Search) | `/recommendation/similar-jobs-cf` (LightFM CF) |
|---|---|---|
| Dựa vào | Nội dung mô tả JD (tự nhiparticle by vector embed) | Hành vi người dùng (VIEW/SAVE/APPLY) |
| Tính tương đồng | Ngữ nghĩa / kỹ thuật trong mô tả | Collaborative signal — cùng nhóm user quan tâm |
| Ví dụ | "Python Senior" ~ "Python Backend 5yr" | "Python Backend" ~ "DevOps" (nếu cùng user xem cả hai) |
| Cold job | Hoạt động nếu có embedding | Fallback sang popular |

### Thuật toán

```python
# 1. Lấy item embeddings từ LightFM
item_biases, item_embeddings = model.get_item_representations(item_features_matrix)

# 2. Cosine similarity (uận nạp collaborative signal)
target = item_embeddings[item_map[job_id]]
cosine_sim = item_embeddings @ target / (|item_embeddings| × |target|)

# 3. Normalize bias về [0, 1]
norm_bias = (item_biases - min) / (max - min)

# 4. Blend: collaborative signal 85% + popularity 15%
final_score = 0.85 × cosine_sim + 0.15 × norm_bias

# 5. Exclude target job + jobs user đã APPLY/SAVE (nếu có userId)
# 6. Filter active jobs, lấy top-N
```

### Tại sao kết hợp bias?

Item bias trong LightFM phản ánh *intrinsic popularity* của job (mức độ được nhiều user tương tác). Blend 15% giúp tránh recommend jobs ít ai biết dù embedding gần, nhưng vẫn giữ collaborative signal là chính.

### Exclusion logic

Nếu `userId` được truyền:
- Exclude jobs user đã **APPLY** (`applied_jobs[userId]`)
- Exclude jobs user đã **SAVE** (`saved_jobs[userId]`)
- Exclude bản thân `job_id` đang xem

Nguồn dữ liệu `saved_jobs` được load từ `interactions` collection cùng với `applied_jobs` và được cập nhật incremental qua `partial_update`.

---

## 7. Model Persistence

Files lưu tại `MODEL_DIR` (default: `./models/`):

| File                      | Nội dung                                    |
|---------------------------|---------------------------------------------|
| `lightfm_model.joblib`    | LightFM model weights                       |
| `lightfm_dataset.joblib`  | Dataset mapping (user/item/feature IDs)     |
| `lightfm_matrices.joblib` | Sparse interaction + feature matrices       |
| `lightfm_meta.joblib`     | Metadata (timestamps, counts, job IDs list) |

---

## 8. APScheduler Configuration

| Job              | Trigger           | Config                                     |
|-----------------|------------------|---------------------------------------------|
| Full retrain     | CronTrigger       | `RETRAIN_HOUR:RETRAIN_MINUTE` (default 2:00 AM) |
| Partial update   | IntervalTrigger   | Mỗi `PARTIAL_UPDATE_INTERVAL_MINUTES` phút (default 30) |

---

## 9. LightFM Hyperparameters

| Param               | Default | Config env var         | Mô tả                    |
|---------------------|---------|------------------------|--------------------------|
| `no_components`     | `64`    | `MODEL_NO_COMPONENTS`  | Số latent factors        |
| `epochs` (full)     | `30`    | `MODEL_EPOCHS`         | Training epochs          |
| `epochs` (partial)  | `5`     | `MODEL_PARTIAL_EPOCHS` | Partial update epochs    |
| `learning_rate`     | `0.05`  | `MODEL_LEARNING_RATE`  | Adam learning rate       |
| `loss`              | `warp`  | `MODEL_LOSS`           | Loss: `warp` hoặc `bpr`  |
| `num_threads`       | `4`     | `MODEL_NUM_THREADS`    | Parallel training threads |

---

## 10. MongoDB Collections

| Collection         | Managed by      | Mô tả                                        |
|-------------------|-----------------|----------------------------------------------|
| `jobs`            | Node.js (read-only) | Job postings với embedding chunks           |
| `candidateprofiles` | Node.js (read-only) | Candidate profiles                        |
| `interactions`    | This service    | User-job interactions (`VIEW/SAVE/APPLY`)    |

**Indexes trên `interactions`:**
```
{ userId: 1, jobId: 1, type: 1 }  →  idx_user_job_type
{ createdAt: 1 }                   →  idx_created_at
```

---

## 11. Offline Evaluation Metrics

`evaluator.py` tính toán:

| Metric          | Mô tả                                               |
|----------------|-----------------------------------------------------|
| `precision@K`  | Tỉ lệ items liên quan trong top-K gợi ý             |
| `recall@K`     | Tỉ lệ items liên quan được tìm thấy trong top-K     |
| `AUC`          | Area Under ROC Curve (LightFM built-in)             |
| `MRR`          | Mean Reciprocal Rank                                |
| `hit_rate@K`   | % users có ít nhất 1 relevant item trong top-K     |
| `coverage`     | % jobs được gợi ý cho ít nhất 1 user               |

---

## 12. Spec: Cải tiến đề xuất

| ID       | Feature                                     | Priority |
|----------|---------------------------------------------|----------|
| REC-001  | A/B testing framework cho model versions    | Medium   |
| REC-002  | Online evaluation (click-through rate)      | High     |
| REC-003  | Diversity/serendipity trong ranking         | Medium   |
| REC-004  | Redis cache cho popular jobs fallback       | Medium   |
| REC-005  | Multi-objective: score + fresh jobs boost   | Low      |
| REC-006  | Expose evaluation metrics qua `/health`     | Medium   |
