"""Locust performance test configuration — sys.path bootstrap for project imports."""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure the project root is on sys.path so that locustfile.py can
# reference project modules (e.g. for schema validation helpers).
_project_root = Path(__file__).resolve().parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))
