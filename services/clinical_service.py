
from __future__ import annotations

import re
from typing import Dict, List, Tuple

def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", str(text).lower()).strip()

def tokenize(text: str) -> set:
    return set(re.findall(r"[a-z0-9\u4e00-\u9fff]+", normalize_text(text)))

def case_summary_text(case: Dict) -> str:
    return " ".join(
        filter(
            None,
            [case.get("id", ""), case.get("diagnosis", ""), case.get("category", ""), case.get("pain_type", ""), case.get("recommended_plan", ""), case.get("risk_notes", "")],
        )
    )

def retrieve_similar_cases(query: str, cases: List[Dict], top_k: int = 3) -> List[Dict]:
    if not cases:
        return []
    q_tokens = tokenize(query)
    if not q_tokens:
        return cases[:top_k]
    scored = []
    for case in cases:
        tokens = tokenize(case_summary_text(case))
        if not tokens:
            continue
        overlap = len(q_tokens & tokens)
        score = overlap / max(len(q_tokens), 1)
        scored.append((score, case))
    scored.sort(key=lambda x: x[0], reverse=True)
    chosen = [c for s, c in scored if s > 0][:top_k]
    return chosen or cases[:top_k]

def calc_ort(age: int, personal_use: str, family_use: str, psych_histories: List[str]) -> Tuple[int, str, List[str]]:
    score = 0
    details = []
    if 16 <= age <= 45:
        score += 1
        details.append("年龄 16-45 岁 +1")
    personal_points = {"无": 0, "酒精使用史": 3, "非法药物使用史": 4, "处方药滥用史": 5}
    family_points = {"无": 0, "家族酒精使用史": 1, "家族非法药物使用史": 2, "家族处方药滥用史": 4}
    psych_points = {"抑郁": 1, "ADHD": 2, "双相障碍": 2, "精神分裂谱系障碍": 2}
    score += personal_points.get(personal_use, 0)
    if personal_points.get(personal_use, 0):
        details.append(f"{personal_use} +{personal_points[personal_use]}")
    score += family_points.get(family_use, 0)
    if family_points.get(family_use, 0):
        details.append(f"{family_use} +{family_points[family_use]}")
    for item in psych_histories:
        pts = psych_points.get(item, 0)
        if pts:
            score += pts
            details.append(f"{item} +{pts}")
    if score <= 3:
        return score, "低风险", details
    if score <= 7:
        return score, "中风险", details
    return score, "高风险", details

def risk_tag_class(level: str) -> str:
    if level == "低风险":
        return "risk-low"
    if level == "中风险":
        return "risk-mid"
    return "risk-high"

def local_plan(age: int, pain_score: int, ort_level: str, opioid_naive: bool, pain_type: str, diagnosis: str = "") -> List[Dict]:
    diag = diagnosis.lower()

    # 诊断特异性规则（优先于通用评分规则）
    if any(k in diag for k in ["胰腺炎", "胰腺"]):
        core = "急性胰腺炎镇痛：禁用吗啡/哌替啶（升高Oddi括约肌压力），首选氢吗啡酮或芬太尼。"
        drug = "氢吗啡酮注射液（首选）；备选：芬太尼PCA"
        dose = "氢吗啡酮 0.2-0.6mg IV q4h；芬太尼 25-50μg IV prn"
    elif any(k in diag for k in ["颅脑创伤", "颅脑损伤", "脑外伤", "tbi"]):
        core = "颅脑创伤镇痛：首选芬太尼（颅内压影响小），避免使用吗啡。"
        drug = "芬太尼注射液（首选）；备选：氢吗啡酮"
        dose = "芬太尼 25-50μg IV prn 或持续泵注，密切监测镇静深度"
    elif any(k in diag for k in ["主动脉夹层", "夹层"]):
        core = "主动脉夹层：镇痛镇静并重，吗啡首选，同步降压治疗。"
        drug = "吗啡注射液"
        dose = "吗啡 5-10mg IV 缓慢注射，监测血压及呼吸"
    elif any(k in diag for k in ["acs", "急性冠脉", "心肌梗死", "心梗"]):
        core = "ACS镇痛：吗啡可缓解疼痛和焦虑，确认无禁忌后使用。"
        drug = "吗啡注射液"
        dose = "吗啡 5-10mg IV，每5-15min可重复，总量不超过15mg"
    elif any(k in diag for k in ["烧伤"]):
        core = "烧伤镇痛：强阿片为主，注意大面积烧伤时药物吸收改变。"
        drug = "吗啡或氢吗啡酮注射液"
        dose = "按体重和烧伤面积调整，建议PCA模式"
    elif pain_score <= 3:
        core = "优先非阿片药物，短期观察。"
        drug = "对乙酰氨基酚/NSAIDs"
        dose = "按说明书常规剂量"
    elif pain_score <= 6:
        core = "短疗程低剂量阿片 + 非阿片联合。"
        drug = "曲马多或低剂量短效阿片"
        dose = "起始低剂量，每 24h 复核"
    else:
        core = "短效强阿片滴定起始，优先建立复评计划。"
        drug = "吗啡短效制剂/芬太尼（按适应证）"
        dose = "最低有效剂量起始，48-72h 内复评"
    monitor = "3-7 天复评"
    if ort_level == "中风险":
        monitor = "72h 内复评 + 限量处方"
    if ort_level == "高风险":
        monitor = "24-72h 内复评 + 会诊 + 二次审方"
    adjunct = "通便、止吐、跌倒风险教育"
    if "癌" in pain_type:
        adjunct = "通便、止吐、睡眠管理、家属教育"
    return [
        {"字段": "处方建议", "内容": core},
        {"字段": "首选药物", "内容": drug},
        {"字段": "起始剂量策略", "内容": dose},
        {"字段": "是否初治", "内容": "是（最低有效剂量）" if opioid_naive else "否（需核对既往耐受）"},
        {"字段": "辅助措施", "内容": adjunct},
        {"字段": "随访计划", "内容": monitor},
    ]

def risk_radar_values(pain_score: int, ort_level: str, current_meds: str, comorbidities: str) -> Dict[str, List[int]]:
    addiction = 3 if ort_level == "低风险" else (6 if ort_level == "中风险" else 9)
    interaction = 8 if ("苯二氮卓" in current_meds or "安眠" in current_meds) else 4
    respiratory = 8 if ("呼吸" in comorbidities or "copd" in normalize_text(comorbidities)) else 3
    policy = 8 if ort_level == "高风险" else 4
    clinical = min(max(pain_score, 1), 10)
    return {
        "临床复杂度": [clinical],
        "成瘾风险": [addiction],
        "相互作用风险": [interaction],
        "呼吸抑制风险": [respiratory],
        "政策合规风险": [policy],
    }

def calc_mme_day(drug: str, dose: float, freq_per_day: int, mme_factors: Dict[str, float]) -> Tuple[float, str]:
    if drug == "无" or dose <= 0:
        return 0.0, "未选择阿片类拟开具药物"
    if drug == "芬太尼贴剂":
        mme = dose * mme_factors["芬太尼贴剂"]
        return round(mme, 1), "换算规则：芬太尼贴剂 MME/day = mcg/h × 2.4"
    factor = mme_factors.get(drug, 0.0)
    if factor <= 0:
        return 0.0, "未匹配到换算系数"
    mme = dose * max(freq_per_day, 1) * factor
    return round(mme, 1), f"换算规则：MME/day = 单次剂量 × 频次 × 系数({factor})"
