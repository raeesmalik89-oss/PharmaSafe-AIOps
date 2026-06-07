# ============================================================
# FILE: Dockerfile
# PURPOSE: Containerise the PharmaSafe-AIOps FastAPI backend
#          Multi-stage build: small final image (~200MB)
# ============================================================

# Stage 1: Build stage (installs dependencies)
FROM python:3.11-slim AS builder

WORKDIR /build

# Copy only requirements first (Docker layer caching)
# If requirements.txt doesn't change, pip install is cached
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# Stage 2: Final stage (lean runtime image)
FROM python:3.11-slim

WORKDIR /app

# Copy installed packages from builder stage
COPY --from=builder /root/.local /root/.local

# Copy application source code
COPY src/ ./src/
COPY security/ ./security/

# Make sure scripts in .local are usable
ENV PATH=/root/.local/bin:$PATH

# Expose FastAPI port
EXPOSE 8000

# Health check — Kubernetes uses /health endpoint
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
  CMD python -c "import requests; requests.get('http://localhost:8000/health').raise_for_status()"

# Start FastAPI with uvicorn
# --host 0.0.0.0  → listen on all interfaces (required in container)
# --workers 2     → 2 worker processes for concurrency
CMD ["python", "-m", "uvicorn", "src.api.app:app",
     "--host", "0.0.0.0",
     "--port", "8000",
     "--workers", "2"]
