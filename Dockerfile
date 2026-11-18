FROM python:3.11-slim as backend-builder

WORKDIR /app

# Install system dependencies for build
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies
COPY venv/pyvenv.cfg ./venv_check
RUN pip install --no-cache-dir \
    fastapi \
    uvicorn \
    pydantic \
    sqlalchemy \
    rapidfuzz \
    pypdf \
    python-multipart

# Node build for frontend
FROM node:20-slim as frontend-builder
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm install
COPY frontend/ ./
RUN npm run build

# Final runner stage
FROM python:3.11-slim
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install backend dependencies in runner
RUN pip install --no-cache-dir \
    fastapi \
    uvicorn \
    pydantic \
    sqlalchemy \
    rapidfuzz \
    pypdf \
    python-multipart

# Copy backend code, policies, kit, and master data
COPY backend/ ./backend/
COPY kit/ ./kit/
COPY app/ ./app/
COPY docs/ ./docs/
COPY APPROACH.md DECISIONS.md pytest.ini ./

# Seed SQLite database on build
RUN python -m backend.app.seed

# Copy built frontend assets
COPY --from=frontend-builder /app/frontend/dist ./frontend/dist

EXPOSE 8000

CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
