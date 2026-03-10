
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

import altair as alt
import streamlit as st
from openai import OpenAI

from repositories.session_repository import append_audit_event, save_last_report
from services.clinical_service import (
    calc_mme_day,
    calc_ort,
    local_plan,
    retrieve_similar_cases,
    risk_radar_values,
    risk_tag_class,
)
from services.llm_service import ask_llm

def render_radar_chart(radar: Dict[str, List[int]], primary: str) -> None:
    categories = list(radar.keys())
    points = [{"category": k, "value": (v[0] if isinstance(v, list) else v)} for k, v in radar.items()]
    chart = (
        alt.Chart(alt.Data(values=points))
        .mark_line(point=True, interpolate="linear-closed", strokeWidth=2)
        .encode(
            theta=alt.Theta("category:N", sort=categories),
            radius=alt.Radius("value:Q", scale=alt.Scale(domain=[0, 10])),
            color=alt.value(primary),
            tooltip=["category:N", "value:Q"],
        )
        .properties(width=360, height=320)
    )
    st.altair_chart(chart, use_container_width=True)

def page_clinical_assistant(
    client: Optional[OpenAI],
    model: str,
    cases: List[Dict],
    option_list: Callable[[str], List[Any]],
    opioid_mme_factors: Dict[str, float],
    primary: str,
) -> None:
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
        mme_day, mme_note = calc_mme_day(plan_drug, float(plan_dose), int(plan_freq_per_day), opioid_mme_factors)
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
                render_radar_chart(result["radar"], primary)
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
                    save_last_report(st.session_state)
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
