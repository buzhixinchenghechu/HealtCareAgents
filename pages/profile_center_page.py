
from __future__ import annotations

from datetime import datetime

import streamlit as st

from repositories.session_repository import get_audit_events, get_patients, get_training_history
from schemas.metrics import ProfileMetrics
from services.metrics_service import compute_profile_metrics


def render_profile_metrics(metrics: ProfileMetrics) -> None:
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("本周辅助决策", str(metrics.weekly_decisions))

    completion_rate_text = f"{metrics.high_risk_followup_completion_rate * 100:.1f}%"
    c2.metric("高风险复评完成率", completion_rate_text)
    c2.caption(f"已完成 {metrics.completed_high_risk_followups} / 应完成 {metrics.due_high_risk_followups}")

    c3.metric("训练场均得分", f"{metrics.training_avg_score:.1f}")
    c4.metric("今日异常预警", str(metrics.today_alerts))


def render_recent_audit(events: list[dict]) -> None:
    st.markdown("#### 最近操作")
    if not events:
        st.info("暂无操作记录。")
        return
    st.dataframe(events[::-1][:20], use_container_width=True, hide_index=True)

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
