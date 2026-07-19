"""Results reporting — generate Markdown-formatted A/B comparison reports."""

from __future__ import annotations

from dataclasses import dataclass, field

from harness.eval.comparator import ABComparisonResult, MetricComparison


def _effect_label(d: float) -> str:
    """Label the magnitude of Cohen's d."""
    ad = abs(d)
    if ad < 0.2:
        return "negligible"
    if ad < 0.5:
        return "small"
    if ad < 0.8:
        return "medium"
    return "large"


def _winner_text(comparison: ABComparisonResult) -> str:
    """Produce text describing the overall winner."""
    winner = comparison.winner
    if winner == "treatment":
        return (
            f"**Winner: Treatment Group** — outperforms control on "
            f"{comparison.win_count} metrics, loses on {comparison.loss_count}, "
            f"ties on {comparison.tie_count}."
        )
    if winner == "control":
        return (
            f"**Winner: Control Group** — outperforms treatment on "
            f"{comparison.win_count} metrics, loses on {comparison.loss_count}, "
            f"ties on {comparison.tie_count}."
        )
    return (
        f"**No Clear Winner** — treatment wins {comparison.win_count}, "
        f"control wins {comparison.loss_count}, ties {comparison.tie_count}."
    )


def _format_metric_row(mc: MetricComparison) -> str:
    """Format a single metric row as a Markdown table row."""
    direction = "↑" if mc.mean_difference > 0 else "↓" if mc.mean_difference < 0 else "="
    winner = (
        "Treatment"
        if mc.winner == "treatment"
        else "Control" if mc.winner == "control"
        else "—"
    )
    return (
        f"| {mc.metric} "
        f"| {mc.control_mean:.4f} "
        f"| {mc.treatment_mean:.4f} "
        f"| {direction} {abs(mc.mean_difference):.4f} "
        f"| {mc.cohens_d:+.4f} ({_effect_label(mc.cohens_d)}) "
        f"| {mc.p_value:.4f} ({mc.confidence}) "
        f"| {winner} |"
    )


@dataclass
class ABReport:
    """Structured A/B comparison report."""

    comparison: ABComparisonResult
    summary: str = ""
    detailed: str = ""

    def to_markdown(self) -> str:
        """Render the full report as Markdown."""
        return self.summary + "\n\n" + self.detailed


def generate_report(
    comparison: ABComparisonResult,
    control_label: str = "Control",
    treatment_label: str = "Treatment",
) -> ABReport:
    """Generate a Markdown-formatted A/B comparison report.

    Args:
        comparison: The ABComparisonResult from ABComparator.compare().
        control_label: Human-readable label for the control group.
        treatment_label: Human-readable label for the treatment group.

    Returns:
        ABReport with summary and detailed sections.
    """
    n_control = len(comparison.control.runs)
    n_treatment = len(comparison.treatment.runs)

    # --- Summary section ---
    summary = "\n".join(
        [
            "# A/B Experiment Report",
            "",
            f"**Control ({control_label}):** {comparison.control.config.to_dict()}",
            f"**Treatment ({treatment_label}):** {comparison.treatment.config.to_dict()}",
            f"**Runs per group:** {n_control} (control) / {n_treatment} (treatment)",
            "",
            _winner_text(comparison),
        ]
    )

    # --- Detailed section ---
    header = (
        "| Metric | Control Mean | Treatment Mean | Δ Diff | Cohen's d | p-value | Winner |\n"
        "|--------|-------------|----------------|--------|-----------|---------|--------|"
    )
    rows = "\n".join(_format_metric_row(mc) for mc in comparison.metrics.values())

    detailed = "\n".join(
        [
            "## Detailed Comparison",
            "",
            header,
            rows,
            "",
            "**Effect size guide:** |d| < 0.2 = negligible, 0.2–0.5 = small, "
            "0.5–0.8 = medium, > 0.8 = large",
            "",
            "**Confidence:** p < 0.01 = high, p < 0.05 = medium, p < 0.10 = low, "
            "p ≥ 0.10 = none",
            "",
            f"**Win/Loss/Tie:** {comparison.win_count} / "
            f"{comparison.loss_count} / {comparison.tie_count}",
        ]
    )

    return ABReport(comparison=comparison, summary=summary, detailed=detailed)
