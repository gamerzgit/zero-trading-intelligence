# ZERO Dashboard Service (Milestone 5)

Real-time command center for the ZERO Trading Intelligence Platform.

## Overview

The dashboard provides a live view of the system state:
- **Regime Status**: Market state (GREEN/YELLOW/RED) with VIX level
- **Brain**: Top opportunities ranked by the core logic service
- **Scanner**: Active candidates from the scanner service

## Features

- **Auto-refresh**: Polls Redis every 2-5 seconds (configurable)
- **Real-time updates**: No manual refresh needed
- **Error handling**: Gracefully handles Redis disconnections and empty data
- **Traffic light display**: Visual indicator for market state
- **Highlighted opportunities**: Color-coded by probability

## Data Sources

Reads from Redis (read-only):
- `key:market_state` - Current market regime state
- `key:opportunity_rank` - Top ranked opportunities
- `key:active_candidates` - Active scanner candidates

## Running

### Docker Compose

```bash
docker compose --env-file .env -f infra/docker-compose.yml up -d zero-dashboard
```

### Access

Open in browser: `http://<jetson-ip>:8501`

## Configuration

Environment variables:
- `REDIS_HOST` - Redis host (default: `redis`)
- `REDIS_PORT` - Redis port (default: `6379`)

## Architecture

- **Framework**: Streamlit
- **Port**: 8501
- **Dependencies**: Redis (read-only)

## Health Check

The service exposes a health endpoint at `/_stcore/health` for Docker health checks.
