"""Streamlit dashboard entry point for the backend runtime.

Delegates execution to frontend.dashboard.app while ensuring zero storage,
simulator, or executor imports.
"""

from __future__ import annotations

from frontend.dashboard.app import fetch_api, main, post_decision

__all__ = ["fetch_api", "main", "post_decision"]

if __name__ == "__main__":
    main()
