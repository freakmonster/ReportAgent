"""Statistical comparison of two experiment groups (A/B testing)."""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import ClassVar, Sequence

from harness.eval.experiment import ExperimentResult

# Metric names available for comparison (content quality + latency)
_METRIC_NAMES: list[str] = [
    "completeness",
    "accuracy",
    "citation_quality",
    "logical_flow",
    "overall",
    "latency_s",
]

# Number of bootstrap resamples for significance testing
_DEFAULT_BOOTSTRAP_SAMPLES: int = 10_000


def _extract_values(runs: ExperimentResult, metric: str) -> list[float]:
    """Extract metric values from all runs in a group."""
    if metric == "latency_s":
        return [r.latency_s for r in runs.runs]
    return [getattr(r.scores, metric, 0.0) for r in runs.runs]


def _mean(values: Sequence[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)


def _std(values: Sequence[float], ddof: int = 1) -> float:
    """Sample standard deviation."""
    n = len(values)
    if n < 2:
        return 0.0
    m = _mean(values)
    variance = sum((v - m) ** 2 for v in values) / (n - ddof)
    return math.sqrt(variance)


def _cohens_d(a: Sequence[float], b: Sequence[float]) -> float:
    """Cohen's d effect size between two independent groups.

    Returns:
        Positive value means group b outperforms group a.
    """
    n1, n2 = len(a), len(b)
    if n1 < 2 or n2 < 2:
        return 0.0

    mean_a, mean_b = _mean(a), _mean(b)
    std_a, std_b = _std(a), _std(b)

    # Pooled standard deviation
    pooled_var = ((n1 - 1) * std_a ** 2 + (n2 - 1) * std_b ** 2) / (n1 + n2 - 2)
    pooled_std = math.sqrt(pooled_var)
    if pooled_std == 0.0:
        return 0.0
    return (mean_b - mean_a) / pooled_std


def _bootstrap_p_value(
    a: Sequence[float],
    b: Sequence[float],
    n_resamples: int = _DEFAULT_BOOTSTRAP_SAMPLES,
    seed: int = 42,
) -> float:
    """Two-sided bootstrap p-value for difference in means.

    H0: mean(a) == mean(b)  (no difference)
    Ha: mean(a) != mean(b)

    Uses bias-corrected bootstrap resampling with stratification by group.
    """
    n_a, n_b = len(a), len(b)
    if n_a < 2 or n_b < 2:
        return 1.0

    observed_diff = _mean(b) - _mean(a)

    # Pool all values and center around the grand mean (null hypothesis)
    all_values = list(a) + list(b)
    grand_mean = _mean(all_values)
    centered_a = [v - _mean(a) + grand_mean for v in a]
    centered_b = [v - _mean(b) + grand_mean for v in b]

    rng = random.Random(seed)
    extreme_count = 0

    for _ in range(n_resamples):
        resample_a = [rng.choice(centered_a) for _ in range(n_a)]
        resample_b = [rng.choice(centered_b) for _ in range(n_b)]
        bootstrap_diff = _mean(resample_b) - _mean(resample_a)
        if abs(bootstrap_diff) >= abs(observed_diff):
            extreme_count += 1

    return extreme_count / n_resamples


def _confidence_level(p_value: float) -> str:
    """Map p-value to a human-readable confidence level."""
    if p_value < 0.01:
        return "high"
    if p_value < 0.05:
        return "medium"
    if p_value < 0.10:
        return "low"
    return "none"


@dataclass
class MetricComparison:
    """Comparison result for a single metric."""

    metric: str
    control_mean: float
    treatment_mean: float
    mean_difference: float
    cohens_d: float
    p_value: float
    confidence: str
    control_std: float = 0.0
    treatment_std: float = 0.0

    @property
    def winner(self) -> str | None:
        """Which group won on this metric, or None if tied."""
        if abs(self.cohens_d) < 0.2:
            return None  # negligible effect
        return "treatment" if self.mean_difference > 0 else "control"


@dataclass
class ABComparisonResult:
    """Full A/B comparison across all metrics."""

    control: ExperimentResult
    treatment: ExperimentResult
    metrics: dict[str, MetricComparison] = field(default_factory=dict)
    win_count: int = 0
    loss_count: int = 0
    tie_count: int = 0

    @property
    def winner(self) -> str | None:
        """Overall winner by majority of metrics (ignoring overall composite)."""
        metric_winners = [
            m.winner
            for k, m in self.metrics.items()
            if k != "overall" and m.winner is not None
        ]
        if not metric_winners:
            return None
        treat_wins = metric_winners.count("treatment")
        control_wins = metric_winners.count("control")
        if treat_wins > control_wins:
            return "treatment"
        if control_wins > treat_wins:
            return "control"
        return None  # tie


class ABComparator:
    """Compare two ExperimentResults with statistical analysis."""

    METRIC_NAMES: ClassVar[list[str]] = _METRIC_NAMES

    def __init__(
        self, bootstrap_samples: int = _DEFAULT_BOOTSTRAP_SAMPLES, seed: int = 42
    ) -> None:
        self._bootstrap_samples = bootstrap_samples
        self._seed = seed

    def compare(
        self, control: ExperimentResult, treatment: ExperimentResult
    ) -> ABComparisonResult:
        """Perform full statistical comparison between control and treatment.

        Args:
            control: Results from the control group.
            treatment: Results from the treatment group.

        Returns:
            ABComparisonResult with per-metric comparisons and win/loss/tie counts.
        """
        metrics: dict[str, MetricComparison] = {}
        win_count = 0
        loss_count = 0
        tie_count = 0

        for metric_name in _METRIC_NAMES:
            mc = self._compare_metric(control, treatment, metric_name)
            metrics[metric_name] = mc

            # Count wins/losses/ties (based on Cohen's d for content metrics,
            # but for latency_s, lower is better, so invert)
            if metric_name == "latency_s":
                # For latency: treatment lower = treatment "wins"
                if mc.cohens_d < -0.2:
                    win_count += 1
                elif mc.cohens_d > 0.2:
                    loss_count += 1
                else:
                    tie_count += 1
            else:
                if mc.cohens_d > 0.2:
                    win_count += 1
                elif mc.cohens_d < -0.2:
                    loss_count += 1
                else:
                    tie_count += 1

        return ABComparisonResult(
            control=control,
            treatment=treatment,
            metrics=metrics,
            win_count=win_count,
            loss_count=loss_count,
            tie_count=tie_count,
        )

    def _compare_metric(
        self,
        control: ExperimentResult,
        treatment: ExperimentResult,
        metric_name: str,
    ) -> MetricComparison:
        """Compare a single metric between groups."""
        control_vals = _extract_values(control, metric_name)
        treatment_vals = _extract_values(treatment, metric_name)

        c_mean = _mean(control_vals)
        t_mean = _mean(treatment_vals)
        diff = t_mean - c_mean
        d = _cohens_d(control_vals, treatment_vals)
        p = _bootstrap_p_value(control_vals, treatment_vals, self._bootstrap_samples, self._seed)

        return MetricComparison(
            metric=metric_name,
            control_mean=round(c_mean, 4),
            treatment_mean=round(t_mean, 4),
            mean_difference=round(diff, 4),
            cohens_d=round(d, 4),
            p_value=round(p, 4),
            confidence=_confidence_level(p),
            control_std=round(_std(control_vals), 4),
            treatment_std=round(_std(treatment_vals), 4),
        )
