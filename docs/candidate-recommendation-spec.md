# CareerZoneAI — Candidate Recommendation Spec

> **Version:** 1.0 | **Date:** 2026-03-03

---

## 1. Tổng quan (Overview)

Chức năng **Gợi ý Ứng viên (Candidate Recommendations)** giúp Nhà tuyển dụng tìm kiếm các ứng viên phù hợp nhất cho một công việc (Job) cụ thể dựa trên nội dung CV và các tiêu chí bắt buộc. Thay vì sử dụng Collaborative Filtering (được dùng cho gợi ý việc làm), hệ thống này kết hợp mô hình học sâu (Vector Embeddings) và Score Ranking theo bộ quy tắc (Rule-based).

Mô hình thiết kế tuân theo luồng **Hybrid Retrieval & Rule-based Scoring**:
1. Lấy Average Embedding của Job
2. Vector Search (Retrieval)
3. MaxSim Re-ranking
4. Rule-based Overlay Scoring

---

## 2. API Endpoint

### `GET /api/v1/recommendations/candidates/{job_id}`

Lấy danh sách gợi ý ứng viên phù hợp cho một công việc cụ thể. 

**Path params:**
- `job_id` — MongoDB ObjectId của job cần tìm ứng viên

**Query params:**
- `page` (int, default: `1`) — Số trang
- `limit` (int, default: `10`) — Số lượng ứng viên trả về mỗi trang
- `minScore` (float, default: `0.5`) — Điểm chẩn chỉnh tối thiểu (0.0 - 1.0) để lọc ứng viên

**Header:**
- `X-Internal-Secret: <INTERNAL_API_KEY>` (Yêu cầu xác thực Internal API)

**Response:**
```json
{
  "jobId": "67b9c1d...",
  "recommendations": [
    {
      "userId": "user-id-1",
      "candidateProfileId": "profile-id-1",
      "score": 0.85,
      "similarityPercentage": 85,
      "matchedSkills": ["React", "Node.js"],
      "experienceYears": 3,
      "matchReasons": [
        {
          "type": "ai_match",
          "value": "Phù hợp với mô tả công việc (AI đánh giá)",
          "weight": 35
        },
        {
          "type": "skill_match",
          "value": "Khớp 2 kỹ năng: React, Node.js",
          "weight": 16
        }
      ]
    }
  ],
  "pagination": {
    "currentPage": 1,
    "totalPages": 5,
    "totalItems": 45,
    "limit": 10,
    "hasNextPage": true,
    "hasPrevPage": false
  },
  "source": "vector_search_maxsim_rulebased"
}
```

---

## 3. Quy trình chi tiết (Architectural Flow)

### 3.1. Calculate Average Job Embedding
Khi query, AI Service sẽ lấy Job object từ MongoDB. Mỗi Job có lưu mảng `chunks[]` chứa các block embedding (được nhúng từ text Description/Requirements). 
- Hệ thống lấy trung bình cộng (Average vector) của toàn bộ các chunk này thành một vector duy nhất mô tả toàn bộ công việc.

### 3.2. Vector Search (Retrieval)
- Sử dụng MongoDB `$vectorSearch` query vào collection `users` (đang có vector search index `default` sử dụng thuật toán HNSW).
- Điểm neo để query là **Average Job Vector**.
- Lọc cứng (Hard Filters): Yêu cầu người dùng có `role = "candidate"` và bật tìm kiếm `allowSearch = true`.
- Top-K: Lấy ra nhanh **100 đến 200 ứng viên** có Profile CV gần nghĩa nhất với Job.

### 3.3. MaxSim Re-ranking (Base AI Score)
Thay vì dùng điểm của thuật toán Vector Search vốn được đo bằng khoảng cách trên Average Vector của user, chúng ta chạy lại hàm cosine similarity (MaxSim):
- Đối với mỗi ứng viên trong tập 100 người, lấy tất cả các embedding `chunks` trong CV của họ.
- Tính Cosine Similarity giữa **Average Job Vector** và **Từng chunk riêng biệt** của ứng viên.
- Lấy điểm cao nhất trong tất cả các chunk đó làm Base Similarity.
- Chuyển hóa mức điểm Base Similarity sang Band Score là **40 điểm (Max 40đ)**.

### 3.4. Rule-based Overlay Scoring
Tải thông tin chi tiết (`CandidateProfile`) của top ứng viên và cộng thêm max 60 điểm cho các rule cứng:
- **Skill match (Max 30đ)**: So khớp mảng kỹ năng trong Job và ứng viên (Bao gồm Exact match - 8 điểm/kỹ năng, Partial match - 3 điểm/kỹ năng).
- **Category match (Max 10đ)**: Job category nằm trong Danh mục mong muốn.
- **Location match (Max 10đ)**: Trùng Tỉnh/Thành phố hoặc Quận/Huyện làm việc (Trùng Tỉnh: +7đ, Trùng Tỉnh & Quận: +10đ).
- **Experience match (Max 5đ)**: Level kinh nghiệm của Job nằm trong nguyện vọng của ứng viên.
- **Work type match (Max 5đ)**: Hình thức làm việc của Job khớp với nguyện vọng của ứng viên.

### 3.5. Trả kết quả (Output Format)
- Normalization: Quy đổi điểm số cuối cùng về hệ mét `0.0` đến `1.0` (Vd: 85 điểm = 0.85).
- Filter: Chỉ hiển thị những ứng viên có điểm số >= `minScore`. Lọc giảm dần.
- Bổ sung trường `matchReasons` để ứng dụng Frontend (Recruiter UI) hiển thị giải thích tính điểm cho nhà tuyển dụng (ví dụ: "Phù hợp với mô tả công việc", "Khớp 3 kỹ năng", v.v).
- Tính `experienceYears` dựa trên dải ngày tháng (startDate, endDate) của ứng viên và trả về để tích hợp trên giao diện thẻ ứng viên.
- Tính toán phân trang dựa theo Request Parameters `page` và `limit`.
