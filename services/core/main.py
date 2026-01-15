"""
ZERO Core Logic Service (Level 3 - Opportunity Ranking)
Ranks Active Candidates using deterministic, explainable scoring
NOTE: Uses confidence (heuristic) not real-world probability until Milestone 6 (Truth Test calibration)
"""

import asyncio
import os
import sys
import logging
import json
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Dict, Any
import pandas as pd

import asyncpg
import redis.asyncio as redis
from aiohttp import web

# Add parent directory to path for contracts
project_root = os.path.join(os.path.dirname(__file__), '../../')
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from contracts.schemas import (
    CandidateList, Opportunity, OpportunityRank, MarketState, HealthCheck
)

try:
    from features import extract_features
    from scoring import calculate_opportunity_score
    from confidence import enrich_opportunity
    from query import QueryEngine
except ImportError:
    # Handle relative imports for Docker
    from .features import extract_features
    from .scoring import calculate_opportunity_score
    from .confidence import enrich_opportunity
    from .query import QueryEngine

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class ZeroCoreLogicService:
    """ZERO Core Logic Service - Level 3 Opportunity Ranking"""
    
    def __init__(self):
        # Configuration
        self.db_host = os.getenv('DB_HOST', 'timescaledb')
        self.db_port = int(os.getenv('DB_PORT', '5432'))
        self.db_name = os.getenv('DB_NAME', 'zero_trading')
        self.db_user = os.getenv('DB_USER', 'zero_user')
        self.db_password = os.getenv('DB_PASSWORD')
        
        self.redis_host = os.getenv('REDIS_HOST', 'redis')
        self.redis_port = int(os.getenv('REDIS_PORT', '6379'))
        
        self.api_port = int(os.getenv('CORE_API_PORT', '8002'))
        
        # Components
        self.db_pool: Optional[asyncpg.Pool] = None
        self.redis_client: Optional[redis.Redis] = None
        self.redis_pubsub: Optional[redis.client.PubSub] = None
        
        # State
        self.is_running = False
        self.market_state: Optional[MarketState] = None
        self.last_ranking_time: Optional[datetime] = None
        self.current_rankings: Dict[str, OpportunityRank] = {}  # horizon -> OpportunityRank
        self.calibration_state: Optional[Dict[str, Any]] = None  # From key:calibration_state
        self.attention_state: Optional[Dict[str, Any]] = None  # From key:attention_state
        
        # Query Engine (SPEC_LOCK §5.2)
        self.query_engine: Optional[QueryEngine] = None
        
    async def connect_db(self):
        """Connect to TimescaleDB"""
        try:
            self.db_pool = await asyncpg.create_pool(
                host=self.db_host,
                port=self.db_port,
                database=self.db_name,
                user=self.db_user,
                password=self.db_password,
                min_size=2,
                max_size=10
            )
            logger.info("✅ Database connected")
        except Exception as e:
            logger.error(f"❌ Database connection failed: {e}")
            raise
    
    async def connect_redis(self):
        """Connect to Redis"""
        try:
            self.redis_client = redis.Redis(
                host=self.redis_host,
                port=self.redis_port,
                decode_responses=False  # Keep bytes for pub/sub compatibility
            )
            await self.redis_client.ping()
            logger.info("✅ Redis connected")
            
            # Subscribe to scanner updates
            self.redis_pubsub = self.redis_client.pubsub()
            await self.redis_pubsub.subscribe('chan:active_candidates')
            logger.info("✅ Subscribed to chan:active_candidates")
            
        except Exception as e:
            logger.error(f"❌ Redis connection failed: {e}")
            raise
    
    async def load_market_state(self) -> Optional[MarketState]:
        """Load current market state from Redis"""
        if not self.redis_client:
            return None
        
        try:
            state_json = await self.redis_client.get('key:market_state')
            if state_json:
                if isinstance(state_json, bytes):
                    state_json = state_json.decode('utf-8')
                state_dict = json.loads(state_json)
                market_state = MarketState(**state_dict)
                # Update cached state
                self.market_state = market_state
                return market_state
            else:
                logger.debug("⚠️  No market state found in Redis (key:market_state is empty)")
        except Exception as e:
            logger.warning(f"⚠️  Failed to load market state: {e}")
        
        return None
    
    async def load_calibration_state(self) -> Optional[Dict[str, Any]]:
        """
        Load calibration state from Redis (Milestone 7).
        Used to apply shrink factors to probabilities.
        """
        if not self.redis_client:
            return None
        
        try:
            cal_json = await self.redis_client.get('key:calibration_state')
            if cal_json:
                if isinstance(cal_json, bytes):
                    cal_json = cal_json.decode('utf-8')
                self.calibration_state = json.loads(cal_json)
                logger.debug(f"📊 Loaded calibration state: {len(self.calibration_state.get('buckets', {}))} buckets")
                return self.calibration_state
        except Exception as e:
            logger.warning(f"⚠️  Failed to load calibration state: {e}")
        
        return None
    
    def get_shrink_factor(self, horizon: str, market_state: str, attention_bucket: str) -> float:
        """
        Get shrink factor for a specific bucket from calibration state.
        Per SPEC_LOCK §6.2: Only shrink, never boost above 1.0.
        """
        if not self.calibration_state:
            return 1.0  # No calibration data - no shrink
        
        bucket_key = f"{horizon}_{market_state}_{attention_bucket}"
        buckets = self.calibration_state.get("buckets", {})
        
        if bucket_key in buckets:
            shrink = buckets[bucket_key].get("shrink_factor", 1.0)
            # Never boost above 1.0
            return min(shrink, 1.0)
        
        # Fall back to global shrink
        global_stats = self.calibration_state.get("global_stats", {})
        global_shrink = global_stats.get("global_shrink", 1.0)
        return min(global_shrink, 1.0)
    
    def apply_calibration(self, probability_raw: float, shrink_factor: float) -> float:
        """
        Apply calibration shrink to probability.
        Per SPEC_LOCK §6.2: Never increase above raw, only shrink.
        """
        adjusted = probability_raw * shrink_factor
        return max(0.0, min(1.0, adjusted))
    
    async def load_attention_state(self) -> Dict[str, Any]:
        """
        Load attention state from Redis (Milestone 8).
        Returns default if not available.
        """
        default_state = {
            "attention_stability_score": 50.0,
            "attention_bucket": "UNSTABLE",
            "risk_on_off_state": "NEUTRAL",
            "correlation_regime": "Unknown"
        }
        
        if not self.redis_client:
            return default_state
        
        try:
            att_json = await self.redis_client.get('key:attention_state')
            if att_json:
                if isinstance(att_json, bytes):
                    att_json = att_json.decode('utf-8')
                self.attention_state = json.loads(att_json)
                logger.info(
                    f"📊 Loaded attention state: score={self.attention_state.get('attention_stability_score')}, "
                    f"bucket={self.attention_state.get('attention_bucket')}"
                )
                return self.attention_state
        except Exception as e:
            logger.warning(f"⚠️  Failed to load attention state: {e}")
        
        return default_state
    
    def should_gate_horizon(self, horizon: str, attention_score: float) -> bool:
        """
        Check if horizon should be gated based on attention score.
        Per SPEC_LOCK:
        - CHAOTIC (<40): only allow H30
        - UNSTABLE (40-69): gate HWEEK
        """
        if attention_score < 40:  # CHAOTIC
            # Only allow H30
            return horizon in ["H2H", "HDAY", "HWEEK"]
        elif attention_score < 70:  # UNSTABLE
            # Gate HWEEK
            return horizon == "HWEEK"
        return False  # STABLE - allow all
    
    async def fetch_candles(self, ticker: str, table: str, lookback_periods: int) -> Optional[pd.DataFrame]:
        """Fetch recent candles from database"""
        if not self.db_pool:
            return None
        
        try:
            # Fetch the most recent N candles regardless of time
            # This ensures we get enough data even if candles are older
            query = f"""
                SELECT time, open, high, low, close, volume
                FROM {table}
                WHERE ticker = $1
                ORDER BY time DESC
                LIMIT $2
            """
            
            rows = await self.db_pool.fetch(query, ticker, lookback_periods)
            
            if not rows:
                return None
            
            # Reverse to get chronological order (oldest first)
            rows = list(reversed(rows))
            
            # Convert to DataFrame
            data = {
                'time': [r['time'] for r in rows],
                'open': [float(r['open']) for r in rows],
                'high': [float(r['high']) for r in rows],
                'low': [float(r['low']) for r in rows],
                'close': [float(r['close']) for r in rows],
                'volume': [int(r['volume']) for r in rows],
            }
            
            return pd.DataFrame(data)
        except Exception as e:
            logger.warning(f"⚠️  Failed to fetch {table} candles for {ticker}: {e}")
            return None
    
    async def rank_candidates(
        self,
        candidates: List[str],
        horizon: str,
        market_state: MarketState
    ) -> List[Opportunity]:
        """Rank candidates and return Opportunity objects"""
        opportunities = []
        
        for ticker in candidates:
            try:
                # Fetch candles (1m, 5m, and optionally 1d for swing horizons)
                candles_1m = await self.fetch_candles(ticker, "candles_1m", lookback_periods=100)
                candles_5m = await self.fetch_candles(ticker, "candles_5m", lookback_periods=20)
                candles_1d = None
                
                # Fetch 1d candles for swing horizons
                if horizon in ["HDAY", "HWEEK"]:
                    candles_1d = await self.fetch_candles(ticker, "candles_1d", lookback_periods=20)
                
                logger.info(f"📊 Fetched candles for {ticker}: 1m={len(candles_1m) if candles_1m is not None else 0}, 5m={len(candles_5m) if candles_5m is not None else 0}")
                
                if candles_1m is None or len(candles_1m) < 20:
                    logger.info(f"⚠️  Skipping {ticker}: Insufficient 1m data ({len(candles_1m) if candles_1m is not None else 0} candles, need 20+)")
                    continue
                
                if candles_5m is None or len(candles_5m) < 20:
                    logger.info(f"⚠️  Skipping {ticker}: Insufficient 5m data ({len(candles_5m) if candles_5m is not None else 0} candles, need 20+)")
                    continue
                
                # Extract features from multiple timeframes
                features = extract_features(candles_1m, candles_5m, candles_1d)
                
                # Calculate scores
                score_data = calculate_opportunity_score(features, market_state.state)
                
                # Get current price and ATR from 5m (more stable)
                current_price = features.get('current_price', 0.0)
                atr = features.get('atr_5m', 0.0)
                
                if atr == 0.0 or current_price == 0.0:
                    logger.info(f"⚠️  Skipping {ticker}: Invalid price/ATR (price={current_price}, atr={atr})")
                    continue
                
                # Enrich with confidence and ATR levels
                # Load attention state from Redis (Milestone 8)
                attention_score = self.attention_state.get("attention_stability_score", 50.0) if self.attention_state else 50.0
                
                enriched = enrich_opportunity(
                    score_data=score_data,
                    ticker=ticker,
                    horizon=horizon,
                    market_state=market_state.state,
                    current_price=current_price,
                    atr=atr,
                    attention_stability_score=attention_score
                )
                
                # Map confidence_pct to probability field (schema requirement)
                # NOTE: This is HEURISTIC until calibrated by Truth Test (Milestone 7)
                confidence_pct_raw = enriched["confidence_pct"]
                
                # Apply calibration shrink factor (Milestone 7)
                # Per SPEC_LOCK §6.2: Only shrink, never boost above raw
                attention_bucket = enriched.get("attention_bucket", "UNSTABLE")
                shrink_factor = self.get_shrink_factor(horizon, market_state.state, attention_bucket)
                confidence_pct = self.apply_calibration(confidence_pct_raw, shrink_factor)
                
                # Build why list with calibration info
                why_list = enriched["why"] + [f"Confidence: {enriched['confidence_band']} (HEURISTIC)"]
                if shrink_factor < 1.0:
                    why_list.append(f"Calibration shrink: {shrink_factor:.2f}")
                
                # Create Opportunity object
                # Schema requires "probability" field, but we document it's heuristic
                opportunity = Opportunity(
                    ticker=enriched["ticker"],
                    horizon=enriched["horizon"],
                    opportunity_score=enriched["opportunity_score"],
                    probability=confidence_pct,  # HEURISTIC - calibrated by shrink factor
                    target_atr=enriched["target_atr"],
                    stop_atr=enriched["stop_atr"],
                    market_state=enriched["market_state"],
                    attention_stability_score=enriched["attention_stability_score"],
                    attention_bucket=enriched["attention_bucket"],
                    attention_alignment=enriched["attention_alignment"],
                    why=why_list,
                    regime_dependency=None,  # TODO: Add regime dependency logic
                    key_levels=None,  # TODO: Add VWAP/support/resistance levels
                    invalidation_rule=None,  # TODO: Add invalidation rules
                    liquidity_grade=None  # TODO: Add liquidity grade
                )
                
                opportunities.append(opportunity)
                logger.info(f"✅ Created opportunity for {ticker} ({horizon}): score={opportunity.opportunity_score:.2f}, confidence={enriched['confidence_band']}")
                
            except Exception as e:
                logger.warning(f"⚠️  Error ranking {ticker}: {e}", exc_info=True)
                continue
        
        # Sort by opportunity_score (descending) and return Top 10
        opportunities.sort(key=lambda x: x.opportunity_score, reverse=True)
        return opportunities[:10]
    
    async def process_scanner_update(self, candidate_list: CandidateList):
        """Process scanner update and rank candidates"""
        # Load current market state
        market_state = await self.load_market_state()
        if not market_state:
            logger.warning("⚠️  No market state available, skipping ranking")
            return
        
        # VETO: If MarketState is RED, do not rank/publish
        if market_state.state == "RED":
            logger.info(f"🚫 MarketState is RED ({market_state.reason}) - vetoing ranking")
            return
        
        # Load calibration state (Milestone 7)
        await self.load_calibration_state()
        
        # Load attention state (Milestone 8)
        attention_state = await self.load_attention_state()
        attention_score = attention_state.get("attention_stability_score", 50.0)
        attention_bucket = attention_state.get("attention_bucket", "UNSTABLE")
        
        # Gate horizons based on attention (SPEC_LOCK requirement)
        if self.should_gate_horizon(candidate_list.horizon, attention_score):
            logger.info(
                f"🚫 Horizon {candidate_list.horizon} gated due to attention={attention_score} ({attention_bucket})"
            )
            return
        
        logger.info(f"📊 Ranking {len(candidate_list.candidates)} candidates for {candidate_list.horizon}")
        
        # Rank candidates
        opportunities = await self.rank_candidates(
            candidates=candidate_list.candidates,
            horizon=candidate_list.horizon,
            market_state=market_state
        )
        
        if not opportunities:
            logger.info(f"⚠️  No opportunities generated for {candidate_list.horizon}")
            return
        
        # Create OpportunityRank
        rank_time = datetime.now(timezone.utc)
        opportunity_rank = OpportunityRank(
            horizon=candidate_list.horizon,
            opportunities=opportunities,
            rank_time=rank_time,
            total_candidates=len(candidate_list.candidates)
        )
        
        # Store in state
        self.current_rankings[candidate_list.horizon] = opportunity_rank
        self.last_ranking_time = rank_time
        
        # Publish to Redis
        logger.info(f"📡 Publishing opportunity rank to Redis...")
        await self.publish_opportunity_rank(opportunity_rank)
        
        # Write Top 5 to database
        logger.info(f"💾 Writing opportunities to database...")
        await self.write_opportunity_log(opportunities[:5])
        
        logger.info(f"✅ Ranked {len(opportunities)} opportunities for {candidate_list.horizon}")
    
    async def publish_opportunity_rank(self, opportunity_rank: OpportunityRank):
        """Publish opportunity rank to Redis"""
        if not self.redis_client:
            logger.warning("⚠️  Redis client not available, skipping publish")
            return
        
        try:
            # Test connection
            await self.redis_client.ping()
            
            # Publish to channel (per Milestone 4 spec: chan:opportunity_update)
            channel = "chan:opportunity_update"
            payload_json = opportunity_rank.model_dump_json()
            payload_bytes = payload_json.encode('utf-8')
            
            logger.info(f"🔄 Attempting to publish to {channel} and store key:opportunity_rank...")
            
            # Publish to channel (redis.asyncio accepts strings for channel names)
            subscribers = await self.redis_client.publish(channel, payload_bytes)
            logger.info(f"📤 Published to {channel} ({subscribers} subscribers)")
            
            # Store in key with TTL (60 seconds as per contract)
            # redis.asyncio accepts strings for key names
            await self.redis_client.setex(
                "key:opportunity_rank",
                60,  # TTL: 60 seconds
                payload_bytes
            )
            logger.info(f"💾 Stored key:opportunity_rank with TTL=60s ({len(opportunity_rank.opportunities)} opportunities)")
            
            # Verify it was stored
            stored = await self.redis_client.get("key:opportunity_rank")
            if stored:
                logger.info(f"✅ Verified: key:opportunity_rank exists in Redis")
            else:
                logger.warning(f"⚠️  Warning: key:opportunity_rank not found after SETEX")
                
        except Exception as e:
            logger.error(f"❌ Failed to publish opportunity rank: {e}", exc_info=True)
            # Don't raise - allow service to continue even if Redis publish fails
    
    async def write_opportunity_log(self, opportunities: List[Opportunity]):
        """Write Top 5 opportunities to database"""
        if not self.db_pool or not opportunities:
            return
        
        try:
            query = """
                INSERT INTO opportunity_log (
                    time, ticker, horizon, opportunity_score, probability,
                    target_atr, stop_atr, market_state, attention_stability_score,
                    attention_bucket, attention_alignment, regime_dependency,
                    key_levels, invalidation_rule, why, liquidity_grade
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16)
            """
            
            for opp in opportunities:
                await self.db_pool.execute(
                    query,
                    datetime.now(timezone.utc),  # time
                    opp.ticker,
                    opp.horizon,
                    opp.opportunity_score,
                    opp.probability,
                    opp.target_atr,
                    opp.stop_atr,
                    opp.market_state,
                    opp.attention_stability_score,
                    opp.attention_bucket,
                    opp.attention_alignment,
                    json.dumps(opp.regime_dependency) if opp.regime_dependency else None,
                    json.dumps(opp.key_levels) if opp.key_levels else None,
                    opp.invalidation_rule,
                    json.dumps(opp.why) if opp.why else None,
                    opp.liquidity_grade
                )
            
            logger.info(f"✅ Wrote {len(opportunities)} opportunities to database")
        except Exception as e:
            logger.error(f"❌ Failed to write opportunity log: {e}")
    
    async def listen_for_updates(self):
        """Listen for scanner updates"""
        if not self.redis_pubsub:
            return
        
        logger.info("👂 Listening for scanner updates on chan:active_candidates...")
        
        # Load initial market state
        initial_state = await self.load_market_state()
        if initial_state:
            logger.info(f"📊 Initial MarketState: {initial_state.state} ({initial_state.reason})")
        else:
            logger.warning("⚠️  Could not load initial MarketState from Redis")
        
        loop_count = 0
        while self.is_running:
            loop_count += 1
            # Log every 60 seconds (60 iterations * 1 second timeout)
            if loop_count % 60 == 0:
                logger.info(f"💓 Listen loop active (iteration {loop_count}), waiting for messages...")
            try:
                message = await self.redis_pubsub.get_message(timeout=1.0)
                
                if message:
                    msg_type = message.get('type')
                    channel = message.get('channel')
                    if isinstance(channel, bytes):
                        channel = channel.decode('utf-8')
                    logger.info(f"📬 Received Redis message: type={msg_type}, channel={channel}")
                    
                    # Handle subscription confirmation
                    if msg_type == 'subscribe':
                        logger.info(f"✅ Subscription confirmed for channel: {channel}")
                    
                if message and message['type'] == 'message':
                    try:
                        # Parse CandidateList
                        data = message['data']
                        if isinstance(data, bytes):
                            data = data.decode('utf-8')
                        logger.info(f"📄 Raw message data: {data[:200]}...")  # Log first 200 chars
                        payload = json.loads(data)
                        candidate_list = CandidateList(**payload)
                        
                        logger.info(f"📨 Received CandidateList for {candidate_list.horizon} with {len(candidate_list.candidates)} candidates")
                        
                        # Process update
                        await self.process_scanner_update(candidate_list)
                        
                    except json.JSONDecodeError as e:
                        logger.warning(f"⚠️  Failed to parse message: {e}")
                    except Exception as e:
                        logger.error(f"❌ Error processing update: {e}", exc_info=True)
                
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error(f"❌ Error in listen loop: {e}", exc_info=True)
                await asyncio.sleep(1)
    
    async def start(self):
        """Start the service"""
        logger.info("🚀 Starting ZERO Core Logic Service...")
        
        await self.connect_db()
        await self.connect_redis()
        
        # Initialize Query Engine
        self.query_engine = QueryEngine(self)
        logger.info("✅ Query Engine initialized")
        
        self.is_running = True
        
        # Start listening for updates
        await self.listen_for_updates()
    
    async def stop(self):
        """Stop the service"""
        logger.info("🛑 Stopping ZERO Core Logic Service...")
        self.is_running = False
        
        if self.redis_pubsub:
            await self.redis_pubsub.unsubscribe()
            await self.redis_pubsub.close()
        
        if self.redis_client:
            await self.redis_client.aclose()
        
        if self.db_pool:
            await self.db_pool.close()
    
    async def health_check(self) -> HealthCheck:
        """Health check endpoint"""
        details = {
            "is_running": self.is_running,
            "last_ranking_time": self.last_ranking_time.isoformat() if self.last_ranking_time else None,
            "current_rankings": {
                horizon: len(rank.opportunities)
                for horizon, rank in self.current_rankings.items()
            },
            "db_connected": self.db_pool is not None,
            "redis_connected": self.redis_client is not None,
            "market_state": self.market_state.state if self.market_state else None,
        }
        
        status = "healthy" if (self.is_running and self.db_pool and self.redis_client) else "unhealthy"
        
        return HealthCheck(
            service="zero-core-logic",
            status=status,
            last_update=datetime.now(timezone.utc),
            details=details
        )


