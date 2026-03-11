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
