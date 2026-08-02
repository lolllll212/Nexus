# NEXUS - unified runtime image (cortex API, subcortex workers, dreaming beat)
FROM python:3.11-slim

WORKDIR /app

# Install system deps for neo4j driver wheels etc.
RUN apt-get update && apt-get install -y --no-install-recommends gcc libpq-dev && rm -rf /var/lib/apt/lists/*

# Install Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source (src layout)
COPY pyproject.toml .
COPY src/ ./src/
ENV PYTHONPATH=/app/src

EXPOSE 8000
