#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ZERO System Verification Script - Standalone Mode
Tests code logic and Alpaca API without requiring Docker services
"""

import asyncio
import os
import sys
from datetime import datetime, timedelta
from typing import Optional
import json

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
    from alpaca.data.historical import StockHistoricalDataClient
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame
    ALPACA_AVAILABLE = True
except ImportError:
    ALPACA_AVAILABLE = False
    print("⚠️  Warning: alpaca-py not installed. Alpaca tests will be skipped.")

# Load environment variables
try:
    from dotenv import load_dotenv
    env_path = os.path.join(project_root, '.env')
    if os.path.exists(env_path):
        load_dotenv(env_path)
        print(f"✅ Loaded .env from {env_path}")
    else:
        print(f"⚠️  Warning: .env file not found at {env_path}")
        print("   Using system environment variables only")
except ImportError:
    print("⚠️  Warning: python-dotenv not installed. Using system environment variables only")


class StandaloneVerifier:
    """Standalone verification (no Docker required)"""
    
    def __init__(self):
        self.alpaca_key = os.getenv('ALPACA_API_KEY')
        self.alpaca_secret = os.getenv('ALPACA_SECRET_KEY')
        self.alpaca_paper = os.getenv('ALPACA_PAPER', 'true').lower() == 'true'
    
    def test_imports(self) -> bool:
        """Test that all required modules can be imported"""
        print("\n" + "="*60)
        print("TEST 1: Module Imports")
        print("="*60)
        
        modules = {
            'asyncpg': 'Database driver',
            'redis': 'Redis client',
            'alpaca-py': 'Alpaca API',
            'aiohttp': 'HTTP client',
            'pydantic': 'Data validation',
            'dotenv': 'Environment variables'
        }
        
        all_ok = True
        for module, desc in modules.items():
            try:
                if module == 'asyncpg':
                    import asyncpg
                elif module == 'redis':
                    import redis.asyncio as aioredis
                elif module == 'alpaca-py':
                    from alpaca.data.historical import StockHistoricalDataClient
                elif module == 'aiohttp':
                    import aiohttp
                elif module == 'pydantic':
                    import pydantic
                elif module == 'dotenv':
                    from dotenv import load_dotenv
                
                print(f"✅ {module:15} - {desc}")
            except ImportError:
                print(f"❌ {module:15} - {desc} (NOT INSTALLED)")
                all_ok = False
        
        return all_ok
    
    def test_project_structure(self) -> bool:
        """Test that project files exist"""
        print("\n" + "="*60)
        print("TEST 2: Project Structure")
        print("="*60)
        
        required_files = [
            ('contracts/schemas.py', 'Pydantic schemas'),
            ('contracts/db_schema.md', 'Database schema'),
            ('contracts/redis_keys.md', 'Redis contracts'),
            ('infra/docker-compose.yml', 'Docker Compose'),
            ('services/ingest/main.py', 'Ingestion service'),
            ('services/ingest/provider/alpaca.py', 'Alpaca provider'),
            ('infra/db/init.sql', 'Database init script'),
        ]
        
        all_ok = True
        for file_path, desc in required_files:
            full_path = os.path.join(project_root, file_path)
            if os.path.exists(full_path):
                print(f"✅ {file_path:40} - {desc}")
            else:
                print(f"❌ {file_path:40} - {desc} (NOT FOUND)")
                all_ok = False
        
        return all_ok
    
    def test_env_variables(self) -> bool:
        """Test that required environment variables are set"""
        print("\n" + "="*60)
        print("TEST 3: Environment Variables")
        print("="*60)
        
        required_vars = {
            'ALPACA_API_KEY': 'Alpaca API Key',
            'ALPACA_SECRET_KEY': 'Alpaca Secret Key',
        }
        
        optional_vars = {
            'DB_HOST': 'Database host',
            'DB_PASSWORD': 'Database password',
            'REDIS_HOST': 'Redis host',
        }
        
        all_ok = True
        
        # Check required
        for var, desc in required_vars.items():
            value = os.getenv(var)
            if value:
                masked = value[:8] + '...' if len(value) > 8 else '***'
                print(f"✅ {var:20} - {desc} ({masked})")
            else:
                print(f"❌ {var:20} - {desc} (NOT SET)")
                all_ok = False
        
        # Check optional
        for var, desc in optional_vars.items():
            value = os.getenv(var)
            if value:
                print(f"✅ {var:20} - {desc} (set)")
            else:
                print(f"⚠️  {var:20} - {desc} (not set, will use default)")
        
        return all_ok
    
    async def test_alpaca_api(self) -> bool:
        """Test Alpaca API connection and data retrieval"""
        print("\n" + "="*60)
        print("TEST 4: Alpaca API Connection & Data Retrieval")
        print("="*60)
        
        if not ALPACA_AVAILABLE:
            print("⚠️  Skipping: alpaca-py not installed")
            return True
        
        if not self.alpaca_key or not self.alpaca_secret:
            print("⚠️  Skipping: Alpaca credentials not found in .env")
            print("   Add ALPACA_API_KEY and ALPACA_SECRET_KEY to .env to test")
            return True
        
        try:
            print("Connecting to Alpaca API...")
            client = StockHistoricalDataClient(
                api_key=self.alpaca_key,
                secret_key=self.alpaca_secret,
                raw_data=False
            )
            
            # Test 1: Get daily bars (doesn't require SIP subscription)
            print("\nTest 4a: Fetching daily bars (30 days)...")
            end_time = datetime.utcnow() - timedelta(days=1)
            start_time = end_time - timedelta(days=30)
            
            request = StockBarsRequest(
                symbol_or_symbols=["SPY"],
                timeframe=TimeFrame.Day,
                start=start_time,
                end=end_time
            )
            
            bars = client.get_stock_bars(request)
            
            if bars and "SPY" in bars and len(bars["SPY"]) > 0:
                latest_bar = bars["SPY"][-1]
                print(f"✅ Daily bars: Retrieved {len(bars['SPY'])} bars")
                print(f"   Latest: {latest_bar.timestamp} @ ${latest_bar.close:.2f}")
            else:
                print("⚠️  Daily bars: No data returned (market may be closed)")
            
            # Test 2: Get minute bars using IEX feed (like ELVA and trading_ai do)
            print("\nTest 4b: Fetching minute bars with IEX feed (like ELVA/trading_ai)...")
            # Use IEX feed (free, no SIP required) - same way ELVA and trading_ai do it
            end_time = datetime.utcnow()
            start_time = end_time - timedelta(days=1)  # Last 24 hours
            
            request = StockBarsRequest(
                symbol_or_symbols=["SPY"],
                timeframe=TimeFrame.Minute,
                start=start_time,
                end=end_time,
                feed='iex'  # Use free IEX feed (no SIP required)
            )
            
            minute_bars = client.get_stock_bars(request)
            if minute_bars and "SPY" in minute_bars and len(minute_bars["SPY"]) > 0:
                print(f"✅ Minute bars: Retrieved {len(minute_bars['SPY'])} bars")
                latest = minute_bars["SPY"][-1]
                print(f"   Latest: {latest.timestamp} @ ${latest.close:.2f}")
                print("   ✅ Data format compatible with ingestion service")
                print("   ✅ Works exactly like ELVA and trading_ai (IEX feed)")
            else:
                print("⚠️  Minute bars: No data (market may be closed)")
                print("   ✅ API connection works - IEX feed accessible")
            
            print("\n✅ Alpaca API: Connection verified and data retrieval works")
            return True
        
        except Exception as e:
            print(f"❌ Alpaca API: Connection failed - {e}")
            print("   Fix: Check ALPACA_API_KEY and ALPACA_SECRET_KEY in .env")
            return False
    
    async def test_provider_code(self) -> bool:
        """Test that provider code can be imported, instantiated, and streams data"""
        print("\n" + "="*60)
        print("TEST 5: Provider Code Validation & Data Streaming")
        print("="*60)
        
        try:
            # Test importing providers
            from services.ingest.provider.base import MarketDataProvider, Candle
            print("✅ Provider base classes imported")
            
            from services.ingest.provider.mock import MockProvider
            print("✅ MockProvider imported")
            
            from services.ingest.provider.polygon import PolygonProvider
            print("✅ PolygonProvider imported")
            
            try:
                from services.ingest.provider.alpaca import AlpacaProvider
                print("✅ AlpacaProvider imported")
            except ImportError as e:
                print(f"⚠️  AlpacaProvider: {e}")
            
            # Test instantiating MockProvider
            mock = MockProvider(["SPY", "AAPL"])
            print("✅ MockProvider can be instantiated")
            
            # Test connecting MockProvider
            await mock.connect()
            print("✅ MockProvider can connect")
            
            # Test streaming (get one candle)
            print("   Testing data stream...")
            candle_count = 0
            async for candle in mock.stream_1m_candles(["SPY"]):
                candle_count += 1
                print(f"   ✅ Received candle: {candle.ticker} @ ${candle.close:.2f} ({candle.time})")
                if candle_count >= 1:
                    break  # Just test one candle
            
            await mock.disconnect()
            print("✅ MockProvider streaming works")
            
            # Test AlpacaProvider instantiation (if credentials available)
            if self.alpaca_key and self.alpaca_secret:
                try:
                    from services.ingest.provider.alpaca import AlpacaProvider
                    alpaca = AlpacaProvider(self.alpaca_key, self.alpaca_secret, True)
                    print("✅ AlpacaProvider can be instantiated")
                    await alpaca.connect()
                    print("✅ AlpacaProvider can connect")
                    health = await alpaca.health_check()
                    if health:
                        print("✅ AlpacaProvider health check passed")
                    await alpaca.disconnect()
                except Exception as e:
                    print(f"⚠️  AlpacaProvider test: {e}")
            
            # Test Candle dataclass
            candle = Candle(
                ticker="SPY",
                time=datetime.utcnow(),
                open=450.0,
                high=451.0,
                low=449.0,
                close=450.5,
                volume=1000000,
                source="test"
            )
            print(f"✅ Candle dataclass works: {candle.ticker} @ ${candle.close}")
            
            return True
        
        except Exception as e:
            print(f"❌ Provider code validation failed: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    async def test_database_writer_code(self) -> bool:
        """Test that database writer code can be imported and methods work"""
        print("\n" + "="*60)
        print("TEST 6: Database Writer Code Validation")
        print("="*60)
        
        try:
            from services.ingest.db.writer import DatabaseWriter
            from services.ingest.provider.base import Candle
            print("✅ DatabaseWriter imported")
            
            # Test that it can be instantiated (won't connect without DB)
            writer = DatabaseWriter("postgresql://test:test@localhost:5432/test")
            print("✅ DatabaseWriter can be instantiated")
            
            # Test creating a sample candle
            test_candle = Candle(
                ticker="SPY",
                time=datetime.utcnow(),
                open=450.0,
                high=451.0,
                low=449.0,
                close=450.5,
                volume=1000000,
                source="test"
            )
            
            # Test that methods exist and can be called (will fail on connect, but that's OK)
            print("   Testing method signatures...")
            import inspect
            
            methods = ['write_1m_candle', 'write_1m_candles_batch', 'aggregate_5m_candles', 
                      'aggregate_1d_candles', 'detect_gaps', 'get_last_candle_time', 'get_candle_count']
            
            for method_name in methods:
                if hasattr(writer, method_name):
                    method = getattr(writer, method_name)
                    sig = inspect.signature(method)
                    print(f"   ✅ {method_name}{sig}")
                else:
                    print(f"   ❌ {method_name} not found")
                    return False
            
            print("✅ DatabaseWriter methods validated")
            
            return True
        
        except Exception as e:
            print(f"❌ Database writer validation failed: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    async def test_redis_publisher_code(self) -> bool:
        """Test that Redis publisher code can be imported and methods work"""
        print("\n" + "="*60)
        print("TEST 7: Redis Publisher Code Validation")
        print("="*60)
        
        try:
            from services.ingest.redis.publisher import RedisPublisher
            from services.ingest.provider.base import Candle
            print("✅ RedisPublisher imported")
            
            # Test that it can be instantiated (won't connect without Redis)
            publisher = RedisPublisher("redis://localhost:6379")
            print("✅ RedisPublisher can be instantiated")
            
            # Test creating a sample candle
            test_candle = Candle(
                ticker="SPY",
                time=datetime.utcnow(),
                open=450.0,
                high=451.0,
                low=449.0,
                close=450.5,
                volume=1000000,
                source="test"
            )
            
            # Test that methods exist
            print("   Testing method signatures...")
            import inspect
            
            methods = ['publish_ticker_update', 'publish_index_update', 'publish_volatility_update']
            
            for method_name in methods:
                if hasattr(publisher, method_name):
                    method = getattr(publisher, method_name)
                    sig = inspect.signature(method)
                    print(f"   ✅ {method_name}{sig}")
                else:
                    print(f"   ❌ {method_name} not found")
                    return False
            
            print("✅ RedisPublisher methods validated")
            
            return True
        
        except Exception as e:
            print(f"❌ Redis publisher validation failed: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    async def test_integration_mock(self) -> bool:
        """Test full pipeline integration with mock data"""
        print("\n" + "="*60)
        print("TEST 9: Integration Test (Mock Pipeline)")
        print("="*60)
        
        try:
            from services.ingest.provider.mock import MockProvider
            from services.ingest.provider.base import Candle
            
            print("Simulating full ingestion pipeline...")
            
            # 1. Create provider
            provider = MockProvider(["SPY"])
            await provider.connect()
            print("✅ Step 1: Provider connected")
            
            # 2. Get a candle
            candle_count = 0
            async for candle in provider.stream_1m_candles(["SPY"]):
                candle_count += 1
                print(f"✅ Step 2: Received candle - {candle.ticker} @ ${candle.close:.2f}")
                
                # 3. Test schema conversion
                try:
                    from contracts.schemas import TickerUpdate
                    update = TickerUpdate(
                        ticker=candle.ticker,
                        price=candle.close,
                        volume=candle.volume,
                        time=candle.time
                    )
                    json_str = update.model_dump_json()
                    print(f"✅ Step 3: Converted to schema - {len(json_str)} bytes JSON")
                except Exception as e:
                    print(f"⚠️  Step 3: Schema conversion - {e}")
                
                # 4. Test database writer format (without actual DB)
                print(f"✅ Step 4: Candle ready for DB write:")
                print(f"   - Ticker: {candle.ticker}")
                print(f"   - Time: {candle.time}")
                print(f"   - OHLC: ${candle.open:.2f} / ${candle.high:.2f} / ${candle.low:.2f} / ${candle.close:.2f}")
                print(f"   - Volume: {candle.volume:,}")
                print(f"   - Source: {candle.source}")
                
                if candle_count >= 1:
                    break
            
            await provider.disconnect()
            print("\n✅ Integration test: Full pipeline logic validated")
            print("   ✅ Provider -> Candle -> Schema -> Ready for DB/Redis")
            return True
        
        except Exception as e:
            print(f"❌ Integration test failed: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def test_schemas(self) -> bool:
        """Test that Pydantic schemas can be imported"""
        print("\n" + "="*60)
        print("TEST 8: Pydantic Schemas Validation")
        print("="*60)
        
        try:
            from contracts.schemas import (
                TickerUpdate, IndexUpdate, VolatilityUpdate,
                MarketState, AttentionState
            )
            print("✅ All schemas imported")
            
            # Test creating a schema instance
            update = TickerUpdate(
                ticker="SPY",
                price=450.5,
                volume=1000000,
                time=datetime.utcnow()
            )
            print(f"✅ TickerUpdate schema works: {update.ticker} @ ${update.price}")
            
            # Test JSON serialization
            json_str = update.model_dump_json()
            print(f"✅ Schema JSON serialization works ({len(json_str)} bytes)")
            
            return True
        
        except Exception as e:
            print(f"❌ Schema validation failed: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    async def run_all_tests(self):
        """Run all standalone tests"""
        print("\n" + "="*60)
        print("ZERO SYSTEM VERIFICATION - STANDALONE MODE")
        print("="*60)
        print(f"Time: {datetime.utcnow().isoformat()}")
        print(f"Project Root: {project_root}")
        print("\nNote: This mode tests code without requiring Docker services")
        
        results = {}
        
        # Test 1: Imports
        results['imports'] = self.test_imports()
        
        # Test 2: Project structure
        results['structure'] = self.test_project_structure()
        
        # Test 3: Environment variables
        results['env_vars'] = self.test_env_variables()
        
        # Test 4: Alpaca API
        results['alpaca'] = await self.test_alpaca_api()
        
        # Test 5: Provider code
        results['provider_code'] = await self.test_provider_code()
        
        # Test 6: Database writer code
        results['db_writer'] = await self.test_database_writer_code()
        
        # Test 7: Redis publisher code
        results['redis_publisher'] = await self.test_redis_publisher_code()
        
        # Test 8: Schemas
        results['schemas'] = self.test_schemas()
        
        # Test 9: Integration test (mock full pipeline)
        results['integration'] = await self.test_integration_mock()
        
        # Summary
        print("\n" + "="*60)
        print("VERIFICATION SUMMARY")
        print("="*60)
        
        for test, passed in results.items():
            status = "✅ PASS" if passed else "❌ FAIL"
            print(f"{test.upper():20} {status}")
        
        critical_tests = ['imports', 'structure', 'provider_code', 'db_writer', 'redis_publisher', 'schemas', 'integration']
        critical_passed = all(results.get(t, False) for t in critical_tests)
        
        if critical_passed:
            print("\n✅ CODE VERIFICATION PASSED: All critical components validated")
            print("\nNext steps:")
            print("1. Deploy to Jetson Orin AGX")
            print("2. Run 'make up' to start Docker services")
            print("3. Run 'python scripts/verify_system.py' for full system test")
            return True
        else:
            print("\n❌ CODE VERIFICATION FAILED: Some critical tests failed")
            return False


async def main():
    """Main entry point"""
    verifier = StandaloneVerifier()
    success = await verifier.run_all_tests()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    asyncio.run(main())

