"""Experiment management — define, run, and collect A/B test results."""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from harness.sensors.eval_suite import EvalScores, evaluate_report

logger = logging.getLogger(__name__)


@dataclass
class GroupConfig:
    """Configuration for a single experimental group (control or treatment)."""

    prompt: str | None = None
    prompt_version: str | None = None
    model: str | None = None
    temperature: float = 0.7
    retrieval_strategy: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        if self.prompt is not None:
            result["prompt"] = self.prompt
        if self.prompt_version is not None:
            result["prompt_version"] = self.prompt_version
        if self.model is not None:
            result["model"] = self.model
        result["temperature"] = self.temperature
        if self.retrieval_strategy is not None:
            result["retrieval_strategy"] = self.retrieval_strategy
        result.update(self.extra)
        return result


@dataclass
class ExperimentConfig:
    """Full experiment configuration with control and treatment groups."""

    name: str
    control: GroupConfig = field(default_factory=GroupConfig)
    treatment: GroupConfig = field(default_factory=GroupConfig)
    runs_per_group: int = 10

    def validate(self) -> None:
        """Validate that the configuration is self-consistent.

        Raises:
            ValueError: If runs_per_group <= 0 or groups are identical.
        """
        if self.runs_per_group <= 0:
            raise ValueError("runs_per_group must be positive")
        if self.control == self.treatment:
            raise ValueError("Control and treatment groups must differ")


@dataclass
class RunResult:
    """Single-run result: raw output, quality scores, and latency."""

    output: str
    scores: EvalScores
    latency_s: float
    run_index: int = 0


@dataclass
class ExperimentResult:
    """Collected results for one experimental group."""

    config: GroupConfig
    runs: list[RunResult] = field(default_factory=list)

    @property
    def mean_latency(self) -> float:
        if not self.runs:
            return 0.0
        return sum(r.latency_s for r in self.runs) / len(self.runs)

    def mean_score(self, metric: str) -> float:
        if not self.runs:
            return 0.0
        values = [getattr(r.scores, metric, 0.0) for r in self.runs]
        return sum(values) / len(values)


class Experiment:
    """Runs an A/B experiment comparing control vs treatment groups."""

    def __init__(self, config: ExperimentConfig) -> None:
        config.validate()
        self.config = config
        self._control_result: ExperimentResult | None = None
        self._treatment_result: ExperimentResult | None = None

    @property
    def control_result(self) -> ExperimentResult | None:
        return self._control_result

    @property
    def treatment_result(self) -> ExperimentResult | None:
        return self._treatment_result

    async def run(
        self,
        runner: Callable[[GroupConfig], Awaitable[str]],
    ) -> tuple[ExperimentResult, ExperimentResult]:
        """Execute the experiment: run control and treatment groups.

        Args:
            runner: An async callable that takes a GroupConfig and returns
                the generated output text for a single run.

        Returns:
            A tuple of (control_result, treatment_result).
        """
        logger.info(
            "Starting experiment '%s': %d runs per group",
            self.config.name,
            self.config.runs_per_group,
        )
        self._control_result = await self._run_group(self.config.control, runner)
        self._treatment_result = await self._run_group(self.config.treatment, runner)
        logger.info("Experiment '%s' complete", self.config.name)
        return self._control_result, self._treatment_result

    async def _run_group(
        self,
        group_config: GroupConfig,
        runner: Callable[[GroupConfig], Awaitable[str]],
    ) -> ExperimentResult:
        """Run all iterations for a single group."""
        tasks = [
            self._single_run(group_config, runner, i) for i in range(self.config.runs_per_group)
        ]
        runs = await asyncio.gather(*tasks)
        return ExperimentResult(config=group_config, runs=list(runs))

    async def _single_run(
        self,
        group_config: GroupConfig,
        runner: Callable[[GroupConfig], Awaitable[str]],
        run_index: int,
    ) -> RunResult:
        """Execute one run: call runner, measure latency, score output."""
        start = time.perf_counter()
        try:
            output = await runner(group_config)
        except Exception as exc:
            logger.error(
                "Run %d failed for group with config %s: %s",
                run_index,
                group_config.to_dict(),
                exc,
            )
            raise
        elapsed = time.perf_counter() - start
        scores = evaluate_report(output)
        return RunResult(
            output=output,
            scores=scores,
            latency_s=round(elapsed, 4),
            run_index=run_index,
        )
