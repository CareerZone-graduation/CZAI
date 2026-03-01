"""
Utilities for normalizing free-text fields (skills, provinces, etc.)
so that user features and item features share the same namespace.
"""

import re

from unidecode import unidecode

# ── Skill synonym mapping ────────────────────────────────────────────────────
# Maps common alternative names → canonical form (all lowercase).
SKILL_SYNONYMS: dict[str, str] = {
    "js": "javascript",
    "reactjs": "react",
    "react.js": "react",
    "react js": "react",
    "vuejs": "vue",
    "vue.js": "vue",
    "vue js": "vue",
    "angularjs": "angular",
    "angular.js": "angular",
    "angular js": "angular",
    "nodejs": "node.js",
    "node": "node.js",
    "node js": "node.js",
    "nextjs": "next.js",
    "next js": "next.js",
    "expressjs": "express",
    "express.js": "express",
    "express js": "express",
    "typescript": "typescript",
    "ts": "typescript",
    "py": "python",
    "python3": "python",
    "python 3": "python",
    "c#": "csharp",
    "c sharp": "csharp",
    "c++": "cpp",
    "cplusplus": "cpp",
    "c plus plus": "cpp",
    "golang": "go",
    "postgres": "postgresql",
    "mongo": "mongodb",
    "mysql": "mysql",
    "mssql": "sql server",
    "ms sql": "sql server",
    "aws": "amazon web services",
    "gcp": "google cloud platform",
    "k8s": "kubernetes",
    "docker compose": "docker-compose",
    "ml": "machine learning",
    "dl": "deep learning",
    "ai": "artificial intelligence",
    "nlp": "natural language processing",
    "cv": "computer vision",
    "html5": "html",
    "css3": "css",
    "scss": "sass",
    "tailwindcss": "tailwind css",
    "tailwind": "tailwind css",
    "flutter": "flutter",
    "react native": "react-native",
    "reactnative": "react-native",
    "rn": "react-native",
    ".net": "dotnet",
    "dot net": "dotnet",
    "asp.net": "aspnet",
    "asp net": "aspnet",
    "spring boot": "spring-boot",
    "springboot": "spring-boot",
}

# ── Province normalization mapping ───────────────────────────────────────────
# Maps various Vietnamese province string representations → canonical slug.
_PROVINCE_RAW_MAP: dict[str, str] = {
    # Ho Chi Minh
    "hồ chí minh": "ho_chi_minh",
    "ho chi minh": "ho_chi_minh",
    "tp.hcm": "ho_chi_minh",
    "tp hcm": "ho_chi_minh",
    "tphcm": "ho_chi_minh",
    "tp. hồ chí minh": "ho_chi_minh",
    "tp hồ chí minh": "ho_chi_minh",
    "thành phố hồ chí minh": "ho_chi_minh",
    "thanh pho ho chi minh": "ho_chi_minh",
    "sài gòn": "ho_chi_minh",
    "sai gon": "ho_chi_minh",
    "saigon": "ho_chi_minh",
    "hcm": "ho_chi_minh",
    # Ha Noi
    "hà nội": "ha_noi",
    "ha noi": "ha_noi",
    "hanoi": "ha_noi",
    "hn": "ha_noi",
    "tp. hà nội": "ha_noi",
    "tp hà nội": "ha_noi",
    "thành phố hà nội": "ha_noi",
    # Da Nang
    "đà nẵng": "da_nang",
    "da nang": "da_nang",
    "danang": "da_nang",
    "tp đà nẵng": "da_nang",
    "tp. đà nẵng": "da_nang",
    # Hai Phong
    "hải phòng": "hai_phong",
    "hai phong": "hai_phong",
    "haiphong": "hai_phong",
    # Can Tho
    "cần thơ": "can_tho",
    "can tho": "can_tho",
    "cantho": "can_tho",
    # Binh Duong
    "bình dương": "binh_duong",
    "binh duong": "binh_duong",
    # Dong Nai
    "đồng nai": "dong_nai",
    "dong nai": "dong_nai",
    # Khanh Hoa (Nha Trang)
    "khánh hòa": "khanh_hoa",
    "khanh hoa": "khanh_hoa",
    "nha trang": "khanh_hoa",
    # Thua Thien Hue
    "thừa thiên huế": "thua_thien_hue",
    "thua thien hue": "thua_thien_hue",
    "huế": "thua_thien_hue",
    "hue": "thua_thien_hue",
    # Bac Ninh
    "bắc ninh": "bac_ninh",
    "bac ninh": "bac_ninh",
    # Quang Ninh
    "quảng ninh": "quang_ninh",
    "quang ninh": "quang_ninh",
    # Long An
    "long an": "long_an",
    # Ba Ria - Vung Tau
    "bà rịa - vũng tàu": "ba_ria_vung_tau",
    "ba ria vung tau": "ba_ria_vung_tau",
    "vũng tàu": "ba_ria_vung_tau",
    "vung tau": "ba_ria_vung_tau",
    # Lam Dong (Da Lat)
    "lâm đồng": "lam_dong",
    "lam dong": "lam_dong",
    "đà lạt": "lam_dong",
    "da lat": "lam_dong",
}


def normalize_skill(raw: str) -> str:
    """
    Normalize a skill string:
    1. Strip whitespace, lowercase
    2. Remove special chars except . - + #
    3. Lookup synonym table
    4. Return canonical slug
    """
    if not raw:
        return ""
    s = raw.strip().lower()
    # Remove chars that are not alphanumeric, space, dot, dash, plus, hash
    s = re.sub(r"[^\w\s.\-+#]", "", s)
    # Collapse multiple spaces
    s = re.sub(r"\s+", " ", s).strip()
    # Synonym lookup
    return SKILL_SYNONYMS.get(s, s)


def normalize_province(raw: str) -> str:
    """
    Normalize a Vietnamese province name to a canonical slug.
    Falls back to unidecode + underscore form if not in the lookup table.
    """
    if not raw:
        return ""
    s = raw.strip().lower()
    # Try direct lookup
    if s in _PROVINCE_RAW_MAP:
        return _PROVINCE_RAW_MAP[s]
    # Try after removing diacritics
    s_ascii = unidecode(s).lower().strip()
    if s_ascii in _PROVINCE_RAW_MAP:
        return _PROVINCE_RAW_MAP[s_ascii]
    # Fallback: transliterate and slugify
    slug = re.sub(r"[^a-z0-9]+", "_", s_ascii).strip("_")
    return slug


def salary_bucket(amount: float | None) -> str:
    """
    Convert a salary amount (VND) into a categorical bucket string.
    Returns 'negotiable' if amount is None or 0.
    """
    if amount is None or amount <= 0:
        return "negotiable"
    # Normalize to millions for bucketing
    amt = float(amount)
    if amt >= 1_000_000:
        amt = amt / 1_000_000  # convert to millions
    # amt is now in millions
    if amt < 5:
        return "0_5m"
    elif amt < 10:
        return "5m_10m"
    elif amt < 15:
        return "10m_15m"
    elif amt < 20:
        return "15m_20m"
    elif amt < 30:
        return "20m_30m"
    elif amt < 50:
        return "30m_50m"
    else:
        return "50m_plus"