# HTTP server for health endpoint
async def health_handler(request):
    """Health check HTTP handler"""
    service = request.app['service']
    health = await service.health_check()
    return web.json_response(health.model_dump(mode='json'))


async def query_handler(request):
    """
    Query Mode endpoint - SPEC_LOCK §5.2
    
    GET /query?ticker=TSLA
    
    Returns eligibility, reason codes, and full breakdown.
    """
    service = request.app['service']
    
    ticker = request.query.get('ticker', '').upper()
    if not ticker:
        return web.json_response(
            {"error": "Missing required parameter: ticker"},
            status=400
        )
    
    if not service.query_engine:
        return web.json_response(
            {"error": "Query engine not initialized"},
            status=503
        )
    
    try:
        result = await service.query_engine.query_ticker(ticker)
        return web.json_response(result.to_dict())
    except Exception as e:
        logger.error(f"Query error for {ticker}: {e}", exc_info=True)
        return web.json_response(
            {"error": str(e), "ticker": ticker},
            status=500
        )


async def init_app():
    """Initialize aiohttp app"""
    app = web.Application()
    service = ZeroCoreLogicService()
    app['service'] = service
    app.router.add_get('/health', health_handler)
    app.router.add_get('/query', query_handler)  # SPEC_LOCK §5.2
    return app, service


async def main():
    """Main entry point"""
    app, service = await init_app()
    
    # Start HTTP server
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', service.api_port)
    await site.start()
    
    logger.info(f"✅ Health endpoint listening on port {service.api_port}")
    
    try:
        # Start service
        await service.start()
    except KeyboardInterrupt:
        logger.info("🛑 Shutting down...")
    finally:
        await service.stop()
        await runner.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
