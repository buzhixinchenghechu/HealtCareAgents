from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Tuple

from rules.monitoring_rules import (
    COMPLETED_FOLLOWUP_STATUS,
    IN_TREATMENT_MED_STATUS,
    OVERDUE_FOLLOWUP_STATUS,
    PENDING_FOLLOWUP_STATUS,
    PENDING_MED_STATUS,
)


def mark_followup_completed(
    patients: List[Dict[str, Any]],
    patient_id: str,
    followup_time: str,
    completion_note: str,
    now: datetime | None = None,
) -> Tuple[bool, str]:
    now = now or datetime.now()
    patient = next((p for p in patients if p.get("id") == patient_id), None)
    if not patient:
        return False, "未找到患者"

    followups = patient.get("followups", [])
    for item in followups:
        status = str(item.get("status") or PENDING_FOLLOWUP_STATUS)
        if item.get("time") != followup_time:
            continue
        if status in {COMPLETED_FOLLOWUP_STATUS}:
            return False, "该随访已完成"
        if status not in {PENDING_FOLLOWUP_STATUS, OVERDUE_FOLLOWUP_STATUS}:
            return False, "当前状态不可完成"

        item["status"] = COMPLETED_FOLLOWUP_STATUS
        item["completed_at"] = now.strftime("%Y-%m-%d %H:%M")
        note = str(item.get("note", "")).strip()
        completion = str(completion_note or "").strip()
        if completion:
            item["note"] = f"{note} | 完成备注: {completion}" if note else f"完成备注: {completion}"

        has_pending = any(
            str(f.get("status") or PENDING_FOLLOWUP_STATUS) in {PENDING_FOLLOWUP_STATUS, OVERDUE_FOLLOWUP_STATUS}
            for f in followups
        )
        patient["med_status"] = PENDING_MED_STATUS if has_pending else IN_TREATMENT_MED_STATUS
        return True, "随访已标记完成"

    return False, "未找到对应随访记录"

