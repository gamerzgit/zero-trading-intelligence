"""
ZERO Execution Gateway Service
Milestone 6: Paper-Only Execution (Opt-In, Kill Switch Protected)
"""

import asyncio
import os
import sys
import logging
import json
from datetime import datetime, timezone
from typing import Optional, Dict, Any

import redis.asyncio as redis
import asyncpg
from aiohttp import web

# Add parent directory to path for contracts
project_root = os.path.join(os.path.dirname(__file__), '../../')
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from contracts.schemas import OpportunityRank, MarketState, HealthCheck
from alpaca.trading.enums import OrderSide

from risk import RiskManager
from executor import AlpacaExecutor

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class ZeroExecutionService:
    """ZERO Execution Gateway - Paper Only, Opt-In"""
    
    def __init__(self):
        # Configuration
        self.redis_host = os.getenv('REDIS_HOST', 'redis')
        self.redis_port = int(os.getenv('REDIS_PORT', '6379'))
        self.api_port = int(os.getenv('EXECUTION_API_PORT', '8003'))
        
        # PAPER ONLY HARD ENFORCEMENT
        alpaca_paper = os.getenv('ALPACA_PAPER', 'false').lower()
        if alpaca_paper != 'true':
            logger.critical("❌ CRITICAL: ALPACA_PAPER must be 'true'. Execution service refuses to start.")
            sys.exit(1)
        
        # Components
        self.redis_client: Optional[redis.Redis] = None
        self.redis_pubsub: Optional[redis.client.PubSub] = None
        self.risk_manager: Optional[RiskManager] = None
        self.executor: Optional[AlpacaExecutor] = None
        
        # Database
        self.db_host = os.getenv('DB_HOST', 'timescaledb')
        self.db_port = int(os.getenv('DB_PORT', '5432'))
        self.db_name = os.getenv('DB_NAME', 'zero_trading')
        self.db_user = os.getenv('DB_USER', 'zero_user')
        self.db_password = os.getenv('DB_PASSWORD')
        self.db_pool: Optional[asyncpg.Pool] = None
        
        # State
        self.is_running = False
        self.last_event: Optional[Dict[str, Any]] = None
        self.start_time = datetime.now(timezone.utc)
    
    async def connect_db(self):
        """Connect to TimescaleDB"""
        try:
            self.db_pool = await asyncpg.create_pool(
                host=self.db_host,
                port=self.db_port,
                database=self.db_name,
                user=self.db_user,
                password=self.db_password,
                min_size=1,
                max_size=5
            )
            logger.info("✅ Database connected")
        except Exception as e:
            logger.error(f"❌ Database connection failed: {e}")
            # Don't fail service startup - execution can work without DB logging
            logger.warning("⚠️  Continuing without database (execution_log will not be written)")
    
    async def connect_redis(self):
        """Connect to Redis"""
        try:
            self.redis_client = redis.Redis(
                host=self.redis_host,
                port=self.redis_port,
                decode_responses=False  # Keep bytes for pub/sub
            )
            await self.redis_client.ping()
            logger.info("✅ Redis connected")
            
            # Initialize risk manager
            self.risk_manager = RiskManager(self.redis_client)
            
            # Subscribe to opportunity updates
            self.redis_pubsub = self.redis_client.pubsub()
            await self.redis_pubsub.subscribe("chan:opportunity_update")
            logger.info("✅ Subscribed to chan:opportunity_update")
            
        except Exception as e:
            logger.error(f"❌ Redis connection failed: {e}")
            raise
    
    async def initialize_executor(self):
        """Initialize Alpaca executor (will fail if not paper mode)"""
        try:
            self.executor = AlpacaExecutor()
            logger.info("✅ Alpaca executor initialized (PAPER MODE)")
        except ValueError as e:
            logger.critical(f"❌ {e}")
            sys.exit(1)
        except Exception as e:
            logger.critical(f"❌ Failed to initialize executor: {e}")
            sys.exit(1)
    
    async def check_execution_enabled(self) -> bool:
        """Check if execution is enabled"""
        if not self.risk_manager:
            return False
        return await self.risk_manager.is_execution_enabled()
    
    async def process_opportunity(self, opportunity_rank: OpportunityRank):
        """Process an opportunity and potentially execute a trade"""
        try:
            # Determine top opportunity early so BLOCKED/SKIPPED events can still be logged
            top_opportunity = opportunity_rank.opportunities[0] if opportunity_rank.opportunities else None

            # Generate a deterministic execution_id for logging/idempotency purposes.
            # If we have a top opportunity, use it. Otherwise fall back to a sentinel ticker.
            execution_id_base_ticker = top_opportunity.ticker if top_opportunity else "UNKNOWN"
            execution_id_base_horizon = top_opportunity.horizon if top_opportunity else opportunity_rank.horizon
            execution_id = self.risk_manager.generate_execution_id(
                execution_id_base_ticker,
                execution_id_base_horizon,
                opportunity_rank.rank_time,
            )

            # 1. Check kill switch
            execution_enabled = await self.check_execution_enabled()
            if not execution_enabled:
                logger.info("🚫 Execution disabled (kill switch off)")
                await self.publish_trade_update(
                    status="BLOCKED",
                    reason="Execution disabled (kill switch)",
                    opportunity_rank=opportunity_rank,
                    opportunity=top_opportunity,
                    execution_id=execution_id,
                )
                return
            
            # 2. Check market state (final veto)
            is_green, veto_reason = await self.risk_manager.is_market_green()
            if not is_green:
                logger.info(f"🚫 Market veto: {veto_reason}")
                await self.publish_trade_update(
                    status="BLOCKED",
                    reason=veto_reason,
                    opportunity_rank=opportunity_rank,
                    opportunity=top_opportunity,
                    execution_id=execution_id,
                )
                return
            
            # 3. Get top opportunity (rank == 1)
            if not top_opportunity:
                logger.debug("No opportunities in rank")
                return
            # Already sorted by rank
            
            # 4. Check probability threshold (>= 0.90)
            if top_opportunity.probability < 0.90:
                logger.info(f"🚫 Probability too low: {top_opportunity.probability:.4f} < 0.90")
                await self.publish_trade_update(
                    status="BLOCKED",
                    reason=f"Probability {top_opportunity.probability:.4f} below threshold 0.90",
                    opportunity_rank=opportunity_rank,
                    opportunity=top_opportunity,
                    execution_id=execution_id,
                )
                return
            
            # 5. Check idempotency
            is_new, was_set = await self.risk_manager.check_idempotency(execution_id)
            if not is_new:
                logger.info(f"🚫 Duplicate execution_id: {execution_id}")
                await self.publish_trade_update(
                    status="SKIPPED",
                    reason="Duplicate execution_id (already processed)",
                    opportunity_rank=opportunity_rank,
                    opportunity=top_opportunity,
                    execution_id=execution_id
                )
                return
            
            # 6. Check cooldown
            can_trade, last_trade_time = await self.risk_manager.check_cooldown(top_opportunity.ticker)
            if not can_trade:
                logger.info(f"🚫 Cooldown active for {top_opportunity.ticker} (last trade: {last_trade_time})")
                await self.publish_trade_update(
                    status="SKIPPED",
                    reason=f"Cooldown active (last trade: {last_trade_time})",
                    opportunity_rank=opportunity_rank,
                    opportunity=top_opportunity,
                    execution_id=execution_id
                )
                return
            
            # 7. Check for existing position
            has_position, position_data = await self.executor.check_open_position(top_opportunity.ticker)
            if has_position:
                logger.info(f"🚫 Already have position in {top_opportunity.ticker}")
                await self.publish_trade_update(
                    status="SKIPPED",
                    reason=f"Already have open position",
                    opportunity_rank=opportunity_rank,
                    opportunity=top_opportunity,
                    execution_id=execution_id
                )
                return
            
            # 8. Place order (PAPER ONLY)
            logger.info(f"📈 Executing trade: {top_opportunity.ticker} (probability={top_opportunity.probability:.4f})")
            order_id, error = await self.executor.place_market_order(
                ticker=top_opportunity.ticker,
                quantity=1,  # Hard limit: 1 share max
                side=OrderSide.BUY
            )
            
            if error:
                await self.publish_trade_update(
                    status="REJECTED",
                    reason=error,
                    opportunity_rank=opportunity_rank,
                    opportunity=top_opportunity,
                    execution_id=execution_id
                )
                return
            
            # 9. Record trade for cooldown
            await self.risk_manager.record_trade(top_opportunity.ticker, execution_id)
            
            # 10. Publish success
            await self.publish_trade_update(
                status="SUBMITTED",
                reason="Order submitted successfully",
                opportunity_rank=opportunity_rank,
                opportunity=top_opportunity,
                execution_id=execution_id,
                alpaca_order_id=order_id
            )
            
            logger.info(f"✅ Trade executed: {top_opportunity.ticker}, order_id={order_id}")
            
        except Exception as e:
            logger.error(f"❌ Error processing opportunity: {e}", exc_info=True)
            await self.publish_trade_update(
                status="ERROR",
                reason=f"Unexpected error: {str(e)}",
                opportunity_rank=opportunity_rank
            )
    
    async def publish_trade_update(
        self,
        status: str,
        reason: str,
        opportunity_rank: OpportunityRank,
        opportunity=None,
        execution_id: Optional[str] = None,
        alpaca_order_id: Optional[str] = None
    ):
        """Publish trade update event to Redis"""
        if not self.redis_client:
            return
        
        try:
            # Get market state snapshot
            market_state = await self.risk_manager.get_market_state()

            # Ensure execution_id is always present for logging. Fall back deterministically if not provided.
            if not execution_id:
                base_ticker = opportunity.ticker if opportunity else "UNKNOWN"
                base_horizon = opportunity.horizon if opportunity else opportunity_rank.horizon
                execution_id = self.risk_manager.generate_execution_id(
                    base_ticker,
                    base_horizon,
                    opportunity_rank.rank_time,
                )
            
            # Build trade update payload
            trade_update = {
                "schema_version": "1.0",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "execution_id": execution_id,
                "status": status,
                # DB logging requires non-null ticker; use a sentinel if we don't have one
                "ticker": opportunity.ticker if opportunity else "UNKNOWN",
                "horizon": opportunity.horizon if opportunity else opportunity_rank.horizon,
                "probability": opportunity.probability if opportunity else None,
                "opportunity_score": opportunity.opportunity_score if opportunity else None,
                "alpaca_order_id": alpaca_order_id,
                "market_state": market_state,
                "why": [reason] + (opportunity.why if opportunity and opportunity.why else []),
                "submitted_at": datetime.now(timezone.utc).isoformat()
            }
            
            # Publish to channel
            channel = "chan:trade_update"
            payload = json.dumps(trade_update).encode('utf-8')
            subscribers = await self.redis_client.publish(channel, payload)
            
            logger.info(f"📤 Published trade_update: {status} for {opportunity.ticker if opportunity else 'N/A'}")
            
            # Store last event
            self.last_event = trade_update
            
            # Write to database
            await self.write_execution_log(trade_update)
            
        except Exception as e:
            logger.error(f"❌ Failed to publish trade_update: {e}", exc_info=True)
    
    async def write_execution_log(self, trade_update: Dict[str, Any]):
        """Write execution event to database"""
        if not self.db_pool:
            return
        
        try:
            async with self.db_pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO execution_log (
                        time, execution_id, ticker, horizon, probability,
                        opportunity_score, status, alpaca_order_id, why,
                        market_state_snapshot
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                    ON CONFLICT (execution_id) DO NOTHING
                    """,
                    datetime.now(timezone.utc),
                    trade_update.get('execution_id'),
                    trade_update.get('ticker'),
                    trade_update.get('horizon'),
                    trade_update.get('probability'),
                    trade_update.get('opportunity_score'),
                    trade_update.get('status'),
                    trade_update.get('alpaca_order_id'),
                    json.dumps(trade_update.get('why', [])),
                    json.dumps(trade_update.get('market_state'))
                )
            logger.debug(f"💾 Wrote execution_log entry: {trade_update.get('execution_id')}")
        except Exception as e:
            logger.error(f"❌ Failed to write execution_log: {e}", exc_info=True)
    
    async def listen_for_opportunities(self):
        """Listen for opportunity updates"""
        if not self.redis_pubsub:
            return
        
        logger.info("👂 Listening for opportunities on chan:opportunity_update...")
        
        while self.is_running:
            try:
                message = await self.redis_pubsub.get_message(timeout=1.0)
                
                if message and message['type'] == 'message':
                    try:
                        # Parse OpportunityRank
                        data = message['data']
                        if isinstance(data, bytes):
                            data = data.decode('utf-8')
                        payload = json.loads(data)
                        opportunity_rank = OpportunityRank(**payload)
                        
                        logger.info(f"📨 Received OpportunityRank for {opportunity_rank.horizon} with {len(opportunity_rank.opportunities)} opportunities")
                        
                        # Process opportunity
                        await self.process_opportunity(opportunity_rank)
                        
                    except json.JSONDecodeError as e:
                        logger.warning(f"⚠️  Failed to parse message: {e}")
                    except Exception as e:
                        logger.error(f"❌ Error processing message: {e}", exc_info=True)
                
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error(f"❌ Error in listen loop: {e}", exc_info=True)
                await asyncio.sleep(1)
    
    async def start(self):
        """Start the service"""
        self.is_running = True
        
        # Initialize executor first (will exit if not paper mode)
        await self.initialize_executor()
        
        # Connect to database (optional - service can run without DB)
        await self.connect_db()
        
        # Connect to Redis
        await self.connect_redis()
        
        # Check initial execution state
        execution_enabled = await self.check_execution_enabled()
        logger.info(f"🔒 Execution enabled: {execution_enabled}")
        if not execution_enabled:
            logger.info("⚠️  Execution is DISABLED (kill switch off). Service will run but will not place orders.")
        
        # Start HTTP server for health checks
        self.app = web.Application()
        self.app['service'] = self
        self.app.router.add_get('/health', self.health_handler)
        self.runner = web.AppRunner(self.app)
        await self.runner.setup()
        self.site = web.TCPSite(self.runner, '0.0.0.0', self.api_port)
        await self.site.start()
        logger.info(f"✅ Health endpoint listening on port {self.api_port}")
        logger.info("🚀 Starting ZERO Execution Gateway Service (PAPER ONLY)...")
        
        # Start listening for opportunities
        await self.listen_for_opportunities()
    
    async def stop(self):
        """Stop the service"""
        logger.info("🛑 Shutting down ZERO Execution Gateway Service...")
        self.is_running = False
        if self.redis_pubsub:
            await self.redis_pubsub.unsubscribe("chan:opportunity_update")
            await self.redis_pubsub.close()
        if self.redis_client:
            await self.redis_client.close()
        if self.db_pool:
            await self.db_pool.close()
        if self.site:
            await self.site.stop()
        if self.runner:
            await self.runner.cleanup()
        logger.info("✅ ZERO Execution Gateway Service stopped.")
    
    async def health_handler(self, request):
        """Health check endpoint"""
        try:
            execution_enabled = await self.check_execution_enabled() if self.risk_manager else False
            account_info = await self.executor.get_account_info() if self.executor else None
            
            details = {
                "paper_mode": True,  # Always true (hard enforced)
                "execution_enabled": execution_enabled,
                "redis_connected": self.redis_client is not None,
                "executor_initialized": self.executor is not None,
                "last_event": self.last_event,
                "account_info": account_info
            }
            
            health = HealthCheck(
                service="zero-execution",
                status="healthy",
                uptime_seconds=(datetime.now(timezone.utc) - self.start_time).total_seconds(),
                last_update=datetime.now(timezone.utc),
                details=details
            )
            
            return web.json_response(health.model_dump(mode='json'))
        except Exception as e:
            logger.error(f"❌ Health check error: {e}", exc_info=True)
            return web.json_response(
                {"service": "zero-execution", "status": "unhealthy", "error": str(e)},
                status=500
            )


async def main():
    """Main entry point"""
    service = ZeroExecutionService()
    try:
        await service.start()
    except KeyboardInterrupt:
        logger.info("Service interrupted by user.")
    except Exception as e:
        logger.critical(f"Unhandled exception: {e}", exc_info=True)
        sys.exit(1)
    finally:
        await service.stop()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Service interrupted by user.")
    except Exception as e:
        logger.critical(f"Unhandled exception in main: {e}", exc_info=True)
        sys.exit(1)
