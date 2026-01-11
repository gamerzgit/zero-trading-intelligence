# API Contract

**Version:** 1.0  
**Last Updated:** 2026-01-11

**Base URL:** `http://localhost:8080` (from host) or `http://zero-query:8080` (from Docker network)

---

## ENDPOINTS

### 1. Query Mode (Mandatory)

**Endpoint:** `GET /query`

**Description:** Get full analytics for any ticker (not limited to scan universe)

**Query Parameters:**
- `ticker` (required): Ticker symbol (e.g., "TSLA", "SPY")
- `horizons` (optional): Comma-separated list of horizons to analyze (default: all)
  - Valid values: `H30`, `H2H`, `HDAY`, `HWEEK`
  - Example: `?ticker=TSLA&horizons=H30,H2H`

**Response:**
- **Status Code:** `200 OK`
- **Content-Type:** `application/json`
- **Body:** `QueryResponse` schema (see schemas.py)

**Example Request:**
```
GET /query?ticker=TSLA
GET /query?ticker=NVDA&horizons=H30,H2H
```

**Example Response:**
```json
{
  "schema_version": "1.0",
  "timestamp": "2026-01-11T12:00:00Z",
  "ticker": "TSLA",
  "eligible": true,
  "reason_codes": null,
  "in_top_opportunities": true,
  "why_not_ranked": null,
  "market_state": {
    "schema_version": "1.0",
    "timestamp": "2026-01-11T12:00:00Z",
    "state": "GREEN",
    "vix_level": 18.5,
    "reason": "Normal volatility, no event risk"
  },
  "attention_state": {
    "schema_version": "1.0",
    "timestamp": "2026-01-11T12:00:00Z",
    "attention_stability_score": 75.0,
    "attention_bucket": "STABLE",
    "risk_on_off_state": "RISK_ON"
  },
  "opportunities": [
    {
      "schema_version": "1.0",
      "timestamp": "2026-01-11T12:00:00Z",
      "ticker": "TSLA",
      "horizon": "H30",
      "opportunity_score": 85.5,
      "probability": 0.78,
      "target_atr": 1.2,
      "stop_atr": 0.8,
      "market_state": "GREEN",
      "attention_stability_score": 75.0,
      "why": ["Strong momentum", "VWAP interaction", "Institutional flow confirmed"]
    }
  ]
}
```

**Error Responses:**

| Status Code | Error | Description |
|------------|-------|-------------|
| `400` | `INVALID_TICKER` | Ticker symbol is invalid or empty |
| `400` | `INVALID_HORIZONS` | Invalid horizon values in horizons parameter |
| `404` | `TICKER_NOT_FOUND` | Ticker not found in data provider |
| `503` | `DATA_UNAVAILABLE` | Data provider unavailable or timeout |
| `500` | `INTERNAL_ERROR` | Internal server error |

**Error Response Format:**
```json
{
  "error": "INVALID_TICKER",
  "message": "Ticker symbol 'INVALID' is not valid",
  "timestamp": "2026-01-11T12:00:00Z"
}
```

---

### 2. Health Check

**Endpoint:** `GET /health`

**Description:** Service health check endpoint

**Response:**
- **Status Code:** `200 OK` (healthy), `503 Service Unavailable` (unhealthy)
- **Content-Type:** `application/json`
- **Body:** `HealthCheck` schema (see schemas.py)

**Example Response:**
```json
{
  "schema_version": "1.0",
  "timestamp": "2026-01-11T12:00:00Z",
  "service": "zero-query",
  "status": "healthy",
  "uptime_seconds": 3600.5,
  "last_update": "2026-01-11T12:00:00Z",
  "details": {
    "database_connected": true,
    "redis_connected": true,
    "data_provider_connected": true
  }
}
```

---

### 3. System Status

**Endpoint:** `GET /status`

**Description:** Get current system status (market state, attention state, etc.)

**Response:**
- **Status Code:** `200 OK`
- **Content-Type:** `application/json`
- **Body:** Combined system state

**Example Response:**
```json
{
  "schema_version": "1.0",
  "timestamp": "2026-01-11T12:00:00Z",
  "market_state": {
    "state": "GREEN",
    "vix_level": 18.5,
    "reason": "Normal volatility"
  },
  "attention_state": {
    "attention_stability_score": 75.0,
    "attention_bucket": "STABLE",
    "risk_on_off_state": "RISK_ON"
  },
  "narrative_state": {
    "theme": "AI sector momentum",
    "drivers": ["Earnings beats", "Product launches"],
    "time_horizon_bias": "H2H"
  },
  "stand_down": null
}
```

---

## ERROR CODES

| Code | HTTP Status | Description |
|------|-------------|-------------|
| `INVALID_TICKER` | 400 | Ticker symbol is invalid |
| `INVALID_HORIZONS` | 400 | Invalid horizon values |
| `TICKER_NOT_FOUND` | 404 | Ticker not found in data provider |
| `DATA_UNAVAILABLE` | 503 | Data provider unavailable |
| `INTERNAL_ERROR` | 500 | Internal server error |
| `SERVICE_UNAVAILABLE` | 503 | Service temporarily unavailable |

---

## RATE LIMITING

- **Query Mode:** 60 requests per minute per IP
- **Health Check:** No rate limit
- **Status:** 10 requests per minute per IP

---

## AUTHENTICATION

**Current:** No authentication required (local network only)

**Future:** If exposed externally, implement API key authentication

---

## VERSIONING

- **Current Version:** v1
- **Breaking Changes:** Require version in path (e.g., `/v2/query`)
- **Non-Breaking Changes:** Can be added to existing version

---

## NOTES

- All timestamps are in ISO 8601 format (UTC)
- All numeric values use standard JSON number types
- All probability values are 0.0-1.0 (not percentages)
- All scores are 0-100 (not 0-1)

---

**END OF API CONTRACT**

