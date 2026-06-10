#!/bin/bash
set -e

echo "Waiting for PostgreSQL to be ready..."
while ! pg_isready -h postgres -p 5432 -q; do
    sleep 1
done
echo "PostgreSQL is ready."

echo "Running Alembic migrations..."
alembic upgrade head
echo "Migrations complete."

echo "Starting FastAPI..."
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload