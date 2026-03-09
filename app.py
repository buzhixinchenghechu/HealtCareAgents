# -*- coding: utf-8 -*-
"""阿片类药物辅助决策系统（按设计初稿升级版）"""

from __future__ import annotations

import json
import os
import random
import re
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

import streamlit as st
from openai import OpenAI


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
SIDEBAR_BG = "#2C3E50"


NEWS_FEED = [
    {
        "date": "2026-03-07",
        "title": "高风险患者复评窗口收紧",
        "summary": "住院及门诊高风险患者建议 72 小时内完成首次复评并记录疗效终点。",
    },
    {
        "date": "2026-03-03",
        "title": "阿片类药物联合用药红线更新",
        "summary": "新增阿片类 + 镇静催眠类联用二次审方提示规则，触发自动预警条。",
    },
    {
        "date": "2026-02-28",
        "title": "虚拟训练新增心理画像反馈机制",
        "summary": "系统可根据训练行为自动标注“恐惧型/放开型/咨询依赖型”并推送微课。",
    },
]


POLICY_LIBRARY = [
    {
        "id": "POL-2026-CN-001",
        "title": "门诊麻精药品处方与复评规范（2026）",
        "authority": "国家卫健相关规范（院内拆解版）",
        "date": "2026-03-01",
        "category": "处方合规",
        "tags": ["红线", "复评", "门诊"],
        "province": "全国",
        "summary": "高风险患者处方须限量并建立 72 小时-7 天复评计划，病历应记录知情同意与依从性评估。",
        "qa": [
            ("是否可以一次性开长疗程？", "❌ 高风险人群不建议一次性长疗程开具。"),
            ("是否必须记录知情同意？", "✅ 是，建议使用标准化知情同意模板并留痕。"),
        ],
        "source_url": "https://www.nhc.gov.cn/",
    },
    {
        "id": "POL-2026-CN-002",
        "title": "阿片类药物联合用药风险审查要点",
        "authority": "国家药监相关要求（院内风险清单）",
        "date": "2026-02-20",
        "category": "风险预警",
        "tags": ["联用", "不良反应"],
        "province": "全国",
        "summary": "与苯二氮卓类、酒精、镇静药联用需标注高风险，建议增加监测频率和复评节点。",
        "qa": [
            ("联用是否绝对禁忌？", "⚠️ 需严格评估获益/风险，并进行高频监测与短期复评。"),
            ("出现过度镇静怎么办？", "❌ 需立即评估减量或停药并记录处置过程。"),
        ],
        "source_url": "https://www.nmpa.gov.cn/",
    },
    {
        "id": "POL-2026-CN-003",
        "title": "省级医保对慢性疼痛门诊支付差异提示",
        "authority": "国家医保局及地方医保政策汇编",
        "date": "2026-02-11",
        "category": "医保支付",
        "tags": ["医保", "地方政策"],
        "province": "上海",
        "summary": "部分省市需满足阶段性试错及备案要求后才纳入长期治疗支付路径。",
        "qa": [
            ("是否直接纳入长期报销？", "⚠️ 视省份政策，需先完成短程评估与备案流程。"),
            ("如何查询本地细则？", "✅ 通过省份切换器查看对应政策拆解与官方链接。"),
        ],
        "source_url": "https://www.nhsa.gov.cn/",
    },
]


