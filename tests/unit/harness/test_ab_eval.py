"""Unit tests for A/B evaluation framework."""

from __future__ import annotations

import sys
from pathlib import Path

_project_root = Path(__file__).resolve().parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import pytest  # noqa: E402

from harness.eval import (
    ABComparator,
    Experiment,
    ExperimentConfig,
    ExperimentResult,
    GroupConfig,
    RunResult,
    generate_report,
)
from harness.eval.comparator import (
    ABComparisonResult,
    MetricComparison,
    _bootstrap_p_value,
    _cohens_d,
    _extract_values,
    _mean,
    _std,
)
from harness.sensors.eval_suite import EvalScores

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_scores(
    completeness: float, accuracy: float, citation_quality: float, logical_flow: float
) -> EvalScores:
    return EvalScores(
        completeness=completeness,
        accuracy=accuracy,
        citation_quality=citation_quality,
        logical_flow=logical_flow,
    )


def _make_run(
    output: str = "", scores: EvalScores | None = None, latency: float = 1.0, idx: int = 0
) -> RunResult:
    return RunResult(
        output=output,
        scores=scores or EvalScores(),
        latency_s=latency,
        run_index=idx,
    )


def _make_group_result(
    runs: list[RunResult], config: GroupConfig | None = None
) -> ExperimentResult:
    return ExperimentResult(config=config or GroupConfig(), runs=runs)


# ---------------------------------------------------------------------------
# ExperimentConfig
# ---------------------------------------------------------------------------


class TestExperimentConfig:
    def test_valid_config(self) -> None:
        ctrl = GroupConfig(model="a")
        treat = GroupConfig(model="b")
        cfg = ExperimentConfig(name="test", control=ctrl, treatment=treat, runs_per_group=5)
        cfg.validate()  # should not raise

    def test_identical_groups_raises(self) -> None:
        ctrl = GroupConfig(model="a")
        cfg = ExperimentConfig(name="bad", control=ctrl, treatment=ctrl)
        with pytest.raises(ValueError, match="must differ"):
            cfg.validate()

    def test_zero_runs_raises(self) -> None:
        cfg = ExperimentConfig(
            name="bad",
            control=GroupConfig(model="a"),
            treatment=GroupConfig(model="b"),
            runs_per_group=0,
        )
        with pytest.raises(ValueError, match="positive"):
            cfg.validate()

    def test_negative_runs_raises(self) -> None:
        cfg = ExperimentConfig(
            name="bad",
            control=GroupConfig(model="a"),
            treatment=GroupConfig(model="b"),
            runs_per_group=-1,
        )
        with pytest.raises(ValueError, match="positive"):
            cfg.validate()

    def test_group_config_to_dict(self) -> None:
        gc = GroupConfig(
            model="x", temperature=0.5, retrieval_strategy="hybrid", prompt_version="v2"
        )
        d = gc.to_dict()
        assert d["model"] == "x"
        assert d["temperature"] == 0.5
        assert d["retrieval_strategy"] == "hybrid"
        assert d["prompt_version"] == "v2"


# ---------------------------------------------------------------------------
# Experiment (runner) — async tests
# ---------------------------------------------------------------------------


class TestExperimentRun:
    async def test_runs_correct_number(self) -> None:
        """Verify Experiment.run() executes the expected number of runs per group."""
        cfg = ExperimentConfig(
            name="test",
            control=GroupConfig(model="ctrl"),
            treatment=GroupConfig(model="treat"),
            runs_per_group=3,
        )

        async def fake_runner(config: GroupConfig) -> str:
            return f"Output from {config.model}"

        exp = Experiment(cfg)
        ctrl_res, treat_res = await exp.run(fake_runner)

        assert len(ctrl_res.runs) == 3
        assert len(treat_res.runs) == 3

    async def test_collects_scores_and_latency(self) -> None:
        cfg = ExperimentConfig(
            name="test",
            control=GroupConfig(model="c"),
            treatment=GroupConfig(model="t"),
            runs_per_group=2,
        )

        async def fake_runner(config: GroupConfig) -> str:
            return "# 摘要\n市场 [1]\n分析 因此 此外 值得注意的是 [2]"

        exp = Experiment(cfg)
        ctrl_res, treat_res = await exp.run(fake_runner)

        for run in ctrl_res.runs:
            assert isinstance(run.scores, EvalScores)
            assert run.latency_s >= 0
            assert run.output

        for run in treat_res.runs:
            assert isinstance(run.scores, EvalScores)
            assert run.latency_s >= 0
            assert run.output

    async def test_runner_failure_propagates(self) -> None:
        cfg = ExperimentConfig(
            name="fail",
            control=GroupConfig(model="c"),
            treatment=GroupConfig(model="t"),
            runs_per_group=2,
        )

        async def bad_runner(config: GroupConfig) -> str:
            raise RuntimeError("intentional failure")

        exp = Experiment(cfg)
        with pytest.raises(RuntimeError, match="intentional failure"):
            await exp.run(bad_runner)


