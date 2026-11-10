# ==============================================================================
# Dockerfile for IoT Incident Response System (Single Unified Image)
# ==============================================================================
FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PIP_NO_CACHE_DIR=1

# Install runtime utilities
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install pinned dependencies
COPY requirements.lock pyproject.toml README.md ./
RUN pip install --no-cache-dir -r requirements.lock && \
    pip install --no-cache-dir -e .

# Copy application source code
COPY . .

# Expose backend API (8000) and frontend dashboard (8501)
EXPOSE 8000 8501

# Default command starts backend API
CMD ["uvicorn", "backend.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
