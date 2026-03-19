"""
Pipeline client package — thin interface for the FastAPI app to interact
with the standalone pipeline worker service.

Contains:
  - enqueue.py  — submit on-demand jobs to the ARQ worker
  - registry.py — tracked ticker management (shared between app and pipeline)

The actual worker and task implementations live in the separate
``pipeline/`` service (``pipeline_worker`` package).
"""
