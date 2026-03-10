
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
