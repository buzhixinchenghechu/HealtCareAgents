# -*- coding: utf-8 -*-
"""阿片类药物辅助决策系统（按设计初稿升级版）"""

from __future__ import annotations

import json
import os
import random
import re
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import altair as alt
import streamlit as st
from openai import OpenAI
from pages.profile_page import render_profile_metrics, render_recent_audit
from repositories.session_repository import append_audit_event, get_audit_events, get_patients, get_training_history
from rules.monitoring_rules import (
    COMPLETED_FOLLOWUP_STATUS,
    HIGH_RISK_LEVEL,
    OVERDUE_FOLLOWUP_STATUS,
    PENDING_FOLLOWUP_STATUS,
    PENDING_MED_STATUS,
    display_followup_status,
)
from services.followup_service import mark_followup_completed
from services.metrics_service import compute_profile_metrics


st.set_page_config(
    page_title="智医助手 - 阿片类药物辅助决策系统",
    page_icon="💊",
    layout="wide",
    initial_sidebar_state="expanded",
)


PRIMARY = "#165DFF"
SUCCESS = "#00B42A"
WARNING = "#FF7D00"
DANGER = "#F53F3F"
SIDEBAR_BG = "#EAF3FF"


BASE_DIR = Path(__file__).resolve().parent
STATIC_CONTENT_PATH = BASE_DIR / "data" / "static_content.json"


@st.cache_data
def load_static_content() -> Dict[str, Any]:
    defaults = {
        "news_feed": [],
        "policy_library": [],
        "course_matrix": [],
        "opioid_mme_factors": {},
        "ui_options": {},
    }
    if not STATIC_CONTENT_PATH.exists():
        return defaults

    for encoding in ("utf-8", "gbk", "gb18030"):
        try:
            with open(STATIC_CONTENT_PATH, "r", encoding=encoding) as f:
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


_STATIC_CONTENT = load_static_content()
NEWS_FEED = _STATIC_CONTENT["news_feed"]
POLICY_LIBRARY = _STATIC_CONTENT["policy_library"]
COURSE_MATRIX = _STATIC_CONTENT["course_matrix"]
OPIOID_MME_FACTORS = _STATIC_CONTENT["opioid_mme_factors"]

REQUIRED_UI_OPTION_KEYS = {
    "sidebar_pages",
    "protected_pages",
    "clinical_gender",
    "clinical_diag_template",
    "clinical_pain_type",
    "clinical_dept",
    "clinical_allergy",
    "clinical_current_opioid",
    "clinical_current_freq",
    "clinical_co_meds",
    "clinical_comorb",
    "clinical_adverse_hist",
    "clinical_plan_drug",
    "clinical_personal_use",
    "clinical_family_use",
    "clinical_psych",
    "clinical_follow_hours",
    "training_difficulty",
    "training_department",
    "training_quiz_binary",
    "training_policy_country",
    "policy_category",
    "policy_tag",
    "policy_country",
    "policy_province",
    "policy_ort_level",
    "doctor_add_department",
    "doctor_add_risk_level",
    "doctor_filter_risk",
    "doctor_filter_status",
    "doctor_eval_personal_use",
    "doctor_eval_family_use",
    "doctor_eval_psych",
    "doctor_tracking_adverse",
    "register_department",
}


def build_ui_options(raw_options: Any) -> Dict[str, List[Any]]:
    raw = raw_options if isinstance(raw_options, dict) else {}
    cleaned: Dict[str, List[Any]] = {}
    for key, value in raw.items():
        if isinstance(key, str) and isinstance(value, list) and value:
            cleaned[key] = value

    missing = sorted(k for k in REQUIRED_UI_OPTION_KEYS if k not in cleaned)
    if missing:
        missing_text = ", ".join(missing)
        raise ValueError(f"ui_options 缺少必要键: {missing_text}")
    return cleaned


UI_OPTIONS = build_ui_options(_STATIC_CONTENT.get("ui_options", {}))


def option_list(name: str) -> List[Any]:
    options = UI_OPTIONS.get(name)
    if not options:
        raise KeyError(f"未配置 UI 选项: {name}")
    return options


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


