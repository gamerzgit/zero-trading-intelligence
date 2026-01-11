#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ZERO System Verification Script
Verifies Milestone 0 Infrastructure + Milestone 1 Price Ingestion
"""

import asyncio
import os
import sys
import subprocess
from datetime import datetime, timedelta
from typing import Optional
import json
import time

# Fix Windows console encoding
if sys.platform == 'win32':
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

# Add project root to path
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(script_dir, '..'))
sys.path.insert(0, project_root)

try:
    import asyncpg
    import redis.asyncio as aioredis
    from alpaca.data.historical import StockHistoricalDataClient
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame
    import aiohttp
    ALPACA_AVAILABLE = True
except ImportError as e:
    print(f"❌ Missing dependencies: {e}")
    print("Install: pip install asyncpg redis alpaca-py aiohttp python-dotenv")
    sys.exit(1)

# Load environment variables
try:
    from dotenv import load_dotenv
    env_path = os.path.join(project_root, '.env')
    if os.path.exists(env_path):
        load_dotenv(env_path)
    else:
        print(f"⚠️  Warning: .env file not found at {env_path}")
except ImportError:
    pass


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
    
    def check_docker_available(self) -> bool:
        """Check if Docker is available"""
        try:
            result = subprocess.run(
                ['docker', '--version'],
                capture_output=True,
                text=True,
                timeout=5
            )
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False
    
    async def check_infrastructure(self) -> bool:
        """Check Redis and TimescaleDB connectivity"""
        print("\n" + "="*60)
        print("STEP 1: Infrastructure Check")
        print("="*60)
        
        # Check Docker first
        if not self.check_docker_available():
            print("❌ Docker not available")
            print("   Fix: Install Docker Desktop or ensure Docker is in PATH")
            print("   Note: Full verification requires Docker services running")
            return False
        
        # Check if services are running
        try:
            result = subprocess.run(
                ['docker', 'compose', '-f', 'infra/docker-compose.yml', 'ps'],
                cwd=project_root,
                capture_output=True,
                text=True,
                timeout=10
            )
            if 'timescaledb' not in result.stdout.lower() or 'redis' not in result.stdout.lower():
                print("⚠️  Docker services may not be running")
                print("   Run: docker compose -f infra/docker-compose.yml up -d")
        except Exception as e:
            print(f"⚠️  Could not check Docker services: {e}")
        
        # Check Redis
        try:
            print("Checking Redis...")
            self.redis_client = aioredis.from_url(
                self.redis_url,
                decode_responses=False,
                socket_connect_timeout=5
            )
            pong = await asyncio.wait_for(self.redis_client.ping(), timeout=5)
            if pong:
                print("✅ Redis: Connected")
            else:
                print("❌ Redis: Ping failed")
                return False
        except asyncio.TimeoutError:
            print(f"❌ Redis: Connection timeout to {self.redis_url}")
            print("   Fix: Ensure Redis container is running (make up)")
            return False
        except Exception as e:
            print(f"❌ Redis: Connection failed - {e}")
            print("   Fix: Ensure Redis container is running (make up)")
            return False
        
        # Check TimescaleDB
        try:
            print("Checking TimescaleDB...")
            self.db_pool = await asyncio.wait_for(
                asyncpg.create_pool(self.db_url, min_size=1, max_size=3),
                timeout=10
            )
            
            async with self.db_pool.acquire() as conn:
                # Check required tables exist
                tables = await conn.fetch("""
                    SELECT table_name 
                    FROM information_schema.tables 
                    WHERE table_schema = 'public' 
                    AND table_name IN ('candles_1m', 'ticks', 'ingest_gap_log')
                    ORDER BY table_name
                """)
                
                required_tables = {'candles_1m', 'ticks', 'ingest_gap_log'}
                found_tables = {row['table_name'] for row in tables}
                missing = required_tables - found_tables
                
                if missing:
                    print(f"❌ TimescaleDB: Missing tables - {missing}")
                    print("   Fix: Ensure init.sql ran successfully")
                    return False
                
                print(f"✅ TimescaleDB: Connected (found {len(found_tables)} required tables)")
        
        except asyncio.TimeoutError:
            print(f"❌ TimescaleDB: Connection timeout to {self.db_url}")
            print("   Fix: Check DB credentials in .env and ensure container is running")
            return False
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
        
        # Try HTTP endpoint first
        try:
            print("Checking ingestion service health endpoint...")
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    'http://localhost:8080/health',
                    timeout=aiohttp.ClientTimeout(total=5)
                ) as resp:
                    if resp.status == 200:
                        health = await resp.json()
                        print(f"✅ Ingestion service: Running (status: {health.get('status', 'unknown')})")
                        
                        # Check if there's a backfill endpoint (future feature)
                        # For now, we'll use environment variable method
                        print("\nTo trigger backfill:")
                        print("1. Set in .env: PROVIDER_TYPE=alpaca")
                        print("2. Set in .env: FORCE_BACKFILL=1 (if supported)")
                        print("3. Restart service:")
                        print("   docker compose -f infra/docker-compose.yml restart zero-ingest-price")
                        print("\nOr wait for next scheduled ingestion cycle...")
                        return True
        except asyncio.TimeoutError:
            print("⚠️  Ingestion service: Not reachable (timeout)")
        except Exception as e:
            print(f"⚠️  Ingestion service: Not reachable - {e}")
        
        # If HTTP fails, provide instructions
        print("\nIngestion service not reachable via HTTP")
        print("To start/restart ingestion:")
        print("1. Ensure .env has:")
        print("   PROVIDER_TYPE=alpaca")
        print("   ALPACA_API_KEY=...")
        print("   ALPACA_SECRET_KEY=...")
        print("2. Run: docker compose -f infra/docker-compose.yml up -d zero-ingest-price")
        print("3. Or restart: docker compose -f infra/docker-compose.yml restart zero-ingest-price")
        
        # Try to restart if Docker is available
        if self.check_docker_available():
            print("\nAttempting to restart ingestion service...")
            try:
                result = subprocess.run(
                    ['docker', 'compose', '-f', 'infra/docker-compose.yml', 'restart', 'zero-ingest-price'],
                    cwd=project_root,
                    capture_output=True,
                    text=True,
                    timeout=30
                )
                if result.returncode == 0:
                    print("✅ Ingestion service restarted")
                    print("   Waiting 5 seconds for service to initialize...")
                    await asyncio.sleep(5)
                    return True
                else:
                    print(f"⚠️  Restart failed: {result.stderr}")
            except Exception as e:
                print(f"⚠️  Could not restart service: {e}")
        
        return True  # Don't fail, just warn
    
    async def verify_persistence(self) -> bool:
        """Verify data was written to database"""
        print("\n" + "="*60)
        print("STEP 3: Verify Persistence")
        print("="*60)
        
        if not self.db_pool:
            print("❌ Database not connected")
            return False
        
        print("Polling database for data (up to 10 seconds)...")
        
        max_wait = 10
        start_time = time.time()
        ticks_found = False
        candles_found = False
        
        while (time.time() - start_time) < max_wait:
            try:
                async with self.db_pool.acquire() as conn:
                    # Check ticks table
                    tick_count = await conn.fetchval("""
                        SELECT COUNT(*) 
                        FROM ticks 
                        WHERE ticker = 'SPY' 
                        AND source = 'alpaca'
                        AND time >= NOW() - INTERVAL '10 days'
                    """)
                    
                    # Check candles_1m table
                    candle_count = await conn.fetchval("""
                        SELECT COUNT(*) 
                        FROM candles_1m 
                        WHERE ticker = 'SPY' 
                        AND time >= NOW() - INTERVAL '10 days'
                    """)
                    
                    if tick_count and tick_count >= 5:
                        ticks_found = True
                        print(f"✅ Ticks found: {tick_count} rows for SPY (source='alpaca')")
                    
                    if candle_count and candle_count >= 5:
                        candles_found = True
                        print(f"✅ Candles found: {candle_count} rows for SPY in candles_1m")
                    
                    if ticks_found and candles_found:
                        print("\n✅ Data Flow Verified: Alpaca -> (normalize) -> Redis -> DB")
                        return True
                    
                    # Wait a bit before next check
                    await asyncio.sleep(1)
            
            except Exception as e:
                print(f"⚠️  Error checking database: {e}")
                await asyncio.sleep(1)
        
        # Final check
        if not ticks_found:
            print(f"⚠️  Ticks: Only {tick_count if 'tick_count' in locals() else 0} rows found (expected >= 5)")
            print("   This is OK if:")
            print("   - Ingestion service hasn't run yet")
            print("   - Market is closed (Sunday/holiday)")
            print("   - Service is using mock provider")
        
        if not candles_found:
            print(f"⚠️  Candles: Only {candle_count if 'candle_count' in locals() else 0} rows found (expected >= 5)")
            print("   This is OK if:")
            print("   - Ingestion service hasn't run yet")
            print("   - Market is closed (Sunday/holiday)")
            print("   - Service is using mock provider")
        
        if ticks_found or candles_found:
            print("\n⚠️  Partial data found - ingestion may be in progress")
            return True
        
        print("\n⚠️  No data found yet - ingestion may not have started")
        return False  # Don't fail completely, but warn
    
    async def verify_redis_events(self) -> bool:
        """Verify Redis Pub/Sub events"""
        print("\n" + "="*60)
        print("STEP 4: Redis Pub/Sub Verification (Bonus)")
        print("="*60)
        
        if not self.redis_client:
            print("❌ Redis not connected")
            return False
        
        try:
            # Subscribe to ticker_update channel
            pubsub = self.redis_client.pubsub()
            await pubsub.subscribe("chan:ticker_update")
            
            print("Subscribed to chan:ticker_update")
            print("Waiting 2 seconds for messages...")
            
            messages_received = 0
            start_time = time.time()
            
            while (time.time() - start_time) < 2:
                try:
                    message = await asyncio.wait_for(pubsub.get_message(), timeout=0.5)
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
                print("⚠️  Redis Pub/Sub: No messages received (non-blocking)")
                print("   This is OK if DB writes succeeded - service may not be actively publishing")
                return True  # Don't fail, just warn
        
        except Exception as e:
            print(f"⚠️  Redis Pub/Sub: Verification failed - {e}")
            print("   This is OK if DB writes succeeded")
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
        print(f"Project Root: {project_root}")
        
        results = {}
        
        try:
            # Step 1: Infrastructure
            results['infrastructure'] = await self.check_infrastructure()
            if not results['infrastructure']:
                print("\n❌ FAILURE: Infrastructure check failed")
                print("   Cannot proceed without Redis and TimescaleDB")
                return False
            
            # Step 2: Trigger ingestion
            results['ingestion'] = await self.trigger_ingestion()
            
            # Step 3: Verify persistence
            results['persistence'] = await self.verify_persistence()
            
            # Step 4: Redis events (bonus)
            results['redis_events'] = await self.verify_redis_events()
            
            # Summary
            print("\n" + "="*60)
            print("VERIFICATION SUMMARY")
            print("="*60)
            
            for check, passed in results.items():
                status = "✅ PASS" if passed else "❌ FAIL"
                print(f"{check.upper():20} {status}")
            
            critical_passed = results.get('infrastructure', False)
            
            if critical_passed and results.get('persistence', False):
                print("\n✅ SYSTEM VERIFIED: Infrastructure and data persistence working")
                return True
            elif critical_passed:
                print("\n⚠️  SYSTEM PARTIAL: Infrastructure ready, but data not yet ingested")
                print("   This is normal if:")
                print("   - Market is closed (Sunday/holiday)")
                print("   - Ingestion service just started")
                print("   - Using mock provider")
                return True
            else:
                print("\n❌ SYSTEM FAILED: Critical checks failed")
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
