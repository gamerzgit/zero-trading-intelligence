#!/bin/bash
# Fix Deployment Issues on Jetson
# This script addresses:
# 1. Rebuild ingest container without cache (fixes redis package)
# 2. Initialize database schema if missing
# 3. Verify .env file is being used

set -e

echo "🔧 Fixing deployment issues..."

# Check if .env exists
if [ ! -f .env ]; then
    echo "❌ ERROR: .env file not found in current directory"
    echo "Please ensure you're in the project root and .env exists"
    exit 1
fi

# Verify passwords are set
if ! grep -q "^POSTGRES_PASSWORD=" .env || ! grep -q "^DB_PASSWORD=" .env; then
    echo "❌ ERROR: POSTGRES_PASSWORD or DB_PASSWORD not set in .env"
    exit 1
fi

echo "✅ .env file found and passwords set"

# Source .env to get passwords
export $(grep -v '^#' .env | xargs)

# Stop services
echo ""
echo "🛑 Stopping services..."
docker compose --env-file .env -f infra/docker-compose.yml down

# Rebuild ingest service without cache
echo ""
echo "🔨 Rebuilding zero-ingest-price container (no cache)..."
docker compose --env-file .env -f infra/docker-compose.yml build --no-cache zero-ingest-price

# Start timescaledb first
echo ""
echo "🚀 Starting TimescaleDB..."
docker compose --env-file .env -f infra/docker-compose.yml up -d timescaledb

# Wait for database to be ready
echo "⏳ Waiting for database to be ready..."
sleep 10
for i in {1..30}; do
    if docker compose --env-file .env -f infra/docker-compose.yml exec -T timescaledb pg_isready -U "${POSTGRES_USER:-zero_user}" > /dev/null 2>&1; then
        echo "✅ Database is ready"
        break
    fi
    if [ $i -eq 30 ]; then
        echo "❌ Database failed to start"
        exit 1
    fi
    sleep 2
done

# Check if regime_log table exists, if not run init.sql
echo ""
echo "🔍 Checking database schema..."
TABLE_EXISTS=$(docker compose --env-file .env -f infra/docker-compose.yml exec -T timescaledb psql -U "${POSTGRES_USER:-zero_user}" -d "${POSTGRES_DB:-zero_trading}" -tAc "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'regime_log');" 2>/dev/null || echo "false")

if [ "$TABLE_EXISTS" = "t" ] || [ "$TABLE_EXISTS" = "true" ]; then
    echo "✅ Database schema already exists"
else
    echo "📝 Initializing database schema..."
    docker compose --env-file .env -f infra/docker-compose.yml exec -T timescaledb psql -U "${POSTGRES_USER:-zero_user}" -d "${POSTGRES_DB:-zero_trading}" -f /docker-entrypoint-initdb.d/init.sql
    echo "✅ Database schema initialized"
fi

# Start all services
echo ""
echo "🚀 Starting all services..."
docker compose --env-file .env -f infra/docker-compose.yml up -d

echo ""
echo "✅ Deployment fix complete!"
echo ""
echo "Waiting 10 seconds for services to start..."
sleep 10

# Show status
docker compose --env-file .env -f infra/docker-compose.yml ps