def inject_css() -> None:
    st.markdown(
        f"""
        <style>
        :root {{
            --brand: {PRIMARY};
            --ok: {SUCCESS};
            --warn: {WARNING};
            --danger: {DANGER};
            --sidebar-bg: {SIDEBAR_BG};
            --text: #1f2d3d;
            --muted: #617085;
        }}
        .stApp {{
            background:
                radial-gradient(900px 320px at -10% -10%, #d9e8ff 0%, rgba(217, 232, 255, 0) 60%),
                radial-gradient(900px 320px at 120% -10%, #dff6ff 0%, rgba(223, 246, 255, 0) 60%),
                #f5f8fc;
        }}
        [data-testid="stSidebar"] {{
            background: var(--sidebar-bg);
            color: #1f3556;
        }}
        [data-testid="stSidebar"] .stRadio label,
        [data-testid="stSidebar"] .stMarkdown,
        [data-testid="stSidebar"] .stCaption,
        [data-testid="stSidebar"] .stText {{
            color: #1f3556 !important;
        }}
        .top-hero {{
            background: linear-gradient(120deg, #1242c4 0%, #165dff 52%, #24b3ee 100%);
            border-radius: 16px;
            border: 1px solid rgba(255,255,255,0.25);
            color: #fff;
            padding: 20px 22px;
            box-shadow: 0 12px 24px rgba(22, 93, 255, 0.20);
        }}
        .top-hero h1 {{
            margin: 0 0 6px 0;
            font-size: 28px;
            font-weight: 800;
        }}
        .top-hero p {{
            margin: 0;
            font-size: 14px;
            opacity: 0.95;
        }}
        .kpi-card {{
            background: #fff;
            border: 1px solid #e7edf6;
            border-radius: 14px;
            padding: 14px;
            box-shadow: 0 6px 14px rgba(20, 40, 70, 0.04);
        }}
        .kpi-title {{ font-size: 12px; color: var(--muted); }}
        .kpi-value {{ font-size: 28px; color: var(--text); font-weight: 700; line-height: 1.1; margin-top: 4px; }}
        .kpi-sub {{ font-size: 12px; color: var(--brand); margin-top: 4px; }}
        .warn-bar {{
            background: #fff2f2;
            color: #9c1d1d;
            border: 1px solid #ffd1d1;
            border-radius: 10px;
            padding: 8px 10px;
            font-size: 13px;
            margin-bottom: 8px;
            font-weight: 600;
        }}
        .ok-bar {{
            background: #effcf3;
            color: #0f6a2a;
            border: 1px solid #c9efda;
            border-radius: 10px;
            padding: 8px 10px;
            font-size: 13px;
            margin-bottom: 8px;
            font-weight: 600;
        }}
        .risk-tag {{
            display: inline-block;
            padding: 2px 8px;
            font-size: 12px;
            border-radius: 999px;
            margin-right: 6px;
        }}
        .risk-low {{ background: #e8f8ee; color: #116f35; }}
        .risk-mid {{ background: #fff5e5; color: #a35c00; }}
        .risk-high {{ background: #ffecef; color: #a61f2f; }}
        .policy-card {{
            background: #fff;
            border: 1px solid #e8edf7;
            border-radius: 12px;
            padding: 12px;
            margin-bottom: 10px;
        }}
        .policy-title {{ font-size: 15px; font-weight: 700; color: #10243d; margin-bottom: 4px; }}
        .source-note {{
            position: fixed;
            left: 50%;
            transform: translateX(-50%);
            bottom: 8px;
            background: rgba(255,255,255,0.85);
            border: 1px solid #dbe7ff;
            color: #5f6d82;
            border-radius: 999px;
            font-size: 11px;
            padding: 4px 12px;
            z-index: 999;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def init_state() -> None:
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
        if key not in st.session_state:
            st.session_state[key] = value


def safe_secret(name: str) -> str:
    try:
        return str(st.secrets.get(name, "")).strip()
    except Exception:
        return ""


@st.cache_resource
def get_client_and_model() -> Tuple[Optional[OpenAI], str]:
    dashscope_key = safe_secret("DASHSCOPE_API_KEY") or os.environ.get("DASHSCOPE_API_KEY", "").strip()
    openai_key = safe_secret("OPENAI_API_KEY") or os.environ.get("OPENAI_API_KEY", "").strip()
    if dashscope_key:
        return (
            OpenAI(api_key=dashscope_key, base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"),
            "qwen-plus",
        )
    if openai_key:
        return OpenAI(api_key=openai_key), "gpt-4o-mini"
    return None, ""


def ask_llm(client: Optional[OpenAI], model: str, system_prompt: str, user_prompt: str) -> str:
    if not client:
        return ""
    try:
        rsp = client.chat.completions.create(
            model=model,
            messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
            temperature=0.2,
            max_tokens=1000,
        )
        return (rsp.choices[0].message.content or "").strip()
    except Exception as exc:
        return f"AI 生成失败：{exc}"


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", str(text).lower()).strip()


def tokenize(text: str) -> set:
    return set(re.findall(r"[a-z0-9\u4e00-\u9fff]+", normalize_text(text)))


@st.cache_data
def load_cases() -> List[Dict]:
    path = BASE_DIR / "data" / "cases" / "sample_cases.json"
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


def mask_name(name: str) -> str:
    name = name.strip()
    if len(name) <= 1:
        return name
    if len(name) == 2:
        return f"{name[0]}*"
    return f"{name[0]}*{name[-1]}"


def get_patient_by_id(pid: str) -> Optional[Dict]:
    for p in st.session_state.patients:
        if p["id"] == pid:
            return p
    return None


def parse_time_safe(value: str) -> datetime:
    text = str(value).strip()
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt)
        except Exception:
            continue
    return datetime.max


def render_tracking_curve(patient: Dict) -> None:
    tracking = patient.get("tracking", [])
    if not tracking:
        st.info("暂无用药后追踪记录。")
        return

    points = []
    for item in tracking:
        t = parse_time_safe(item.get("time", ""))
        if t == datetime.max:
            continue
        points.append({"time": t.strftime("%Y-%m-%d"), "metric": "疼痛评分", "value": float(item.get("pain", 0))})
        points.append({"time": t.strftime("%Y-%m-%d"), "metric": "依从性", "value": float(item.get("adherence", 0))})

    if points:
        chart = (
            alt.Chart(alt.Data(values=points))
            .mark_line(point=True)
            .encode(
                x=alt.X("time:T", title="日期"),
                y=alt.Y("value:Q", title="数值"),
                color=alt.Color("metric:N", scale=alt.Scale(domain=["疼痛评分", "依从性"], range=[DANGER, PRIMARY])),
                tooltip=["time:T", "metric:N", "value:Q"],
            )
            .properties(height=260)
        )
        st.altair_chart(chart, use_container_width=True)

    rows = []
    for item in tracking:
        rows.append(
            {
                "日期": item.get("time", ""),
                "疼痛评分": item.get("pain", ""),
                "依从性": item.get("adherence", ""),
                "不良反应": item.get("adverse", "无明显"),
            }
        )
    st.dataframe(rows, use_container_width=True, hide_index=True)


def render_followup_timeline(patient: Dict) -> None:
    followups = patient.get("followups", [])
    if not followups:
        st.info("暂无随访计划。")
        return

    now = datetime.now()
    sorted_items = sorted(followups, key=lambda x: parse_time_safe(x.get("time", "")))
    for item in sorted_items:
        due = parse_time_safe(item.get("time", ""))
        status = item.get("status", "待完成")
        if status == "待完成" and due != datetime.max and due < now:
            status = "逾期"
        if status == "已完成":
            color = SUCCESS
            icon = "✅"
        elif status == "逾期":
            color = DANGER
            icon = "❌"
        else:
            color = WARNING
            icon = "⏳"
        st.markdown(
            f"<div style='border-left:3px solid {color};padding-left:10px;margin:8px 0;'>"
            f"<b>{icon} {item.get('time','')}</b> | 状态：<span style='color:{color};font-weight:700'>{status}</span><br/>"
            f"<span style='color:#5b6b7e'>{item.get('note','')}</span></div>",
            unsafe_allow_html=True,
        )


def local_plan(age: int, pain_score: int, ort_level: str, opioid_naive: bool, pain_type: str) -> List[Dict]:
    if pain_score <= 3:
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


def calc_mme_day(drug: str, dose: float, freq_per_day: int) -> Tuple[float, str]:
    if drug == "无" or dose <= 0:
        return 0.0, "未选择阿片类拟开具药物"
    if drug == "芬太尼贴剂":
        mme = dose * OPIOID_MME_FACTORS["芬太尼贴剂"]
        return round(mme, 1), "换算规则：芬太尼贴剂 MME/day = mcg/h × 2.4"
    factor = OPIOID_MME_FACTORS.get(drug, 0.0)
    if factor <= 0:
        return 0.0, "未匹配到换算系数"
    mme = dose * max(freq_per_day, 1) * factor
    return round(mme, 1), f"换算规则：MME/day = 单次剂量 × 频次 × 系数({factor})"


def render_radar_chart(radar: Dict[str, List[int]]) -> None:
    categories = list(radar.keys())
    points = [{"category": k, "value": (v[0] if isinstance(v, list) else v)} for k, v in radar.items()]
    chart = (
        alt.Chart(alt.Data(values=points))
        .mark_line(point=True, interpolate="linear-closed", strokeWidth=2)
        .encode(
            theta=alt.Theta("category:N", sort=categories),
            radius=alt.Radius("value:Q", scale=alt.Scale(domain=[0, 10])),
            color=alt.value(PRIMARY),
            tooltip=["category:N", "value:Q"],
        )
        .properties(width=360, height=320)
    )
    st.altair_chart(chart, use_container_width=True)


def render_header() -> None:
    date_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    st.markdown(
        f"""
        <div class="top-hero">
            <h1>智医助手 · 阿片类药物辅助决策系统</h1>
            <p>临床辅助 + 虚拟训练 + 政策解读 + 管理后台闭环 | 当前时间：{date_str}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def sidebar_navigation() -> str:
    pages = option_list("sidebar_pages")
    with st.sidebar:
        st.markdown("## 智医助手")
        st.caption("Opioid Decision Support v2026")
        page = st.radio("导航", pages, index=pages.index(st.session_state.current_page))
        st.session_state.current_page = page
        st.markdown("---")
        st.markdown("### 账户状态")
        if st.session_state.is_logged_in:
            st.success(f"已登录：{st.session_state.doctor_name}")
            st.caption(st.session_state.doctor_title)
            if st.button("退出登录", use_container_width=True):
                st.session_state.is_logged_in = False
                st.session_state.doctor_name = "未登录用户"
                st.session_state.doctor_title = "请先登录"
                st.rerun()
        else:
            st.warning("未登录")
            st.caption("进入“登录与安全”可完成认证")
        st.markdown("---")
        st.caption("数据保密：患者敏感信息默认脱敏显示，所有日志可追溯不可删除。")
    return page


def render_footer_note() -> None:
    st.markdown("---")
    st.caption("数据来源：国家卫健委/医保局/药监局及核心医学期刊 | 本系统仅作临床辅助参考")
    st.markdown(
        """
        <div class="source-note">
            医疗数据保密声明：遵循《个人信息保护法》，敏感字段脱敏展示，访问全程审计
        </div>
        """,
        unsafe_allow_html=True,
    )


def page_dashboard(cases: List[Dict]) -> None:
    st.markdown("### 工作台总览")
    profile_metrics = compute_profile_metrics(get_patients(st.session_state), get_training_history(st.session_state))
    completion_rate = f"{profile_metrics.high_risk_followup_completion_rate * 100:.1f}%"

    c1, c2, c3, c4 = st.columns(4)
    metrics = [
        ("本周辅助决策", str(profile_metrics.weekly_decisions), "来自评估记录自动统计"),
        (
            "高风险复评完成率",
            completion_rate,
            f"已完成 {profile_metrics.completed_high_risk_followups}/{profile_metrics.due_high_risk_followups}",
        ),
        ("今日异常预警", str(profile_metrics.today_alerts), "根据追踪记录自动识别"),
        ("训练平均得分", f"{profile_metrics.training_avg_score:.1f}", "仅统计本周训练"),
    ]
    for col, (title, val, sub) in zip([c1, c2, c3, c4], metrics):
        with col:
            st.markdown(
                f"""
                <div class="kpi-card">
                    <div class="kpi-title">{title}</div>
                    <div class="kpi-value">{val}</div>
                    <div class="kpi-sub">{sub}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    left, mid, right = st.columns([1.1, 1.1, 0.9])
    pages = option_list("sidebar_pages")
    with left:
        st.markdown("#### 核心功能入口")
        if st.button("进入真实病例辅助", use_container_width=True):
            st.session_state.current_page = pages[1]
            st.rerun()
        if st.button("进入虚拟训练场", use_container_width=True):
            st.session_state.current_page = pages[2]
            st.rerun()
        if st.button("进入政策文献库", use_container_width=True):
            st.session_state.current_page = pages[3]
            st.rerun()
        if st.button("进入医生管理后台", use_container_width=True):
            st.session_state.current_page = pages[4]
            st.rerun()
        st.markdown("#### 科室用药统计概览")
        st.bar_chart({"肿瘤科": [38], "疼痛科": [31], "骨科": [19], "急诊科": [14]})

    with mid:
        st.markdown("#### 实时医学进展流")
        for item in NEWS_FEED:
            with st.container(border=True):
                st.write(f"**{item['title']}**")
                st.caption(item["date"])
                st.write(item["summary"])

    with right:
        st.markdown("#### 今日状态")
        st.info(f"今日异常预警 {profile_metrics.today_alerts} 条，建议优先复核高风险记录。")
        pending = profile_metrics.due_high_risk_followups - profile_metrics.completed_high_risk_followups
        if pending > 0:
            st.warning(f"当前仍有 {pending} 项高风险随访待完成。")
        else:
            st.success("当前高风险随访已全部完成。")
        st.success(f"政策引擎已加载 {len(POLICY_LIBRARY)} 条结构化政策文档。")
        st.markdown("#### 快速指南")
        st.markdown("1. 先评估风险，再制定剂量。")
        st.markdown("2. 高风险处方必须限量并记录知情同意。")
        st.markdown("3. 复评节点必须写入病历和随访计划。")


def page_clinical_assistant(client: Optional[OpenAI], model: str, cases: List[Dict]) -> None:
    st.markdown("### 真实病例辅助")
    st.caption("左侧病例录入工作台，右侧 AI 辅助建议看板（处方卡片 + 风险雷达 + 循证溯源 + 会诊讨论）。")
    left, right = st.columns([1.0, 1.15], gap="large")
    submitted = False
    with left:
        with st.form("clinical_form", clear_on_submit=False):
            a, b, c = st.columns(3)
            with a:
                patient_name = st.text_input("患者姓名", placeholder="如：张某", key="clinical_patient_name")
                age = st.number_input("年龄", 1, 120, 58, key="clinical_age")
                gender = st.selectbox("性别", option_list("clinical_gender"), key="clinical_gender")
                pain_score = st.slider("疼痛评分 NRS", 0, 10, 7, key="clinical_pain_score")
            with b:
                diagnosis_template = st.selectbox(
                    "主要诊断模板",
                    option_list("clinical_diag_template"),
                    key="clinical_diag_template",
                )
                diagnosis_extra = st.text_input("诊断补充", placeholder="如：伴睡眠障碍", key="clinical_diag_extra")
                pain_type = st.selectbox("疼痛类型", option_list("clinical_pain_type"), key="clinical_pain_type")
                department = st.selectbox("科室", option_list("clinical_dept"), key="clinical_dept")
            with c:
                opioid_naive = st.checkbox("阿片初治患者", True, key="clinical_opioid_naive")
                renal_liver_issue = st.checkbox("肝肾功能异常", False, key="clinical_renal_liver")
                allergy = st.multiselect("过敏史", option_list("clinical_allergy"), key="clinical_allergy")

            st.markdown("##### 当前用药（结构化录入）")
            d1, d2, d3 = st.columns(3)
            with d1:
                current_opioid = st.selectbox("当前阿片药物", option_list("clinical_current_opioid"), key="clinical_current_opioid")
            with d2:
                current_dose = st.number_input("当前单次剂量", 0.0, 500.0, 0.0, 0.5, key="clinical_current_dose")
            with d3:
                current_freq = st.selectbox("当前给药频次", option_list("clinical_current_freq"), key="clinical_current_freq")

            e1, e2 = st.columns(2)
            with e1:
                co_meds = st.multiselect("联合药物", option_list("clinical_co_meds"), key="clinical_co_meds")
                comorb_list = st.multiselect("合并症", option_list("clinical_comorb"), key="clinical_comorb")
            with e2:
                adverse_hist = st.multiselect("既往不良反应", option_list("clinical_adverse_hist"), key="clinical_adverse_hist")
                extra_notes = st.text_area("补充说明", key="clinical_extra_notes")

            st.markdown("##### 拟开具方案（用于 MME 换算）")
            p1, p2, p3 = st.columns(3)
            with p1:
                plan_drug = st.selectbox("拟开具阿片药物", option_list("clinical_plan_drug"), key="clinical_plan_drug")
            with p2:
                dose_label = "剂量 (mcg/h)" if plan_drug == "芬太尼贴剂" else "单次剂量 (mg)"
                plan_dose = st.number_input(dose_label, 0.0, 500.0, 0.0, 0.5, key="clinical_plan_dose")
            with p3:
                if plan_drug == "芬太尼贴剂":
                    st.caption("贴剂默认按 24 小时持续给药计算")
                    plan_freq_per_day = 1
                else:
                    plan_freq_per_day = st.slider("每日频次", 1, 6, 2, key="clinical_plan_freq")

            personal_use = st.selectbox("本人物质使用史", option_list("clinical_personal_use"), key="clinical_personal_use")
            family_use = st.selectbox("家族物质使用史", option_list("clinical_family_use"), key="clinical_family_use")
            psych_histories = st.multiselect("心理/精神病史", option_list("clinical_psych"), key="clinical_psych")
            submitted = st.form_submit_button("生成 AI 深度建议", type="primary", use_container_width=True)

        diagnosis = diagnosis_template if diagnosis_template != "其他" else ""
        if diagnosis_extra.strip():
            diagnosis = f"{diagnosis}；{diagnosis_extra.strip()}" if diagnosis else diagnosis_extra.strip()
        current_meds_text = (
            f"{current_opioid} {current_dose} ({current_freq})"
            if current_opioid != "无" and current_dose > 0
            else "无阿片当前用药"
        )
        if co_meds:
            current_meds_text += "；联合：" + "、".join(co_meds)
        comorbidities = "、".join(comorb_list) if comorb_list else "无"
        adverse_hist_text = "、".join(adverse_hist) if adverse_hist else "无"
        allergy_text = "、".join(allergy) if allergy else "无"

        ort_score, ort_level, ort_details = calc_ort(age, personal_use, family_use, psych_histories)
        st.markdown(
            f"<span class='risk-tag {risk_tag_class(ort_level)}'>ORT：{ort_score} 分（{ort_level}）</span>",
            unsafe_allow_html=True,
        )
        st.caption(" | ".join(ort_details) if ort_details else "未识别显著成瘾风险因子")
        mme_day, mme_note = calc_mme_day(plan_drug, float(plan_dose), int(plan_freq_per_day))
        st.caption(f"当前拟开具 MME/day：{mme_day} | {mme_note}")

        if submitted and not diagnosis.strip():
            st.warning("请先填写主要诊断。")
            submitted = False

        if submitted:
            query = f"{diagnosis} {pain_type} {department} {comorbidities}"
            similar_cases = retrieve_similar_cases(query, cases, top_k=3)
            local_cards = local_plan(age, pain_score, ort_level, opioid_naive, pain_type)
            radar = risk_radar_values(pain_score, ort_level, current_meds_text, comorbidities)
            summary = f"""
患者：{patient_name or "未命名患者"}，{age} 岁 {gender}
诊断：{diagnosis}
疼痛评分：{pain_score}/10（{pain_type}）
科室：{department}
合并症：{comorbidities}
当前用药：{current_meds_text}
拟开具药物：{plan_drug}，剂量：{plan_dose}，频次：{plan_freq_per_day}/day，MME/day={mme_day}
本人物质使用史：{personal_use}
家族物质使用史：{family_use}
心理病史：{", ".join(psych_histories) if psych_histories else "无"}
ORT：{ort_score}（{ort_level}）
过敏史：{allergy_text}
既往不良反应：{adverse_hist_text}
补充：{extra_notes or "无"}
"""
            ai_text = ask_llm(
                client,
                model,
                "你是阿片类药物临床助手，请以结构化格式输出：处方建议、备选方案、风险提示、复评计划。",
                summary,
            )
            st.session_state.clinical_last_result = {
                "patient_name": patient_name or "未命名患者",
                "age": age,
                "gender": gender,
                "diagnosis": diagnosis,
                "pain_score": pain_score,
                "pain_type": pain_type,
                "department": department,
                "comorbidities": comorbidities,
                "current_meds_text": current_meds_text,
                "plan_drug": plan_drug,
                "plan_dose": float(plan_dose),
                "plan_freq_per_day": int(plan_freq_per_day),
                "mme_day": mme_day,
                "mme_note": mme_note,
                "ort_score": ort_score,
                "ort_level": ort_level,
                "allergy_text": allergy_text,
                "adverse_hist_text": adverse_hist_text,
                "summary": summary,
                "local_cards": local_cards,
                "radar": radar,
                "similar_cases": similar_cases,
                "ai_text": ai_text,
                "renal_liver_issue": renal_liver_issue,
            }

    result = st.session_state.get("clinical_last_result")
    required_keys = {"local_cards", "radar", "summary", "similar_cases", "ort_level", "ort_score", "mme_day"}
    if result and not required_keys.issubset(set(result.keys())):
        result = None
        st.session_state.clinical_last_result = None

    with right:
        st.markdown("#### AI 计算状态实时回馈")
        if submitted:
            with st.status("正在计算中", expanded=True) as status:
                st.write("1) 正在解析病例字段与病史结构...")
                st.write("2) 正在执行 ORT 风险分层与合规规则匹配...")
                st.write("3) 正在检索相似病例与循证依据...")
                status.update(label="计算完成", state="complete")

        if result:
            if result["ort_level"] == "高风险" or result["mme_day"] >= 90:
                st.markdown("<div class='warn-bar'>⚠️ 红线预警：高风险或高剂量方案，建议 24-72h 复评 + 二次审方。</div>", unsafe_allow_html=True)
            else:
                st.markdown("<div class='ok-bar'>✅ 风险可控：建议按计划复评并持续监测不良反应。</div>", unsafe_allow_html=True)

            tab1, tab2, tab3, tab4 = st.tabs(["处方卡片", "风险雷达", "循证溯源", "专家会诊讨论区"])
            with tab1:
                st.table(result["local_cards"])
                if result["ai_text"]:
                    st.markdown("**AI 补充建议**")
                    st.write(result["ai_text"])
                else:
                    st.info("未检测到 API Key，已展示本地规则建议。")

            with tab2:
                st.caption("风险雷达（极坐标）")
                render_radar_chart(result["radar"])
                st.metric("MME/day", result["mme_day"])
                st.caption(result["mme_note"])
                if result["mme_day"] >= 90:
                    st.error("❌ 剂量红线：MME/day >= 90，需强制复核并记录调整依据。")
                elif result["mme_day"] >= 50:
                    st.warning("⚠️ 剂量警戒：MME/day >= 50，建议评估纳洛酮与高频复评。")
                if result["renal_liver_issue"]:
                    st.error("存在肝肾功能异常：需减量并延长给药间隔。")
                if "苯二氮卓" in result["current_meds_text"]:
                    st.error("检测到联用高风险：阿片类 + 苯二氮卓。")

            with tab3:
                st.markdown("**相似病例**")
                for c in result["similar_cases"]:
                    st.markdown(f"- `{c.get('id', 'N/A')}` {c.get('diagnosis', '')} | {c.get('recommended_plan', '')}")
                st.markdown("**权威链接**")
                st.markdown("- [国家卫健委](https://www.nhc.gov.cn/)")
                st.markdown("- [国家医保局](https://www.nhsa.gov.cn/)")
                st.markdown("- [国家药监局](https://www.nmpa.gov.cn/)")
                st.markdown("- [PubMed](https://pubmed.ncbi.nlm.nih.gov/)")

            with tab4:
                st.markdown("##### 会诊讨论区")
                discuss_input = st.text_area(
                    "补充会诊意见",
                    placeholder="可输入会诊意见、沟通重点、复评触发条件等。",
                    key="clinical_discuss_input",
                )
                if st.button("生成会诊摘要", key="clinical_discuss_btn", type="primary"):
                    consult_prompt = (
                        f"病例摘要：{result.get('summary', '')}\n\n"
                        f"会诊补充：{discuss_input or '无补充'}\n\n"
                        "请输出：1) 会诊结论 2) 48-72h复评重点 3) 风险沟通要点。"
                    )
                    consult_text = ask_llm(
                        client,
                        model,
                        "你是医院疼痛管理MDT秘书，请输出简洁、可落地的会诊摘要。",
                        consult_prompt,
                    )
                    if not consult_text:
                        consult_text = (
                            "会诊结论：维持低剂量起始并短周期复评。\n"
                            "复评重点：疼痛评分、呼吸抑制、镇静程度、依从性。\n"
                            "沟通要点：明确红线风险，记录知情同意与复评时间。"
                        )
                    st.session_state.last_report = consult_text
                    append_audit_event(
                        st.session_state,
                        "clinical_report_generated",
                        {
                            "patient_name": result.get("patient_name", ""),
                            "ort_level": result.get("ort_level", ""),
                            "mme_day": result.get("mme_day", 0),
                        },
                    )
                    st.success("会诊摘要已生成并保存到个人中心下载区。")
                    st.write(consult_text)


def page_training(client: Optional[OpenAI], model: str, cases: List[Dict]) -> None:
    st.markdown("### 虚拟训练")
    st.caption("基于真实病例模板进行问答与方案演练，训练记录会计入个人中心统计。")

    c1, c2, c3 = st.columns(3)
    train_department = c1.selectbox("训练科室", option_list("training_department"), key="training_department")
    train_difficulty = c2.selectbox("训练难度", option_list("training_difficulty"), key="training_difficulty")
    train_country = c3.selectbox("政策场景", option_list("training_policy_country"), key="training_policy_country")

    if st.button("生成训练病例", type="primary"):
        pool = [c for c in cases if train_department[:2] in f"{c.get('category', '')}{c.get('diagnosis', '')}"]
        chosen = random.choice(pool or cases or [{}])
        st.session_state.training_case = {
            "id": chosen.get("id", f"SIM-{uuid.uuid4().hex[:6]}"),
            "diagnosis": chosen.get("diagnosis", "未命名病例"),
            "pain_type": chosen.get("pain_type", "未知"),
            "pain_score": chosen.get("pain_score", 0),
            "risk_notes": chosen.get("risk_notes", "无"),
            "recommended_plan": chosen.get("recommended_plan", "无"),
            "department": train_department,
            "difficulty": train_difficulty,
            "country": train_country,
        }
        append_audit_event(
            st.session_state,
            "training_case_generated",
            {
                "case_id": st.session_state.training_case["id"],
                "department": train_department,
                "difficulty": train_difficulty,
            },
        )
        st.rerun()

    case = st.session_state.training_case
    if not case:
        st.info("请先生成训练病例。")
    else:
        with st.container(border=True):
            st.markdown(f"**病例编号：{case['id']}**")
            st.caption(f"科室：{case['department']} | 难度：{case['difficulty']} | 政策场景：{case['country']}")
            st.write(f"诊断：{case['diagnosis']}")
            st.write(f"疼痛类型：{case['pain_type']} | 疼痛评分：{case['pain_score']}")
            st.write(f"风险提示：{case['risk_notes']}")

        with st.form("training_submit_form"):
            plan_text = st.text_area("请给出你的处置方案", placeholder="至少包含剂量策略、复评计划和风险沟通。")
            need_review = st.selectbox("是否需要 72h 内复评", option_list("training_quiz_binary"), key="training_need_review")
            need_warning = st.selectbox("是否触发高风险预警", option_list("training_quiz_binary"), key="training_need_warning")
            submit_training = st.form_submit_button("提交训练", type="primary")

        if submit_training:
            score = 60
            if len(plan_text.strip()) >= 30:
                score += 15
            if "复评" in plan_text:
                score += 10
            if "风险" in plan_text or "知情同意" in plan_text:
                score += 10
            if need_review == "是":
                score += 3
            if need_warning == "是":
                score += 2
            score = min(score, 100)

            if len(plan_text.strip()) < 20:
                psych_label = "恐惧型"
            elif "立即加量" in plan_text or "大剂量" in plan_text:
                psych_label = "放开型"
            elif "请上级" in plan_text or "会诊" in plan_text:
                psych_label = "咨询依赖型"
            else:
                psych_label = "均衡型"

            st.session_state.psych_label_counts[psych_label] = st.session_state.psych_label_counts.get(psych_label, 0) + 1
            record = {
                "时间": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "科室": case["department"],
                "难度": case["difficulty"],
                "评分": score,
                "心理画像": psych_label,
                "案例": case["id"],
            }
            st.session_state.training_history.append(record)
            append_audit_event(st.session_state, "training_submitted", record)

            ai_feedback = ask_llm(
                client,
                model,
                "你是临床教学带教老师，请简短点评训练方案，并给出两条改进建议。",
                f"病例：{case}\n学员方案：{plan_text}\n评分：{score}",
            )
            if not ai_feedback:
                ai_feedback = "训练完成。建议保持低剂量起始、固定复评节点，并强化不良反应监测记录。"
            st.session_state.last_report = ai_feedback
            st.success(f"训练提交成功，得分 {score} 分。")
            st.write(ai_feedback)

    st.markdown("#### 课程矩阵推荐")
    st.dataframe(COURSE_MATRIX, use_container_width=True, hide_index=True)
    st.markdown("#### 训练心理画像分布")
    st.bar_chart(st.session_state.psych_label_counts)


def page_policy(client: Optional[OpenAI], model: str) -> None:
    st.markdown("### 文献与政策库")
    st.caption("统一从 `data/static_content.json` 读取政策内容、标签和筛选项。")

    f1, f2, f3, f4, f5 = st.columns(5)
    country = f1.selectbox("国家/地区", option_list("policy_country"), key="policy_country")
    category = f2.selectbox("分类", option_list("policy_category"), key="policy_category")
    tag = f3.selectbox("标签", option_list("policy_tag"), key="policy_tag")
    province = f4.selectbox("省份", option_list("policy_province"), key="policy_province")
    ort_level = f5.selectbox("风险级别", option_list("policy_ort_level"), key="policy_ort_level")

    filtered = []
    for item in POLICY_LIBRARY:
        if category != "全部" and item.get("category") != category:
            continue
        if tag != "全部" and tag not in item.get("tags", []):
            continue
        if province != "全国" and item.get("province") not in {province, "全国"}:
            continue
        filtered.append(item)

    st.caption(f"{country} / {province} 场景共匹配 {len(filtered)} 条政策。")
    if ort_level == HIGH_RISK_LEVEL:
        st.warning("当前为高风险场景：建议优先查看“处方合规”和“风险预警”类政策。")

    if not filtered:
        st.info("当前筛选条件下暂无政策。")
    else:
        for idx, item in enumerate(filtered):
            tags = "、".join(item.get("tags", []))
            st.markdown(
                f"""
                <div class="policy-card">
                    <div class="policy-title">{item.get("title", "")}</div>
                    <div>编号：{item.get("id", "")} | 发布：{item.get("date", "")} | 归属：{item.get("authority", "")}</div>
                    <div>分类：{item.get("category", "")} | 标签：{tags} | 省份：{item.get("province", "")}</div>
                    <div style="margin-top:6px;">{item.get("summary", "")}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            st.link_button(
                "查看官方来源",
                item.get("source_url", "https://www.nhc.gov.cn/"),
            )

    st.markdown("#### 政策问答")
    policy_ids = [f"{p.get('id', '')} | {p.get('title', '')}" for p in (filtered or POLICY_LIBRARY)]
    selected_policy = st.selectbox("选择政策", policy_ids, key="policy_qa_select")
    question = st.text_input("输入问题", key="policy_question", placeholder="例如：高风险患者是否可一次性开具长疗程？")
    if st.button("生成解读", key="policy_qa_btn", type="primary"):
        pid = selected_policy.split("|")[0].strip()
        policy = next((p for p in POLICY_LIBRARY if p.get("id") == pid), None)
        answer = ""
        if policy:
            query_tokens = tokenize(question)
            for qa_item in policy.get("qa", []):
                if len(qa_item) != 2:
                    continue
                q_text, a_text = qa_item
                if any(token in q_text for token in query_tokens):
                    answer = a_text
                    break
        if not answer and policy:
            prompt = f"政策：{policy}\n问题：{question}\n请给出简洁、合规、可执行的答复。"
            answer = ask_llm(client, model, "你是医院合规办公室政策助理。", prompt)
        if not answer:
            answer = "未匹配到直接条款，建议按高风险路径执行：限量处方、短周期复评、留痕审计。"

        append_audit_event(
            st.session_state,
            "policy_qa",
            {"policy_id": pid, "question": question, "country": country, "province": province},
        )
        st.success("解读完成")
        st.write(answer)


def page_doctor_dashboard() -> None:
    st.markdown("### 医生管理后台")
    tab1, tab2, tab3, tab4, tab5 = st.tabs(["患者台账", "风险评估", "随访管理", "账号与安全设置", "患者详情页"])

    with tab1:
        f1, f2 = st.columns(2)
        risk_filter = f1.selectbox("风险筛选", option_list("doctor_filter_risk"), key="doctor_filter_risk")
        status_filter = f2.selectbox("状态筛选", option_list("doctor_filter_status"), key="doctor_filter_status")

        table_rows = []
        for p in st.session_state.patients:
            if risk_filter != "全部" and p.get("risk_level") != risk_filter:
                continue
            if status_filter != "全部" and p.get("med_status") != status_filter:
                continue
            pending_count = sum(
                1
                for item in p.get("followups", [])
                if item.get("status", PENDING_FOLLOWUP_STATUS) != COMPLETED_FOLLOWUP_STATUS
            )
            table_rows.append(
                {
                    "患者ID": p.get("id", ""),
                    "姓名": mask_name(p.get("name", "")),
                    "科室": p.get("department", ""),
                    "诊断": p.get("diagnosis", ""),
                    "风险等级": p.get("risk_level", ""),
                    "当前状态": p.get("med_status", ""),
                    "待随访数": pending_count,
                    "建档日期": p.get("created_at", ""),
                }
            )
        st.dataframe(table_rows, use_container_width=True, hide_index=True)

        st.markdown("##### 新增患者")
        with st.form("doctor_add_patient_form"):
            a1, a2, a3 = st.columns(3)
            with a1:
                add_name = st.text_input("姓名")
                add_department = st.selectbox("科室", option_list("doctor_add_department"))
            with a2:
                add_diag = st.text_input("诊断")
                add_risk = st.selectbox("风险等级", option_list("doctor_add_risk_level"))
            with a3:
                add_note = st.text_input("随访备注", value="首次复评")
                add_submit = st.form_submit_button("新增患者", type="primary")

        if add_submit:
            if not add_name.strip() or not add_diag.strip():
                st.error("姓名和诊断不能为空。")
            else:
                existing_ids = {p.get("id", "") for p in st.session_state.patients}
                next_num = len(existing_ids) + 1
                new_id = f"PT-{next_num:03d}"
                while new_id in existing_ids:
                    next_num += 1
                    new_id = f"PT-{next_num:03d}"

                due = (datetime.now() + timedelta(hours=24)).strftime("%Y-%m-%d %H:%M")
                new_patient = {
                    "id": new_id,
                    "name": add_name.strip(),
                    "diagnosis": add_diag.strip(),
                    "department": add_department,
                    "risk_level": add_risk,
                    "med_status": PENDING_MED_STATUS,
                    "created_at": datetime.now().strftime("%Y-%m-%d"),
                    "evaluations": [],
                    "tracking": [],
                    "followups": [{"time": due, "status": PENDING_FOLLOWUP_STATUS, "note": add_note.strip() or "首次复评"}],
                }
                st.session_state.patients.append(new_patient)
                append_audit_event(st.session_state, "patient_created", {"patient_id": new_id, "department": add_department})
                st.success(f"患者 {new_id} 已新增。")
                st.rerun()

    with tab2:
        options = [f"{p['id']} | {mask_name(p['name'])} | {p['diagnosis']}" for p in st.session_state.patients]
        selected = st.selectbox("选择患者", options, key="doctor_eval_select")
        pid = selected.split("|")[0].strip()
        patient = get_patient_by_id(pid)
        if not patient:
            st.warning("未找到患者。")
        else:
            with st.form("doctor_eval_form"):
                e1, e2 = st.columns(2)
                with e1:
                    eval_pain = st.slider("当前疼痛评分", 0, 10, 6, key="doctor_eval_pain")
                    eval_personal = st.selectbox("本人物质使用史", option_list("doctor_eval_personal_use"))
                    eval_family = st.selectbox("家族物质使用史", option_list("doctor_eval_family_use"))
                with e2:
                    eval_psych = st.multiselect("心理/精神病史", option_list("doctor_eval_psych"))
                    eval_note = st.text_area("评估备注", placeholder="填写风险判断依据、沟通要点和复评建议。")
                    eval_submit = st.form_submit_button("提交评估", type="primary")

            if eval_submit:
                score, level, details = calc_ort(int(patient.get("age", 40) or 40), eval_personal, eval_family, eval_psych)
                report = (
                    f"疼痛评分 {eval_pain}/10；ORT={score}（{level}）。"
                    f"评估备注：{eval_note or '无'}。建议按风险等级调整复评频次。"
                )
                patient["risk_level"] = level
                patient["evaluations"].append(
                    {"time": datetime.now().strftime("%Y-%m-%d %H:%M"), "report": report, "details": details}
                )
                append_audit_event(
                    st.session_state,
                    "risk_evaluated",
                    {"patient_id": pid, "ort_score": score, "ort_level": level, "pain_score": eval_pain},
                )
                st.success(f"评估已保存，患者风险等级更新为：{level}")

    with tab3:
        st.markdown("#### 随访计划总览")
        now = datetime.now()
        todo_rows = []
        for p in st.session_state.patients:
            for item in p.get("followups", []):
                due = parse_time_safe(item.get("time", ""))
                due_dt = None if due == datetime.max else due
                show_status = display_followup_status(item.get("status", PENDING_FOLLOWUP_STATUS), due_dt, now)
                todo_rows.append(
                    {
                        "患者": f"{p.get('id', '')} | {mask_name(p.get('name', ''))}",
                        "随访时间": item.get("time", ""),
                        "状态": show_status,
                        "备注": item.get("note", ""),
                    }
                )
        st.dataframe(todo_rows, use_container_width=True, hide_index=True)

        pending_map: Dict[str, Tuple[str, str]] = {}
        pending_labels: List[str] = []
        for p in st.session_state.patients:
            for item in p.get("followups", []):
                if item.get("status", PENDING_FOLLOWUP_STATUS) == COMPLETED_FOLLOWUP_STATUS:
                    continue
                label = f"{p['id']} | {mask_name(p['name'])} | {item.get('time', '')} | {item.get('note', '')}"
                pending_map[label] = (p["id"], item.get("time", ""))
                pending_labels.append(label)

        if pending_labels:
            c1, c2 = st.columns([2, 2])
            selected_follow = c1.selectbox("选择待完成随访", pending_labels, key="follow_done_select")
            done_note = c2.text_input("完成备注", key="follow_done_note", placeholder="如：疼痛下降至4分，无呼吸抑制")
            if st.button("标记为已完成", key="follow_done_btn", type="primary"):
                target_pid, target_time = pending_map[selected_follow]
                ok, msg = mark_followup_completed(st.session_state.patients, target_pid, target_time, done_note)
                if ok:
                    append_audit_event(
                        st.session_state,
                        "followup_completed",
                        {"patient_id": target_pid, "followup_time": target_time, "note": done_note.strip()},
                    )
                    st.success(msg)
                    st.rerun()
                else:
                    st.error(msg)
        else:
            st.info("当前没有待完成随访。")

        st.markdown("#### 新建随访计划")
        patient_options = [f"{p['id']} | {mask_name(p['name'])}" for p in st.session_state.patients]
        selected = st.selectbox("选择患者", patient_options, key="follow_select")
        pid = selected.split("|")[0].strip()
        patient = get_patient_by_id(pid)
        with st.form("follow_form"):
            follow_hours = st.selectbox("随访时点（小时）", option_list("clinical_follow_hours"))
            note = st.text_input("随访备注", value="例行复评")
            submit_follow = st.form_submit_button("创建随访", type="primary")
        if submit_follow and patient:
            when = (datetime.now() + timedelta(hours=int(follow_hours))).strftime("%Y-%m-%d %H:%M")
            patient["followups"].append({"time": when, "status": PENDING_FOLLOWUP_STATUS, "note": note or "例行复评"})
            patient["med_status"] = PENDING_MED_STATUS
            append_audit_event(
                st.session_state,
                "followup_created",
                {"patient_id": pid, "followup_time": when, "note": note or "例行复评"},
            )
            st.success("随访计划已创建。")
            st.rerun()

    with tab4:
        st.markdown("#### 账号与安全设置")
        st.checkbox("启用二次验证（高敏模块）", value=True)
        st.checkbox("绑定登录 IP 白名单", value=False)
        st.checkbox("开启异常登录通知", value=True)
        st.checkbox("自动锁屏（15 分钟）", value=True)
        st.info("所有患者信息默认脱敏展示，操作日志可追溯。")

    with tab5:
        st.markdown("#### 患者详情页")
        options = [f"{p['id']} | {mask_name(p['name'])} | {p['diagnosis']}" for p in st.session_state.patients]
        selected = st.selectbox("选择患者", options, key="detail_select")
        pid = selected.split("|")[0].strip()
        patient = get_patient_by_id(pid)

        if not patient:
            st.warning("未找到患者。")
            return

        d1, d2, d3, d4 = st.columns(4)
        d1.metric("患者ID", patient.get("id", ""))
        d2.metric("风险等级", patient.get("risk_level", ""))
        d3.metric("当前状态", patient.get("med_status", ""))
        d4.metric("评估次数", str(len(patient.get("evaluations", []))))

        st.caption(
            f"患者：{mask_name(patient.get('name', ''))} | 科室：{patient.get('department', '')} | "
            f"诊断：{patient.get('diagnosis', '')} | 建档：{patient.get('created_at', '')}"
        )

        c1, c2 = st.columns([1, 1], gap="large")
        with c1:
            st.markdown("##### 评估历史")
            evals = patient.get("evaluations", [])
            if evals:
                rows = [{"时间": e.get("time", ""), "摘要": e.get("report", "")} for e in evals]
                st.dataframe(rows, use_container_width=True, hide_index=True)
                with st.expander("查看评估详情"):
                    for i, e in enumerate(reversed(evals), start=1):
                        st.markdown(f"**{i}. {e.get('time', '')}**")
                        st.write(e.get("report", ""))
                        details = e.get("details", [])
                        if details:
                            st.caption(" | ".join([str(x) for x in details]))
            else:
                st.info("暂无评估历史。")

            with st.form("tracking_form"):
                t1, t2 = st.columns(2)
                with t1:
                    tracking_pain = st.slider("追踪疼痛评分", 0, 10, 5, key="tracking_pain")
                    tracking_adverse = st.selectbox("不良反应", option_list("doctor_tracking_adverse"), key="tracking_adverse")
                with t2:
                    tracking_adherence = st.slider("依从性 (%)", 0, 100, 85, key="tracking_adherence")
                    tracking_submit = st.form_submit_button("新增追踪记录", type="primary")
            if tracking_submit:
                patient["tracking"].append(
                    {
                        "time": datetime.now().strftime("%Y-%m-%d"),
                        "pain": tracking_pain,
                        "adherence": tracking_adherence,
                        "adverse": tracking_adverse,
                    }
                )
                append_audit_event(
                    st.session_state,
                    "tracking_added",
                    {"patient_id": pid, "pain": tracking_pain, "adherence": tracking_adherence, "adverse": tracking_adverse},
                )
                st.success("追踪记录已新增。")
                st.rerun()

        with c2:
            st.markdown("##### 随访时间轴")
            render_followup_timeline(patient)

        st.markdown("##### 用药后追踪曲线")
        render_tracking_curve(patient)


def page_profile() -> None:
    st.markdown("### 个人中心")
    patients = get_patients(st.session_state)
    training_history = get_training_history(st.session_state)
    metrics = compute_profile_metrics(patients, training_history)

    l, r = st.columns([1, 2])
    with l:
        with st.container(border=True):
            st.subheader(st.session_state.doctor_name)
            st.caption(st.session_state.doctor_title)
            st.caption("机构：示例三甲医院")
            st.caption("角色：麻醉疼痛管理组")
            st.caption("执业编号：MD-2026-041")
    with r:
        render_profile_metrics(metrics)

    st.markdown("#### 训练历史")
    if training_history:
        st.dataframe(training_history[::-1], use_container_width=True, hide_index=True)
    else:
        st.info("暂无训练记录。")

    render_recent_audit(get_audit_events(st.session_state))

    if st.session_state.last_report:
        st.download_button(
            "下载最近一次会诊/训练报告",
            data=st.session_state.last_report.encode("utf-8"),
            file_name=f"last_report_{datetime.now().strftime('%Y%m%d')}.txt",
            mime="text/plain",
        )


def page_login() -> None:
    st.markdown("### 登录与安全")
    st.caption("支持账号密码/验证码双登录，附医疗数据保密声明。")
    tab1, tab2, tab3 = st.tabs(["账号登录", "验证码登录", "注册认证"])

    with tab1:
        with st.form("login_pwd"):
            username = st.text_input("用户名")
            pwd = st.text_input("密码", type="password")
            agree = st.checkbox("我已阅读并同意《医疗数据保密条款》", value=True)
            submit = st.form_submit_button("登录", type="primary")
        if submit:
            if username.strip() and pwd.strip() and agree:
                st.session_state.is_logged_in = True
                st.session_state.doctor_name = username.strip()
                st.session_state.doctor_title = "临床医生"
                st.success("登录成功。")
            else:
                st.error("请完成登录信息并勾选保密条款。")

    with tab2:
        with st.form("login_code"):
            mobile = st.text_input("手机号")
            code = st.text_input("验证码")
            submit2 = st.form_submit_button("登录", type="primary")
        if submit2:
            if mobile.strip() and code.strip():
                st.session_state.is_logged_in = True
                st.session_state.doctor_name = f"用户{mobile[-4:]}"
                st.session_state.doctor_title = "临床医生"
                st.success("登录成功。")
            else:
                st.error("请输入手机号和验证码。")

    with tab3:
        with st.form("register_form"):
            c1, c2 = st.columns(2)
            with c1:
                license_id = st.text_input("执业医师证号")
                real_name = st.text_input("姓名")
                dept = st.selectbox("科室", option_list("register_department"))
            with c2:
                hospital = st.text_input("医院")
                mobile = st.text_input("手机号", key="reg_mobile")
                verify = st.text_input("实名认证码")
            reg = st.form_submit_button("提交注册", type="primary")
        if reg:
            if all([license_id.strip(), real_name.strip(), hospital.strip(), mobile.strip(), verify.strip()]):
                _ = dept  # 保留字段
                st.success("注册信息已提交，等待实名认证审核。")
            else:
                st.error("请完整填写注册信息。")

    st.markdown("---")
    st.info("合规声明：系统遵循《个人信息保护法》，敏感字段脱敏展示，操作日志可审计。")


def main() -> None:
    inject_css()
    init_state()
    client, model = get_client_and_model()
    cases = load_cases()

    render_header()
    page = sidebar_navigation()

    protected = set(option_list("protected_pages"))
    if not st.session_state.is_logged_in and page in protected:
        st.warning("当前未登录，请先进入“登录与安全”完成认证，或启用体验模式。")
        if st.button("启用体验模式", type="primary"):
            st.session_state.is_logged_in = True
            st.session_state.doctor_name = "体验账号"
            st.session_state.doctor_title = "演示模式"
            st.rerun()
        render_footer_note()
        st.stop()

    pages = option_list("sidebar_pages")
    if page == pages[0]:
        page_dashboard(cases)
    elif page == pages[1]:
        page_clinical_assistant(client, model, cases)
    elif page == pages[2]:
        page_training(client, model, cases)
    elif page == pages[3]:
        page_policy(client, model)
    elif page == pages[4]:
        page_doctor_dashboard()
    elif page == pages[5]:
        page_profile()
    else:
        page_login()

    render_footer_note()


if __name__ == "__main__":
    main()
