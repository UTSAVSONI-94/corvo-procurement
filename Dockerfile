# -------------------------------------------------------------
# Stage 1: Build Frontend SPA
# -------------------------------------------------------------
FROM node:20-slim AS frontend-builder
WORKDIR /app/frontend

COPY frontend/package*.json ./
RUN npm install

COPY frontend/ ./
RUN npm run build

# -------------------------------------------------------------
# Stage 2: Python Application Runner
# -------------------------------------------------------------
FROM python:3.11-slim
WORKDIR /app

# Install system dependencies (curl for healthcheck, libpq for postgres)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend application, reference kit, docs, and configs
COPY backend/ ./backend/
COPY kit/ ./kit/
COPY app/ ./app/
COPY docs/ ./docs/
COPY APPROACH.md DECISIONS.md pytest.ini ./

# Copy built frontend assets to frontend/dist for static serving
COPY --from=frontend-builder /app/frontend/dist ./frontend/dist

# Expose FastAPI port
EXPOSE 8000

# Default environment variables
ENV PORT=8000
ENV PYTHONUNBUFFERED=1

# Healthcheck targeting /health endpoint
HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=3 \
  CMD curl -f http://localhost:8000/health || exit 1

# Start Uvicorn server (auto-seeds master data & policy on first startup)
CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
