copilot_tools = [
    {
        "type": "function",
        "function": {
            "name": "search_jobs",
            "description": "Tìm kiếm việc làm theo nhiều tiêu chí hoặc tìm kiếm theo ngữ nghĩa. Dùng khi user muốn tìm job theo từ khóa, kỹ năng, địa điểm, mức lương, loại hình công việc, v.v. Hỗ trợ cả tìm kiếm ngữ nghĩa (semantic) và lọc chính xác (exact filter).",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Từ khóa tìm kiếm ngữ nghĩa (semantic search). VD: 'lập trình viên React có kinh nghiệm fintech'"
                    },
                    "province": {
                        "type": "string",
                        "description": "Tỉnh/thành phố. VD: 'Hồ Chí Minh', 'Hà Nội'"
                    },
                    "district": {
                        "type": "string",
                        "description": "Quận/huyện"
                    },
                    "category": {
                        "type": "string",
                        "enum": [
                            "IT", "SOFTWARE_DEVELOPMENT", "DATA_SCIENCE", "MACHINE_LEARNING", 
                            "WEB_DEVELOPMENT", "SALES", "MARKETING", "ACCOUNTING", 
                            "GRAPHIC_DESIGN", "CONTENT_WRITING", "MEDICAL", "TEACHING", 
                            "ENGINEERING", "PRODUCTION", "LOGISTICS", "HOSPITALITY", 
                            "REAL_ESTATE", "LAW", "FINANCE", "HUMAN_RESOURCES", 
                            "CUSTOMER_SERVICE", "ADMINISTRATION", "MANAGEMENT", "OTHER"
                        ],
                        "description": "Danh mục ngành nghề"
                    },
                    "type": {
                        "type": "string",
                        "enum": ["FULL_TIME", "PART_TIME", "CONTRACT", "INTERNSHIP", "TEMPORARY", "VOLUNTEER", "FREELANCE"],
                        "description": "Loại hình công việc"
                    },
                    "workType": {
                        "type": "string",
                        "enum": ["ON_SITE", "REMOTE", "HYBRID"],
                        "description": "Hình thức làm việc"
                    },
                    "experience": {
                        "type": "string",
                        "enum": ["ENTRY_LEVEL", "MID_LEVEL", "SENIOR_LEVEL", "EXECUTIVE", "NO_EXPERIENCE", "INTERN", "FRESHER"],
                        "description": "Yêu cầu kinh nghiệm"
                    },
                    "minSalary": {
                        "type": "number",
                        "description": "Mức lương tối thiểu (VND/tháng)"
                    },
                    "maxSalary": {
                        "type": "number",
                        "description": "Mức lương tối đa (VND/tháng)"
                    },
                    "skills": {
                        "type": "array",
                        "items": { "type": "string" },
                        "description": "Danh sách kỹ năng yêu cầu. VD: ['React', 'Node.js']"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Số lượng kết quả tối đa (default: 10, max: 20)"
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_job_detail",
            "description": "Lấy thông tin chi tiết của một việc làm theo ID. Dùng khi cần xem chi tiết, tóm tắt, hoặc phân tích một job cụ thể.",
            "parameters": {
                "type": "object",
                "properties": {
                    "jobId": {
                        "type": "string",
                        "description": "MongoDB ObjectId của job"
                    }
                },
                "required": ["jobId"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_recommendations",
            "description": "Lấy danh sách việc làm gợi ý cá nhân hóa cho ứng viên dựa trên lịch sử tương tác (xem, lưu, ứng tuyển). Chỉ dùng cho user có role 'candidate'.",
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "Số lượng gợi ý (default: 10, max: 20)"
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_my_interviews",
            "description": "Lấy lịch phỏng vấn sắp tới hoặc đã qua (đã hoàn thành). Dùng cho cả recruiter và candidate.",
            "parameters": {
                "type": "object",
                "properties": {
                    "timeRange": {
                        "type": "string",
                        "enum": ["upcoming", "past"],
                        "description": "Khoảng thời gian (default: upcoming)"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Số lượng (default: 10)"
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_my_applications",
            "description": "Lấy danh sách các công việc mà ứng viên đã ứng tuyển. Dùng khi candidate muốn xem trạng thái của các đơn xin việc của mình.",
            "parameters": {
                "type": "object",
                "properties": {
                    "status": {
                        "type": "string",
                        "enum": ["PENDING", "REVIEWING", "INTERVIEWING", "ACCEPTED", "REJECTED"],
                        "description": "Trạng thái đơn xin việc"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Số lượng kết quả trả về"
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "getExpiringJobs",
            "description": "Lấy danh sách các bài đăng tuyển dụng của nhà tuyển dụng sắp hết hạn. Chỉ dùng cho user có role 'recruiter'.",
            "parameters": {
                "type": "object",
                "properties": {
                    "days": {
                        "type": "integer",
                        "description": "Số ngày còn lại trước khi hết hạn (ví dụ: 7 ngày)"
                    },
                    "limit": {
                        "type": "integer"
                    }
                },
                "required": []
            }
        }
    },

    {
        "type": "function",
        "function": {
            "name": "getSavedJobsExpiringSoon",
            "description": "Lấy danh sách các công việc đã lưu, yêu thích sắp tới hạn chót nộp hồ sơ. Dùng cho role 'candidate'.",
            "parameters": {
                "type": "object",
                "properties": {
                    "days": {
                        "type": "integer",
                        "description": "Số ngày để check (ví dụ: việc hết hạn trong 3 ngày tới)"
                    },
                    "limit": {
                        "type": "integer"
                    }
                },
                "required": []
            }
        }
    }
]
