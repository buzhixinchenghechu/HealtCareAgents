# -*- coding: utf-8 -*-

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

import streamlit as st

from pages.clinical_page import page_clinical_assistant
from pages.dashboard_page import page_dashboard
from pages.doctor_page import page_doctor_dashboard
from pages.layout_page import inject_css, render_footer_note, render_header, sidebar_navigation
from pages.login_page import page_login
from pages.policy_page import page_policy
from pages.profile_center_page import page_profile
from pages.training_page import page_training
from repositories.content_repository import load_cases, load_static_content
from repositories.session_repository import initialize_persistent_state
from services.llm_service import get_client_and_model
from services.state_service import init_state


st.set_page_config(
    page_title="HealthCareAgents",
    page_icon=":hospital:",
    layout="wide",
    initial_sidebar_state="expanded",
)


PRIMARY = "#165DFF"
SUCCESS = "#00B42A"
WARNING = "#FF7D00"
DANGER = "#F53F3F"
SIDEBAR_BG = "#EAF3FF"


BASE_DIR = Path(__file__).resolve().parent
STATIC_CONTENT_PATH = BASE_DIR / "data" / "static_content.json"


REQUIRED_UI_OPTION_KEYS = {
    "sidebar_pages",
    "protected_pages",
    "clinical_gender",
    "clinical_diag_template",
    "clinical_pain_type",
    "clinical_dept",
    "clinical_allergy",
    "clinical_current_opioid",
    "clinical_current_freq",
    "clinical_co_meds",
    "clinical_comorb",
    "clinical_adverse_hist",
    "clinical_plan_drug",
    "clinical_personal_use",
    "clinical_family_use",
    "clinical_psych",
    "clinical_follow_hours",
    "training_difficulty",
    "training_department",
    "training_quiz_binary",
    "training_policy_country",
    "policy_category",
    "policy_tag",
    "policy_country",
    "policy_province",
    "policy_ort_level",
    "doctor_add_department",
    "doctor_add_risk_level",
    "doctor_filter_risk",
    "doctor_filter_status",
    "doctor_eval_personal_use",
    "doctor_eval_family_use",
    "doctor_eval_psych",
    "doctor_tracking_adverse",
    "register_department",
}


def build_ui_options(raw_options: Any) -> Dict[str, List[Any]]:
    raw = raw_options if isinstance(raw_options, dict) else {}
    cleaned: Dict[str, List[Any]] = {}
    for key, value in raw.items():
        if isinstance(key, str) and isinstance(value, list) and value:
            cleaned[key] = value

    missing = sorted(k for k in REQUIRED_UI_OPTION_KEYS if k not in cleaned)
    if missing:
        missing_text = ", ".join(missing)
        raise ValueError(f"ui_options ?????: {missing_text}")
    return cleaned


_STATIC_CONTENT = load_static_content(STATIC_CONTENT_PATH)
NEWS_FEED = _STATIC_CONTENT["news_feed"]
POLICY_LIBRARY = _STATIC_CONTENT["policy_library"]
COURSE_MATRIX = _STATIC_CONTENT["course_matrix"]
OPIOID_MME_FACTORS = _STATIC_CONTENT["opioid_mme_factors"]
UI_OPTIONS = build_ui_options(_STATIC_CONTENT.get("ui_options", {}))


def option_list(name: str) -> List[Any]:
    options = UI_OPTIONS.get(name)
    if not options:
        raise KeyError(f"??? UI ??: {name}")
    return options


def main() -> None:
    inject_css(PRIMARY, SUCCESS, WARNING, DANGER, SIDEBAR_BG)
    init_state(st.session_state, option_list)
    initialize_persistent_state(st.session_state)

    client, model = get_client_and_model()
    cases = load_cases(BASE_DIR)

    render_header()
    page = sidebar_navigation(option_list)

    protected = set(option_list("protected_pages"))
    if not st.session_state.is_logged_in and page in protected:
        st.warning("??????????????????????????????")
        if st.button("??????", type="primary"):
            st.session_state.is_logged_in = True
            st.session_state.doctor_name = "????"
            st.session_state.doctor_title = "????"
            st.rerun()
        render_footer_note()
        st.stop()

    pages = option_list("sidebar_pages")
    if st.session_state.current_page not in pages:
        st.session_state.current_page = pages[0]
        page = pages[0]
    if page == pages[0]:
        page_dashboard(cases, option_list, NEWS_FEED, POLICY_LIBRARY)
    elif page == pages[1]:
        page_clinical_assistant(client, model, cases, option_list, OPIOID_MME_FACTORS, PRIMARY)
    elif page == pages[2]:
        page_training(client, model, cases, option_list, COURSE_MATRIX)
    elif page == pages[3]:
        page_policy(client, model, option_list, POLICY_LIBRARY)
    elif page == pages[4]:
        page_doctor_dashboard(option_list, PRIMARY, SUCCESS, WARNING, DANGER)
    elif page == pages[5]:
        page_profile()
    else:
        page_login(option_list)

    render_footer_note()


if __name__ == "__main__":
    main()
