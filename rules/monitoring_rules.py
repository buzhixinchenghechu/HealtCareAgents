from __future__ import annotations

from datetime import datetime

PENDING_FOLLOWUP_STATUS = "待完成"
COMPLETED_FOLLOWUP_STATUS = "已完成"
OVERDUE_FOLLOWUP_STATUS = "逾期"

HIGH_RISK_LEVEL = "高风险"
PENDING_MED_STATUS = "待随访"
IN_TREATMENT_MED_STATUS = "用药中"

ALERT_ADVERSE_KEYWORDS = ("呼吸抑制", "意识模糊")


def is_tracking_alert(pain: float, adverse_text: str) -> bool:
    try:
        pain_value = float(pain)
    except Exception:
        pain_value = 0.0
    if pain_value >= 8:
        return True

    adverse = str(adverse_text or "")
    return any(keyword in adverse for keyword in ALERT_ADVERSE_KEYWORDS)


def display_followup_status(raw_status: str, due_time: datetime | None, now: datetime) -> str:
    status = str(raw_status or PENDING_FOLLOWUP_STATUS)
    if status == PENDING_FOLLOWUP_STATUS and due_time and due_time < now:
        return OVERDUE_FOLLOWUP_STATUS
    return status

