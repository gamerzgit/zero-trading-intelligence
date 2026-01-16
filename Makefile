# ============================================
# BEAST ENGINE - Makefile
# ============================================
# THE ULTIMATE 0DTE TRADING INTELLIGENCE
# ============================================

.PHONY: help install run run-final test-final scan query brief patterns validate docker-build docker-up docker-down docker-logs clean test train train-quick train-full assistant telegram web

# Default target
help:
	@echo ""
	@echo "  BEAST ENGINE - Commands"
	@echo "  =========================="
	@echo ""
	@echo "  SISTEMA PRINCIPAL (VALIDADO):"
	@echo "  make run-final      - Ejecutar sistema GANADOR (12-14h ET)"
	@echo "  make test-final     - Probar sistema y enviar alerta"
	@echo ""
	@echo "  OTROS COMANDOS:"
	@echo "  make install        - Instalar dependencias"
	@echo "  make run            - Ejecutar beast_engine.py original"
	@echo "  make scan           - Escaneo unico del mercado"
	@echo "  make query S=SPY    - Analizar simbolo especifico"
	@echo "  make brief          - Enviar brief matutino"
	@echo "  make patterns       - Escanear patrones"
	@echo ""
	@echo "  ASISTENTE INTERACTIVO:"
	@echo "  make assistant      - CLI interactivo (terminal)"
	@echo "  make telegram       - Bot de Telegram (celular)"
	@echo "  make web            - Web interface (localhost:8080)"
	@echo ""
	@echo "  VALIDACION:"
	@echo "  make validate       - Backtest del sistema (90 dias)"
	@echo "  make validate-refined - Backtest con configuraciones"
	@echo ""
	@echo "  AI TRAINING:"
	@echo "  make train          - Reentrenar modelos (60 dias)"
	@echo "  make train-quick    - Entrenamiento rapido (30 dias)"
	@echo "  make train-full     - Entrenamiento completo (1 anio)"
	@echo ""
	@echo "  DOCKER:"
	@echo "  make docker-build   - Construir imagen Docker"
	@echo "  make docker-up      - Iniciar contenedores"
	@echo "  make docker-down    - Detener contenedores"
	@echo "  make docker-logs    - Ver logs"
	@echo ""
	@echo "  make clean          - Limpiar logs y cache"
	@echo "  make test           - Probar imports"
	@echo ""

# Install dependencies
install:
	pip install -r requirements.txt

# ============================================
# SISTEMA GANADOR - CONFIGURACION VALIDADA
# ============================================

# Ejecutar sistema ganador (24/7 durante market hours)
run-final:
	python beast_final.py

# Test del sistema ganador
test-final:
	python beast_final.py test

# ============================================
# OTROS COMANDOS
# ============================================

# Run continuous scanning (original)
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

# Scan for chart patterns
patterns:
	python beast_engine.py patterns

# ============================================
# VALIDACION Y BACKTEST
# ============================================

# Backtest completo
validate:
	python validate_probability_system.py

# Backtest con configuraciones refinadas
validate-refined:
	python validate_refined.py

# ============================================
# AI TRAINING
# ============================================

# Train/Retrain AI models with fresh data
train:
	python train_models.py --days 60

train-quick:
	python train_models.py --days 30

train-full:
	python train_models.py --days 365

# ============================================
# DOCKER
# ============================================

docker-build:
	docker compose build

docker-up:
	docker compose up -d

docker-down:
	docker compose down

docker-logs:
	docker compose logs -f beast

# ============================================
# UTILIDADES
# ============================================

# Clean logs and cache
clean:
	rm -rf logs/*.log
	rm -rf __pycache__
	rm -rf .pytest_cache

# Test the engine
test:
	python -c "from beast_engine import BeastEngine, Config; print('Import OK')"
	python -c "import pandas; import numpy; import joblib; print('Dependencies OK')"
	python -c "import alpaca; print('Alpaca OK')"
	@echo ""
	@echo "All tests passed!"

# ============================================
# ASISTENTE INTERACTIVO
# ============================================

# CLI interactivo - escribes preguntas en terminal
assistant:
	python beast_assistant.py

# Bot de Telegram - CHAT + ALERTAS INTELIGENTES
telegram:
	python beast_telegram.py

# Web interface - abres http://localhost:8080
web:
	python beast_web.py

# ============================================
# STATUS
# ============================================

# Status - muestra configuracion actual
status:
	@echo ""
	@echo "BEAST ENGINE STATUS"
	@echo "==================="
	@echo ""
	@echo "Configuracion validada:"
	@echo "  - Horas rentables: 12:00-14:00 ET"
	@echo "  - ADX minimo: 25"
	@echo "  - Win Rate esperado: 47.7%"
	@echo "  - EV esperado: +0.0623%/trade"
	@echo "  - Profit Factor: 1.63"
	@echo ""
	@echo "Para iniciar: make run-final"
	@echo ""
