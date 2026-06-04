"""Dashboard descriptor helpers: load, validate, and resolve widget layout.

The dashboard JSON (log_analytics/dashboards/oci_zpr_visibility_dashboard.json)
carries, per widget: `name`, `query`, `visualization_type`, optional
`visualization_options`, and `layout` (width/height only). Row/column are
computed by `resolve_layout` on a 12-column grid — widgets never hand-author
row/column (matches the OCI LA deploy convention).
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

PROJECT_DIR = Path(__file__).resolve().parent.parent
# Env override lets a pip-installed deployment (e.g. the ORM controller) point at
# the dashboard descriptor when log_analytics/ is not next to the package.
DASHBOARD_PATH = Path(
    os.environ.get(
        "OCI_ZPR_DASHBOARD_PATH",
        PROJECT_DIR / "log_analytics" / "dashboards" / "oci_zpr_visibility_dashboard.json",
    )
)
SOURCE_DISPLAY_NAME = "OCI ZPR Visibility JSON"
GRID_COLUMNS = 12

VALID_VISUALIZATIONS = {
    "tile", "table", "records", "records_histogram", "table_histogram",
    "bar", "hbar", "line", "pie", "sunburst", "treemap", "link",
    "summary_table", "map", "distinct", "cluster",
}


def load_dashboard(path: Path | None = None) -> dict[str, Any]:
    return json.loads((path or DASHBOARD_PATH).read_text())


def iter_widgets(dash: dict[str, Any]) -> list[dict[str, Any]]:
    return [w for tab in dash.get("tabs", []) for w in tab.get("widgets", [])]


def validate_dashboard(dash: dict[str, Any]) -> list[str]:
    """Return a list of schema errors (empty = valid)."""
    errors: list[str] = []
    for w in iter_widgets(dash):
        name = w.get("name", "<unnamed>")
        if not w.get("query"):
            errors.append(f"{name}: missing query")
        viz = w.get("visualization_type")
        if viz not in VALID_VISUALIZATIONS:
            errors.append(f"{name}: invalid visualization_type {viz!r}")
        layout = w.get("layout", {})
        width, height = layout.get("width"), layout.get("height")
        if not isinstance(width, int) or not (1 <= width <= GRID_COLUMNS):
            errors.append(f"{name}: width {width!r} out of 1..{GRID_COLUMNS}")
        if not isinstance(height, int) or height <= 0:
            errors.append(f"{name}: height {height!r} must be positive")
    return errors


def resolve_layout(widgets: list[dict[str, Any]], columns: int = GRID_COLUMNS) -> list[dict[str, Any]]:
    """Pack widgets left-to-right on a `columns`-wide grid, wrapping rows.

    Returns each widget's placement as {name, row, column, width, height}.
    Row advances by the tallest widget in the row when it wraps.
    """
    placed: list[dict[str, Any]] = []
    col = 0
    row = 0
    row_height = 0
    for w in widgets:
        layout = w.get("layout", {})
        width = min(int(layout.get("width", columns)), columns)
        height = int(layout.get("height", 1))
        if col + width > columns:
            row += row_height
            col = 0
            row_height = 0
        placed.append({"name": w.get("name"), "row": row, "column": col,
                       "width": width, "height": height})
        col += width
        row_height = max(row_height, height)
    return placed
