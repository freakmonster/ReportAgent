"""
Chart MCP Server — Data visualization generation.

Provides line chart, bar chart, and pie chart generation.
Outputs base64-encoded PNG images suitable for embedding in reports.

Runs as an independent HTTP (FastAPI) service on port 8003.
"""

from __future__ import annotations

import base64
import io
import logging
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Request models (module-level for correct FastAPI body parsing)
# ---------------------------------------------------------------------------

class LineChartReq(BaseModel):
    """Request model for line chart generation."""
    title: str = Field(..., description="Chart title")
    x_label: str = Field(default="X", description="X-axis label")
    y_label: str = Field(default="Y", description="Y-axis label")
    data: dict[str, list[float]] = Field(..., description="Series name → values")
    x_ticks: list[str] | None = None


class BarChartReq(BaseModel):
    """Request model for bar chart generation."""
    title: str = Field(..., description="Chart title")
    x_label: str = Field(default="Category", description="X-axis label")
    y_label: str = Field(default="Value", description="Y-axis label")
    data: dict[str, list[float]] = Field(..., description="Series name → values")
    x_ticks: list[str] | None = None
    horizontal: bool = False


class PieChartReq(BaseModel):
    """Request model for pie chart generation."""
    title: str = Field(..., description="Chart title")
    data: dict[str, float] = Field(..., description="Label → value mapping")


# ---------------------------------------------------------------------------
# Chart generation (uses matplotlib)
# ---------------------------------------------------------------------------

class ChartGenerator:
    """Generate chart images using matplotlib."""

    # Default matplotlib style for consistent, clean charts
    DEFAULT_STYLE: str = "seaborn-v0_8-whitegrid"

    def __init__(self) -> None:
        self._mpl_available: bool = False
        self._check_matplotlib()
        self._cjk_font: str = self._detect_cjk_font()

    @staticmethod
    def _detect_cjk_font() -> str:
        """Detect a CJK-supporting font available on the system."""
        try:
            import matplotlib.font_manager as fm
            for candidate in ("Microsoft YaHei", "SimHei", "SimSun", "KaiTi", "FangSong"):
                for f in fm.fontManager.ttflist:
                    if f.name == candidate:
                        return candidate
        except Exception:
            pass
        return ""  # fallback: use matplotlib default (no CJK)

    def _check_matplotlib(self) -> None:
        """Check if matplotlib is available."""
        try:
            import matplotlib  # noqa: F401
            self._mpl_available = True
        except ImportError:
            logger.warning(
                "matplotlib not installed. Chart generation will return "
                "placeholder responses. Install with: pip install matplotlib"
            )

    def _setup_figure(self, figsize: tuple[int, int] = (10, 6)) -> tuple[object, object]:
        """Set up a matplotlib figure and axis with the default style."""
        import matplotlib
        matplotlib.use("Agg")  # Non-interactive backend
        import matplotlib.pyplot as plt

        try:
            plt.style.use(self.DEFAULT_STYLE)
        except Exception:
            logger.debug("Style '%s' not available, using default", self.DEFAULT_STYLE)

        # Apply CJK font AFTER style (style resets font settings)
        if self._cjk_font:
            plt.rcParams["font.sans-serif"] = [self._cjk_font] + plt.rcParams["font.sans-serif"]
            plt.rcParams["axes.unicode_minus"] = False

        fig, ax = plt.subplots(figsize=figsize)
        return fig, ax

    def _figure_to_base64(self, fig: object) -> str:
        """Convert a matplotlib figure to a base64-encoded PNG string."""
        import matplotlib.pyplot as plt

        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=150, bbox_inches="tight")
        plt.close(fig)
        buf.seek(0)
        return base64.b64encode(buf.read()).decode("utf-8")

    def generate_line_chart(
        self,
        title: str,
        x_label: str,
        y_label: str,
        data: dict[str, list[float]],
        x_ticks: list[str] | None = None,
    ) -> dict[str, Any]:
        """Generate a line chart.

        Args:
            title: Chart title.
            x_label: X-axis label.
            y_label: Y-axis label.
            data: Mapping of series name → list of y-values.
            x_ticks: Optional x-axis tick labels.

        Returns:
            Dict with keys: chart_type, title, image_base64, generated_at.
        """
        if not self._mpl_available:
            return self._placeholder("line_chart", title)

        import matplotlib.pyplot as plt

        fig, ax = self._setup_figure()
        for label, values in data.items():
            ax.plot(range(len(values)), values, marker="o", linewidth=2, label=label)

        if x_ticks:
            ax.set_xticks(range(len(x_ticks)))
            ax.set_xticklabels(x_ticks, rotation=45, ha="right")

        ax.set_title(title, fontsize=14, fontweight="bold")
        ax.set_xlabel(x_label)
        ax.set_ylabel(y_label)
        ax.legend(loc="best")
        ax.grid(True, alpha=0.3)

        img_b64 = self._figure_to_base64(fig)

        return {
            "chart_type": "line",
            "title": title,
            "image_base64": img_b64,
            "generated_at": datetime.utcnow().isoformat(),
        }

    def generate_bar_chart(
        self,
        title: str,
        x_label: str,
        y_label: str,
        data: dict[str, list[float]],
        x_ticks: list[str] | None = None,
        horizontal: bool = False,
    ) -> dict[str, Any]:
        """Generate a bar chart (vertical or horizontal).

        Args:
            title: Chart title.
            x_label: X-axis label.
            y_label: Y-axis label.
            data: Mapping of series name → list of values.
            x_ticks: Optional category labels.
            horizontal: If True, generate horizontal bars.

        Returns:
            Dict with keys: chart_type, title, image_base64, generated_at.
        """
        if not self._mpl_available:
            return self._placeholder("bar_chart", title)

        import numpy as np

        fig, ax = self._setup_figure()

        categories = x_ticks or [str(i + 1) for i in range(len(next(iter(data.values()))))]
        n_categories = len(categories)
        n_series = len(data)

        if horizontal:
            bar_height = 0.8 / n_series
            y_pos = np.arange(n_categories)
            for i, (label, values) in enumerate(data.items()):
                offset = (i - n_series / 2 + 0.5) * bar_height
                ax.barh(y_pos + offset, values, bar_height, label=label)
            ax.set_yticks(y_pos)
            ax.set_yticklabels(categories)
            ax.set_xlabel(y_label)
            ax.set_ylabel(x_label)
        else:
            bar_width = 0.8 / n_series
            x_pos = np.arange(n_categories)
            for i, (label, values) in enumerate(data.items()):
                offset = (i - n_series / 2 + 0.5) * bar_width
                ax.bar(x_pos + offset, values, bar_width, label=label)
            ax.set_xticks(x_pos)
            ax.set_xticklabels(categories, rotation=45, ha="right")
            ax.set_xlabel(x_label)
            ax.set_ylabel(y_label)

        ax.set_title(title, fontsize=14, fontweight="bold")
        ax.legend(loc="best")

        img_b64 = self._figure_to_base64(fig)

        return {
            "chart_type": "bar",
            "title": title,
            "image_base64": img_b64,
            "generated_at": datetime.utcnow().isoformat(),
        }

    def generate_pie_chart(
        self,
        title: str,
        data: dict[str, float],
    ) -> dict[str, Any]:
        """Generate a pie chart.

        Args:
            title: Chart title.
            data: Mapping of label → value.

        Returns:
            Dict with keys: chart_type, title, image_base64, generated_at.
        """
        if not self._mpl_available:
            return self._placeholder("pie_chart", title)

        fig, ax = self._setup_figure((8, 8))
        labels = list(data.keys())
        values = list(data.values())

        wedges, texts, autotexts = ax.pie(
            values,
            labels=labels,
            autopct="%1.1f%%",
            startangle=90,
            pctdistance=0.85,
        )
        for autotext in autotexts:
            autotext.set_fontsize(9)
        ax.set_title(title, fontsize=14, fontweight="bold")

        img_b64 = self._figure_to_base64(fig)

        return {
            "chart_type": "pie",
            "title": title,
            "image_base64": img_b64,
            "generated_at": datetime.utcnow().isoformat(),
        }

    def _placeholder(self, chart_type: str, title: str) -> dict[str, Any]:
        """Return a placeholder response when matplotlib is not available."""
        return {
            "chart_type": chart_type,
            "title": title,
            "image_base64": "",
            "error": "Chart generation unavailable: matplotlib not installed",
            "generated_at": datetime.utcnow().isoformat(),
        }


