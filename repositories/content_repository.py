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
    cases: List[Dict] = []

    # 1. 阿片类病例（sample_cases.json）
    opioid_path = base_dir / "data" / "cases" / "sample_cases.json"
    if opioid_path.exists():
        for encoding in ("utf-8", "gbk", "gb18030"):
            try:
                with open(opioid_path, "r", encoding=encoding) as f:
                    data = json.load(f)
                if isinstance(data, list):
                    cases.extend(data)
                    break
            except Exception:
                continue

    # 2. 成瘾治疗病例（addiction_cases.csv）—— 转换为统一格式
    import csv
    addiction_path = base_dir / "skill" / "addiction-treatment" / "data" / "addiction_cases.csv"
    if addiction_path.exists():
        try:
            with open(addiction_path, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for i, row in enumerate(reader):
                    cases.append({
                        "id": f"ADD-{row.get('患者ID', i+1):0>4}",
                        "diagnosis": f"{row.get('诊断', '').strip()}成瘾",
                        "category": "成瘾治疗",
                        "pain_type": "成瘾相关",
                        "pain_score": 0,
                        "comorbidities": "",
                        "recommended_plan": row.get("answer", ""),
                        "evidence": "addiction-treatment知识库",
                        "risk_notes": f"主要药物：{row.get('药物', '')}",
                        "outcome": "",
                        "question": row.get("question", ""),
                    })
        except Exception:
            pass

    return cases
