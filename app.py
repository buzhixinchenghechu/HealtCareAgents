# -*- coding: utf-8 -*-
"""阿片类药物辅助决策系统（Streamlit）"""

from __future__ import annotations

import json
import os
import random
import re
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import streamlit as st
from openai import OpenAI


st.set_page_config(
    page_title="阿片类药物辅助决策系统",
    page_icon="💊",
    layout="wide",
    initial_sidebar_state="expanded",
)


NEWS_FEED = [
    {
        "date": "2026-03-01",
        "title": "门诊阿片类处方复评流程更新",
        "summary": "新增“7天内复评”规则，要求高风险患者必须进行二次评估并记录知情同意。",
    },
    {
        "date": "2026-02-25",
        "title": "肿瘤疼痛多学科协作路径发布",
        "summary": "建议肿瘤科、麻醉疼痛科、药学部协同制定初始方案并联合随访。",
    },
    {
        "date": "2026-02-18",
        "title": "阿片类药物不良反应监测重点提示",
        "summary": "重点关注呼吸抑制、便秘、镇静过度与跌倒风险，强调起始剂量和合并用药审查。",
    },
]


POLICY_LIBRARY = [
    {
        "id": "POL-2026-001",
        "title": "门诊阿片类药物处方与复评规范（2026版）",
        "source": "医院药事管理委员会",
        "date": "2026-03-01",
        "tags": ["处方合规", "复评流程"],
        "summary": "高风险患者应在 7 天内完成首次复评；长期治疗需建立随访计划并记录疗效和不良反应。",
        "action": "用于门诊长期镇痛治疗流程设计与审方。",
    },
    {
        "id": "POL-2026-002",
        "title": "阿片类药物知情同意与患者教育要点",
        "source": "医务处",
        "date": "2026-02-20",
        "tags": ["知情同意", "患者教育"],
        "summary": "明确沟通治疗目标、停药条件、潜在风险与紧急就医指征；建议统一模板留存签署记录。",
        "action": "用于建立处方前沟通与病历留痕。",
    },
    {
        "id": "POL-2026-003",
        "title": "阿片类药物联合用药风险清单",
        "source": "临床药学部",
        "date": "2026-02-12",
        "tags": ["药物相互作用", "风险预警"],
        "summary": "重点审查与镇静催眠药、酒精、抗焦虑药联用风险，建议起始期高频监测。",
        "action": "用于临床辅助页面的自动风险提示。",
    },
    {
        "id": "POL-2026-004",
        "title": "住院镇痛路径中的 ORT 风险分层应用",
        "source": "麻醉与疼痛质控组",
        "date": "2026-01-30",
        "tags": ["ORT", "风险分层"],
        "summary": "将 ORT 评分纳入住院镇痛路径，低中高风险分别匹配不同监测与随访强度。",
        "action": "用于高风险患者预警和随访排班。",
    },
]


