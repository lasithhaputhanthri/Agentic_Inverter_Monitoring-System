# ==============================================================================
# Multi-stage Dockerfile for IoT Incident Response System
# ==============================================================================
FROM python:3.11-slim AS base

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# Install runtime tools
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install pinned dependencies
COPY requirements.lock pyproject.toml README.md ./
RUN pip install --no-cache-dir -r requirements.lock && \
    pip install --no-cache-dir -e .

# Copy application source code
COPY . .

# ------------------------------------------------------------------------------
# Target: Backend API Server (FastAPI on Port 8000)
# ------------------------------------------------------------------------------
FROM base AS backend
EXPOSE 8000
CMD ["uvicorn", "backend.api.main:app", "--host", "0.0.0.0", "--port", "8000"]

# ------------------------------------------------------------------------------
# Target: Frontend Operator Dashboard (Streamlit on Port 8501)
# ------------------------------------------------------------------------------
FROM base AS frontend
EXPOSE 8501
CMD ["streamlit", "run", "frontend/dashboard/app.py", "--server.port=8501", "--server.address=0.0.0.0", "--server.headless=true"]

# ------------------------------------------------------------------------------
# Target: Inverter Fleet Telemetry Simulator
# ------------------------------------------------------------------------------
FROM base AS simulator
CMD ["python", "-m", "simulator.runner", "--devices", "20", "--speed", "1.0"]
