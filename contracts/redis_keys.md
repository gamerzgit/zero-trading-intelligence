# Redis Keys & Channels Contract

**Version:** 1.0  
**Last Updated:** 2026-01-11

**Naming Convention:**
- PubSub channels: `chan:<name>`
- Key-values: `key:<name>`
- Streams: `stream:<name>`

**CRITICAL ARCHITECTURE RULES:**
- **STATE lives ONLY in Redis key-value stores**
- **State change Pub/Sub messages are notifications only** (not full state payloads)
- **Market data streams (ticker/index/news) may publish full payloads** via Pub/Sub
- **Grafana reads ONLY from TimescaleDB** (not Redis)

---

## PUBSUB CHANNELS

**IMPORTANT:** Channels serve two distinct purposes:
1. **MARKET DATA STREAMS** - Full payloads (ticker/index/vol/news/events)
2. **STATE CHANGE NOTIFICATIONS** - Notifications only (not full state payloads)

---

### MARKET DATA STREAMS (Full Payloads)

These channels publish complete data payloads for real-time market data ingestion.

#### Price & Market Data

| Channel Name | Type | Publisher | Subscribers | Payload Structure |
|-------------|------|-----------|-------------|-------------------|
| `chan:ticker_update` | PubSub | zero-ingest-price | zero-scanner, zero-core-logic | `TickerUpdate` (see schemas.py) - **FULL PAYLOAD** |
| `chan:index_update` | PubSub | zero-ingest-price | zero-regime, zero-attention | `IndexUpdate` (see schemas.py) - **FULL PAYLOAD** |
| `chan:volatility_update` | PubSub | zero-ingest-price | zero-regime | `VolatilityUpdate` (see schemas.py) - **FULL PAYLOAD** |

#### News & Events

| Channel Name | Type | Publisher | Subscribers | Payload Structure |
|-------------|------|-----------|-------------|-------------------|
| `chan:news_raw` | PubSub | zero-ingest-news | zero-narrative-llm | `NewsRaw` (see schemas.py) - **FULL PAYLOAD** |
| `chan:event_alert` | PubSub | zero-ingest-news | zero-regime, zero-urgency | `EventAlert` (see schemas.py) - **FULL PAYLOAD** |

---

### STATE CHANGE NOTIFICATIONS (Notifications Only - NOT Full State)

| Channel Name | Type | Publisher | Subscribers | Payload Structure |
|-------------|------|-----------|-------------|-------------------|
| `chan:market_state_changed` | PubSub | zero-regime | zero-scanner, zero-core-logic, zero-urgency | `StateChangeNotification` (see schemas.py) |
| `chan:attention_state_changed` | PubSub | zero-attention | zero-core-logic, zero-urgency | `StateChangeNotification` (see schemas.py) |
| `chan:narrative_state_changed` | PubSub | zero-narrative-llm | zero-core-logic | `StateChangeNotification` (see schemas.py) |

**StateChangeNotification Payload (NOT full state):**
```json
{
  "schema_version": "1.0",
  "timestamp": "2026-01-11T12:00:00Z",
  "changed_fields": ["state", "risk_state"],
  "state_key": "key:market_state"
}
```

**Subscribers must fetch full state from Redis key-value store using `state_key`.**

---

### OPPORTUNITY DISCOVERY (Internal Data Streams)

| Channel Name | Type | Publisher | Subscribers | Payload Structure |
|-------------|------|-----------|-------------|-------------------|
| `chan:active_candidates` | PubSub | zero-scanner | zero-core-logic | `CandidateList` (see schemas.py) |
| `chan:opportunity_update` | PubSub | zero-core-logic | zero-urgency | `OpportunityRank` (see schemas.py) |
| `chan:urgency_flags` | PubSub | zero-urgency | (internal only) | `UrgencyFlags` (see schemas.py) |

**Note:** Grafana does NOT subscribe to Redis channels. Grafana reads from TimescaleDB only. If Grafana needs to display these values, they must be written to TimescaleDB tables (e.g., `ops_metrics` or `system_state_log`).

### Stand-Down Signals

| Channel Name | Type | Publisher | Subscribers | Payload Structure |
|-------------|------|-----------|-------------|-------------------|
| `chan:stand_down` | PubSub | zero-regime, zero-urgency | zero-scanner, zero-core-logic | `StandDownSignal` (see schemas.py) |

---

## KEY-VALUE STORES (State Storage)

### State Keys (Current State - Persistent)

| Key Name | Type | Writer | Readers | TTL | Payload Structure |
|----------|------|--------|---------|-----|-------------------|
| `key:market_state` | String (JSON) | zero-regime | All services | None | `MarketState` (see schemas.py) |
| `key:attention_state` | String (JSON) | zero-attention | zero-core-logic, zero-urgency | None | `AttentionState` (see schemas.py) |
| `key:narrative_state` | String (JSON) | zero-narrative-llm | zero-core-logic | None | `NarrativeState` (see schemas.py) |
| `key:stand_down_reason` | String (JSON) | zero-regime, zero-urgency | All services | None | `StandDownReason` (see schemas.py) |

### Ephemeral State Keys (With TTL)

