
from __future__ import annotations

from typing import Any, Callable, Dict, List

import streamlit as st

from repositories.session_repository import get_patients, get_training_history
from services.metrics_service import compute_profile_metrics

def page_dashboard(cases: List[Dict], option_list: Callable[[str], List[Any]], news_feed: List[Dict[str, Any]], policy_library: List[Dict[str, Any]]) -> None:
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
        for item in news_feed:
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
        st.success(f"政策引擎已加载 {len(policy_library)} 条结构化政策文档。")
        st.markdown("#### 快速指南")
        st.markdown("1. 先评估风险，再制定剂量。")
        st.markdown("2. 高风险处方必须限量并记录知情同意。")
        st.markdown("3. 复评节点必须写入病历和随访计划。")
