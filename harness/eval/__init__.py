"""A/B evaluation framework — compare prompts, models, and retrieval strategies."""

from __future__ import annotations

from typing import Awaitable, Callable

from harness.eval.comparator import ABComparator, ABComparisonResult
from harness.eval.experiment import (
    Experiment,
    ExperimentConfig,
    ExperimentResult,
    GroupConfig,
    RunResult,
)
from harness.eval.reporter import ABReport, generate_report

__all__ = [
    "Experiment",
    "ExperimentConfig",
    "ExperimentResult",
    "GroupConfig",
    "ABComparator",
    "ABComparisonResult",
    "ABReport",
    "RunResult",
    "generate_report",
    "run_ab_test",
]


async def run_ab_test(
    config: ExperimentConfig,
    runner: Callable[[GroupConfig], Awaitable[str]],
    bootstrap_samples: int = 10_000,
    seed: int = 42,
    control_label: str = "Control",
    treatment_label: str = "Treatment",
) -> ABReport:
    """Convenience: run experiment, compare, and generate report in one call.

    Args:
        config: Experiment configuration with control/treatment groups.
        runner: Async callable that takes GroupConfig and returns output text.
        bootstrap_samples: Number of bootstrap resamples for p-value estimation.
        seed: Random seed for reproducible bootstrap.
        control_label: Human-readable label for control group in report.
        treatment_label: Human-readable label for treatment group in report.

    Returns:
        ABReport with summary and detailed Markdown sections.
    """
    experiment = Experiment(config)
    ctrl_result, treat_result = await experiment.run(runner)
    comparison = ABComparator(
        bootstrap_samples=bootstrap_samples, seed=seed
    ).compare(ctrl_result, treat_result)
    return generate_report(comparison, control_label, treatment_label)