| Key Name | Type | Writer | Readers | TTL | Payload Structure |
|----------|------|--------|---------|-----|-------------------|
| `key:active_candidates` | String (JSON) | zero-scanner | zero-core-logic | 300s (5 min) | `CandidateList` (see schemas.py) |
| `key:opportunity_rank` | String (JSON) | zero-core-logic | (internal) | Horizon-dependent | `OpportunityRank` (see schemas.py) |
| `key:urgency_flags` | String (JSON) | zero-urgency | (internal) | 120s (2 min) | `UrgencyFlags` (see schemas.py) |

**TTL Rules:**
- `active_candidates`: 300s (candidates refresh every scan cycle)
- `opportunity_rank`: TTL = horizon duration (H30: 3600s, H2H: 14400s, HDAY: 86400s)
- `urgency_flags`: 120s (urgency changes frequently)

### Configuration Keys

| Key Name | Type | Writer | Readers | TTL | Payload Structure |
|----------|------|--------|---------|-----|-------------------|
| `key:scan_universe` | String (JSON) | Config | zero-scanner | None | List of tickers |
| `key:system_config` | String (JSON) | Config | All services | None | System configuration |

### Cache Keys

| Key Name | Type | Writer | Readers | TTL | Payload Structure |
|----------|------|--------|---------|-----|-------------------|
| `key:last_scan_time` | String | zero-scanner | (internal) | None | ISO timestamp |
| `key:last_regime_update` | String | zero-regime | (internal) | None | ISO timestamp |
| `key:ingestion_lag` | String | zero-ingest-price | (internal) | 60s | Lag in milliseconds |
| `key:redis_backpressure` | String | (monitoring) | All services | 30s | Backpressure flag (true/false) |

---

## STREAMS (Optional - For Audit/Replay)

| Stream Name | Type | Writer | Readers | Payload Structure |
|-------------|------|--------|---------|-------------------|
| `stream:market_state_history` | Stream | zero-regime | truth-test | `MarketState` (see schemas.py) |
| `stream:opportunity_history` | Stream | zero-core-logic | truth-test | `Opportunity` (see schemas.py) |

---

## QUERY MODE (HTTP-Only, NOT Redis)

**CRITICAL:** Query Mode is implemented via HTTP endpoint, NOT Redis Pub/Sub.

- **Endpoint:** `GET /query?ticker=TSLA`
- **Response:** HTTP JSON response
- **Redis Usage:** Internal only (zero-query service may use Redis internally, but NOT as API surface)

**Removed Channels:**
- ❌ `chan:query_request` (removed - use HTTP)
- ❌ `chan:query_response` (removed - use HTTP)

---

## PAYLOAD SCHEMA REFERENCES

All payload structures are defined in `/contracts/schemas.py` as Pydantic models:

- `TickerUpdate`: Price/volume update for a ticker
- `IndexUpdate`: Index (SPY/QQQ/IWM) update
- `VolatilityUpdate`: VIX/volatility update
- `NewsRaw`: Raw news headline/article
- `EventAlert`: Economic event/earnings alert
- `StateChangeNotification`: State change notification (changed fields only)
- `MarketState`: Level 0 permission state (GREEN/YELLOW/RED) - stored in `key:market_state`
- `AttentionState`: Level 1 attention state (score-based, 0-100) - stored in `key:attention_state`
- `NarrativeState`: Level 1 narrative state (LLM output) - stored in `key:narrative_state`
- `StandDownReason`: Stand-down signal with reason - stored in `key:stand_down_reason`
- `CandidateList`: Level 2 scanner output (list of candidates) - stored in `key:active_candidates`
- `Opportunity`: Level 3 opportunity (with probability)
- `OpportunityRank`: Top-N ranked opportunities - stored in `key:opportunity_rank`
- `UrgencyFlags`: Level 4 urgency flags - stored in `key:urgency_flags`

---

## REDIS CONNECTION

**Inside Docker containers:**
- **Host:** `redis` (Docker service name)
- **Port:** 6379
- **Database:** 0 (default)
- **Password:** None (local network only)

**From host machine (if ports published):**
- **Host:** `localhost`
- **Port:** 6379

---

## MESSAGE FORMAT

All messages published to Redis channels MUST:
1. Be JSON-encoded strings
2. Include `schema_version` field
3. Include `timestamp` field (ISO 8601 format)
4. Match the Pydantic model in `schemas.py`

---

## ERROR HANDLING

- If subscriber fails to parse message: Log error, skip message
- If publisher fails to publish: Retry 3 times, then log error
- If Redis unavailable: Service must degrade gracefully, log error
- **If Redis backpressure detected:** Scanner throttles/pauses, log backpressure event

---

## BACKPRESSURE PROTECTION

### Detection

Monitor Redis:
- Memory usage > 80% capacity
- Command queue length > 1000
- Latency > 100ms

### Response

If backpressure detected:
1. Set `key:redis_backpressure` = "true" (TTL: 30s)
2. Scanner throttles (reduces scan frequency) or pauses
3. Log backpressure event with severity
4. Services continue with cached state (graceful degradation)

---

**END OF REDIS CONTRACT**
