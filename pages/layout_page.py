
from __future__ import annotations

from datetime import datetime
from typing import Any, Callable, List

import streamlit as st

def inject_css(primary: str, success: str, warning: str, danger: str, sidebar_bg: str) -> None:
    st.markdown(
        f"""
        <style>
        :root {{
            --brand: {primary};
            --ok: {success};
            --warn: {warning};
            --danger: {danger};
            --sidebar-bg: {sidebar_bg};
            --text: #1f2d3d;
            --muted: #617085;
        }}
        .stApp {{
            background:
                radial-gradient(900px 320px at -10% -10%, #d9e8ff 0%, rgba(217, 232, 255, 0) 60%),
                radial-gradient(900px 320px at 120% -10%, #dff6ff 0%, rgba(223, 246, 255, 0) 60%),
                #f5f8fc;
        }}
        [data-testid="stSidebar"] {{
            background: var(--sidebar-bg);
            color: #1f3556;
        }}
        [data-testid="stSidebar"] .stRadio label,
        [data-testid="stSidebar"] .stMarkdown,
        [data-testid="stSidebar"] .stCaption,
        [data-testid="stSidebar"] .stText {{
            color: #1f3556 !important;
        }}
        .top-hero {{
            background: linear-gradient(120deg, #1242c4 0%, #165dff 52%, #24b3ee 100%);
            border-radius: 16px;
            border: 1px solid rgba(255,255,255,0.25);
            color: #fff;
            padding: 20px 22px;
            box-shadow: 0 12px 24px rgba(22, 93, 255, 0.20);
        }}
        .top-hero h1 {{
            margin: 0 0 6px 0;
            font-size: 28px;
            font-weight: 800;
        }}
        .top-hero p {{
            margin: 0;
            font-size: 14px;
            opacity: 0.95;
        }}
        .kpi-card {{
            background: #fff;
            border: 1px solid #e7edf6;
            border-radius: 14px;
            padding: 14px;
            box-shadow: 0 6px 14px rgba(20, 40, 70, 0.04);
        }}
        .kpi-title {{ font-size: 12px; color: var(--muted); }}
        .kpi-value {{ font-size: 28px; color: var(--text); font-weight: 700; line-height: 1.1; margin-top: 4px; }}
        .kpi-sub {{ font-size: 12px; color: var(--brand); margin-top: 4px; }}
        .warn-bar {{
            background: #fff2f2;
            color: #9c1d1d;
            border: 1px solid #ffd1d1;
            border-radius: 10px;
            padding: 8px 10px;
            font-size: 13px;
            margin-bottom: 8px;
            font-weight: 600;
        }}
        .ok-bar {{
            background: #effcf3;
            color: #0f6a2a;
            border: 1px solid #c9efda;
            border-radius: 10px;
            padding: 8px 10px;
            font-size: 13px;
            margin-bottom: 8px;
            font-weight: 600;
        }}
        .risk-tag {{
            display: inline-block;
            padding: 2px 8px;
            font-size: 12px;
            border-radius: 999px;
            margin-right: 6px;
        }}
        .risk-low {{ background: #e8f8ee; color: #116f35; }}
        .risk-mid {{ background: #fff5e5; color: #a35c00; }}
        .risk-high {{ background: #ffecef; color: #a61f2f; }}
        .policy-card {{
            background: #fff;
            border: 1px solid #e8edf7;
            border-radius: 12px;
            padding: 12px;
            margin-bottom: 10px;
        }}
        .policy-title {{ font-size: 15px; font-weight: 700; color: #10243d; margin-bottom: 4px; }}
        .source-note {{
            position: fixed;
            left: 50%;
            transform: translateX(-50%);
            bottom: 8px;
            background: rgba(255,255,255,0.85);
            border: 1px solid #dbe7ff;
            color: #5f6d82;
            border-radius: 999px;
            font-size: 11px;
            padding: 4px 12px;
            z-index: 999;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )

def render_header() -> None:
    date_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    st.markdown(
        f"""
        <div class="top-hero">
            <h1>智医助手 · 阿片类药物辅助决策系统</h1>
            <p>临床辅助 + 虚拟训练 + 政策解读 + 管理后台闭环 | 当前时间：{date_str}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

def sidebar_navigation(option_list: Callable[[str], List[Any]]) -> str:
    pages = option_list("sidebar_pages")
    with st.sidebar:
        st.markdown("## 智医助手")
        st.caption("Opioid Decision Support v2026")
        current_page = st.session_state.get("current_page")
        default_index = pages.index(current_page) if current_page in pages else 0
        page = st.radio("导航", pages, index=default_index)
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
            st.caption("进入“登录与安全”可完成认证")
        st.markdown("---")
        st.caption("数据保密：患者敏感信息默认脱敏显示，所有日志可追溯不可删除。")
    return page

def render_footer_note() -> None:
    st.markdown("---")
    st.caption("数据来源：国家卫健委/医保局/药监局及核心医学期刊 | 本系统仅作临床辅助参考")
    st.markdown(
        """
        <div class="source-note">
            医疗数据保密声明：遵循《个人信息保护法》，敏感字段脱敏展示，访问全程审计
        </div>
        """,
        unsafe_allow_html=True,
    )
