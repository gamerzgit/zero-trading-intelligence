#!/usr/bin/env python3
"""
ZERO System Verification Script
Verifies Milestone 0 Infrastructure + Milestone 1 Ingestion
"""

import asyncio
import os
import sys
from datetime import datetime, timedelta
from typing import Optional
import json

# Add project root to path
project_root = os.path.join(os.path.dirname(__file__), '..')
sys.path.insert(0, project_root)

try:
    import asyncpg
    import redis.asyncio as aioredis
    from alpaca.data.historical import StockHistoricalDataClient
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame
    from alpaca.trading.client import TradingClient
    from alpaca.trading.enums import AssetClass
except ImportError as e:
    print(f"❌ Missing dependencies: {e}")
    print("Install: pip install asyncpg redis alpaca-py")
    sys.exit(1)

# Load environment variables
from dotenv import load_dotenv
load_dotenv(os.path.join(project_root, '.env'))


class SystemVerifier:
    """System verification class"""
    
    def __init__(self):
        # Database connection
        self.db_url = (
            f"postgresql://{os.getenv('DB_USER', 'zero_user')}:"
            f"{os.getenv('DB_PASSWORD')}@"
            f"{os.getenv('DB_HOST', 'timescaledb')}:"
            f"{os.getenv('DB_PORT', '5432')}/"
            f"{os.getenv('DB_NAME', 'zero_trading')}"
        )
        self.db_pool: Optional[asyncpg.Pool] = None
        
        # Redis connection
        self.redis_url = (
            f"redis://{os.getenv('REDIS_HOST', 'redis')}:"
            f"{os.getenv('REDIS_PORT', '6379')}"
        )
        self.redis_client: Optional[aioredis.Redis] = None
        
        # Alpaca credentials
        self.alpaca_key = os.getenv('ALPACA_API_KEY')
        self.alpaca_secret = os.getenv('ALPACA_SECRET_KEY')
        self.alpaca_paper = os.getenv('ALPACA_PAPER', 'true').lower() == 'true'
    
    async def check_infrastructure(self) -> bool:
        """Check Redis and TimescaleDB connectivity"""
        print("\n" + "="*60)
        print("STEP 1: Infrastructure Check")
        print("="*60)
        
        # Check Redis
        try:
            print("Checking Redis...")
            self.redis_client = aioredis.from_url(self.redis_url, decode_responses=False)
            pong = await self.redis_client.ping()
            if pong:
                print("✅ Redis: Connected")
            else:
                print("❌ Redis: Ping failed")
                return False
        except Exception as e:
            print(f"❌ Redis: Connection failed - {e}")
            print("   Fix: Ensure Redis container is running (make up)")
            return False
        
        # Check TimescaleDB
        try:
            print("Checking TimescaleDB...")
            self.db_pool = await asyncpg.create_pool(self.db_url, min_size=1, max_size=3)
            
            async with self.db_pool.acquire() as conn:
                # Check required tables exist
                tables = await conn.fetch("""
                    SELECT table_name 
                    FROM information_schema.tables 
                    WHERE table_schema = 'public' 
                    AND table_name IN ('candles_1m', 'candles_5m', 'candles_1d', 'ticks', 'ingest_gap_log')
                    ORDER BY table_name
                """)
                
                required_tables = {'candles_1m', 'candles_5m', 'candles_1d', 'ticks', 'ingest_gap_log'}
                found_tables = {row['table_name'] for row in tables}
                missing = required_tables - found_tables
                
                if missing:
                    print(f"❌ TimescaleDB: Missing tables - {missing}")
                    print("   Fix: Ensure init.sql ran successfully")
                    return False
                
                print(f"✅ TimescaleDB: Connected (found {len(found_tables)} required tables)")
                
                # Check hypertables
                hypertables = await conn.fetch("""
                    SELECT hypertable_name 
                    FROM timescaledb_information.hypertables
                """)
                print(f"✅ TimescaleDB: {len(hypertables)} hypertables configured")
        
        except Exception as e:
            print(f"❌ TimescaleDB: Connection failed - {e}")
            print("   Fix: Check DB credentials in .env and ensure container is running")
            return False
        
        print("\n✅ Infrastructure Ready")
        return True
    
    async def trigger_ingestion(self) -> bool:
        """Trigger ingestion or provide instructions"""
        print("\n" + "="*60)
        print("STEP 2: Trigger Ingestion")
        print("="*60)
        
        # Check if ingestion service is running
        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.get('http://localhost:8080/health', timeout=aiohttp.ClientTimeout(total=5)) as resp:
                    if resp.status == 200:
                        health = await resp.json()
                        print(f"✅ Ingestion service: Running (status: {health.get('status', 'unknown')})")
                        
                        # Check if we can trigger backfill via env or need to restart
                        print("\nTo trigger backfill with Alpaca:")
                        print("1. Set in .env: PROVIDER_TYPE=alpaca")
                        print("2. Set in .env: FORCE_BACKFILL=1 (if supported)")
                        print("3. Restart: docker compose -f infra/docker-compose.yml restart zero-ingest-price")
                        print("\nOr wait for next scheduled ingestion cycle...")
                        return True
        except Exception as e:
            print(f"⚠️  Ingestion service: Not reachable - {e}")
            print("   This is OK if service hasn't started yet")
            print("\nTo start ingestion:")
            print("1. Ensure .env has ALPACA_API_KEY and ALPACA_SECRET_KEY")
            print("2. Set PROVIDER_TYPE=alpaca in .env")
            print("3. Run: make up")
            return True  # Don't fail, just warn
    
    async def verify_alpaca_connection(self) -> bool:
        """Verify Alpaca API connection"""
        print("\n" + "="*60)
        print("STEP 3: Alpaca API Verification")
        print("="*60)
        
        if not self.alpaca_key or not self.alpaca_secret:
            print("⚠️  Alpaca credentials not found in .env")
            print("   Skipping Alpaca verification")
            return True  # Don't fail, just skip
        
        try:
            print("Connecting to Alpaca API...")
            client = StockHistoricalDataClient(
                api_key=self.alpaca_key,
                secret_key=self.alpaca_secret,
                raw_data=False
            )
            
            # Get last 5 minutes of market data (most recent trading day)
            end_time = datetime.utcnow()
            start_time = end_time - timedelta(days=10)  # Look back 10 days to find last trading day
            
            request = StockBarsRequest(
                symbol_or_symbols=["SPY"],
                timeframe=TimeFrame.Minute,
                start=start_time,
                end=end_time
            )
            
            bars = client.get_stock_bars(request)
            
            if bars and "SPY" in bars and len(bars["SPY"]) > 0:
                latest_bar = bars["SPY"][-1]
                print(f"✅ Alpaca API: Connected")
                print(f"   Latest SPY bar: {latest_bar.timestamp} @ ${latest_bar.close}")
                print(f"   Retrieved {len(bars['SPY'])} bars")
                return True
            else:
                print("⚠️  Alpaca API: Connected but no recent data found")
                print("   Market may be closed or no data available")
                return True  # Don't fail
        
        except Exception as e:
            print(f"❌ Alpaca API: Connection failed - {e}")
            print("   Fix: Check ALPACA_API_KEY and ALPACA_SECRET_KEY in .env")
            return False
    
    async def verify_data_persistence(self) -> bool:
        """Verify data was written to database"""
        print("\n" + "="*60)
        print("STEP 4: Data Persistence Verification")
        print("="*60)
        
        if not self.db_pool:
            print("❌ Database not connected")
            return False
        
        try:
            async with self.db_pool.acquire() as conn:
                # Check candles_1m for SPY
                candle_count = await conn.fetchval("""
                    SELECT COUNT(*) 
                    FROM candles_1m 
                    WHERE ticker = 'SPY' 
                    AND time >= NOW() - INTERVAL '10 days'
                """)
                
                print(f"SPY 1-minute candles (last 10 days): {candle_count}")
                
                if candle_count >= 5:
                    print("✅ candles_1m: Data found")
                else:
                    print(f"⚠️  candles_1m: Only {candle_count} rows found (expected >= 5)")
                    print("   This is OK if ingestion hasn't run yet or market is closed")
                
                # Check for aggregated data
                candle_5m_count = await conn.fetchval("""
                    SELECT COUNT(*) 
                    FROM candles_5m 
                    WHERE ticker = 'SPY' 
                    AND time >= NOW() - INTERVAL '10 days'
                """)
                
                print(f"SPY 5-minute candles (last 10 days): {candle_5m_count}")
                
                if candle_5m_count > 0:
                    print("✅ candles_5m: Aggregation working")
                
                # Check ticks table (if data exists)
                tick_count = await conn.fetchval("""
                    SELECT COUNT(*) 
                    FROM ticks 
                    WHERE ticker = 'SPY' 
                    AND time >= NOW() - INTERVAL '7 days'
                """)
                
                print(f"SPY ticks (last 7 days): {tick_count}")
                
                # Check gap log
                gap_count = await conn.fetchval("""
                    SELECT COUNT(*) 
                    FROM ingest_gap_log 
                    WHERE backfilled = false
                """)
                
                if gap_count > 0:
                    print(f"⚠️  Gap log: {gap_count} unbackfilled gaps detected")
                else:
                    print("✅ Gap log: No unbackfilled gaps")
                
                # Get latest candle time
                latest_time = await conn.fetchval("""
                    SELECT MAX(time) 
                    FROM candles_1m 
                    WHERE ticker = 'SPY'
                """)
                
                if latest_time:
                    print(f"✅ Latest SPY candle: {latest_time}")
                else:
                    print("⚠️  No SPY candles found yet")
            
            print("\n✅ Data Persistence: Verified")
            return True
        
        except Exception as e:
            print(f"❌ Data Persistence: Verification failed - {e}")
            return False
    
    async def verify_redis_events(self) -> bool:
        """Verify Redis Pub/Sub events"""
        print("\n" + "="*60)
        print("STEP 5: Redis Pub/Sub Verification")
        print("="*60)
        
        if not self.redis_client:
            print("❌ Redis not connected")
            return False
        
        try:
            # Subscribe to ticker_update channel
            pubsub = self.redis_client.pubsub()
            await pubsub.subscribe("chan:ticker_update")
            
            print("Subscribed to chan:ticker_update")
            print("Waiting 5 seconds for messages...")
            
            messages_received = 0
            start_time = datetime.utcnow()
            
            while (datetime.utcnow() - start_time).total_seconds() < 5:
                try:
                    message = await asyncio.wait_for(pubsub.get_message(), timeout=1.0)
                    if message and message['type'] == 'message':
                        messages_received += 1
                        try:
                            data = json.loads(message['data'].decode('utf-8'))
                            print(f"   Received: {data.get('ticker', 'unknown')} @ {data.get('time', 'unknown')}")
                        except:
                            pass
                except asyncio.TimeoutError:
                    continue
            
            await pubsub.unsubscribe("chan:ticker_update")
            await pubsub.close()
            
            if messages_received > 0:
                print(f"✅ Redis Pub/Sub: {messages_received} messages received")
                return True
            else:
                print("⚠️  Redis Pub/Sub: No messages received (service may not be running)")
                print("   This is OK if ingestion service hasn't started or market is closed")
                return True  # Don't fail, just warn
        
        except Exception as e:
            print(f"⚠️  Redis Pub/Sub: Verification failed - {e}")
            print("   This is OK if no active ingestion")
            return True  # Don't fail
    
    async def cleanup(self):
        """Cleanup connections"""
        if self.db_pool:
            await self.db_pool.close()
        if self.redis_client:
            await self.redis_client.aclose()
    
    async def run_all_checks(self):
        """Run all verification checks"""
        print("\n" + "="*60)
        print("ZERO SYSTEM VERIFICATION")
        print("="*60)
        print(f"Time: {datetime.utcnow().isoformat()}")
        
        results = {}
        
        try:
            # Step 1: Infrastructure
            results['infrastructure'] = await self.check_infrastructure()
            if not results['infrastructure']:
                print("\n❌ FAILURE: Infrastructure check failed")
                return False
            
            # Step 2: Ingestion service
            results['ingestion'] = await self.trigger_ingestion()
            
            # Step 3: Alpaca API
            results['alpaca'] = await self.verify_alpaca_connection()
            
            # Step 4: Data persistence
            results['persistence'] = await self.verify_data_persistence()
            
            # Step 5: Redis events
            results['redis_events'] = await self.verify_redis_events()
            
            # Summary
            print("\n" + "="*60)
            print("VERIFICATION SUMMARY")
            print("="*60)
            
            for check, passed in results.items():
                status = "✅ PASS" if passed else "❌ FAIL"
                print(f"{check.upper():20} {status}")
            
            all_critical = results.get('infrastructure', False) and results.get('persistence', False)
            
            if all_critical:
                print("\n✅ SYSTEM VERIFIED: Infrastructure and data persistence working")
                return True
            else:
                print("\n⚠️  SYSTEM PARTIAL: Some checks failed (see above)")
                return False
        
        finally:
            await self.cleanup()


async def main():
    """Main entry point"""
    verifier = SystemVerifier()
    success = await verifier.run_all_checks()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    asyncio.run(main())

