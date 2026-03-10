
from __future__ import annotations

from typing import Any, Callable, List

import streamlit as st


def page_login(option_list: Callable[[str], List[Any]]) -> None:
    st.markdown("### 登录与安全")
    st.caption("支持账号密码/验证码双登录，附医疗数据保密声明。")
    tab1, tab2, tab3 = st.tabs(["账号登录", "验证码登录", "注册认证"])

    with tab1:
        with st.form("login_pwd"):
            username = st.text_input("用户名")
            pwd = st.text_input("密码", type="password")
            agree = st.checkbox("我已阅读并同意《医疗数据保密条款》", value=True)
            submit = st.form_submit_button("登录", type="primary")
        if submit:
            if username.strip() and pwd.strip() and agree:
                st.session_state.is_logged_in = True
                st.session_state.doctor_name = username.strip()
                st.session_state.doctor_title = "临床医生"
                st.success("登录成功。")
            else:
                st.error("请完成登录信息并勾选保密条款。")

    with tab2:
        with st.form("login_code"):
            mobile = st.text_input("手机号")
            code = st.text_input("验证码")
            submit2 = st.form_submit_button("登录", type="primary")
        if submit2:
            if mobile.strip() and code.strip():
                st.session_state.is_logged_in = True
                st.session_state.doctor_name = f"用户{mobile[-4:]}"
                st.session_state.doctor_title = "临床医生"
                st.success("登录成功。")
            else:
                st.error("请输入手机号和验证码。")

    with tab3:
        with st.form("register_form"):
            c1, c2 = st.columns(2)
            with c1:
                license_id = st.text_input("执业医师证号")
                real_name = st.text_input("姓名")
                dept = st.selectbox("科室", option_list("register_department"))
            with c2:
                hospital = st.text_input("医院")
                mobile = st.text_input("手机号", key="reg_mobile")
                verify = st.text_input("实名认证码")
            reg = st.form_submit_button("提交注册", type="primary")
        if reg:
            if all([license_id.strip(), real_name.strip(), hospital.strip(), mobile.strip(), verify.strip()]):
                _ = dept  # 保留字段
                st.success("注册信息已提交，等待实名认证审核。")
            else:
                st.error("请完整填写注册信息。")

    st.markdown("---")
    st.info("合规声明：系统遵循《个人信息保护法》，敏感字段脱敏展示，操作日志可审计。")
