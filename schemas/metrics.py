from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ProfileMetrics:
    weekly_decisions: int
    high_risk_followup_completion_rate: float
    training_avg_score: float
    today_alerts: int
    due_high_risk_followups: int
    completed_high_risk_followups: int

