FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    POETRY_VIRTUALENVS_CREATE=false \
    POETRY_NO_INTERACTION=1

WORKDIR /app

# System deps (kept minimal). curl used for basic debugging/health in containers.
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
  && rm -rf /var/lib/apt/lists/*

# Poetry
RUN pip install --no-cache-dir poetry==1.8.5

# Install deps first for better layer caching
COPY pyproject.toml poetry.lock* /app/
RUN poetry install --no-root

# Copy application code
COPY . /app

EXPOSE 8000

