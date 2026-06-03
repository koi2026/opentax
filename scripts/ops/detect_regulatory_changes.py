"""Backward-compatible entrypoint for regulatory area change detection.

The canonical implementation lives in ``src.ingestion.area_designation_pipeline``.
"""
from __future__ import annotations

from src.ingestion.area_designation_pipeline import main


if __name__ == "__main__":
    main()
