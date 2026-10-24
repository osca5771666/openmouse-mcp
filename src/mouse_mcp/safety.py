from __future__ import annotations

import re
from dataclasses import dataclass

from pydantic import BaseModel, Field


HIGH_RISK_PATTERN = re.compile(
    r"删除|永久删除|抹除|清空|格式化|恢复出厂|批量提交|全部提交|提交全部|"
    r"关闭全部|全部关闭|关闭所有|批量删除|批量关闭|覆盖全部|注销账户|"
    r"\bdelete\b|\bpermanent(?:ly)? delete\b|\berase\b|\bformat\b|"
    r"\bremove all\b|\bclear all\b|\bsubmit all\b|\bbulk submit\b|"
    r"\bclose all\b|\bdelete all\b|\bwipe\b|\boverwrite all\b|"
    r"\bdeactivate account\b",
    re.IGNORECASE,
)


class ConfirmationInput(BaseModel):
    confirm: bool = Field(
        description="Explicit human approval for this specific high-risk mouse action."
    )


@dataclass(frozen=True)
class RiskAssessment:
    is_high_risk: bool
    evidence: list[str]


def classify_risk(*parts: str | None) -> RiskAssessment:
    evidence: list[str] = []
    for part in parts:
        if not part:
            continue
        match = HIGH_RISK_PATTERN.search(part)
        if match:
            snippet = part[max(0, match.start() - 18) : match.end() + 28].strip()
            evidence.append(snippet[:160])
    unique = list(dict.fromkeys(evidence))
    return RiskAssessment(bool(unique), unique)


def confirmation_message(action_name: str, risk: RiskAssessment, details: str = "") -> str:
    evidence = "; ".join(risk.evidence) or "semantic high-risk intent"
    suffix = f" Details: {details}" if details else ""
    return (
        f"Approve this high-risk mouse action ({action_name})? "
        f"Detected: {evidence}.{suffix} "
        "Choose deny unless you want this exact action performed now."
    )
