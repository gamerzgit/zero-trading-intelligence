#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ZERO System State Verification Script
Comprehensive validation for Milestones 0-3: Infrastructure + Services + State

Validates:
- Milestone 0: Infrastructure (containers, Redis, TimescaleDB, schema)
- Milestone 1: Ingestion (health, freshness, gaps, market calendar aware)
- Milestone 2: Regime (health, Redis state, DB logs, logic consistency)
- Milestone 3: Scanner (health, veto-aware, Redis outputs, DB logging)
"""

import asyncio
import os
import sys
import json
import subprocess
from datetime import datetime, timezone, timedelta, time as dt_time, date
from typing import Tuple, Optional, Dict, Any, List
from enum import Enum

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
    import aiohttp
    import asyncpg
    import redis.asyncio as redis
    from dotenv import load_dotenv
    DEPENDENCIES_AVAILABLE = True
except ImportError as e:
    DEPENDENCIES_AVAILABLE = False
    print(f"❌ Missing dependencies: {e}")
    print("   Install: pip install -r scripts/requirements.txt")
    sys.exit(1)

# Load environment
env_path = os.path.join(project_root, '.env')
if os.path.exists(env_path):
    load_dotenv(env_path)

# Configuration
# For host-side scripts, use localhost (Docker ports are exposed)
# For Docker containers, use service names (timescaledb, redis)
DB_HOST = os.getenv('DB_HOST', 'localhost')
# If DB_HOST is a Docker service name, try localhost for host-side scripts
if DB_HOST in ['timescaledb', 'redis']:
    DB_HOST = 'localhost'

DB_PORT = int(os.getenv('DB_PORT', '5432'))
DB_NAME = os.getenv('DB_NAME', 'zero_trading')
DB_USER = os.getenv('DB_USER', 'zero_user')
DB_PASSWORD = os.getenv('DB_PASSWORD', '')

REDIS_HOST = os.getenv('REDIS_HOST', 'localhost')
# If REDIS_HOST is a Docker service name, try localhost for host-side scripts
if REDIS_HOST in ['timescaledb', 'redis']:
    REDIS_HOST = 'localhost'

REDIS_PORT = int(os.getenv('REDIS_PORT', '6379'))

INGEST_PORT = 8080
REGIME_PORT = 8000
SCANNER_PORT = 8001

# Market calendar (optional - graceful degradation)
try:
    import pandas_market_calendars as mcal
    import pytz
    NYSE = mcal.get_calendar('NYSE')
    ET = pytz.timezone('America/New_York')
    MARKET_CALENDAR_AVAILABLE = True
except ImportError:
    MARKET_CALENDAR_AVAILABLE = False
    ET = None


class CheckResult(Enum):
    PASS = "PASS"
    WARN = "WARN"
    FAIL = "FAIL"


class StateVerifier:
    """Comprehensive system state verification for Milestones 0-3"""
    
    def __init__(self):
        self.results: Dict[str, Tuple[CheckResult, str]] = {}
        self.db_pool: Optional[asyncpg.Pool] = None
        self.redis_client: Optional[redis.Redis] = None
        
    def is_market_open(self, dt: datetime) -> Tuple[bool, str]:
        """Check if market is open (weekend/holiday/off-hours aware)"""
        if not MARKET_CALENDAR_AVAILABLE:
            # Fallback: basic weekday check
            weekday = dt.weekday()
            if weekday >= 5:  # Saturday (5) or Sunday (6)
                return False, "Weekend"
            # Assume market hours 9:30 AM - 4:00 PM ET
            et_time = dt.astimezone(ET) if ET else dt
            hour = et_time.hour
            if hour < 9 or (hour == 9 and et_time.minute < 30) or hour >= 16:
                return False, "Off-hours"
            return True, "Market open"
        
        try:
            et_dt = dt.astimezone(ET)
            schedule = NYSE.schedule(start_date=et_dt.date(), end_date=et_dt.date())
            
            if schedule.empty:
                return False, "NYSE holiday"
            
            market_open = schedule.iloc[0]['market_open'].astimezone(ET)
            market_close = schedule.iloc[0]['market_close'].astimezone(ET)
            
            if et_dt < market_open or et_dt > market_close:
                return False, "Off-hours"
            
            return True, "Market open"
        except Exception as e:
            # Fallback on error
            return False, f"Calendar error: {str(e)[:50]}"
    
    async def check_docker_services(self) -> Tuple[CheckResult, str]:
        """Check if Docker services are running"""
        try:
            compose_file = os.path.join(project_root, 'infra', 'docker-compose.yml')
            result = subprocess.run(
                ['docker', 'compose', '-f', compose_file, 'ps', '--format', 'json'],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode != 0:
                return CheckResult.FAIL, "Docker Compose command failed"
            
            services = []
            for line in result.stdout.strip().split('\n'):
                if line:
                    try:
                        service = json.loads(line)
                        services.append(service)
                    except:
                        pass
            
            required_services = ['timescaledb', 'redis', 'grafana', 'zero-ingest-price', 'zero-regime', 'zero-scanner']
            running_services = {s.get('Service', ''): s.get('State', '') for s in services}
            
            missing = []
            not_running = []
            for svc in required_services:
                if svc not in running_services:
                    missing.append(svc)
                elif running_services[svc] != 'running':
                    not_running.append(f"{svc}({running_services[svc]})")
            
            if missing:
                return CheckResult.FAIL, f"Missing services: {', '.join(missing)}"
            if not_running:
                return CheckResult.FAIL, f"Services not running: {', '.join(not_running)}"
            
            return CheckResult.PASS, f"All {len(required_services)} services running"
        except FileNotFoundError:
            return CheckResult.FAIL, "Docker not found - install Docker Desktop"
        except Exception as e:
            return CheckResult.FAIL, f"Docker check error: {str(e)[:100]}"
    
    async def check_redis_connectivity(self) -> Tuple[CheckResult, str]:
        """Check Redis connectivity"""
        try:
            if not self.redis_client:
                await self.connect_redis()
            
            if not self.redis_client:
                return CheckResult.FAIL, "Redis connection failed"
            
            await self.redis_client.ping()
            return CheckResult.PASS, f"Redis connected: {REDIS_HOST}:{REDIS_PORT}"
        except Exception as e:
            return CheckResult.FAIL, f"Redis ping failed: {str(e)[:100]}"
    
    async def check_db_connectivity(self) -> Tuple[CheckResult, str]:
        """Check TimescaleDB connectivity"""
        try:
            if not self.db_pool:
                await self.connect_db()
            
            if not self.db_pool:
                return CheckResult.FAIL, "Database connection failed"
            
            await self.db_pool.fetchval("SELECT 1")
            return CheckResult.PASS, f"TimescaleDB connected: {DB_HOST}:{DB_PORT}"
        except Exception as e:
            return CheckResult.FAIL, f"Database query failed: {str(e)[:100]}"
    
    async def check_db_schema_integrity(self) -> Tuple[CheckResult, str]:
        """Check that required tables and hypertables exist"""
        if not self.db_pool:
            return CheckResult.FAIL, "Database not connected"
        
        try:
            # Required tables
            required_tables = [
                'candles_1m', 'candles_5m', 'candles_1d',
                'ticks',
                'regime_log', 'attention_log',
                'ingest_gap_log',
                'scanner_log'
            ]
            
            # Check tables exist
            tables_check = await self.db_pool.fetch("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_name = ANY($1::text[])
            """, required_tables)
            
            found_tables = {row['table_name'] for row in tables_check}
            missing_tables = set(required_tables) - found_tables
            
            if missing_tables:
                return CheckResult.FAIL, f"Missing tables: {', '.join(sorted(missing_tables))}"
            
            # Check hypertables
            hypertables_check = await self.db_pool.fetch("""
                SELECT hypertable_name 
                FROM timescaledb_information.hypertables
                WHERE hypertable_name = ANY($1::text[])
            """, ['candles_1m', 'candles_5m', 'candles_1d', 'ticks', 'regime_log', 'attention_log'])
            
            found_hypertables = {row['hypertable_name'] for row in hypertables_check}
            required_hypertables = {'candles_1m', 'candles_5m', 'candles_1d', 'ticks', 'regime_log', 'attention_log'}
            missing_hypertables = required_hypertables - found_hypertables
            
            if missing_hypertables:
                return CheckResult.FAIL, f"Missing hypertables: {', '.join(sorted(missing_hypertables))}"
            
            return CheckResult.PASS, f"Schema OK: {len(found_tables)} tables, {len(found_hypertables)} hypertables"
        except Exception as e:
            return CheckResult.FAIL, f"Schema check error: {str(e)[:100]}"
    
    async def check_service_health(self, service_name: str, port: int) -> Tuple[CheckResult, str, Optional[Dict]]:
        """Check service health endpoint"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f'http://localhost:{port}/health',
                    timeout=aiohttp.ClientTimeout(total=5)
                ) as resp:
                    if resp.status != 200:
                        return CheckResult.FAIL, f"Health endpoint returned {resp.status}", None
                    
                    try:
                        data = await resp.json()
                        return CheckResult.PASS, f"{service_name} health OK", data
                    except json.JSONDecodeError:
                        return CheckResult.FAIL, "Invalid JSON response", None
        except aiohttp.ClientError as e:
            return CheckResult.FAIL, f"Health endpoint unreachable: {str(e)[:100]}", None
        except Exception as e:
            return CheckResult.FAIL, f"Health check error: {str(e)[:100]}", None
    
    async def check_ingestion_freshness(self) -> Tuple[CheckResult, str]:
        """Check ingestion freshness (market calendar aware)"""
        if not self.db_pool:
            return CheckResult.FAIL, "Database not connected"
        
        try:
            # Get latest candle timestamp
            latest_time = await self.db_pool.fetchval("""
                SELECT MAX(time) FROM candles_1m
            """)
            
            if not latest_time:
                return CheckResult.WARN, "No candles found in database"
            
            now = datetime.now(timezone.utc)
            age_seconds = (now - latest_time).total_seconds()
            age_minutes = age_seconds / 60
            
            # Check if market is open
            is_open, reason = self.is_market_open(now)
            
            if not is_open:
                # Market closed - warn if data is very old (>7 days), otherwise pass
                if age_seconds > 7 * 24 * 3600:
                    return CheckResult.WARN, f"Market closed ({reason}), but last candle is {age_minutes:.0f} minutes old (>7 days)"
                return CheckResult.PASS, f"Market closed ({reason}) - freshness not expected (last candle: {age_minutes:.0f}m ago)"
            
            # Market is open - should be fresh (<5 minutes)
            if age_minutes > 5:
                return CheckResult.FAIL, f"Market open but last candle is {age_minutes:.0f} minutes old (>5 minutes)"
            
            return CheckResult.PASS, f"Freshness OK: last candle {age_minutes:.1f} minutes ago"
        except Exception as e:
            return CheckResult.FAIL, f"Freshness check error: {str(e)[:100]}"
    
    async def check_ingestion_gaps(self) -> Tuple[CheckResult, str]:
        """Check for ingestion gaps"""
        if not self.db_pool:
            return CheckResult.FAIL, "Database not connected"
        
        try:
            unbackfilled_count = await self.db_pool.fetchval("""
                SELECT COUNT(*) FROM ingest_gap_log WHERE backfilled = false
            """)
            
            if unbackfilled_count > 0:
                return CheckResult.WARN, f"{unbackfilled_count} unbackfilled gaps detected"
            
            return CheckResult.PASS, "No unbackfilled gaps"
        except Exception as e:
            return CheckResult.FAIL, f"Gap check error: {str(e)[:100]}"
    
    async def check_redis_contracts(self) -> Tuple[CheckResult, str]:
        """Check Redis keys and channels exist"""
        if not self.redis_client:
            return CheckResult.FAIL, "Redis not connected"
        
        try:
            # Check required keys
            required_keys = ['key:market_state']
            missing_keys = []
            
            for key in required_keys:
                exists = await self.redis_client.exists(key)
                if not exists:
                    missing_keys.append(key)
            
            if missing_keys:
                return CheckResult.FAIL, f"Missing Redis keys: {', '.join(missing_keys)}"
            
            # Check channels (via PUBSUB)
            channels = await self.redis_client.pubsub_channels('chan:*')
            channel_names = [ch.decode('utf-8') if isinstance(ch, bytes) else ch for ch in channels]
            
            required_channels = ['chan:ticker_update', 'chan:market_state_changed']
            missing_channels = [ch for ch in required_channels if ch not in channel_names]
            
            if missing_channels:
                return CheckResult.WARN, f"Missing channels (may not be active): {', '.join(missing_channels)}"
            
            return CheckResult.PASS, f"Redis contracts OK: {len(required_keys)} keys, {len(channel_names)} channels"
        except Exception as e:
            return CheckResult.FAIL, f"Redis contract check error: {str(e)[:100]}"
    
    async def check_regime_redis_state(self) -> Tuple[CheckResult, str]:
        """Check regime Redis state (key:market_state)"""
        if not self.redis_client:
            return CheckResult.FAIL, "Redis not connected"
        
        try:
            state_json = await self.redis_client.get("key:market_state")
            if not state_json:
                return CheckResult.FAIL, "key:market_state not found in Redis"
            
            state_dict = json.loads(state_json.decode('utf-8'))
            state = state_dict.get('state', 'UNKNOWN')
            
            # Validate state
            if state not in ['GREEN', 'YELLOW', 'RED']:
                return CheckResult.FAIL, f"Invalid market state: {state}"
            
            # Check weekend/holiday logic
            now = datetime.now(timezone.utc)
            is_open, reason = self.is_market_open(now)
            
            if not is_open and state != 'RED':
                return CheckResult.FAIL, f"Market closed ({reason}) but state is {state} (should be RED)"
            
            return CheckResult.PASS, f"MarketState: {state} ({state_dict.get('reason', 'N/A')})"
        except json.JSONDecodeError:
            return CheckResult.FAIL, "key:market_state contains invalid JSON"
        except Exception as e:
            return CheckResult.FAIL, f"Regime state check error: {str(e)[:100]}"
    
    async def check_regime_db_logs(self) -> Tuple[CheckResult, str]:
        """Check regime database logging"""
        if not self.db_pool:
            return CheckResult.FAIL, "Database not connected"
        
        try:
            # Check regime_log has entries
            count = await self.db_pool.fetchval("SELECT COUNT(*) FROM regime_log")
            
            if count == 0:
                return CheckResult.WARN, "regime_log is empty"
            
            # Check latest entry is recent (<10 minutes)
            latest_time = await self.db_pool.fetchval("SELECT MAX(created_at) FROM regime_log")
            if latest_time:
                age_minutes = (datetime.now(timezone.utc) - latest_time).total_seconds() / 60
                if age_minutes > 10:
                    return CheckResult.WARN, f"Latest regime_log entry is {age_minutes:.0f} minutes old"
                return CheckResult.PASS, f"regime_log OK: {count} entries, latest {age_minutes:.1f}m ago"
            
            return CheckResult.PASS, f"regime_log OK: {count} entries"
        except Exception as e:
            return CheckResult.FAIL, f"Regime DB log check error: {str(e)[:100]}"
    
    async def check_scanner_health(self) -> Tuple[CheckResult, str, Optional[Dict]]:
        """Check scanner service health endpoint"""
        return await self.check_service_health("zero-scanner", SCANNER_PORT)
    
    async def check_scanner_veto_aware(self) -> Tuple[CheckResult, str]:
        """Check that scanner respects MarketState RED veto"""
        if not self.redis_client:
            return CheckResult.FAIL, "Redis not connected"
        
        try:
            # Get market state
            state_json = await self.redis_client.get("key:market_state")
            if not state_json:
                return CheckResult.FAIL, "MarketState not found in Redis"
            
            state_dict = json.loads(state_json.decode('utf-8'))
            market_state = state_dict.get('state', 'UNKNOWN')
            
            # Get scanner health
            health_result, health_msg, health_data = await self.check_scanner_health()
            if health_result == CheckResult.FAIL:
                return CheckResult.FAIL, f"Cannot verify veto-aware: {health_msg}"
            
            if market_state == "RED":
                # Scanner should be aware of RED state
                if health_data:
                    details = health_data.get('details', {})
                    market_state_seen = details.get('market_state_seen', 'UNKNOWN')
                    
                    if market_state_seen != 'RED':
                        return CheckResult.WARN, f"MarketState RED but scanner sees: {market_state_seen}"
                    
                    return CheckResult.PASS, f"MarketState RED - scanner aware (status: {health_data.get('status')})"
                else:
                    return CheckResult.WARN, "MarketState RED - cannot verify scanner awareness"
            else:
                return CheckResult.PASS, f"MarketState {market_state} - scanner should be active"
        except Exception as e:
            return CheckResult.FAIL, f"Veto check error: {str(e)[:100]}"
    
    async def check_scanner_redis_outputs(self) -> Tuple[CheckResult, str]:
        """Check scanner Redis outputs (key:active_candidates)"""
        if not self.redis_client:
            return CheckResult.FAIL, "Redis not connected"
        
        try:
            candidates_json = await self.redis_client.get("key:active_candidates")
            
            if not candidates_json:
                return CheckResult.WARN, "key:active_candidates not found (scanner may not have run yet)"
            
            candidates_data = json.loads(candidates_json.decode('utf-8'))
            
            # Validate structure
            if not isinstance(candidates_data, dict):
                return CheckResult.FAIL, "key:active_candidates is not a structured object"
            
            # Check for required fields (structured format)
            has_intraday = 'intraday' in candidates_data
            has_swing = 'swing' in candidates_data
            has_scan_time = 'scan_time' in candidates_data
            
            if not (has_intraday and has_swing and has_scan_time):
                return CheckResult.FAIL, f"Missing required fields (intraday: {has_intraday}, swing: {has_swing}, scan_time: {has_scan_time})"
            
            # Verify NO ranking/probability fields (Level 2 only)
            forbidden_fields = ['opportunity_score', 'probability', 'rank', 'score', 'opportunity']
            candidate_str = json.dumps(candidates_data).lower()
            has_forbidden = any(field in candidate_str for field in forbidden_fields)
            
            if has_forbidden:
                return CheckResult.FAIL, "key:active_candidates contains forbidden Level 3 fields"
            
            # Count candidates
            intraday = candidates_data.get('intraday', {})
            swing = candidates_data.get('swing', {})
            total_intraday = sum(len(intraday.get(h, [])) for h in ['H30', 'H2H'])
            total_swing = sum(len(swing.get(h, [])) for h in ['HDAY', 'HWEEK'])
            
            return CheckResult.PASS, f"Scanner outputs OK: {total_intraday} intraday, {total_swing} swing candidates"
        except json.JSONDecodeError:
            return CheckResult.FAIL, "key:active_candidates contains invalid JSON"
        except Exception as e:
            return CheckResult.FAIL, f"Scanner Redis output check error: {str(e)[:100]}"
    
    async def check_scanner_db_logging(self) -> Tuple[CheckResult, str]:
        """Check scanner database logging (scanner_log table)"""
        if not self.db_pool:
            return CheckResult.FAIL, "Database not connected"
        
        try:
            # Check scanner_log table exists
            table_exists = await self.db_pool.fetchval("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_schema = 'public' 
                    AND table_name = 'scanner_log'
                )
            """)
            
            if not table_exists:
                return CheckResult.FAIL, "scanner_log table does not exist"
            
            # Check table has correct columns
            columns = await self.db_pool.fetch("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'scanner_log'
            """)
            
            found_columns = {row['column_name'] for row in columns}
            required_columns = {'time', 'ticker', 'horizon', 'action', 'reason_json'}
            missing_columns = required_columns - found_columns
            
            if missing_columns:
                return CheckResult.FAIL, f"scanner_log missing columns: {', '.join(missing_columns)}"
            
            # Verify scanner is NOT writing to opportunity_log (that's Level 3/Milestone 4)
            # opportunity_log requires ranking fields - scanner should not use it
            opp_log_count = await self.db_pool.fetchval("SELECT COUNT(*) FROM opportunity_log")
            if opp_log_count > 0:
                return CheckResult.WARN, f"opportunity_log has {opp_log_count} entries (scanner should use scanner_log only)"
            
            return CheckResult.PASS, f"scanner_log OK: {len(found_columns)} columns, using correct table"
        except Exception as e:
            return CheckResult.FAIL, f"Scanner DB logging check error: {str(e)[:100]}"
    
    async def connect_db(self):
        """Connect to TimescaleDB"""
        try:
            self.db_pool = await asyncpg.create_pool(
                host=DB_HOST,
                port=DB_PORT,
                database=DB_NAME,
                user=DB_USER,
                password=DB_PASSWORD,
                min_size=1,
                max_size=5
            )
        except Exception as e:
            self.db_pool = None
    
    async def connect_redis(self):
        """Connect to Redis"""
        try:
            self.redis_client = redis.Redis(
                host=REDIS_HOST,
                port=REDIS_PORT,
                decode_responses=False
            )
            await self.redis_client.ping()
        except Exception:
            self.redis_client = None
    
    async def run_all_checks(self):
        """Run all verification checks"""
        print("\n" + "="*70)
        print("ZERO SYSTEM STATE VERIFICATION - Milestones 0-3")
        print("="*70)
        print(f"Time: {datetime.now(timezone.utc).isoformat()}")
        print(f"Project: {project_root}")
        if not MARKET_CALENDAR_AVAILABLE:
            print("⚠️  Warning: pandas-market-calendars not available - using basic market hours")
        print("="*70)
        print()
        
        # Connect to services
        await self.connect_db()
        await self.connect_redis()
        
        # ========================================================================
        # MILESTONE 0: Infrastructure
        # ========================================================================
        print("="*70)
        print("MILESTONE 0: Infrastructure")
        print("="*70)
        print()
        
        # Check 1: Docker Services
        print("CHECK 1.1: Docker Services")
        print("-" * 70)
        result, msg = await self.check_docker_services()
        self.results['docker_services'] = (result, msg)
        status_icon = "✅" if result == CheckResult.PASS else ("⚠️ " if result == CheckResult.WARN else "❌")
        print(f"{status_icon} {result.value}: {msg}")
        print()
        
        # Check 2: Redis Connectivity
        print("CHECK 1.2: Redis Connectivity")
        print("-" * 70)
        result, msg = await self.check_redis_connectivity()
        self.results['redis_connectivity'] = (result, msg)
        status_icon = "✅" if result == CheckResult.PASS else ("⚠️ " if result == CheckResult.WARN else "❌")
        print(f"{status_icon} {result.value}: {msg}")
        print()
        
        # Check 3: Database Connectivity
        print("CHECK 1.3: TimescaleDB Connectivity")
        print("-" * 70)
        result, msg = await self.check_db_connectivity()
        self.results['db_connectivity'] = (result, msg)
        status_icon = "✅" if result == CheckResult.PASS else ("⚠️ " if result == CheckResult.WARN else "❌")
        print(f"{status_icon} {result.value}: {msg}")
        print()
        
        # Check 4: DB Schema Integrity
        print("CHECK 1.4: Database Schema Integrity")
        print("-" * 70)
        result, msg = await self.check_db_schema_integrity()
        self.results['db_schema'] = (result, msg)
        status_icon = "✅" if result == CheckResult.PASS else ("⚠️ " if result == CheckResult.WARN else "❌")
        print(f"{status_icon} {result.value}: {msg}")
        print()
        
        # ========================================================================
        # MILESTONE 1: Ingestion
        # ========================================================================
        print("="*70)
        print("MILESTONE 1: Ingestion Service")
        print("="*70)
        print()
        
        # Check 5: Ingestion Health
        print("CHECK 2.1: Ingestion Service Health")
        print("-" * 70)
        result, msg, data = await self.check_service_health("zero-ingest-price", INGEST_PORT)
        self.results['ingest_health'] = (result, msg)
        status_icon = "✅" if result == CheckResult.PASS else ("⚠️ " if result == CheckResult.WARN else "❌")
        print(f"{status_icon} {result.value}: {msg}")
        if data:
            print(f"   Status: {data.get('status')}")
            details = data.get('details', {})
            if 'provider_connected' in details:
                print(f"   Provider: {'✅' if details.get('provider_connected') else '❌'}")
            if 'database_connected' in details:
                print(f"   Database: {'✅' if details.get('database_connected') else '❌'}")
            if 'redis_connected' in details:
                print(f"   Redis: {'✅' if details.get('redis_connected') else '❌'}")
        print()
        
        # Check 6: Ingestion Freshness
        print("CHECK 2.2: Ingestion Freshness (Market Calendar Aware)")
        print("-" * 70)
        result, msg = await self.check_ingestion_freshness()
        self.results['ingest_freshness'] = (result, msg)
        status_icon = "✅" if result == CheckResult.PASS else ("⚠️ " if result == CheckResult.WARN else "❌")
        print(f"{status_icon} {result.value}: {msg}")
        print()
        
        # Check 7: Ingestion Gaps
        print("CHECK 2.3: Ingestion Gap Detection")
        print("-" * 70)
        result, msg = await self.check_ingestion_gaps()
        self.results['ingest_gaps'] = (result, msg)
        status_icon = "✅" if result == CheckResult.PASS else ("⚠️ " if result == CheckResult.WARN else "❌")
        print(f"{status_icon} {result.value}: {msg}")
        print()
        
        # ========================================================================
        # MILESTONE 2: Regime Engine
        # ========================================================================
        print("="*70)
        print("MILESTONE 2: Regime Engine")
        print("="*70)
        print()
        
        # Check 8: Regime Health
        print("CHECK 3.1: Regime Service Health")
        print("-" * 70)
        result, msg, data = await self.check_service_health("zero-regime", REGIME_PORT)
        self.results['regime_health'] = (result, msg)
        status_icon = "✅" if result == CheckResult.PASS else ("⚠️ " if result == CheckResult.WARN else "❌")
        print(f"{status_icon} {result.value}: {msg}")
        if data and 'market_state' in data:
            state = data['market_state']
            print(f"   Market State: {state.get('state')} ({state.get('reason', 'N/A')})")
        print()
        
        # Check 9: Redis Contracts
        print("CHECK 3.2: Redis Contracts (Keys + Channels)")
        print("-" * 70)
        result, msg = await self.check_redis_contracts()
        self.results['redis_contracts'] = (result, msg)
        status_icon = "✅" if result == CheckResult.PASS else ("⚠️ " if result == CheckResult.WARN else "❌")
        print(f"{status_icon} {result.value}: {msg}")
        print()
        
        # Check 10: Regime Redis State
        print("CHECK 3.3: Regime Redis State (key:market_state)")
        print("-" * 70)
        result, msg = await self.check_regime_redis_state()
        self.results['regime_redis_state'] = (result, msg)
        status_icon = "✅" if result == CheckResult.PASS else ("⚠️ " if result == CheckResult.WARN else "❌")
        print(f"{status_icon} {result.value}: {msg}")
        print()
        
        # Check 11: Regime DB Logs
        print("CHECK 3.4: Regime Database Logging")
        print("-" * 70)
        result, msg = await self.check_regime_db_logs()
        self.results['regime_db_logs'] = (result, msg)
        status_icon = "✅" if result == CheckResult.PASS else ("⚠️ " if result == CheckResult.WARN else "❌")
        print(f"{status_icon} {result.value}: {msg}")
        print()
        
        # ========================================================================
        # MILESTONE 3: Scanner Engine
        # ========================================================================
        print("="*70)
        print("MILESTONE 3: Scanner Engine")
        print("="*70)
        print()
        
        # Check 12: Scanner Health
        print("CHECK 4.1: Scanner Service Health")
        print("-" * 70)
        result, msg, data = await self.check_scanner_health()
        self.results['scanner_health'] = (result, msg)
        status_icon = "✅" if result == CheckResult.PASS else ("⚠️ " if result == CheckResult.WARN else "❌")
        print(f"{status_icon} {result.value}: {msg}")
        if data:
            print(f"   Status: {data.get('status')}")
            details = data.get('details', {})
            if 'market_state_seen' in details:
                print(f"   Market State Seen: {details.get('market_state_seen')}")
            if 'last_scan_time' in details:
                print(f"   Last Scan: {details.get('last_scan_time')}")
        print()
        
        # Check 13: Veto-Aware Behavior
        print("CHECK 4.2: Veto-Aware Behavior (MarketState RED)")
        print("-" * 70)
        result, msg = await self.check_scanner_veto_aware()
        self.results['scanner_veto_aware'] = (result, msg)
        status_icon = "✅" if result == CheckResult.PASS else ("⚠️ " if result == CheckResult.WARN else "❌")
        print(f"{status_icon} {result.value}: {msg}")
        print()
        
        # Check 14: Scanner Redis Outputs
        print("CHECK 4.3: Scanner Redis Outputs (key:active_candidates)")
        print("-" * 70)
        result, msg = await self.check_scanner_redis_outputs()
        self.results['scanner_redis_outputs'] = (result, msg)
        status_icon = "✅" if result == CheckResult.PASS else ("⚠️ " if result == CheckResult.WARN else "❌")
        print(f"{status_icon} {result.value}: {msg}")
        print()
        
        # Check 15: Scanner DB Logging
        print("CHECK 4.4: Scanner Database Logging")
        print("-" * 70)
        result, msg = await self.check_scanner_db_logging()
        self.results['scanner_db_logging'] = (result, msg)
        status_icon = "✅" if result == CheckResult.PASS else ("⚠️ " if result == CheckResult.WARN else "❌")
        print(f"{status_icon} {result.value}: {msg}")
        print()
        
        # ========================================================================
        # SUMMARY
        # ========================================================================
        print("="*70)
        print("VERIFICATION SUMMARY")
        print("="*70)
        print()
        
        fails = []
        warns = []
        passes = []
        
        for check_name, (result, msg) in self.results.items():
            if result == CheckResult.FAIL:
                fails.append(check_name)
            elif result == CheckResult.WARN:
                warns.append(check_name)
            else:
                passes.append(check_name)
        
        print(f"✅ PASS: {len(passes)}")
        print(f"⚠️  WARN: {len(warns)}")
        print(f"❌ FAIL: {len(fails)}")
        print()
        
        if warns:
            print("Warnings:")
            for check in warns:
                result, msg = self.results[check]
                print(f"  ⚠️  {check}: {msg}")
            print()
        
        if fails:
            print("Failures:")
            for check in fails:
                result, msg = self.results[check]
                print(f"  ❌ {check}: {msg}")
            print()
        
        # Final result
        if fails:
            print("❌ SYSTEM NOT READY - Fix failures before proceeding to Milestone 4")
            return False
        elif warns:
            print("⚠️  SYSTEM READY WITH WARNINGS - Review warnings before proceeding")
            print("✅ SYSTEM READY FOR MILESTONE 4")
            return True
        else:
            print("✅ ALL CHECKS PASSED")
            print("✅ SYSTEM READY FOR MILESTONE 4")
            return True
    
    async def cleanup(self):
        """Cleanup connections"""
        if self.db_pool:
            await self.db_pool.close()
        if self.redis_client:
            await self.redis_client.close()


async def main():
    """Main entry point"""
    verifier = StateVerifier()
    try:
        success = await verifier.run_all_checks()
        await verifier.cleanup()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n🛑 Verification interrupted")
        await verifier.cleanup()
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Verification error: {e}")
        import traceback
        traceback.print_exc()
        await verifier.cleanup()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
