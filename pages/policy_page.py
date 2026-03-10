
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

import streamlit as st
from openai import OpenAI

from repositories.session_repository import append_audit_event
from rules.monitoring_rules import HIGH_RISK_LEVEL
from services.clinical_service import tokenize
from services.llm_service import ask_llm

def page_policy(
    client: Optional[OpenAI],
    model: str,
    option_list: Callable[[str], List[Any]],
    policy_library: List[Dict[str, Any]],
) -> None:
    st.markdown("### 文献与政策库")
    st.caption("统一从 `data/static_content.json` 读取政策内容、标签和筛选项。")

    f1, f2, f3, f4, f5 = st.columns(5)
    country = f1.selectbox("国家/地区", option_list("policy_country"), key="policy_country")
    category = f2.selectbox("分类", option_list("policy_category"), key="policy_category")
    tag = f3.selectbox("标签", option_list("policy_tag"), key="policy_tag")
    province = f4.selectbox("省份", option_list("policy_province"), key="policy_province")
    ort_level = f5.selectbox("风险级别", option_list("policy_ort_level"), key="policy_ort_level")

    filtered = []
    for item in policy_library:
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
    candidates = filtered or policy_library
    if not candidates:
        st.info("当前暂无可用于问答的政策数据。")
        return
    policy_ids = [f"{p.get('id', '')} | {p.get('title', '')}" for p in candidates]
    selected_policy = st.selectbox("选择政策", policy_ids, key="policy_qa_select")
    question = st.text_input("输入问题", key="policy_question", placeholder="例如：高风险患者是否可一次性开具长疗程？")
    if st.button("生成解读", key="policy_qa_btn", type="primary"):
        pid = selected_policy.split("|")[0].strip()
        policy = next((p for p in policy_library if p.get("id") == pid), None)
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