def inject_css() -> None:
    st.markdown(
        """
        <style>
        :root {
            --bg: #f4f7fb;
            --card: #ffffff;
            --text: #10243d;
            --muted: #5b6b7e;
            --brand: #1d5cff;
            --ok: #169c4b;
            --warn: #de7b00;
            --danger: #d7263d;
        }
        .stApp {
            background:
                radial-gradient(1200px 400px at -20% -10%, #dce8ff 0%, rgba(220, 232, 255, 0) 55%),
                radial-gradient(1200px 400px at 120% -20%, #e4f5ff 0%, rgba(228, 245, 255, 0) 55%),
                var(--bg);
        }
        .hero {
            background: linear-gradient(120deg, #1446cc 0%, #1d5cff 55%, #29b6f6 100%);
            color: #fff;
            border-radius: 18px;
            padding: 20px 22px;
            border: 1px solid rgba(255,255,255,0.25);
            box-shadow: 0 12px 30px rgba(20, 70, 204, 0.20);
            margin-bottom: 12px;
        }
        .hero h1 {
            margin: 0 0 6px 0;
            font-size: 28px;
            font-weight: 800;
            letter-spacing: 0.2px;
        }
        .hero p {
            margin: 0;
            opacity: 0.95;
            font-size: 14px;
        }
        .kpi-card {
            background: var(--card);
            border-radius: 14px;
            border: 1px solid #e8edf7;
            padding: 14px 16px;
            box-shadow: 0 8px 20px rgba(16, 36, 61, 0.04);
        }
        .kpi-title {
            color: var(--muted);
            font-size: 12px;
            margin-bottom: 6px;
        }
        .kpi-value {
            color: var(--text);
            font-size: 28px;
            font-weight: 700;
            line-height: 1.1;
        }
        .kpi-sub {
            color: #2f6df8;
            font-size: 12px;
            margin-top: 4px;
        }
        .tag {
            display: inline-block;
            padding: 2px 8px;
            border-radius: 999px;
            font-size: 11px;
            border: 1px solid transparent;
            margin-right: 6px;
            margin-top: 6px;
        }
        .tag-low { background: #e8f8ee; color: #116f35; border-color: #bde7cd; }
        .tag-mid { background: #fff6e8; color: #a75800; border-color: #ffd9ad; }
        .tag-high { background: #ffecee; color: #a61f2f; border-color: #ffc7ce; }
        .muted { color: var(--muted); font-size: 13px; }
        .policy-card {
            background: #fff;
            border: 1px solid #e8edf7;
            border-radius: 14px;
            padding: 14px;
            margin-bottom: 10px;
        }
        .policy-title {
            font-size: 16px;
            font-weight: 700;
            color: var(--text);
            margin-bottom: 6px;
        }
        .timeline-item {
            border-left: 2px solid #cfe0ff;
            padding-left: 12px;
            margin-left: 6px;
            margin-bottom: 12px;
        }
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
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.2,
            max_tokens=1200,
        )
        content = response.choices[0].message.content or ""
        return str(content).strip()
    except Exception as exc:  # pragma: no cover
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
            [
                case.get("id", ""),
                case.get("diagnosis", ""),
                case.get("category", ""),
                case.get("pain_type", ""),
                case.get("recommended_plan", ""),
                case.get("risk_notes", ""),
            ],
        )
    )


def retrieve_similar_cases(query: str, cases: List[Dict], top_k: int = 3) -> List[Dict]:
    if not cases:
        return []

    query_tokens = tokenize(query)
    if not query_tokens:
        return cases[:top_k]

    scored = []
    for case in cases:
        text = case_summary_text(case)
        tokens = tokenize(text)
        if not tokens:
            continue
        overlap = len(query_tokens & tokens)
        score = overlap / (len(query_tokens) + 1)
        if query in text:
            score += 0.2
        scored.append((score, case))

    scored.sort(key=lambda item: item[0], reverse=True)
    selected = [case for score, case in scored if score > 0][:top_k]
    return selected or cases[:top_k]


def calc_ort(age: int, personal_use: str, family_use: str, psych_histories: List[str]) -> Tuple[int, str, List[str]]:
    score = 0
    details = []

    if 16 <= age <= 45:
        score += 1
        details.append("年龄 16-45 岁 +1")

    personal_points = {
        "无": 0,
        "酒精使用史": 3,
        "非法药物使用史": 4,
        "处方药滥用史": 5,
    }
    family_points = {
        "无": 0,
        "家族酒精使用史": 1,
        "家族非法药物使用史": 2,
        "家族处方药滥用史": 4,
    }
    psych_points = {
        "抑郁": 1,
        "ADHD": 2,
        "双相障碍": 2,
        "精神分裂谱系障碍": 2,
    }

    pp = personal_points.get(personal_use, 0)
    fp = family_points.get(family_use, 0)
    score += pp + fp
    if pp:
        details.append(f"{personal_use} +{pp}")
    if fp:
        details.append(f"{family_use} +{fp}")

    for item in psych_histories:
        pts = psych_points.get(item, 0)
        if pts:
            score += pts
            details.append(f"{item} +{pts}")

    if score <= 3:
        level = "低风险"
    elif score <= 7:
        level = "中风险"
    else:
        level = "高风险"
    return score, level, details


def local_plan(age: int, pain_score: int, ort_level: str, opioid_naive: bool) -> str:
    if pain_score <= 3:
        base = "优先非阿片药物（对乙酰氨基酚或 NSAIDs）并动态评估。"
    elif pain_score <= 6:
        base = "可考虑短疗程弱阿片或低剂量短效阿片，联合非阿片药物。"
    else:
        base = "可考虑短效强阿片起始，先小剂量滴定并尽早复评。"

    naive_hint = "为阿片初治患者，建议从最低有效剂量起步。" if opioid_naive else "已有阿片暴露史，建议核对既往耐受与换算剂量。"

    if ort_level == "低风险":
        monitor = "随访建议：3-7 天复评镇痛效果和不良反应。"
    elif ort_level == "中风险":
        monitor = "随访建议：3 天内复评，要求处方限量、记录知情同意。"
    else:
        monitor = "随访建议：24-72 小时复评，优先多学科会诊并强化监测。"

    return (
        f"### 本地规则建议\n"
        f"1. {base}\n"
        f"2. {naive_hint}\n"
        f"3. 优先口服给药，非必要不选择注射途径。\n"
        f"4. 联合通便、止吐和跌倒风险教育。\n"
        f"5. {monitor}\n"
    )


def local_risk_and_compliance(pain_score: int, ort_level: str, comorbidities: str, current_meds: str) -> str:
    risks = []
    if pain_score >= 7:
        risks.append("高疼痛评分提示可能需要快速滴定，需防止过量镇静。")
    if "呼吸" in comorbidities or "copd" in normalize_text(comorbidities):
        risks.append("存在呼吸系统风险，需重点警惕呼吸抑制。")
    if "苯二氮卓" in current_meds or "安眠" in current_meds:
        risks.append("与镇静催眠药联用，过度镇静风险上升。")
    if ort_level == "高风险":
        risks.append("ORT 高风险，建议短处方、高频复评、必要时会诊。")

    if not risks:
        risks.append("未识别到显著高危信号，仍需按流程复评。")

    compliance = [
        "确认诊断与镇痛目标，并记录疗效终点。",
        "完成知情同意：包含依赖风险、不良反应、停药条件。",
        "高风险患者执行限量处方和随访计划。",
        "病历中记录不良反应监测与复评时间点。",
    ]

    text = "### 风险提示\n"
    for idx, item in enumerate(risks, start=1):
        text += f"{idx}. {item}\n"
    text += "\n### 合规要点\n"
    for idx, item in enumerate(compliance, start=1):
        text += f"{idx}. {item}\n"
    return text


def render_top_banner() -> None:
    date_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    st.markdown(
        f"""
        <div class="hero">
            <h1>阿片类药物辅助决策系统</h1>
            <p>覆盖工作台总览、临床辅助、虚拟训练、文献政策和个人中心 | 当前时间：{date_str}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def sidebar_navigation() -> str:
    with st.sidebar:
        st.markdown("## 医疗智能平台")
        st.caption("Opioid Decision Support v2.0")
        page = st.radio(
            "导航",
            ["工作台总览", "临床辅助", "虚拟训练", "文献与政策库", "个人中心", "登录与安全"],
            index=["工作台总览", "临床辅助", "虚拟训练", "文献与政策库", "个人中心", "登录与安全"].index(
                st.session_state.current_page
            ),
        )
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
            st.caption("可进入“登录与安全”完成认证")

        st.markdown("---")
        st.caption("提示：本系统输出仅作临床辅助参考。")
    return page


def page_dashboard(cases: List[Dict]) -> None:
    st.markdown("### 工作台总览")

    col1, col2, col3, col4 = st.columns(4)
    metrics = [
        ("今日待评估病例", str(max(8, len(cases) // 8 or 12)), "较昨日 +2"),
        ("高风险预警", str(max(3, len(cases) // 20 or 5)), "需优先复评"),
        ("处方合规率", "96.2%", "稳定"),
        ("本周复评完成率", "88.5%", "持续提升"),
    ]
    for col, (title, value, sub) in zip([col1, col2, col3, col4], metrics):
        with col:
            st.markdown(
                f"""
                <div class="kpi-card">
                    <div class="kpi-title">{title}</div>
                    <div class="kpi-value">{value}</div>
                    <div class="kpi-sub">{sub}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    st.markdown("")
    left, right = st.columns([1.2, 1])

    with left:
        st.markdown("#### 本周风险趋势")
        st.bar_chart({"低风险": [22, 20, 24, 21, 23, 26, 25], "中高风险": [8, 9, 7, 10, 9, 8, 7]})

        st.markdown("#### 最新动态")
        for item in NEWS_FEED:
            with st.container(border=True):
                st.write(f"**{item['title']}**")
                st.caption(f"{item['date']}")
                st.write(item["summary"])

    with right:
        st.markdown("#### 快捷入口")
        if st.button("进入临床辅助", use_container_width=True):
            st.session_state.current_page = "临床辅助"
            st.rerun()
        if st.button("进入虚拟训练", use_container_width=True):
            st.session_state.current_page = "虚拟训练"
            st.rerun()
        if st.button("查看文献与政策库", use_container_width=True):
            st.session_state.current_page = "文献与政策库"
            st.rerun()

        st.markdown("#### 今日提醒")
        st.info("请优先处理 ORT 高风险且疼痛评分 >= 7 的患者。")
        st.warning("发现 2 例“阿片 + 镇静催眠药”联用处方，建议复核。")
        st.success("知识库最近 7 天已同步 4 条院内政策。")


def page_clinical_assistant(client: Optional[OpenAI], model: str, cases: List[Dict]) -> None:
    st.markdown("### 临床辅助")
    st.caption("输入患者信息后生成：用药建议、风险评估、合规提示、相似病例参考。")

    with st.form("clinical_form", clear_on_submit=False):
        c1, c2, c3 = st.columns(3)
        with c1:
            age = st.number_input("年龄", min_value=1, max_value=120, value=60, step=1)
            gender = st.selectbox("性别", ["男", "女"])
            pain_score = st.slider("疼痛评分 NRS", 0, 10, 7)
        with c2:
            diagnosis = st.text_input("主要诊断", placeholder="如：晚期肿瘤骨转移")
            pain_type = st.selectbox("疼痛类型", ["癌性疼痛", "非癌性急性疼痛", "非癌性慢性疼痛"])
            department = st.selectbox("科室", ["肿瘤科", "疼痛科", "骨科", "急诊科", "麻醉科", "其他"])
        with c3:
            opioid_naive = st.checkbox("阿片初治患者", value=True)
            renal_liver_issue = st.checkbox("存在肝肾功能异常", value=False)
            allergy = st.text_input("过敏史", placeholder="如：吗啡过敏")

        d1, d2 = st.columns(2)
        with d1:
            current_meds = st.text_area("当前用药", placeholder="每行一个，例如：劳拉西泮 1mg qn")
            comorbidities = st.text_area("合并症", placeholder="如：COPD、睡眠呼吸暂停、高血压")
        with d2:
            personal_use = st.selectbox("本人物质使用史", ["无", "酒精使用史", "非法药物使用史", "处方药滥用史"])
            family_use = st.selectbox("家族物质使用史", ["无", "家族酒精使用史", "家族非法药物使用史", "家族处方药滥用史"])
            psych_histories = st.multiselect("心理/精神病史", ["抑郁", "ADHD", "双相障碍", "精神分裂谱系障碍"])
            extra_notes = st.text_area("补充说明", placeholder="其他需要纳入决策的信息")

        submit = st.form_submit_button("生成辅助建议", type="primary", use_container_width=True)

    ort_score, ort_level, ort_details = calc_ort(age, personal_use, family_use, psych_histories)
    risk_class = "tag-low" if ort_level == "低风险" else ("tag-mid" if ort_level == "中风险" else "tag-high")

    st.markdown(
        f"""
        <span class="tag {risk_class}">ORT 评分：{ort_score} 分</span>
        <span class="tag {risk_class}">风险分层：{ort_level}</span>
        """,
        unsafe_allow_html=True,
    )
    st.caption(" | ".join(ort_details) if ort_details else "未识别显著成瘾高危因素")

    if not submit:
        return

    if not diagnosis.strip():
        st.warning("请填写主要诊断后再生成建议。")
        return

    query = f"{diagnosis} {pain_type} {department} {comorbidities}"
    similar_cases = retrieve_similar_cases(query, cases, top_k=3)

    summary = f"""
患者：{age} 岁 {gender}
主要诊断：{diagnosis}
疼痛评分：{pain_score}/10（{pain_type}）
科室：{department}
阿片初治：{"是" if opioid_naive else "否"}
肝肾异常：{"是" if renal_liver_issue else "否"}
过敏史：{allergy or "无"}
当前用药：{current_meds or "无"}
合并症：{comorbidities or "无"}
本人物质使用史：{personal_use}
家族物质使用史：{family_use}
心理/精神病史：{", ".join(psych_histories) if psych_histories else "无"}
ORT：{ort_score} 分（{ort_level}）
补充说明：{extra_notes or "无"}
"""

    local_plan_text = local_plan(age, pain_score, ort_level, opioid_naive)
    local_risk_text = local_risk_and_compliance(pain_score, ort_level, comorbidities, current_meds)

    case_ref = []
    for c in similar_cases:
        case_ref.append(
            f"- [{c.get('id', 'N/A')}] {c.get('diagnosis', '')} | 推荐：{c.get('recommended_plan', '')}"
        )
    case_ref_text = "\n".join(case_ref) if case_ref else "无可用参考病例。"

    tabs = st.tabs(["用药建议", "风险与合规", "相似病例与证据"])

    with tabs[0]:
        st.markdown(local_plan_text)
        ai_text = ask_llm(
            client,
            model,
            "你是临床阿片类处方助手，请给出简洁、结构化、可执行的处方建议。",
            f"请基于以下病例给出建议，并包含备选方案与复评时间：\n{summary}",
        )
        if ai_text:
            st.markdown("### AI 补充建议")
            st.write(ai_text)
        else:
            st.info("未检测到可用 API Key，当前显示本地规则建议。")

    with tabs[1]:
        st.markdown(local_risk_text)
        if renal_liver_issue:
            st.warning("存在肝肾功能异常：请优先考虑减量、延长给药间隔并加强监测。")
        if "苯二氮卓" in current_meds:
            st.error("检测到潜在高风险联用（阿片 + 苯二氮卓），需复核必要性。")

    with tabs[2]:
        st.markdown("### 相似病例")
        st.markdown(case_ref_text)
        st.markdown("### 参考政策")
        st.markdown("- 门诊阿片类药物处方与复评规范（2026版）")
        st.markdown("- 阿片类药物知情同意与患者教育要点")
        st.markdown("- 阿片类药物联合用药风险清单")

    report = (
        "【阿片类药物辅助决策报告】\n\n"
        + summary
        + "\n"
        + local_plan_text.replace("### ", "")
        + "\n"
        + local_risk_text.replace("### ", "")
        + "\n相似病例：\n"
        + case_ref_text
    )
    st.session_state.last_report = report
    st.download_button(
        "下载本次建议报告",
        data=report.encode("utf-8"),
        file_name=f"opioid_decision_report_{datetime.now().strftime('%Y%m%d_%H%M')}.txt",
        mime="text/plain",
        use_container_width=True,
    )


def build_training_case(cases: List[Dict], difficulty: str, scenario: str) -> str:
    case = random.choice(cases) if cases else {}
    age = case.get("age", random.randint(35, 75))
    gender = case.get("gender", random.choice(["男", "女"]))
    diagnosis = case.get("diagnosis", "慢性顽固性疼痛")
    pain = case.get("pain_score", random.randint(6, 9))
    extra = {
        "初级": "重点练习初始评估与安全起始剂量。",
        "中级": "重点练习联合用药、复评与不良反应管理。",
        "高级": "重点练习高风险分层、合规留痕与多学科沟通。",
    }.get(difficulty, "完成处方并解释你的决策逻辑。")

    return (
        f"【虚拟病例】\n"
        f"- 场景：{scenario}\n"
        f"- 难度：{difficulty}\n"
        f"- 患者：{age} 岁，{gender}\n"
        f"- 诊断：{diagnosis}\n"
        f"- 疼痛评分：NRS {pain}/10\n"
        f"- 既往史：高血压，偶发失眠\n"
        f"- 当前问题：拟启动阿片类镇痛治疗，请设计首日处方方案与复评计划。\n"
        f"- 训练目标：{extra}\n"
    )


def evaluate_training_answer(answer: str) -> Tuple[int, List[str], List[str]]:
    score = 100
    strengths = []
    issues = []
    text = normalize_text(answer)

    if any(k in text for k in ["复评", "随访", "48h", "72h"]):
        strengths.append("提到了复评或随访安排。")
    else:
        score -= 20
        issues.append("缺少复评时间点。")

    if any(k in text for k in ["知情同意", "风险告知", "教育"]):
        strengths.append("考虑了沟通和知情同意。")
    else:
        score -= 15
        issues.append("未体现知情同意与患者教育。")

    if any(k in text for k in ["便秘", "止吐", "不良反应", "监测"]):
        strengths.append("包含了不良反应管理要点。")
    else:
        score -= 15
        issues.append("缺少不良反应预防/监测策略。")

    if any(k in text for k in ["高风险", "ort", "依赖风险"]):
        strengths.append("考虑了成瘾风险因素。")
    else:
        score -= 10
        issues.append("未明确风险分层依据。")

    if len(answer.strip()) < 40:
        score -= 20
        issues.append("方案过于简短，临床可执行性不足。")

    return max(score, 0), strengths, issues


def page_training(client: Optional[OpenAI], model: str, cases: List[Dict]) -> None:
    st.markdown("### 虚拟训练")
    st.caption("生成病例后提交你的处方方案，系统会自动评分并给出改进建议。")

    t1, t2, t3 = st.columns(3)
    with t1:
        difficulty = st.selectbox("难度", ["初级", "中级", "高级"])
    with t2:
        scenario = st.selectbox("场景", ["肿瘤科门诊", "急诊科", "骨科病房", "疼痛科门诊"])
    with t3:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("生成训练病例", type="primary", use_container_width=True):
            st.session_state.training_case = build_training_case(cases, difficulty, scenario)

    if not st.session_state.training_case:
        st.info("点击“生成训练病例”开始练习。")
        return

    with st.container(border=True):
        st.markdown(st.session_state.training_case)

    with st.form("training_form"):
        answer = st.text_area(
            "你的处方方案",
            height=180,
            placeholder="请写明：药物与剂量、给药途径、疗程、监测计划、知情同意与复评安排。",
        )
        submitted = st.form_submit_button("提交并评分", type="primary", use_container_width=True)

    if not submitted:
        return

    if not answer.strip():
        st.warning("请填写你的处方方案。")
        return

    score, strengths, issues = evaluate_training_answer(answer)
    c1, c2, c3 = st.columns(3)
    c1.metric("综合得分", f"{score}/100")
    c2.metric("优势项", str(len(strengths)))
    c3.metric("待改进项", str(len(issues)))

    st.markdown("#### 评分反馈")
    if strengths:
        st.success("优点：\n" + "\n".join([f"- {s}" for s in strengths]))
    if issues:
        st.error("改进：\n" + "\n".join([f"- {i}" for i in issues]))

    ai_feedback = ask_llm(
        client,
        model,
        "你是医学教育评估助手，请对学生阿片类处方方案做教学反馈。",
        f"病例：\n{st.session_state.training_case}\n\n学生方案：\n{answer}\n\n请给出改进建议。",
    )
    if ai_feedback:
        st.markdown("#### AI 个性化建议")
        st.write(ai_feedback)

    st.session_state.training_history.append(
        {
            "时间": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "场景": scenario,
            "难度": difficulty,
            "得分": score,
            "摘要": answer[:80].replace("\n", " ") + ("..." if len(answer) > 80 else ""),
        }
    )

    if st.session_state.training_history:
        st.markdown("#### 训练历史")
        st.dataframe(st.session_state.training_history[::-1], use_container_width=True, hide_index=True)


def page_policy(client: Optional[OpenAI], model: str) -> None:
    st.markdown("### 文献与政策库")
    st.caption("支持按关键字和标签过滤政策条目，并提供合规问答。")

    c1, c2 = st.columns([2, 1])
    with c1:
        keyword = st.text_input("搜索", placeholder="输入药物、风险点或政策关键词")
    with c2:
        selected_tags = st.multiselect("标签筛选", sorted({t for p in POLICY_LIBRARY for t in p["tags"]}))

    policies = POLICY_LIBRARY
    if keyword.strip():
        k = normalize_text(keyword)
        policies = [
            p
            for p in policies
            if k in normalize_text(p["title"]) or k in normalize_text(p["summary"]) or k in normalize_text(" ".join(p["tags"]))
        ]
    if selected_tags:
        policies = [p for p in policies if any(tag in p["tags"] for tag in selected_tags)]

    st.markdown(f"检索结果：{len(policies)} 条")
    for p in policies:
        tags = " ".join([f"<span class='tag tag-mid'>{tag}</span>" for tag in p["tags"]])
        st.markdown(
            f"""
            <div class="policy-card">
                <div class="policy-title">{p["title"]}</div>
                <div class="muted">{p["source"]} | {p["date"]} | {p["id"]}</div>
                <div style="margin-top: 8px; margin-bottom: 6px;">{p["summary"]}</div>
                <div class="muted"><b>应用场景：</b>{p["action"]}</div>
                <div>{tags}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown("#### 合规核查清单")
    ck1 = st.checkbox("已记录诊断依据与镇痛目标")
    ck2 = st.checkbox("已完成知情同意并签名留痕")
    ck3 = st.checkbox("已制定复评计划（时间 + 指标）")
    ck4 = st.checkbox("已完成高风险联用审查")
    done = sum([ck1, ck2, ck3, ck4])
    st.progress(done / 4, text=f"完成度：{done}/4")

    st.markdown("#### AI 政策助手")
    q = st.text_area("输入问题", placeholder="例如：门诊高风险患者开具阿片类药物时，最低需要哪些留痕？")
    if st.button("生成政策解读", use_container_width=True):
        if not q.strip():
            st.warning("请先输入问题。")
        else:
            ai_text = ask_llm(
                client,
                model,
                "你是医疗政策助手，请给出结构化、可执行、简洁的合规建议。",
                q,
            )
            if ai_text:
                st.write(ai_text)
            else:
                st.info("未检测到可用 API Key，以下为本地建议：")
                st.write(
                    "1) 明确诊断与适应证；2) 记录风险分层与知情同意；"
                    "3) 设置限量处方与复评节点；4) 对高风险联用处方进行二次审核。"
                )


def page_profile() -> None:
    st.markdown("### 个人中心")

    p1, p2 = st.columns([1, 2])
    with p1:
        with st.container(border=True):
            st.subheader(st.session_state.doctor_name)
            st.caption(st.session_state.doctor_title)
            st.caption("科室：疼痛医学中心")
            st.caption("职级：主任医师")
            st.caption("工号：MD-2026-041")
    with p2:
        c1, c2, c3 = st.columns(3)
        c1.metric("本周辅助决策次数", "37")
        c2.metric("高风险病例复评达成率", "90%")
        c3.metric("训练场平均得分", "86")

    st.markdown("#### 偏好设置")
    st.toggle("开启高风险处方即时提醒", value=True)
    st.toggle("开启政策更新推送", value=True)
    st.toggle("开启复评逾期提醒", value=True)

    st.markdown("#### 最近活动")
    history = st.session_state.training_history[-5:][::-1]
    if history:
        for item in history:
            st.markdown(
                f"""
                <div class="timeline-item">
                    <b>{item["时间"]}</b> | {item["场景"]} | {item["难度"]} | 得分 {item["得分"]}<br/>
                    <span class="muted">{item["摘要"]}</span>
                </div>
                """,
                unsafe_allow_html=True,
            )
    else:
        st.info("暂无训练记录。")

    if st.session_state.last_report:
        st.download_button(
            "下载最近一次临床辅助报告",
            data=st.session_state.last_report.encode("utf-8"),
            file_name=f"profile_last_report_{datetime.now().strftime('%Y%m%d')}.txt",
            mime="text/plain",
            use_container_width=True,
        )


def page_login() -> None:
    st.markdown("### 登录与安全")
    st.caption("用于模拟登录流程与安全设置。")

    tab1, tab2 = st.tabs(["账号登录", "验证码登录"])
    with tab1:
        with st.form("login_form_pwd"):
            username = st.text_input("用户名", placeholder="doctor_zhang")
            password = st.text_input("登录密码", type="password")
            submit = st.form_submit_button("登录", type="primary", use_container_width=True)
        if submit:
            if username.strip() and password.strip():
                st.session_state.is_logged_in = True
                st.session_state.doctor_name = username.strip()
                st.session_state.doctor_title = "临床医生"
                st.success("登录成功")
            else:
                st.error("请输入用户名和密码")

    with tab2:
        with st.form("login_form_code"):
            mobile = st.text_input("手机号", placeholder="138****0000")
            code = st.text_input("验证码", placeholder="6位验证码")
            submit2 = st.form_submit_button("登录", use_container_width=True)
        if submit2:
            if mobile.strip() and code.strip():
                st.session_state.is_logged_in = True
                st.session_state.doctor_name = f"用户{mobile[-4:]}"
                st.session_state.doctor_title = "临床医生"
                st.success("登录成功")
            else:
                st.error("请输入手机号和验证码")

    st.markdown("#### 安全策略")
    st.info(
        "合规声明：系统遵循医疗数据最小化原则，敏感字段加密存储；"
        "高风险处方页面建议开启二次验证。"
    )
    st.checkbox("查看敏感处方时启用二次校验", value=True)
    st.checkbox("检测异常登录地提醒", value=True)
    st.checkbox("自动锁定空闲会话（15分钟）", value=True)


def main() -> None:
    inject_css()
    init_state()

    client, model = get_client_and_model()
    cases = load_cases()

    render_top_banner()
    page = sidebar_navigation()

    if not st.session_state.is_logged_in and page in ["临床辅助", "虚拟训练", "个人中心"]:
        st.warning("当前未登录，建议先在“登录与安全”完成认证。")
        if st.button("启用体验模式", type="primary"):
            st.session_state.is_logged_in = True
            st.session_state.doctor_name = "体验账号"
            st.session_state.doctor_title = "演示模式"
            st.rerun()
        st.stop()

    if page == "工作台总览":
        page_dashboard(cases)
    elif page == "临床辅助":
        page_clinical_assistant(client, model, cases)
    elif page == "虚拟训练":
        page_training(client, model, cases)
    elif page == "文献与政策库":
        page_policy(client, model)
    elif page == "个人中心":
        page_profile()
    elif page == "登录与安全":
        page_login()


if __name__ == "__main__":
    main()
