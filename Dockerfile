# =============================================================================
# Stage 1: Build the J.A.R.V.I.S. Second Brain React Dashboard
# =============================================================================
FROM node:22-alpine AS ui-builder

WORKDIR /web
COPY web/package*.json ./
RUN npm ci

COPY web/ ./
RUN npm run build

# =============================================================================
# Stage 2: Production Python Backend & Conscious Engine
# =============================================================================
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies (build-essential, libpq for PostgreSQL, curl for healthchecks, docker CLI for sandboxing)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    curl \
    git \
    docker.io \
    && rm -rf /var/lib/apt/lists/*

# Install Python requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code and config
COPY pyproject.toml .
COPY src/ ./src/

# Copy compiled production UI assets from Stage 1
COPY --from=ui-builder /frontend/dist/ ./frontend/dist/
COPY --from=ui-builder /frontend/dist/ ./frontend/

ENV PYTHONPATH=/app/src
ENV PYTHONUNBUFFERED=1

EXPOSE 8000

HEALTHCHECK --interval=20s --timeout=5s --start-period=10s --retries=3 \
  CMD curl -f http://localhost:8000/healthz || exit 1

CMD ["uvicorn", "nexus.infrastructure.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