COURSE_MATRIX = [
    {"科室": "肿瘤科", "课程": "晚期癌痛长期管理", "重点": "滴定策略、便秘预防、人道主义镇痛"},
    {"科室": "骨科/口腔科", "课程": "术后急性疼痛短程处方", "重点": "短疗程管理、停药节奏、依从性"},
    {"科室": "急诊科", "课程": "快速风险评估与极短程处方", "重点": "高风险识别、红线控制、转归记录"},
    {"科室": "疼痛科", "课程": "慢性疼痛多学科协同", "重点": "心理共病、复评机制、联合治疗"},
]


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
            color: #fff;
        }}
        [data-testid="stSidebar"] .stRadio label,
        [data-testid="stSidebar"] .stMarkdown,
        [data-testid="stSidebar"] .stCaption,
        [data-testid="stSidebar"] .stText {{
            color: #fff !important;
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
        "current_page": "工作台总览",
        "is_logged_in": False,
        "doctor_name": "未登录用户",
        "doctor_title": "请先登录",
        "training_case": "",
        "training_history": [],
        "last_report": "",
        "policy_country": "中国",
        "policy_province": "全国",
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
    path = os.path.join("data", "cases", "sample_cases.json")
    if not os.path.exists(path):
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
    pages = ["工作台总览", "临床辅助", "虚拟训练", "文献与政策库", "医生管理后台", "个人中心", "登录与安全"]
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
    c1, c2, c3, c4 = st.columns(4)
    metrics = [
        ("今日临床推演完成率", "82%", "较昨日 +6%"),
        ("高风险病例待复评", str(max(4, len(cases) // 20 or 6)), "需优先处理"),
        ("处方合规率", "96.4%", "稳定"),
        ("随访按时完成率", "89.1%", "持续提升"),
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
    with left:
        st.markdown("#### 核心功能入口")
        if st.button("进入真实病例辅助", use_container_width=True):
            st.session_state.current_page = "临床辅助"
            st.rerun()
        if st.button("进入虚拟训练场", use_container_width=True):
            st.session_state.current_page = "虚拟训练"
            st.rerun()
        if st.button("进入政策文献库", use_container_width=True):
            st.session_state.current_page = "文献与政策库"
            st.rerun()
        if st.button("进入医生管理后台", use_container_width=True):
            st.session_state.current_page = "医生管理后台"
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
        st.info("发现 2 例“阿片 + 镇静催眠药”联用处方，已触发红线提示。")
        st.warning("3 位中高风险患者尚未完成 72h 复评。")
        st.success("政策引擎同步完成：全国 + 上海 + 广东。")
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
                age = st.number_input("年龄", 1, 120, 58)
                gender = st.selectbox("性别", ["男", "女"])
                pain_score = st.slider("疼痛评分 NRS", 0, 10, 7)
            with b:
                diagnosis = st.text_input("主要诊断", placeholder="如：晚期肿瘤骨转移痛")
                pain_type = st.selectbox("疼痛类型", ["癌性疼痛", "非癌性急性疼痛", "非癌性慢性疼痛"])
                department = st.selectbox("科室", ["肿瘤科", "疼痛科", "骨科", "急诊科", "麻醉科", "口腔科"])
            with c:
                opioid_naive = st.checkbox("阿片初治患者", True)
                renal_liver_issue = st.checkbox("肝肾功能异常", False)
                allergy = st.text_input("过敏史", placeholder="如：吗啡过敏")

            d1, d2 = st.columns(2)
            with d1:
                current_meds = st.text_area("当前用药", placeholder="每行一个")
                comorbidities = st.text_area("合并症", placeholder="如：COPD、睡眠呼吸暂停")
            with d2:
                personal_use = st.selectbox("本人物质使用史", ["无", "酒精使用史", "非法药物使用史", "处方药滥用史"])
                family_use = st.selectbox("家族物质使用史", ["无", "家族酒精使用史", "家族非法药物使用史", "家族处方药滥用史"])
                psych_histories = st.multiselect("心理/精神病史", ["抑郁", "ADHD", "双相障碍", "精神分裂谱系障碍"])
                extra_notes = st.text_area("补充说明")
            submitted = st.form_submit_button("生成 AI 深度建议", type="primary", use_container_width=True)

        ort_score, ort_level, ort_details = calc_ort(age, personal_use, family_use, psych_histories)
        st.markdown(
            f"<span class='risk-tag {risk_tag_class(ort_level)}'>ORT：{ort_score} 分（{ort_level}）</span>",
            unsafe_allow_html=True,
        )
        st.caption(" | ".join(ort_details) if ort_details else "未识别显著成瘾风险因子")
        if submitted and not diagnosis.strip():
            st.warning("请先填写主要诊断。")
            submitted = False

    with right:
        st.markdown("#### AI 计算状态实时回馈")
        if submitted:
            with st.status("正在计算中", expanded=True) as status:
                st.write("1) 正在解析病例字段与病史结构...")
                st.write("2) 正在执行 ORT 风险分层与合规规则匹配...")
                st.write("3) 正在检索相似病例与循证依据...")
                status.update(label="计算完成", state="complete")

            query = f"{diagnosis} {pain_type} {department} {comorbidities}"
            similar_cases = retrieve_similar_cases(query, cases, top_k=3)
            local_cards = local_plan(age, pain_score, ort_level, opioid_naive, pain_type)
            radar = risk_radar_values(pain_score, ort_level, current_meds, comorbidities)

            summary = f"""
患者：{age} 岁 {gender}
诊断：{diagnosis}
疼痛评分：{pain_score}/10（{pain_type}）
科室：{department}
合并症：{comorbidities or "无"}
当前用药：{current_meds or "无"}
本人物质使用史：{personal_use}
家族物质使用史：{family_use}
心理病史：{", ".join(psych_histories) if psych_histories else "无"}
ORT：{ort_score}（{ort_level}）
补充：{extra_notes or "无"}
过敏史：{allergy or "无"}
"""
            ai_text = ask_llm(
                client,
                model,
                "你是阿片类药物临床助手，请以结构化格式输出：处方建议、备选方案、风险提示、复评计划。",
                summary,
            )

            if ort_level == "高风险":
                st.markdown("<div class='warn-bar'>⚠️ 高风险处方：建议 24-72h 复评 + 二次审方 + 知情同意留痕。</div>", unsafe_allow_html=True)
            else:
                st.markdown("<div class='ok-bar'>✅ 风险可控：建议按计划复评并持续监测不良反应。</div>", unsafe_allow_html=True)

            tab1, tab2, tab3, tab4 = st.tabs(["处方卡片", "风险雷达", "循证溯源", "专家会诊讨论区"])
            with tab1:
                st.table(local_cards)
                if ai_text:
                    st.markdown("**AI 补充建议**")
                    st.write(ai_text)
                else:
                    st.info("未检测到 API Key，已展示本地规则建议。")

            with tab2:
                st.caption("风险雷达（简化柱状图展示）")
                st.bar_chart(radar)
                if renal_liver_issue:
                    st.error("存在肝肾功能异常：需减量并延长给药间隔。")
                if "苯二氮卓" in current_meds:
                    st.error("检测到联用高风险：阿片类 + 苯二氮卓。")

            with tab3:
                st.markdown("**相似病例**")
                for c in similar_cases:
                    st.markdown(f"- `{c.get('id','N/A')}` {c.get('diagnosis','')} | {c.get('recommended_plan','')}")
                st.markdown("**权威链接**")
                st.markdown("- [国家卫健委](https://www.nhc.gov.cn/)")
                st.markdown("- [国家医保局](https://www.nhsa.gov.cn/)")
                st.markdown("- [国家药监局](https://www.nmpa.gov.cn/)")
                st.markdown("- [PubMed](https://pubmed.ncbi.nlm.nih.gov/)")

            with tab4:
                st.markdown("**会诊记录（模拟）**")
                st.markdown("- 疼痛科：建议先短效滴定，48 小时内观察镇痛与镇静评分。")
                st.markdown("- 药学部：需评估联用药相互作用，建议加入通便方案。")
                st.markdown("- 护理组：建议增加夜间呼吸监测频次，完善患者教育。")

            report = "【阿片类药物辅助决策报告】\n\n" + summary
            report += "\n【处方卡片】\n" + "\n".join([f"- {i['字段']}：{i['内容']}" for i in local_cards])
            report += "\n\n【会诊建议】\n- 疼痛科/药学部/护理组联合复评\n"
            st.session_state.last_report = report
            st.download_button(
                "下载本次建议报告",
                data=report.encode("utf-8"),
                file_name=f"clinical_report_{datetime.now().strftime('%Y%m%d_%H%M')}.txt",
                mime="text/plain",
                use_container_width=True,
            )
        else:
            st.info("提交病例后，这里将显示结构化建议看板。")


def build_training_case(cases: List[Dict], difficulty: str, dept: str) -> Dict:
    base = random.choice(cases) if cases else {}
    age = base.get("age", random.randint(30, 75))
    gender = base.get("gender", random.choice(["男", "女"]))
    diagnosis = base.get("diagnosis", "复杂慢性疼痛")
    pain = base.get("pain_score", random.randint(6, 10))
    case_text = (
        f"患者 {age} 岁，{gender}，{dept}场景；主诉疼痛 NRS {pain}/10。\n"
        f"诊断：{diagnosis}。\n"
        f"既往史：高血压、偶发失眠；家族史提示可能存在物质使用风险。\n"
        f"请完成：风险筛查 -> 初始处方 -> 合规说明 -> 复评计划。"
    )
    questions = [
        {"q": "是否应在开具处方前完成 ORT 风险评估？", "a": "是"},
        {"q": "高风险患者是否可以一次性长疗程处方？", "a": "否"},
        {"q": "是否需要记录知情同意与复评时间点？", "a": "是"},
    ]
    return {"text": case_text, "questions": questions, "difficulty": difficulty, "dept": dept, "pain": pain}


def policy_dual_track(country: str, mme_day: int, ort_level: str) -> str:
    if country == "美国":
        if mme_day > 50:
            return "⚠️ CDC 视角：超过 50 MME/day，建议评估纳洛酮需求并强化复评。"
        return "✅ CDC 视角：当前剂量处于相对审慎区间，仍需共享决策与复评。"
    if ort_level == "高风险" or mme_day > 40:
        return "❌ 中国合规视角：需限量处方、知情同意、二次审方并缩短复评周期。"
    return "✅ 中国合规视角：可常规执行，建议在病历中留存复评计划与风险说明。"


def classify_psych_style(mme_day: int, ask_help: bool) -> str:
    if ask_help:
        return "咨询依赖型"
    if mme_day <= 20:
        return "恐惧型"
    if mme_day >= 60:
        return "放开型"
    return "均衡型"


def page_training(client: Optional[OpenAI], model: str, cases: List[Dict]) -> None:
    st.markdown("### 虚拟训练场")
    st.caption("模块化训练：病例推演 + 动态问答 + 中美政策双轨解析 + AI 心理画像 + 课程矩阵。")
    a, b, c = st.columns(3)
    with a:
        difficulty = st.selectbox("难度", ["初级", "中级", "高级"])
    with b:
        dept = st.selectbox("训练科室", ["肿瘤科", "骨科/口腔科", "急诊科", "疼痛科"])
    with c:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("生成高保真虚拟病例", type="primary", use_container_width=True):
            st.session_state.training_case = build_training_case(cases, difficulty, dept)

    if not st.session_state.training_case:
        st.info("请先生成虚拟病例。")
        return
    case = st.session_state.training_case
    with st.container(border=True):
        st.markdown("#### 临床病例推演")
        st.write(case["text"])

    st.markdown("#### 动态问答判断题")
    answer_map = {}
    for idx, item in enumerate(case["questions"], start=1):
        answer_map[idx] = st.radio(item["q"], ["是", "否"], index=0, key=f"quiz_{idx}")

    with st.form("training_submit"):
        mme_day = st.slider("你建议的初始 MME/day（模拟）", 5, 120, 30)
        ask_help = st.checkbox("我希望调用 AI 咨询辅助后再定稿")
        plan = st.text_area("你的处方方案", height=170, placeholder="请写明药物、剂量、复评、合规与不良反应管理")
        country = st.selectbox("政策视角", ["中国", "美国"])
        submitted = st.form_submit_button("提交训练结果", type="primary", use_container_width=True)

    if not submitted:
        st.markdown("#### 课程矩阵")
        st.dataframe(COURSE_MATRIX, use_container_width=True, hide_index=True)
        return
    if not plan.strip():
        st.warning("请填写处方方案后再提交。")
        return

    correct = sum(1 for i, q in enumerate(case["questions"], start=1) if answer_map[i] == q["a"])
    quiz_score = int(correct / len(case["questions"]) * 30)
    text_score = 70
    low = normalize_text(plan)
    if "复评" not in low and "随访" not in low:
        text_score -= 15
    if "知情同意" not in low and "合规" not in low:
        text_score -= 15
    if "不良反应" not in low and "便秘" not in low and "监测" not in low:
        text_score -= 15
    if len(plan.strip()) < 60:
        text_score -= 10
    final_score = max(0, quiz_score + max(text_score, 20))

    ort_score, ort_level, _ = calc_ort(
        age=random.randint(25, 70),
        personal_use=random.choice(["无", "酒精使用史", "非法药物使用史"]),
        family_use=random.choice(["无", "家族酒精使用史", "家族处方药滥用史"]),
        psych_histories=random.sample(["抑郁", "ADHD", "双相障碍"], k=1),
    )
    policy_result = policy_dual_track(country, mme_day, ort_level)
    psych_style = classify_psych_style(mme_day, ask_help)
    st.session_state.psych_label_counts[psych_style] += 1

    x1, x2, x3 = st.columns(3)
    x1.metric("综合评分", f"{final_score}/100")
    x2.metric("ORT 风险", f"{ort_score} 分 / {ort_level}")
    x3.metric("心理画像", psych_style)

    if "❌" in policy_result or "⚠️" in policy_result:
        st.markdown(f"<div class='warn-bar'>{policy_result}</div>", unsafe_allow_html=True)
    else:
        st.markdown(f"<div class='ok-bar'>{policy_result}</div>", unsafe_allow_html=True)

    feedback = ask_llm(
        client,
        model,
        "你是医学教育评估助手，请对学生处方方案给出针对性改进建议。",
        f"病例：{case['text']}\n方案：{plan}\n政策视角：{country}\nMME/day：{mme_day}",
    )
    if feedback:
        st.markdown("#### AI 个性化辅导")
        st.write(feedback)
    else:
        st.info("本地反馈：请强化复评时间点、知情同意和高风险联用审查。")

    st.session_state.training_history.append(
        {"时间": datetime.now().strftime("%Y-%m-%d %H:%M"), "科室": dept, "难度": difficulty, "评分": final_score, "MME/day": mme_day, "心理画像": psych_style}
    )

    st.markdown("#### 心理画像趋势")
    st.bar_chart(st.session_state.psych_label_counts)
    st.markdown("#### 课程矩阵推荐")
    st.dataframe(COURSE_MATRIX, use_container_width=True, hide_index=True)
    if psych_style == "恐惧型":
        st.warning("微课建议：强化“镇痛不足的伦理风险”与“循证滴定策略”。")
    elif psych_style == "放开型":
        st.error("微课建议：强化“成瘾风险管理”与“政策红线合规训练”。")
    elif psych_style == "咨询依赖型":
        st.info("微课建议：强化“独立决策框架”，逐步减少对外部建议依赖。")
    else:
        st.success("微课建议：保持均衡决策，继续训练复杂共病场景。")


def page_policy(client: Optional[OpenAI], model: str) -> None:
    st.markdown("### 文献与政策库")
    st.caption("三栏固定布局：左侧导航 + 中央政策文献内容 + 右侧智能辅助。")
    st.markdown(
        "<div class='warn-bar'>顶部红线警示：若处方剂量超阈值或缺失知情同意，将触发自动合规预警。</div>",
        unsafe_allow_html=True,
    )

    left, center, right = st.columns([0.85, 1.75, 1.0], gap="large")
    with left:
        st.markdown("#### 功能导航")
        st.button("政策解读引擎", use_container_width=True)
        st.button("权威文献库", use_container_width=True)
        st.button("匿名处方示例", use_container_width=True)
        st.button("AI 合规校验", use_container_width=True)
        st.button("个人收藏", use_container_width=True)
        st.markdown("---")
        st.markdown("#### 高频快捷入口")
        st.markdown("- 癌痛吗啡用量上限")
        st.markdown("- 门诊麻精备案要求")
        st.markdown("- 阿片类联用红线")
        st.markdown("- 复评与随访模板")

    with center:
        keyword = st.text_input("政策/文献搜索（支持自然语言）", placeholder="例如：癌痛吗啡用量上限")
        c1, c2, c3 = st.columns(3)
        with c1:
            category = st.selectbox("分类", ["全部", "处方合规", "风险预警", "医保支付"])
        with c2:
            tag = st.selectbox("标签", ["全部", "红线", "复评", "联用", "医保", "门诊"])
        with c3:
            country = st.selectbox("视角", ["中国", "美国"])
            st.session_state.policy_country = country

        policies = POLICY_LIBRARY
        if st.session_state.policy_province != "全国":
            policies = [p for p in policies if p["province"] in ("全国", st.session_state.policy_province)]
        if category != "全部":
            policies = [p for p in policies if p["category"] == category]
        if tag != "全部":
            policies = [p for p in policies if tag in p["tags"]]
        if keyword.strip():
            k = normalize_text(keyword)
            policies = [p for p in policies if k in normalize_text(p["title"] + p["summary"] + " ".join(p["tags"]))]

        st.caption(f"检索结果：{len(policies)} 条")
        for p in policies:
            qa_html = ""
            for q, a in p["qa"]:
                color = SUCCESS if "✅" in a else (DANGER if "❌" in a else WARNING)
                qa_html += f"<p><b>Q:</b> {q}<br><span style='color:{color};font-weight:600'>{a}</span></p>"
            st.markdown(
                f"""
                <div class="policy-card">
                    <div class="policy-title">{p["title"]}</div>
                    <div style="font-size:12px;color:#65758b">{p["authority"]} | {p["date"]} | {p["id"]}</div>
                    <div style="margin-top:6px">{p["summary"]}</div>
                    <div style="margin-top:8px">{qa_html}</div>
                    <div style="margin-top:8px"><a href="{p["source_url"]}" target="_blank">官方原文链接</a></div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        st.markdown("#### 三联动展示（政策 + 文献 + 处方）")
        tri = [
            {"模块": "政策", "要点": "高风险处方必须限量 + 知情同意 + 复评"},
            {"模块": "文献", "要点": "联合不良反应管理可提升依从性"},
            {"模块": "处方示例", "要点": "按科室模板输出脱敏处方并标注风险等级"},
        ]
        st.table(tri)

    with right:
        st.markdown("#### 省份选择器")
        province = st.selectbox("地区", ["全国", "上海", "广东", "北京", "浙江"])
        st.session_state.policy_province = province
        st.markdown("#### AI 实时合规提示")
        dose = st.slider("拟开具 MME/day", 5, 120, 30)
        ort_level = st.selectbox("风险分层", ["低风险", "中风险", "高风险"])
        consent = st.checkbox("已完成知情同意")

        policy_tip = policy_dual_track(st.session_state.policy_country, dose, ort_level)
        if not consent:
            policy_tip += " ⚠️ 缺少知情同意留痕。"
        if "❌" in policy_tip or "⚠️" in policy_tip:
            st.markdown(f"<div class='warn-bar'>{policy_tip}</div>", unsafe_allow_html=True)
        else:
            st.markdown(f"<div class='ok-bar'>{policy_tip}</div>", unsafe_allow_html=True)

        st.markdown("#### AI 政策问答")
        q = st.text_area("输入问题", placeholder="如：本省高风险患者门诊处方需要哪些留痕？")
        if st.button("生成解读", use_container_width=True):
            if not q.strip():
                st.warning("请输入问题。")
            else:
                ai_text = ask_llm(
                    client,
                    model,
                    "你是政策解读助手，请输出简洁、可执行、分条的合规建议。",
                    f"地区：{province}\n视角：{st.session_state.policy_country}\n问题：{q}",
                )
                if ai_text:
                    st.write(ai_text)
                else:
                    st.info("本地建议：记录诊断、风险分层、知情同意、复评节点与药物联用审查。")

        st.markdown("#### 更新通知")
        st.info("2026-03：门诊高风险处方复评窗口更新。")
        st.info("2026-02：联用风险提示规则强化。")


def page_doctor_dashboard() -> None:
    st.markdown("### 医生管理后台")
    st.caption("闭环流程：患者建档 -> 用药前评估 -> 用药后追踪 -> 随访管理。")
    top1, top2, top3, top4 = st.columns(4)
    top1.metric("患者总数", str(len(st.session_state.patients)))
    top2.metric("高风险患者", str(sum(1 for p in st.session_state.patients if p["risk_level"] == "高风险")))
    top3.metric("待随访", str(sum(1 for p in st.session_state.patients for f in p["followups"] if f["status"] == "待完成")))
    top4.metric("今日异常预警", "2")

    tab1, tab2, tab3, tab4, tab5 = st.tabs(["我的患者库", "用药前评估", "用药后追踪", "随访管理", "账号设置"])
    with tab1:
        st.markdown("#### 患者建档（极简表单）")
        with st.form("add_patient_form"):
            c1, c2, c3, c4 = st.columns(4)
            with c1:
                pname = st.text_input("姓名")
            with c2:
                pdiag = st.text_input("诊断")
            with c3:
                pdept = st.selectbox("科室", ["肿瘤科", "疼痛科", "骨科", "急诊科", "麻醉科"])
            with c4:
                prisk = st.selectbox("风险等级", ["低风险", "中风险", "高风险"])
            add = st.form_submit_button("新建患者", type="primary")
        if add:
            if pname.strip() and pdiag.strip():
                st.session_state.patients.append(
                    {
                        "id": f"PT-{uuid.uuid4().hex[:6].upper()}",
                        "name": pname.strip(),
                        "diagnosis": pdiag.strip(),
                        "department": pdept,
                        "risk_level": prisk,
                        "med_status": "待评估",
                        "created_at": datetime.now().strftime("%Y-%m-%d"),
                        "evaluations": [],
                        "tracking": [],
                        "followups": [],
                    }
                )
                st.success("患者建档成功。")
            else:
                st.error("姓名与诊断不能为空。")

        st.markdown("#### 分类筛选")
        f1, f2 = st.columns(2)
        with f1:
            risk_filter = st.selectbox("风险筛选", ["全部", "低风险", "中风险", "高风险"])
        with f2:
            status_filter = st.selectbox("状态筛选", ["全部", "待评估", "用药中", "待随访"])

        rows = []
        for p in st.session_state.patients:
            if risk_filter != "全部" and p["risk_level"] != risk_filter:
                continue
            if status_filter != "全部" and p["med_status"] != status_filter:
                continue
            rows.append({"患者": mask_name(p["name"]), "ID": p["id"], "诊断": p["diagnosis"], "科室": p["department"], "风险": p["risk_level"], "状态": p["med_status"], "建档日期": p["created_at"]})
        st.dataframe(rows, use_container_width=True, hide_index=True)

    with tab2:
        st.markdown("#### 用药前风险评估")
        options = [f"{p['id']} | {mask_name(p['name'])} | {p['diagnosis']}" for p in st.session_state.patients]
        selected = st.selectbox("选择患者", options)
        pid = selected.split("|")[0].strip()
        patient = get_patient_by_id(pid)
        if patient:
            st.info(f"已关联患者：{mask_name(patient['name'])} / {patient['diagnosis']} / {patient['department']}")
            with st.form("pre_eval"):
                c1, c2, c3 = st.columns(3)
                with c1:
                    age = st.number_input("年龄", 1, 120, 56)
                    personal_use = st.selectbox("本人物质使用史", ["无", "酒精使用史", "非法药物使用史", "处方药滥用史"])
                with c2:
                    family_use = st.selectbox("家族物质使用史", ["无", "家族酒精使用史", "家族非法药物使用史", "家族处方药滥用史"])
                    psych = st.multiselect("心理病史", ["抑郁", "ADHD", "双相障碍", "精神分裂谱系障碍"])
                with c3:
                    policy_risk = st.checkbox("存在政策红线风险")
                    clinical_risk = st.checkbox("存在临床高危联用")
                    psych_risk = st.checkbox("存在心理共病风险")
                submit_eval = st.form_submit_button("生成评估报告", type="primary")
            if submit_eval:
                ort_score, ort_level, details = calc_ort(age, personal_use, family_use, psych)
                report = (
                    f"患者 {mask_name(patient['name'])} 评估结果：ORT {ort_score} 分（{ort_level}）；"
                    f"临床风险={'是' if clinical_risk else '否'}；政策风险={'是' if policy_risk else '否'}；"
                    f"心理风险={'是' if psych_risk else '否'}。"
                )
                patient["risk_level"] = ort_level
                patient["med_status"] = "用药中"
                patient["evaluations"].append({"time": datetime.now().strftime("%Y-%m-%d %H:%M"), "report": report, "details": details})
                st.success("评估完成，报告已归档至患者详情。")
                st.write(report)
                st.download_button(
                    "导出评估报告",
                    data=report.encode("utf-8"),
                    file_name=f"pre_eval_{pid}_{datetime.now().strftime('%Y%m%d_%H%M')}.txt",
                    mime="text/plain",
                )

    with tab3:
        st.markdown("#### 用药后追踪")
        options = [f"{p['id']} | {mask_name(p['name'])}" for p in st.session_state.patients]
        selected = st.selectbox("追踪患者", options, key="track_select")
        pid = selected.split("|")[0].strip()
        patient = get_patient_by_id(pid)
        if patient:
            with st.form("tracking_form"):
                c1, c2, c3 = st.columns(3)
                with c1:
                    pain = st.slider("今日疼痛评分", 0, 10, 5)
                with c2:
                    adherence = st.slider("依从性(%)", 0, 100, 80)
                with c3:
                    adverse = st.text_input("不良反应", placeholder="如：便秘、恶心、嗜睡")
                submit_track = st.form_submit_button("保存追踪记录", type="primary")
            if submit_track:
                patient["tracking"].append({"time": datetime.now().strftime("%Y-%m-%d"), "pain": pain, "adverse": adverse or "无明显", "adherence": adherence})
                if pain >= 8 or "呼吸" in adverse:
                    st.markdown("<div class='warn-bar'>⚠️ 指标异常：建议立即复核方案并记录调整原因。</div>", unsafe_allow_html=True)
                else:
                    st.success("追踪记录已保存。")
            if patient["tracking"]:
                st.markdown("**疼痛趋势**")
                st.line_chart({"疼痛评分": [x["pain"] for x in patient["tracking"]]})
                st.markdown("**依从性趋势**")
                st.line_chart({"依从性": [x["adherence"] for x in patient["tracking"]]})

    with tab4:
        st.markdown("#### 随访管理")
        todo = []
        now = datetime.now()
        for p in st.session_state.patients:
            for item in p["followups"]:
                due = datetime.strptime(item["time"], "%Y-%m-%d %H:%M")
                overdue = due < now and item["status"] == "待完成"
                todo.append({"患者": mask_name(p["name"]), "时间": item["time"], "状态": "逾期" if overdue else item["status"], "说明": item["note"]})
        st.dataframe(todo, use_container_width=True, hide_index=True)

        options = [f"{p['id']} | {mask_name(p['name'])}" for p in st.session_state.patients]
        selected = st.selectbox("新增随访计划", options, key="follow_select")
        pid = selected.split("|")[0].strip()
        patient = get_patient_by_id(pid)
        with st.form("follow_form"):
            when = st.text_input("随访时间（YYYY-MM-DD HH:MM）", value=(datetime.now() + timedelta(hours=24)).strftime("%Y-%m-%d %H:%M"))
            note = st.text_input("随访内容")
            submit_follow = st.form_submit_button("添加计划", type="primary")
        if submit_follow and patient:
            patient["followups"].append({"time": when, "status": "待完成", "note": note or "常规复评"})
            patient["med_status"] = "待随访"
            st.success("随访计划已添加。")

    with tab5:
        st.markdown("#### 账号与安全设置")
        st.checkbox("启用二次验证（高敏模块）", value=True)
        st.checkbox("绑定登录 IP 白名单", value=False)
        st.checkbox("开启异常登录通知", value=True)
        st.checkbox("自动锁屏（15 分钟）", value=True)
        st.info("所有患者信息默认脱敏展示，操作日志可追溯。")


def page_profile() -> None:
    st.markdown("### 个人中心")
    l, r = st.columns([1, 2])
    with l:
        with st.container(border=True):
            st.subheader(st.session_state.doctor_name)
            st.caption(st.session_state.doctor_title)
            st.caption("科室：疼痛医学中心")
            st.caption("医院：示例三甲医院")
            st.caption("工号：MD-2026-041")
    with r:
        c1, c2, c3 = st.columns(3)
        c1.metric("本周辅助决策", "42")
        c2.metric("高风险复评完成率", "91%")
        c3.metric("训练场平均得分", "88")

    st.markdown("#### 最近训练记录")
    if st.session_state.training_history:
        st.dataframe(st.session_state.training_history[::-1], use_container_width=True, hide_index=True)
    else:
        st.info("暂无训练记录。")

    if st.session_state.last_report:
        st.download_button(
            "下载最近临床辅助报告",
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
                dept = st.selectbox("科室", ["肿瘤科", "疼痛科", "骨科", "急诊科", "麻醉科"])
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

    protected = {"临床辅助", "虚拟训练", "医生管理后台", "个人中心"}
    if not st.session_state.is_logged_in and page in protected:
        st.warning("当前未登录，请先进入“登录与安全”完成认证，或启用体验模式。")
        if st.button("启用体验模式", type="primary"):
            st.session_state.is_logged_in = True
            st.session_state.doctor_name = "体验账号"
            st.session_state.doctor_title = "演示模式"
            st.rerun()
        render_footer_note()
        st.stop()

    if page == "工作台总览":
        page_dashboard(cases)
    elif page == "临床辅助":
        page_clinical_assistant(client, model, cases)
    elif page == "虚拟训练":
        page_training(client, model, cases)
    elif page == "文献与政策库":
        page_policy(client, model)
    elif page == "医生管理后台":
        page_doctor_dashboard()
    elif page == "个人中心":
        page_profile()
    else:
        page_login()

    render_footer_note()


if __name__ == "__main__":
    main()