# ---------------------------------------------------------------------------
# ExperimentResult helpers
# ---------------------------------------------------------------------------


class TestExperimentResult:
    def test_mean_latency(self) -> None:
        runs = [
            _make_run(latency=1.0, idx=0),
            _make_run(latency=2.0, idx=1),
            _make_run(latency=3.0, idx=2),
        ]
        er = _make_group_result(runs)
        assert er.mean_latency == pytest.approx(2.0)

    def test_mean_score(self) -> None:
        runs = [
            _make_run(scores=_make_scores(0.5, 0.0, 0.0, 0.0), idx=0),
            _make_run(scores=_make_scores(1.0, 0.0, 0.0, 0.0), idx=1),
        ]
        er = _make_group_result(runs)
        assert er.mean_score("completeness") == pytest.approx(0.75)

    def test_empty_mean_latency(self) -> None:
        er = _make_group_result([])
        assert er.mean_latency == 0.0

    def test_empty_mean_score(self) -> None:
        er = _make_group_result([])
        assert er.mean_score("accuracy") == 0.0


# ---------------------------------------------------------------------------
# Statistical helpers
# ---------------------------------------------------------------------------


class TestStatsHelpers:
    def test_mean(self) -> None:
        assert _mean([1.0, 2.0, 3.0]) == pytest.approx(2.0)
        assert _mean([]) == 0.0

    def test_std(self) -> None:
        assert _std([1.0, 1.0, 1.0]) == pytest.approx(0.0)
        assert _std([1.0, 2.0, 3.0]) == pytest.approx(1.0, abs=0.01)
        assert _std([1.0]) == 0.0  # single value
        assert _std([]) == 0.0

    def test_cohens_d_equal(self) -> None:
        a = [1.0, 2.0, 3.0, 4.0, 5.0]
        b = [1.0, 2.0, 3.0, 4.0, 5.0]
        assert _cohens_d(a, b) == pytest.approx(0.0)

    def test_cohens_d_clear_difference(self) -> None:
        a = [1.0, 1.5, 2.0, 2.5, 3.0]
        b = [4.0, 4.5, 5.0, 5.5, 6.0]
        d = _cohens_d(a, b)
        assert d > 1.0  # large effect

    def test_cohens_d_single_value(self) -> None:
        assert _cohens_d([1.0], [2.0]) == 0.0

    def test_bootstrap_p_value_same_distributions(self) -> None:
        """With identical distributions, p should be large (fail to reject H0)."""
        # Use identical lists so there's no real difference
        a = [0.5, 0.6, 0.7, 0.8, 0.9, 0.5, 0.6, 0.7, 0.8, 0.9]
        b = [0.5, 0.6, 0.7, 0.8, 0.9, 0.5, 0.6, 0.7, 0.8, 0.9]
        p = _bootstrap_p_value(a, b)
        # With identical data and centered resampling, p should be very high
        assert p > 0.5

    def test_bootstrap_p_value_different_distributions(self) -> None:
        """With clearly different distributions, p should be small."""
        a = [0.1, 0.15, 0.2, 0.15, 0.1, 0.2, 0.1, 0.15, 0.2, 0.15]
        b = [0.8, 0.85, 0.9, 0.85, 0.8, 0.9, 0.8, 0.85, 0.9, 0.85]
        p = _bootstrap_p_value(a, b)
        assert p < 0.01

    def test_bootstrap_small_samples(self) -> None:
        """Small samples should default to p=1.0."""
        assert _bootstrap_p_value([1.0], [2.0]) == 1.0
        assert _bootstrap_p_value([], []) == 1.0

    def test_extract_values(self) -> None:
        runs = [
            _make_run(scores=_make_scores(0.5, 0.6, 0.7, 0.8), latency=1.5, idx=0),
            _make_run(scores=_make_scores(0.1, 0.2, 0.3, 0.4), latency=2.0, idx=1),
        ]
        er = _make_group_result(runs)
        assert _extract_values(er, "completeness") == [0.5, 0.1]
        assert _extract_values(er, "latency_s") == [1.5, 2.0]


