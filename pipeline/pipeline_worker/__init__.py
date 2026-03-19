"""
Pipeline worker — standalone data ingestion service via ARQ.

This is a separate deployable service. It owns ALL external API calls
(yfinance, FinancialDatasets, Yahoo, AI). The FastAPI app only reads
from Redis/Postgres.

Start the worker::

    arq pipeline_worker.worker.WorkerSettings

Start the dashboard::

    uvicorn pipeline_worker.dashboard.app:app --port 9000
"""
