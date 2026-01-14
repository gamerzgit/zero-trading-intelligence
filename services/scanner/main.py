"""
ZERO Scanner Service (Level 2 - Opportunity Discovery)
Filters universe to find Active Candidates
"""

import asyncio
import os
import sys
import logging
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Dict, Any
import json

import asyncpg
import redis.asyncio as redis
from aiohttp import web
import pandas as pd

# Add parent directory to path for contracts
project_root = os.path.join(os.path.dirname(__file__), '../../')
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from contracts.schemas import CandidateList, MarketState, HealthCheck

try:
    from horizon import get_all_horizons, get_horizon_info
    from filters import ScannerFilters
except ImportError:
    # Handle relative imports for Docker
    from .horizon import get_all_horizons, get_horizon_info
    from .filters import ScannerFilters

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class ZeroScannerService:
    """ZERO Scanner Service - Level 2 Opportunity Discovery"""
    
    def __init__(self):
        # Configuration
        self.db_host = os.getenv('DB_HOST', 'timescaledb')
        self.db_port = int(os.getenv('DB_PORT', '5432'))
        self.db_name = os.getenv('DB_NAME', 'zero_trading')
        self.db_user = os.getenv('DB_USER', 'zero_user')
        self.db_password = os.getenv('DB_PASSWORD')
        
        self.redis_host = os.getenv('REDIS_HOST', 'redis')
        self.redis_port = int(os.getenv('REDIS_PORT', '6379'))
        
        self.scan_interval = int(os.getenv('SCAN_INTERVAL_SECONDS', '60'))  # Scan every 60 seconds
        self.scan_universe: List[str] = []  # Will be loaded from Alpaca API in connect_redis()
        
        # Components
        self.db_pool: Optional[asyncpg.Pool] = None
        self.redis_client: Optional[redis.Redis] = None
        self.filters = ScannerFilters()
        
        # State
        self.is_running = False
        self.last_scan_time: Optional[datetime] = None
        self.current_candidates: Dict[str, List[str]] = {}  # horizon -> list of tickers
        self.previous_candidates: Dict[str, List[str]] = {}  # For diff detection
        self.market_state: Optional[MarketState] = None
        self.last_market_state_time: Optional[datetime] = None
        self.market_state_warning_logged = False  # Log warning once
        self.scan_event = asyncio.Event()  # For event-based wakeups
        
    def _load_scan_universe(self) -> List[str]:
        """
        Load scan universe from Alpaca API (all tradeable stocks)
        Falls back to Redis key:scan_universe if Alpaca unavailable
        """
        # Try to load from Redis first (cached)
        # If not available, fetch from Alpaca API
        return []  # Will be loaded async in connect_redis()
    
    async def _fetch_universe_from_alpaca(self) -> List[str]:
        """
        Fetch tradeable stocks from Alpaca Assets API
        
        Returns:
            List of ticker symbols (e.g., ['AAPL', 'MSFT', ...])
        """
        try:
            from alpaca.trading.client import TradingClient
            from alpaca.trading.enums import AssetClass, AssetStatus
            
            # Initialize TradingClient (uses same credentials as data client)
            trading_client = TradingClient(
                api_key=os.getenv('ALPACA_API_KEY'),
                secret_key=os.getenv('ALPACA_SECRET_KEY'),
                paper=True  # Paper mode for data access
            )
            
            # Get all active US equity assets
            logger.info("📡 Fetching tradeable stocks from Alpaca Assets API...")
            assets = trading_client.get_all_assets(
                asset_class=AssetClass.US_EQUITY,
                status=AssetStatus.ACTIVE
            )
            
            # Extract ticker symbols
            tickers = [asset.symbol for asset in assets if asset.tradable]
            
            logger.info(f"✅ Loaded {len(tickers)} tradeable stocks from Alpaca")
            return tickers
            
        except ImportError:
            logger.warning("⚠️  alpaca-py not available - cannot fetch universe from Alpaca")
            return []
        except Exception as e:
            logger.error(f"❌ Failed to fetch universe from Alpaca: {e}")
            # Fallback to Redis or default
            return await self._load_universe_from_redis()
    
    async def _load_universe_from_redis(self) -> List[str]:
        """Load universe from Redis key:scan_universe (if cached)"""
        if not self.redis_client:
            return []
        
        try:
            universe_json = await self.redis_client.get("key:scan_universe")
            if universe_json:
                if isinstance(universe_json, bytes):
                    universe_json = universe_json.decode('utf-8')
                universe_data = json.loads(universe_json)
                if isinstance(universe_data, list):
                    logger.info(f"✅ Loaded {len(universe_data)} tickers from Redis key:scan_universe")
                    return universe_data
        except Exception as e:
            logger.warning(f"⚠️  Failed to load universe from Redis: {e}")
        
        # Final fallback: minimal default (only if Alpaca and Redis both fail)
        logger.warning("⚠️  Using minimal fallback universe (Alpaca and Redis unavailable)")
        return ["SPY", "QQQ", "IWM", "AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA"]
    
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
            logger.info("✅ Connected to TimescaleDB")
        except Exception as e:
            logger.error(f"❌ Failed to connect to TimescaleDB: {e}")
            raise
    
    async def connect_redis(self):
        """Connect to Redis and load scan universe from Alpaca API"""
        try:
            self.redis_client = redis.Redis(
                host=self.redis_host,
                port=self.redis_port,
                decode_responses=False  # We'll decode manually
            )
            await self.redis_client.ping()
            logger.info("✅ Connected to Redis")
            
            # Load scan universe from Alpaca API (or Redis cache)
            self.scan_universe = await self._fetch_universe_from_alpaca()
            
            # Cache in Redis for next time (TTL 24 hours)
            if self.scan_universe:
                await self.redis_client.setex(
                    "key:scan_universe",
                    86400,  # 24 hours
                    json.dumps(self.scan_universe).encode('utf-8')
                )
                logger.info(f"✅ Cached {len(self.scan_universe)} tickers in Redis key:scan_universe")
            else:
                logger.warning("⚠️  Scan universe is empty - scanner will not find any candidates")
                
        except Exception as e:
            logger.error(f"❌ Failed to connect to Redis: {e}")
            raise
    
    async def get_market_state(self) -> Optional[MarketState]:
        """Get current MarketState from Redis"""
        if not self.redis_client:
            return None
        
        try:
            state_json = await self.redis_client.get("key:market_state")
            if not state_json:
                # If missing, assume RED (veto) - log warning once
                if not self.market_state_warning_logged:
                    logger.warning("⚠️  MarketState not found in Redis - assuming RED (veto)")
                    self.market_state_warning_logged = True
                return None
            
            state_dict = json.loads(state_json.decode('utf-8'))
            market_state = MarketState(**state_dict)
            self.market_state = market_state
            self.last_market_state_time = datetime.now(timezone.utc)
            self.market_state_warning_logged = False  # Reset if we get state
            return market_state
        except Exception as e:
            logger.error(f"❌ Failed to get MarketState: {e}")
            return None
    
    async def subscribe_market_state_changes(self):
        """Subscribe to market state changes for event-based wakeups"""
        if not self.redis_client:
            return
        
        try:
            pubsub = self.redis_client.pubsub()
            await pubsub.subscribe("chan:market_state_changed")
            
            logger.info("✅ Subscribed to chan:market_state_changed")
            
            async for message in pubsub.listen():
                if not self.is_running:
                    break
                    
                if message['type'] == 'message':
                    try:
                        # Parse notification
                        data = json.loads(message['data'].decode('utf-8'))
                        state_key = data.get('state_key', 'key:market_state')
                        
                        # Get old state before fetching new one
                        old_state_str = self.market_state.state if self.market_state else None
                        
                        # Get new state
                        new_state = await self.get_market_state()
                        
                        if new_state:
                            new_state_str = new_state.state
                            
                            # Trigger immediate rescan on favorable transitions
                            if old_state_str == "RED" and new_state_str in ["YELLOW", "GREEN"]:
                                logger.info(f"🔄 MarketState changed {old_state_str} -> {new_state_str} - triggering immediate scan")
                                self.scan_event.set()
                            elif old_state_str == "YELLOW" and new_state_str == "GREEN":
                                logger.info(f"🔄 MarketState changed {old_state_str} -> {new_state_str} - triggering immediate scan")
                                self.scan_event.set()
                    except Exception as e:
                        logger.error(f"❌ Error processing market state change: {e}")
        except Exception as e:
            logger.error(f"❌ Failed to subscribe to market state changes: {e}")
    
    async def fetch_candles(
        self, 
        ticker: str, 
        timeframe: str = "5m",
        lookback_minutes: int = 240
    ) -> pd.DataFrame:
        """Fetch candles from database"""
        if not self.db_pool:
            return pd.DataFrame()
        
        table_name = f"candles_{timeframe}"
        
        try:
            query = f"""
                SELECT time, open, high, low, close, volume
                FROM {table_name}
                WHERE ticker = $1
                AND time >= NOW() - INTERVAL '{lookback_minutes} minutes'
                ORDER BY time ASC
            """
            
            rows = await self.db_pool.fetch(query, ticker)
            
            if not rows:
                return pd.DataFrame()
            
            # Convert to DataFrame
            data = {
                'time': [r['time'] for r in rows],
                'open': [float(r['open']) for r in rows],
                'high': [float(r['high']) for r in rows],
                'low': [float(r['low']) for r in rows],
                'close': [float(r['close']) for r in rows],
                'volume': [int(r['volume']) for r in rows]
            }
            
            return pd.DataFrame(data)
        except Exception as e:
            logger.error(f"❌ Failed to fetch candles for {ticker}: {e}")
            return pd.DataFrame()
    
    async def scan_horizon(self, horizon: str) -> List[str]:
        """Scan for candidates for a specific horizon"""
        candidates = []
        horizon_info = get_horizon_info(horizon)
        
        if not horizon_info:
            logger.warning(f"⚠️  Unknown horizon: {horizon}")
            return candidates
        
        lookback_minutes = horizon_info.get("lookback_minutes", 240)
        
        logger.info(f"🔍 Scanning {len(self.scan_universe)} tickers for {horizon}...")
        
        for ticker in self.scan_universe:
            try:
                # Fetch candles
                candles_5m = await self.fetch_candles(ticker, "5m", lookback_minutes)
                candles_1m = await self.fetch_candles(ticker, "1m", min(lookback_minutes, 60))  # Limit 1m to 60 min
                
                # Apply filters
                passed, stats = self.filters.apply_all_filters(ticker, candles_1m, candles_5m)
                
                if passed:
                    candidates.append(ticker)
                    logger.debug(f"✅ {ticker} passed filters for {horizon}")
                else:
                    failed_filter = stats.get('failed_filter', 'unknown')
                    logger.debug(f"❌ {ticker} failed {failed_filter} filter")
                    
            except Exception as e:
                logger.error(f"❌ Error scanning {ticker}: {e}")
                continue
        
        logger.info(f"✅ Found {len(candidates)} candidates for {horizon}")
        return candidates
    
    async def scan_all_horizons(self) -> Dict[str, List[str]]:
        """Scan all horizons"""
        results = {}
        
        for horizon in get_all_horizons():
            candidates = await self.scan_horizon(horizon)
            results[horizon] = candidates
        
        return results
    
    async def publish_all_candidates(self, all_candidates: Dict[str, List[str]]):
        """Publish all horizon candidates to Redis (structured, no overwrite)"""
        if not self.redis_client:
            return
        
        try:
            # Publish per-horizon CandidateList messages (contract compliance)
            # Also store structured state in key for easy access
            total_candidates = 0
            
            for horizon, candidates in all_candidates.items():
                # Create CandidateList per horizon (contract compliance)
                candidate_list = CandidateList(
                    candidates=candidates,
                    horizon=horizon,
                    scan_time=datetime.now(timezone.utc),
                    filter_stats={}  # Can add stats later
                )
                
                # Publish to channel (per-horizon messages)
                channel = "chan:active_candidates"
                payload = candidate_list.model_dump_json().encode('utf-8')
                await self.redis_client.publish(channel, payload)
                
                total_candidates += len(candidates)
            
            # Store structured state in key (all horizons together, no overwrite)
            scanner_state = {
                "intraday": {
                    "H30": all_candidates.get("H30", []),
                    "H2H": all_candidates.get("H2H", [])
                },
                "swing": {
                    "HDAY": all_candidates.get("HDAY", []),
                    "HWEEK": all_candidates.get("HWEEK", [])
                },
                "scan_time": datetime.now(timezone.utc).isoformat()
            }
            
            state_json = json.dumps(scanner_state)
            key = "key:active_candidates"
            await self.redis_client.setex(
                key,
                300,  # 5 minute TTL
                state_json
            )
            
            # Update last scan time
            await self.redis_client.set(
                "key:last_scan_time",
                datetime.now(timezone.utc).isoformat()
            )
            
            logger.info(f"✅ Published {total_candidates} total candidates (all horizons) to Redis")
        except Exception as e:
            logger.error(f"❌ Failed to publish candidates: {e}")
    
    async def log_candidate_changes_to_db(
        self, 
        horizon: str, 
        new_candidates: List[str],
        previous_candidates: List[str],
        market_state: MarketState
    ):
        """Log candidate changes to scanner_log (edge-based, not spam)"""
        if not self.db_pool:
            return
        
        try:
            # Calculate diff
            added = set(new_candidates) - set(previous_candidates)
            removed = set(previous_candidates) - set(new_candidates)
            maintained = set(new_candidates) & set(previous_candidates)
            
            now = datetime.now(timezone.utc)
            
            # Log added candidates
            for ticker in added:
                await self.db_pool.execute(
                    """
                    INSERT INTO scanner_log (time, ticker, horizon, action, reason_json)
                    VALUES ($1, $2, $3, $4, $5)
                    """,
                    now,
                    ticker,
                    horizon,
                    'ADDED',
                    json.dumps({
                        "market_state": market_state.state,
                        "filter_passed": True
                    })
                )
            
            # Log removed candidates
            for ticker in removed:
                await self.db_pool.execute(
                    """
                    INSERT INTO scanner_log (time, ticker, horizon, action, reason_json)
                    VALUES ($1, $2, $3, $4, $5)
                    """,
                    now,
                    ticker,
                    horizon,
                    'REMOVED',
                    json.dumps({
                        "market_state": market_state.state,
                        "filter_failed": True
                    })
                )
            
            # Only log maintained on first scan (when previous is empty)
            if not previous_candidates:
                for ticker in maintained:
                    await self.db_pool.execute(
                        """
                        INSERT INTO scanner_log (time, ticker, horizon, action, reason_json)
                        VALUES ($1, $2, $3, $4, $5)
                        """,
                        now,
                        ticker,
                        horizon,
                        'MAINTAINED',
                        json.dumps({
                            "market_state": market_state.state,
                            "filter_passed": True
                        })
                    )
            
            total_changes = len(added) + len(removed) + (len(maintained) if not previous_candidates else 0)
            if total_changes > 0:
                logger.info(f"✅ Logged {total_changes} candidate changes for {horizon} to scanner_log")
        except Exception as e:
            logger.error(f"❌ Failed to log candidate changes to DB: {e}")
    
    async def scan_loop(self):
        """Main scanning loop (event-aware)"""
        logger.info("🚀 Starting scanner loop...")
        
        # Get initial market state
        market_state = await self.get_market_state()
        
        while self.is_running:
            try:
                # Check MarketState - if RED or missing, sleep
                market_state = await self.get_market_state()
                
                if not market_state:
                    # Missing state = assume RED (veto)
                    logger.debug("🔴 MarketState missing - assuming RED, sleeping...")
                    # Wait for event or timeout
                    try:
                        await asyncio.wait_for(self.scan_event.wait(), timeout=self.scan_interval)
                        self.scan_event.clear()
                        continue  # Event triggered, re-check state
                    except asyncio.TimeoutError:
                        continue  # Timeout, re-check state
                
                if market_state.state == "RED":
                    logger.debug("🔴 MarketState is RED - scanner sleeping")
                    # Wait for event or timeout
                    try:
                        await asyncio.wait_for(self.scan_event.wait(), timeout=self.scan_interval)
                        self.scan_event.clear()
                        continue  # Event triggered, re-check state
                    except asyncio.TimeoutError:
                        continue  # Timeout, re-check state
                
                # Market is GREEN or YELLOW - proceed with scan
                logger.info(f"✅ MarketState is {market_state.state} - scanning...")
                
                # Scan all horizons
                results = await self.scan_all_horizons()
                
                # Publish all results together (structured, no overwrite)
                await self.publish_all_candidates(results)
                
                # Log changes to DB (edge-based)
                for horizon in get_all_horizons():
                    new_candidates = results.get(horizon, [])
                    previous_candidates = self.previous_candidates.get(horizon, [])
                    await self.log_candidate_changes_to_db(
                        horizon, 
                        new_candidates, 
                        previous_candidates,
                        market_state
                    )
                
                # Update state
                self.previous_candidates = results.copy()
                self.current_candidates = results
                self.last_scan_time = datetime.now(timezone.utc)
                
                # Wait for next scan or event
                try:
                    await asyncio.wait_for(self.scan_event.wait(), timeout=self.scan_interval)
                    self.scan_event.clear()
                except asyncio.TimeoutError:
                    pass  # Normal timeout, continue loop
                
            except Exception as e:
                logger.error(f"❌ Error in scan loop: {e}")
                await asyncio.sleep(self.scan_interval)
    
    async def start(self):
        """Start the scanner service"""
        logger.info("🚀 Starting ZERO Scanner Service...")
        
        await self.connect_db()
        await self.connect_redis()
        
        self.is_running = True
        
        # Start market state subscription (background task)
        asyncio.create_task(self.subscribe_market_state_changes())
        
        # Start scan loop
        await self.scan_loop()
    
    async def stop(self):
        """Stop the scanner service"""
        logger.info("🛑 Stopping scanner service...")
        self.is_running = False
        
        if self.db_pool:
            await self.db_pool.close()
        
        if self.redis_client:
            await self.redis_client.close()
    
    async def health_check(self) -> HealthCheck:
        """Health check endpoint"""
        details = {
            "is_running": self.is_running,
            "last_scan_time": self.last_scan_time.isoformat() if self.last_scan_time else None,
            "current_candidates": {
                horizon: len(candidates) 
                for horizon, candidates in self.current_candidates.items()
            },
            "scan_universe_size": len(self.scan_universe),
            "db_connected": self.db_pool is not None,
            "redis_connected": self.redis_client is not None,
            "market_state_seen": self.market_state.state if self.market_state else None,
            "last_market_state_timestamp": self.last_market_state_time.isoformat() if self.last_market_state_time else None
        }
        
        status = "healthy" if (self.is_running and self.db_pool and self.redis_client) else "unhealthy"
        
        return HealthCheck(
            service="zero-scanner",
            status=status,
            last_update=datetime.now(timezone.utc),
            details=details
        )


# HTTP server for health endpoint
async def health_handler(request):
    """Health check HTTP handler"""
    service = request.app['scanner_service']
    health = await service.health_check()
    return web.json_response(health.model_dump(mode='json'))


async def create_app():
    """Create aiohttp app"""
    app = web.Application()
    
    scanner_service = ZeroScannerService()
    app['scanner_service'] = scanner_service
    
    app.router.add_get('/health', health_handler)
    
    return app, scanner_service


async def main():
    """Main entry point"""
    app, scanner_service = await create_app()
    
    # Start HTTP server
    runner = web.AppRunner(app)
    await runner.setup()
    
    port = int(os.getenv('API_PORT', '8001'))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    
    logger.info(f"✅ Health endpoint listening on port {port}")
    
    try:
        await scanner_service.start()
    except KeyboardInterrupt:
        logger.info("🛑 Received shutdown signal")
    finally:
        await scanner_service.stop()
        await runner.cleanup()


if __name__ == "__main__":
    asyncio.run(main())

