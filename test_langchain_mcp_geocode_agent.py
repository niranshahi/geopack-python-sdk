"""
Thin runner for the public sample: examples/langchain_geopack_geocode_workflow.py

Prefer running the example directly:
  python examples/langchain_geopack_geocode_workflow.py "Your question"
"""
from __future__ import annotations

import runpy
import sys
from pathlib import Path

if __name__ == "__main__":
    target = Path(__file__).resolve().parent / "examples" / "langchain_geopack_geocode_workflow.py"
    sys.argv[0] = str(target)
    runpy.run_path(str(target), run_name="__main__")
