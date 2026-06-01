"""Streamlit multipage entrypoint for the admin dashboard."""
from __future__ import annotations

import runpy


runpy.run_module("src.pages.admin", run_name="__main__")
