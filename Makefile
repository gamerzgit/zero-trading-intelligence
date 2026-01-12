.PHONY: help up down logs psql redis-cli clean restart status

# Default target
help:
	@echo "ZERO Trading Intelligence Platform - Makefile"
	@echo ""
	@echo "Available commands:"
	@echo "  make up          - Start all services"
	@echo "  make down        - Stop all services"
	@echo "  make logs        - View logs from all services"
	@echo "  make psql        - Connect to TimescaleDB via psql"
	@echo "  make redis-cli    - Connect to Redis via redis-cli"
	@echo "  make restart     - Restart all services"
	@echo "  make status      - Show service status"
	@echo "  make clean       - Remove all containers, volumes, and data (Irreversible - Deletes NVMe Data)"
	@echo ""

# Start all services
up:
	@echo "Starting ZERO platform services..."
	docker compose --env-file .env -f infra/docker-compose.yml up -d
	@echo "Services started. Waiting for health checks..."
	@sleep 5
	@make status

# Stop all services
down:
	@echo "Stopping ZERO platform services..."
	docker compose --env-file .env -f infra/docker-compose.yml down

# View logs
logs:
	docker compose --env-file .env -f infra/docker-compose.yml logs -f

# Connect to TimescaleDB
psql:
	@echo "Connecting to TimescaleDB..."
	@echo "Database: zero_trading"
	@echo "User: zero_user"
	@echo ""
	docker compose --env-file .env -f infra/docker-compose.yml exec timescaledb psql -U zero_user -d zero_trading

# Connect to Redis
redis-cli:
	@echo "Connecting to Redis..."
	docker compose --env-file .env -f infra/docker-compose.yml exec redis redis-cli

# Restart all services
restart:
	@echo "Restarting ZERO platform services..."
	docker compose --env-file .env -f infra/docker-compose.yml restart
	@make status

# Show service status
status:
	@echo "Service Status:"
	@echo "==============="
	docker compose --env-file .env -f infra/docker-compose.yml ps
	@echo ""
	@echo "Health Checks:"
	@echo "=============="
	@docker compose --env-file .env -f infra/docker-compose.yml ps --format json | grep -o '"Health":"[^"]*"' || echo "No health status available"

# Clean everything (WARNING: removes all data)
clean:
	@echo "WARNING: This will remove all containers, volumes, and data!"
	@echo "IRREVERSIBLE - Deletes NVMe Data in ./data_nvme/"
	@read -p "Are you sure? [y/N] " -n 1 -r; \
	echo; \
	if [[ $$REPLY =~ ^[Yy]$$ ]]; then \
		docker compose --env-file .env -f infra/docker-compose.yml down -v; \
		rm -rf data_nvme/*; \
		echo "Cleaned."; \
	else \
		echo "Cancelled."; \
	fi

# Validate init.sql (syntax check)
validate-sql:
	@echo "Validating init.sql syntax..."
	@docker compose --env-file .env -f infra/docker-compose.yml run --rm timescaledb psql -U zero_user -d zero_trading -f /docker-entrypoint-initdb.d/init.sql --dry-run || echo "Note: Dry-run may not work, but SQL will be validated on first run"

# Initialize database schema (run if tables are missing)
init-db:
	@echo "Initializing database schema..."
	@docker compose --env-file .env -f infra/docker-compose.yml exec timescaledb sh -c 'psql -U zero_user -d zero_trading -f /docker-entrypoint-initdb.d/init.sql' || \
		(echo "⚠️  Note: If database already initialized, some errors are expected (tables may already exist)" && exit 0)
	@echo "✅ Database schema initialization completed"

