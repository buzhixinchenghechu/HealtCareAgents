
from __future__ import annotations

import random
import uuid
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

import streamlit as st
from openai import OpenAI

from repositories.session_repository import (
    append_audit_event,
    save_last_report,
    save_psych_label_counts,
    save_training_history,
)
from services.llm_service import ask_llm

def page_training(
    client: Optional[OpenAI],
    model: str,
    cases: List[Dict],
    option_list: Callable[[str], List[Any]],
    course_matrix: List[Dict[str, Any]],
) -> None:
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
            save_psych_label_counts(st.session_state)
            record = {
                "时间": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "科室": case["department"],
                "难度": case["difficulty"],
                "评分": score,
                "心理画像": psych_label,
                "案例": case["id"],
            }
            st.session_state.training_history.append(record)
            save_training_history(st.session_state)
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
            save_last_report(st.session_state)
            st.success(f"训练提交成功，得分 {score} 分。")
            st.write(ai_feedback)

    st.markdown("#### 课程矩阵推荐")
    st.dataframe(course_matrix, use_container_width=True, hide_index=True)
    st.markdown("#### 训练心理画像分布")
    st.bar_chart(st.session_state.psych_label_counts)
