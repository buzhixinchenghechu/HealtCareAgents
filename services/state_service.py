
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, MutableMapping

def seed_patients() -> List[Dict]:
    now = datetime.now()
    return [
        {
            "id": "PT-001",
            "name": "张建民",
            "diagnosis": "晚期肿瘤骨转移痛",
            "department": "肿瘤科",
            "risk_level": "中风险",
            "med_status": "用药中",
            "created_at": now.strftime("%Y-%m-%d"),
            "evaluations": [],
            "tracking": [
                {"time": (now - timedelta(days=2)).strftime("%Y-%m-%d"), "pain": 8, "adverse": "轻度便秘", "adherence": 80},
                {"time": (now - timedelta(days=1)).strftime("%Y-%m-%d"), "pain": 6, "adverse": "无明显", "adherence": 90},
            ],
            "followups": [{"time": now.strftime("%Y-%m-%d 14:00"), "status": "待完成", "note": "首次复评"}],
        },
        {
            "id": "PT-002",
            "name": "李海宁",
            "diagnosis": "术后急性疼痛",
            "department": "骨科",
            "risk_level": "低风险",
            "med_status": "待评估",
            "created_at": now.strftime("%Y-%m-%d"),
            "evaluations": [],
            "tracking": [],
            "followups": [{"time": (now + timedelta(hours=3)).strftime("%Y-%m-%d %H:%M"), "status": "待完成", "note": "24h 随访"}],
        },
    ]

def init_state(session_state: MutableMapping[str, Any], option_list: Callable[[str], List[Any]]) -> None:
    defaults = {
        "current_page": option_list("sidebar_pages")[0],
        "is_logged_in": False,
        "doctor_name": "未登录用户",
        "doctor_title": "请先登录",
        "training_case": "",
        "training_history": [],
        "audit_events": [],
        "last_report": "",
        "clinical_last_result": None,
        "policy_country": option_list("policy_country")[0],
        "policy_province": option_list("policy_province")[0],
        "patients": seed_patients(),
        "psych_label_counts": {"恐惧型": 0, "均衡型": 0, "放开型": 0, "咨询依赖型": 0},
    }
    for key, value in defaults.items():
        if key not in session_state:
            session_state[key] = value
