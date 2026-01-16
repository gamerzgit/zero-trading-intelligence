# ============================================
# BEAST ENGINE - Makefile
# ============================================
# THE ULTIMATE 0DTE TRADING INTELLIGENCE
# ============================================

.PHONY: help install run scan query brief docker-build docker-up docker-down docker-logs clean test

# Default target
help:
	@echo ""
	@echo "  🦁 BEAST ENGINE - Commands"
	@echo "  =========================="
	@echo ""
	@echo "  make install    - Install Python dependencies"
	@echo "  make run        - Run continuous scanning"
	@echo "  make scan       - Single market scan"
	@echo "  make query S=SPY - Query specific symbol"
	@echo "  make brief      - Send morning brief"
	@echo ""
	@echo "  Docker Commands:"
	@echo "  make docker-build - Build Docker image"
	@echo "  make docker-up    - Start containers"
	@echo "  make docker-down  - Stop containers"
	@echo "  make docker-logs  - View logs"
	@echo ""
	@echo "  make clean      - Clean logs and cache"
	@echo "  make test       - Test the engine"
	@echo ""

# Install dependencies
install:
	pip install -r requirements.txt

# Run continuous scanning
run:
	python beast_engine.py

# Single scan
scan:
	python beast_engine.py scan

# Query specific symbol (usage: make query S=SPY)
query:
	python beast_engine.py query $(S)

# Send morning brief
brief:
	python beast_engine.py brief

# Docker commands
docker-build:
	docker compose build

docker-up:
	docker compose up -d

docker-down:
	docker compose down

docker-logs:
	docker compose logs -f beast

# Clean logs and cache
clean:
	rm -rf logs/*.log
	rm -rf __pycache__
	rm -rf .pytest_cache

# Test the engine
test:
	python -c "from beast_engine import BeastEngine, Config; print('✅ Import OK')"
	python -c "import pandas; import numpy; import joblib; print('✅ Dependencies OK')"
	python -c "import alpaca; print('✅ Alpaca OK')"
	@echo ""
	@echo "🦁 All tests passed!"
