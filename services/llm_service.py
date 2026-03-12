from __future__ import annotations

import os
from typing import Optional, Tuple

import streamlit as st
from openai import OpenAI


def safe_secret(name: str) -> str:
    try:
        return str(st.secrets.get(name, "")).strip()
    except Exception:
        return ""


@st.cache_resource
def get_client_and_model() -> Tuple[Optional[OpenAI], str]:
    # Primary: OC Gateway (Claude + medical knowledge base skill)
    oc_token = safe_secret("OC_GATEWAY_TOKEN") or os.environ.get("OC_GATEWAY_TOKEN", "").strip()
    oc_url = safe_secret("OC_GATEWAY_URL") or os.environ.get("OC_GATEWAY_URL", "http://127.0.0.1:18789/v1").strip()
    if oc_token:
        return OpenAI(api_key=oc_token, base_url=oc_url), "minimax"
    # Fallback: DashScope/Qwen
    dashscope_key = safe_secret("DASHSCOPE_API_KEY") or os.environ.get("DASHSCOPE_API_KEY", "").strip()
    if dashscope_key:
        return (
            OpenAI(api_key=dashscope_key, base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"),
            "qwen-plus",
        )
    openai_key = safe_secret("OPENAI_API_KEY") or os.environ.get("OPENAI_API_KEY", "").strip()
    if openai_key:
        return OpenAI(api_key=openai_key), "gpt-4o-mini"
    return None, ""


@st.cache_resource
def get_baichuan_client() -> Optional[OpenAI]:
    key = safe_secret("BAICHUAN_API_KEY") or os.environ.get("BAICHUAN_API_KEY", "").strip()
    if key:
        return OpenAI(api_key=key, base_url="https://api.baichuan-ai.com/v1")
    return None


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


def ask_llm_debate(
    oc_client: Optional[OpenAI],
    oc_model: str,
    baichuan_client: Optional[OpenAI],
    system_prompt: str,
    user_prompt: str,
) -> Tuple[str, str, str]:
    """
    OC（病例库+专家共识） 与 百川医疗大模型 互相审阅，达成共识。
    返回 (oc_answer, baichuan_review, consensus)
    若百川不可用，直接返回 OC 的答案。
    """
    # 第一步：OC 基于知识库给出初步答案
    oc_answer = ask_llm(oc_client, oc_model, system_prompt, user_prompt)
    if not oc_answer or not baichuan_client:
        return oc_answer, "", oc_answer

    # 第二步：百川医疗大模型审阅 OC 的答案，补充或纠正
    baichuan_prompt = (
        f"以下是另一个AI系统基于临床病例数据库给出的回答，请你作为医学专家审阅：\n\n"
        f"【原始问题】\n{user_prompt}\n\n"
        f"【病例库AI的回答】\n{oc_answer}\n\n"
        f"请指出回答中需要补充或纠正的内容（如有），并给出你的专业意见。如无异议请说明。"
    )
    try:
        rsp = baichuan_client.chat.completions.create(
            model="Baichuan4-Turbo",
            messages=[
                {"role": "system", "content": "你是百川医疗大模型，具备丰富的临床医学知识，请对病例库AI的回答进行专业审阅。"},
                {"role": "user", "content": baichuan_prompt},
            ],
            temperature=0.2,
            max_tokens=800,
        )
        baichuan_review = (rsp.choices[0].message.content or "").strip()
    except Exception as exc:
        return oc_answer, "", oc_answer

    # 第三步：OC 综合两方意见，生成最终共识答案
    consensus_prompt = (
        f"【原始问题】\n{user_prompt}\n\n"
        f"【病例库初步答案】\n{oc_answer}\n\n"
        f"【百川医疗专家审阅意见】\n{baichuan_review}\n\n"
        f"请综合以上两个来源，整合为一个完整、准确、可直接用于临床参考的最终答案。"
    )
    consensus = ask_llm(
        oc_client, oc_model,
        "你是临床决策辅助系统，请综合病例数据库与医学专家意见，给出最终临床建议。",
        consensus_prompt,
    )
    return oc_answer, baichuan_review, consensus or oc_answer
