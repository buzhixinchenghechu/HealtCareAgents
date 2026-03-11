from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional

from rules.monitoring_rules import (
    COMPLETED_FOLLOWUP_STATUS,
    HIGH_RISK_LEVEL,
    is_tracking_alert,
)
from schemas.metrics import ProfileMetrics


def parse_time(value: Any) -> Optional[datetime]:
    text = str(value or "").strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt)
        except Exception:
            continue
    return None


def _is_same_week(target: datetime, now: datetime) -> bool:
    return target.isocalendar()[:2] == now.isocalendar()[:2]


def _extract_training_score(record: Dict[str, Any]) -> Optional[float]:
    for key in ("评分", "score", "Score"):
        if key in record:
            try:
                return float(record[key])
            except Exception:
                return None
    return None


def compute_today_alerts(patients: Iterable[Dict[str, Any]], now: Optional[datetime] = None) -> int:
    now = now or datetime.now()
    today = now.date()
    alerts = 0
    for patient in patients:
        for item in patient.get("tracking", []):
            tracking_time = parse_time(item.get("time"))
            if not tracking_time or tracking_time.date() != today:
                continue
            if is_tracking_alert(item.get("pain", 0), item.get("adverse", "")):
                alerts += 1
    return alerts


def compute_profile_metrics(
    patients: List[Dict[str, Any]],
    training_history: List[Dict[str, Any]],
    now: Optional[datetime] = None,
) -> ProfileMetrics:
    now = now or datetime.now()

    weekly_decisions = 0
    due_high_risk_followups = 0
    completed_high_risk_followups = 0

    for patient in patients:
        for evaluation in patient.get("evaluations", []):
            ts = parse_time(evaluation.get("time"))
            if ts and _is_same_week(ts, now):
                weekly_decisions += 1

        if patient.get("risk_level") != HIGH_RISK_LEVEL:
            continue
        for followup in patient.get("followups", []):
            due_time = parse_time(followup.get("time"))
            if not due_time or due_time > now:
                continue
            due_high_risk_followups += 1
            if followup.get("status") == COMPLETED_FOLLOWUP_STATUS:
                completed_high_risk_followups += 1

    if due_high_risk_followups > 0:
        high_risk_completion_rate = completed_high_risk_followups / due_high_risk_followups
    else:
        high_risk_completion_rate = 0.0

    weekly_scores: List[float] = []
    for item in training_history:
        ts = parse_time(item.get("时间"))
        if ts and _is_same_week(ts, now):
            score = _extract_training_score(item)
            if score is not None:
                weekly_scores.append(score)

    training_avg_score = sum(weekly_scores) / len(weekly_scores) if weekly_scores else 0.0
    today_alerts = compute_today_alerts(patients, now=now)

    return ProfileMetrics(
        weekly_decisions=weekly_decisions,
        high_risk_followup_completion_rate=high_risk_completion_rate,
        training_avg_score=training_avg_score,
        today_alerts=today_alerts,
        due_high_risk_followups=due_high_risk_followups,
        completed_high_risk_followups=completed_high_risk_followups,
    )