# ---------------------------------------------------------------------------
# FastAPI application
# ---------------------------------------------------------------------------

def create_chart_app() -> object:
    """Create and configure the FastAPI chart MCP server application."""
    from fastapi import FastAPI

    app = FastAPI(title="MCP Chart Server", version="0.1.0")
    generator = ChartGenerator()

    # ── Health ──────────────────────────────────────────────────────

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "service": "mcp-chart"}

    # ── Tool endpoints ──────────────────────────────────────────────

    @app.post("/tools/generate_line_chart")
    async def line_chart(req: LineChartReq) -> dict[str, Any]:
        return generator.generate_line_chart(
            title=req.title,
            x_label=req.x_label,
            y_label=req.y_label,
            data=req.data,
            x_ticks=req.x_ticks,
        )

    @app.post("/tools/generate_bar_chart")
    async def bar_chart(req: BarChartReq) -> dict[str, Any]:
        return generator.generate_bar_chart(
            title=req.title,
            x_label=req.x_label,
            y_label=req.y_label,
            data=req.data,
            x_ticks=req.x_ticks,
            horizontal=req.horizontal,
        )

    @app.post("/tools/generate_pie_chart")
    async def pie_chart(req: PieChartReq) -> dict[str, Any]:
        return generator.generate_pie_chart(
            title=req.title,
            data=req.data,
        )

    return app


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

app = create_chart_app()


def main() -> None:
    """Run the chart MCP server."""
    import uvicorn

    from config.settings import settings

    uvicorn.run(
        "mcp_tools.mcp_servers.chart_server:app",
        host="0.0.0.0",
        port=8003,
        log_level=settings.log_level.lower(),
    )


if __name__ == "__main__":
    main()
