
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional, Tuple

import altair as alt
import streamlit as st

from repositories.session_repository import append_audit_event, save_patients
from rules.monitoring_rules import (
    COMPLETED_FOLLOWUP_STATUS,
    PENDING_FOLLOWUP_STATUS,
    PENDING_MED_STATUS,
    display_followup_status,
)
from services.clinical_service import calc_ort
from services.followup_service import mark_followup_completed

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

def render_tracking_curve(patient: Dict, primary: str, danger: str) -> None:
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
                color=alt.Color("metric:N", scale=alt.Scale(domain=["疼痛评分", "依从性"], range=[danger, primary])),
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

def render_followup_timeline(patient: Dict, success: str, warning: str, danger: str) -> None:
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
            color = success
            icon = "✅"
        elif status == "逾期":
            color = danger
            icon = "❌"
        else:
            color = warning
            icon = "⏳"
        st.markdown(
            f"<div style='border-left:3px solid {color};padding-left:10px;margin:8px 0;'>"
            f"<b>{icon} {item.get('time','')}</b> | 状态：<span style='color:{color};font-weight:700'>{status}</span><br/>"
            f"<span style='color:#5b6b7e'>{item.get('note','')}</span></div>",
            unsafe_allow_html=True,
        )

def page_doctor_dashboard(
    option_list: Callable[[str], List[Any]],
    primary: str,
    success: str,
    warning: str,
    danger: str,
) -> None:
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
                save_patients(st.session_state)
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
                save_patients(st.session_state)
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
                    save_patients(st.session_state)
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
            save_patients(st.session_state)
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

        st.markdown("##### 编辑病例基础信息")
        dept_options = option_list("doctor_add_department")
        risk_options = option_list("doctor_add_risk_level")
        current_dept = patient.get("department", "")
        current_risk = patient.get("risk_level", "")
        dept_index = dept_options.index(current_dept) if current_dept in dept_options else 0
        risk_index = risk_options.index(current_risk) if current_risk in risk_options else 0
        with st.form(f"patient_edit_form_{pid}"):
            e1, e2 = st.columns(2)
            with e1:
                edit_name = st.text_input("姓名", value=patient.get("name", ""))
                edit_department = st.selectbox("科室", dept_options, index=dept_index)
            with e2:
                edit_diagnosis = st.text_input("诊断", value=patient.get("diagnosis", ""))
                edit_risk = st.selectbox("风险等级", risk_options, index=risk_index)
            save_basic = st.form_submit_button("保存基础信息", type="primary")

        if save_basic:
            if not edit_name.strip() or not edit_diagnosis.strip():
                st.error("姓名和诊断不能为空。")
            else:
                before = {
                    "name": patient.get("name", ""),
                    "department": patient.get("department", ""),
                    "diagnosis": patient.get("diagnosis", ""),
                    "risk_level": patient.get("risk_level", ""),
                }
                patient["name"] = edit_name.strip()
                patient["department"] = edit_department
                patient["diagnosis"] = edit_diagnosis.strip()
                patient["risk_level"] = edit_risk
                save_patients(st.session_state)
                append_audit_event(
                    st.session_state,
                    "patient_basic_updated",
                    {
                        "patient_id": pid,
                        "before": before,
                        "after": {
                            "name": patient.get("name", ""),
                            "department": patient.get("department", ""),
                            "diagnosis": patient.get("diagnosis", ""),
                            "risk_level": patient.get("risk_level", ""),
                        },
                    },
                )
                st.success("基础信息已更新。")
                st.rerun()

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
                save_patients(st.session_state)
                append_audit_event(
                    st.session_state,
                    "tracking_added",
                    {"patient_id": pid, "pain": tracking_pain, "adherence": tracking_adherence, "adverse": tracking_adverse},
                )
                st.success("追踪记录已新增。")
                st.rerun()

        with c2:
            st.markdown("##### 随访时间轴")
            render_followup_timeline(patient, success, warning, danger)

        st.markdown("##### 用药后追踪曲线")
        render_tracking_curve(patient, primary, danger)