# ---------------------------------------------------------------------------
# ABComparator
# ---------------------------------------------------------------------------


class TestABComparator:
    def test_basic_comparison(self) -> None:
        """Comparator should produce all metrics without crashing."""
        # Use varied scores so std is non-zero and Cohen's d is meaningful
        ctrl_runs = [
            _make_run(scores=_make_scores(0.4, 0.5, 0.6, 0.7), latency=1.0, idx=0),
            _make_run(scores=_make_scores(0.5, 0.6, 0.7, 0.8), latency=1.1, idx=1),
            _make_run(scores=_make_scores(0.3, 0.4, 0.5, 0.6), latency=0.9, idx=2),
            _make_run(scores=_make_scores(0.6, 0.7, 0.8, 0.9), latency=1.2, idx=3),
            _make_run(scores=_make_scores(0.5, 0.5, 0.7, 0.7), latency=1.0, idx=4),
        ]
        treat_runs = [
            _make_run(scores=_make_scores(0.6, 0.7, 0.8, 0.9), latency=0.7, idx=0),
            _make_run(scores=_make_scores(0.7, 0.8, 0.9, 1.0), latency=0.8, idx=1),
            _make_run(scores=_make_scores(0.5, 0.7, 0.7, 0.8), latency=0.9, idx=2),
            _make_run(scores=_make_scores(0.8, 0.9, 1.0, 1.0), latency=0.7, idx=3),
            _make_run(scores=_make_scores(0.7, 0.8, 0.9, 0.9), latency=0.8, idx=4),
        ]

        ctrl = _make_group_result(ctrl_runs, GroupConfig(model="ctrl"))
        treat = _make_group_result(treat_runs, GroupConfig(model="treat"))

        comparator = ABComparator()
        result = comparator.compare(ctrl, treat)

        assert isinstance(result, ABComparisonResult)
        assert len(result.metrics) == 6  # 4 scores + overall + latency
        assert "completeness" in result.metrics
        assert "latency_s" in result.metrics

        # Treatment should have higher scores
        mc = result.metrics["completeness"]
        assert isinstance(mc, MetricComparison)
        assert mc.cohens_d > 0

    def test_equal_results(self) -> None:
        """Identical results should produce negligible effects."""
        scores = _make_scores(0.5, 0.5, 0.5, 0.5)
        ctrl_runs = [_make_run(scores=scores, latency=1.0, idx=i) for i in range(5)]
        treat_runs = [_make_run(scores=scores, latency=1.0, idx=i) for i in range(5)]

        ctrl = _make_group_result(ctrl_runs, GroupConfig(model="ctrl"))
        treat = _make_group_result(treat_runs, GroupConfig(model="treat"))

        result = ABComparator().compare(ctrl, treat)

        # All effects should be negligible
        for mc in result.metrics.values():
            assert abs(mc.cohens_d) < 0.3, f"{mc.metric}: cohens_d={mc.cohens_d}"

    def test_empty_results(self) -> None:
        """Empty results should not crash."""
        ctrl = _make_group_result([])
        treat = _make_group_result([])

        result = ABComparator().compare(ctrl, treat)

        assert len(result.metrics) == 6
        for mc in result.metrics.values():
            assert mc.control_mean == 0.0
            assert mc.treatment_mean == 0.0
            assert mc.cohens_d == 0.0
            assert mc.p_value == 1.0

    def test_single_run(self) -> None:
        """Single run per group should still work (stats are degenerate)."""
        ctrl = _make_group_result([_make_run(scores=_make_scores(0.5, 0.0, 0.0, 0.0), idx=0)])
        treat = _make_group_result([_make_run(scores=_make_scores(1.0, 0.0, 0.0, 0.0), idx=0)])

        result = ABComparator().compare(ctrl, treat)
        assert len(result.metrics) == 6


# ---------------------------------------------------------------------------
# generate_report
# ---------------------------------------------------------------------------


