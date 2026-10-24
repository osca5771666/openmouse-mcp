from __future__ import annotations

import pytest

from mouse_mcp.safety import classify_risk


@pytest.mark.parametrize(
    "text",
    [
        "删除全部记录",
        "永久删除这个文件",
        "批量提交所有申请",
        "close all windows",
        "Delete all rows",
        "bulk submit the form",
        "overwrite all files",
    ],
)
def test_high_risk_intent_is_detected(text: str) -> None:
    assessment = classify_risk(text)

    assert assessment.is_high_risk
    assert assessment.evidence


@pytest.mark.parametrize(
    "text",
    [
        "open the Save button",
        "scroll down to read the next paragraph",
        "select the sentence in the note",
        "点击保存",
        "拖动滑块到 50%",
    ],
)
def test_normal_intent_does_not_require_confirmation(text: str) -> None:
    assessment = classify_risk(text)

    assert not assessment.is_high_risk
    assert assessment.evidence == []


def test_risk_evidence_is_deduplicated_across_fields() -> None:
    assessment = classify_risk("删除全部", "delete all", "删除全部")

    assert assessment.is_high_risk
    assert len(assessment.evidence) == len(set(assessment.evidence))
