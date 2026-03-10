from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

import streamlit as st


@st.cache_data
def load_static_content(static_content_path: Path) -> Dict[str, Any]:
    defaults = {
        "news_feed": [],
        "policy_library": [],
        "course_matrix": [],
        "opioid_mme_factors": {},
        "ui_options": {},
    }
    if not static_content_path.exists():
        return defaults

    for encoding in ("utf-8", "gbk", "gb18030"):
        try:
            with open(static_content_path, "r", encoding=encoding) as f:
                data = json.load(f)
            if not isinstance(data, dict):
                continue

            merged = defaults.copy()
            for key, default_val in defaults.items():
                val = data.get(key, default_val)
                if isinstance(default_val, list) and isinstance(val, list):
                    merged[key] = val
                elif isinstance(default_val, dict) and isinstance(val, dict):
                    merged[key] = val
            return merged
        except Exception:
            continue

    return defaults


@st.cache_data
def load_cases(base_dir: Path) -> List[Dict]:
    path = base_dir / "data" / "cases" / "sample_cases.json"
    if not path.exists():
        return []
    for encoding in ("utf-8", "gbk", "gb18030"):
        try:
            with open(path, "r", encoding=encoding) as f:
                data = json.load(f)
            if isinstance(data, list):
                return data
        except Exception:
            continue
    return []
