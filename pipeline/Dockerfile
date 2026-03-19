FROM python:3.12-slim

WORKDIR /workspace

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Backend shared code (models, config, database, services)
COPY backend/ ./backend/

# Pipeline code
COPY pipeline/ ./pipeline/

# Install all dependencies
RUN pip install --no-cache-dir -r backend/requirements.txt \
    && pip install --no-cache-dir -r pipeline/requirements.txt

# backend/app is the shared package, pipeline/pipeline_worker is the worker package
ENV PYTHONPATH=/workspace/backend:/workspace/pipeline

EXPOSE 9000

# Default: run the ARQ worker. Override in docker-compose for dashboard.
CMD ["arq", "pipeline_worker.worker.WorkerSettings"]
