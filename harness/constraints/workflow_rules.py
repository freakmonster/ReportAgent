"""
Workflow rules — hard constraints that cannot be violated.

Rules:
- retry_count > 3 → force human review
- Reviewer must approve before publishing
- Reports must include risk warning (validated in report_service)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class WorkflowRuleCheck:
    """Result of checking a workflow rule."""

    passed: bool
    rule_name: str
    detail: str = ""
    action: str = ""  # e.g. "force_human_review", "reject"


# ── Rule definitions ────────────────────────────────────────────────

MAX_RETRY_COUNT: int = 3


def check_retry_limit(retry_count: int) -> WorkflowRuleCheck:
    """Check if retry count exceeds the maximum allowed.

    If retry_count > 3, the workflow MUST escalate to human review.

    Args:
        retry_count: Current number of retries.

    Returns:
        WorkflowRuleCheck with passed=False if retry limit exceeded.
    """
    if retry_count > MAX_RETRY_COUNT:
        return WorkflowRuleCheck(
            passed=False,
            rule_name="retry_limit",
            detail=f"Retry count {retry_count} > {MAX_RETRY_COUNT}, forcing human review",
            action="force_human_review",
        )
    return WorkflowRuleCheck(passed=True, rule_name="retry_limit")


def check_reviewer_approved(reviewer_decision: str) -> WorkflowRuleCheck:
    """Check if the reviewer has approved the report.

    Args:
        reviewer_decision: One of 'approved', 'needs_human', 'rejected'.

    Returns:
        WorkflowRuleCheck — only 'approved' passes.
    """
    if reviewer_decision == "approved":
        return WorkflowRuleCheck(passed=True, rule_name="reviewer_approval")
    if reviewer_decision == "rejected":
        return WorkflowRuleCheck(
            passed=False,
            rule_name="reviewer_approval",
            detail="Reviewer rejected the report",
            action="reject",
        )
    return WorkflowRuleCheck(
        passed=False,
        rule_name="reviewer_approval",
        detail=f"Reviewer decision '{reviewer_decision}' requires human intervention",
        action="force_human_review",
    )


def check_risk_section_present(chapters: list[str]) -> WorkflowRuleCheck:
    """Check that the report includes a mandatory risk warning section.

    V2.0 mandatory compliance rule.

    Args:
        chapters: List of chapter titles.

    Returns:
        WorkflowRuleCheck — passed only if a risk keyword is found.
    """
    risk_keywords = ["风险提示", "风险警示", "风险因素", "风险分析", "风险"]
    text = " ".join(chapters).lower()
    has_risk = any(kw in text for kw in risk_keywords)

    if not has_risk:
        return WorkflowRuleCheck(
            passed=False,
            rule_name="risk_section",
            detail="Report is missing the mandatory 风险提示 section",
            action="reject",
        )
    return WorkflowRuleCheck(passed=True, rule_name="risk_section")