class TestGenerateReport:
    def test_report_generation(self) -> None:
        ctrl_runs = [
            _make_run(scores=_make_scores(0.5, 0.6, 0.7, 0.8), latency=1.0, idx=i) for i in range(5)
        ]
        treat_runs = [
            _make_run(scores=_make_scores(0.7, 0.8, 0.9, 1.0), latency=0.8, idx=i) for i in range(5)
        ]

        ctrl = _make_group_result(ctrl_runs, GroupConfig(model="ctrl"))
        treat = _make_group_result(treat_runs, GroupConfig(model="treat"))

        comparison = ABComparator().compare(ctrl, treat)
        report = generate_report(comparison, control_label="Baseline", treatment_label="Variant")

        md = report.to_markdown()
        assert "# A/B Experiment Report" in md
        assert "## Detailed Comparison" in md
        assert "Baseline" in md
        assert "Variant" in md
        assert "completeness" in md

    def test_report_no_winner(self) -> None:
        """When groups are equal, report should indicate no clear winner."""
        scores = _make_scores(0.5, 0.6, 0.7, 0.8)
        ctrl_runs = [_make_run(scores=scores, latency=1.0, idx=i) for i in range(5)]
        treat_runs = [_make_run(scores=scores, latency=1.0, idx=i) for i in range(5)]

        ctrl = _make_group_result(ctrl_runs, GroupConfig(model="ctrl"))
        treat = _make_group_result(treat_runs, GroupConfig(model="treat"))

        comparison = ABComparator().compare(ctrl, treat)
        report = generate_report(comparison)
        md = report.to_markdown()
        assert "No Clear Winner" in md


# ---------------------------------------------------------------------------
# MetricComparison
# ---------------------------------------------------------------------------


class TestMetricComparison:
    def test_winner_property(self) -> None:
        mc_treat = MetricComparison(
            metric="test",
            control_mean=0.5,
            treatment_mean=0.8,
            mean_difference=0.3,
            cohens_d=1.0,
            p_value=0.001,
            confidence="high",
        )
        assert mc_treat.winner == "treatment"

        mc_control = MetricComparison(
            metric="test",
            control_mean=0.8,
            treatment_mean=0.5,
            mean_difference=-0.3,
            cohens_d=-1.0,
            p_value=0.001,
            confidence="high",
        )
        assert mc_control.winner == "control"

        mc_tie = MetricComparison(
            metric="test",
            control_mean=0.5,
            treatment_mean=0.55,
            mean_difference=0.05,
            cohens_d=0.1,
            p_value=0.5,
            confidence="none",
        )
        assert mc_tie.winner is None


# ---------------------------------------------------------------------------
# ABComparisonResult.winner property
# ---------------------------------------------------------------------------


class TestABComparisonResultWinner:
    def test_treatment_winner(self) -> None:
        """When treatment wins more metrics, overall winner is treatment."""
        ctrl = _make_group_result([])
        treat = _make_group_result([])
        result = ABComparisonResult(
            control=ctrl,
            treatment=treat,
            metrics={
                "completeness": MetricComparison(
                    metric="completeness",
                    control_mean=0.5,
                    treatment_mean=0.8,
                    mean_difference=0.3,
                    cohens_d=1.0,
                    p_value=0.001,
                    confidence="high",
                ),
                "accuracy": MetricComparison(
                    metric="accuracy",
                    control_mean=0.8,
                    treatment_mean=0.5,
                    mean_difference=-0.3,
                    cohens_d=-1.0,
                    p_value=0.001,
                    confidence="high",
                ),
                "citation_quality": MetricComparison(
                    metric="citation_quality",
                    control_mean=0.5,
                    treatment_mean=0.8,
                    mean_difference=0.3,
                    cohens_d=1.0,
                    p_value=0.001,
                    confidence="high",
                ),
                "logical_flow": MetricComparison(
                    metric="logical_flow",
                    control_mean=0.5,
                    treatment_mean=0.55,
                    mean_difference=0.05,
                    cohens_d=0.1,
                    p_value=0.5,
                    confidence="none",
                ),
            },
            win_count=3,
            loss_count=1,
            tie_count=1,
        )
        # completeness=treatment, accuracy=control, citation_quality=treatment, logical_flow=tie
        # treatment 2, control 1
        assert result.winner == "treatment"

    def test_winner_no_effect(self) -> None:
        """When all effects are negligible, no winner."""
        ctrl = _make_group_result([])
        treat = _make_group_result([])
        result = ABComparisonResult(
            control=ctrl,
            treatment=treat,
            metrics={
                "completeness": MetricComparison(
                    metric="completeness",
                    control_mean=0.5,
                    treatment_mean=0.55,
                    mean_difference=0.05,
                    cohens_d=0.1,
                    p_value=0.5,
                    confidence="none",
                ),
            },
            win_count=0,
            loss_count=0,
            tie_count=1,
        )
        assert result.winner is None
