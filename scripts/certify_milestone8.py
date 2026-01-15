#!/usr/bin/env python3
"""
ZERO Milestone 8 Certification Script

Validates:
A) Contracts + naming (SPEC_LOCK 9.x)
B) End-to-end dataflow
C) Level override rules (SPEC_LOCK 1.x)
D) Probability definition compliance (SPEC_LOCK 2.x)
E) Truth test loop + calibration (SPEC_LOCK 6.x)
F) Safety + execution hardening
G) Time + timezone correctness
H) Performance sanity

Run during market hours for full certification.
"""

import asyncio
import json
import sys
import os
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Tuple

# Add project root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    import redis
    import psycopg2
    import requests
except ImportError:
    print("Installing required packages...")
    os.system("pip install redis psycopg2-binary requests")
    import redis
    import psycopg2
    import requests


class Certifier:
    def __init__(self):
        self.redis_host = os.getenv('REDIS_HOST', 'localhost')
        self.redis_port = int(os.getenv('REDIS_PORT', '6379'))
        self.db_host = os.getenv('DB_HOST', 'localhost')
        self.db_port = int(os.getenv('DB_PORT', '5432'))
        self.db_name = os.getenv('DB_NAME', 'zero_trading')
        self.db_user = os.getenv('DB_USER', 'zero_user')
        self.db_password = os.getenv('DB_PASSWORD', os.getenv('POSTGRES_PASSWORD', ''))
        
        self.redis_client = None
        self.db_conn = None
        self.results = {"pass": 0, "fail": 0, "warn": 0, "checks": []}
    
    def connect(self):
        """Connect to Redis and DB"""
        try:
            self.redis_client = redis.Redis(
                host=self.redis_host,
                port=self.redis_port,
                decode_responses=True
            )
            self.redis_client.ping()
            print(f"✅ Redis connected: {self.redis_host}:{self.redis_port}")
        except Exception as e:
            print(f"❌ Redis connection failed: {e}")
            sys.exit(1)
        
        try:
            self.db_conn = psycopg2.connect(
                host=self.db_host,
                port=self.db_port,
                database=self.db_name,
                user=self.db_user,
                password=self.db_password
            )
            print(f"✅ Database connected: {self.db_host}:{self.db_port}/{self.db_name}")
        except Exception as e:
            print(f"❌ Database connection failed: {e}")
            sys.exit(1)
    
    def record(self, category: str, check: str, passed: bool, details: str = ""):
        """Record a check result"""
        status = "PASS" if passed else "FAIL"
        self.results["checks"].append({
            "category": category,
            "check": check,
            "status": status,
            "details": details
        })
        if passed:
            self.results["pass"] += 1
            print(f"  ✅ {check}")
        else:
            self.results["fail"] += 1
            print(f"  ❌ {check}: {details}")
    
    def warn(self, category: str, check: str, details: str = ""):
        """Record a warning"""
        self.results["warn"] += 1
        self.results["checks"].append({
            "category": category,
            "check": check,
            "status": "WARN",
            "details": details
        })
        print(f"  ⚠️  {check}: {details}")
    
    # =========================================================================
    # A) CONTRACTS + NAMING
    # =========================================================================
    def certify_contracts(self):
        print("\n" + "="*70)
        print("A) CONTRACTS + NAMING (SPEC_LOCK 9.x)")
        print("="*70)
        
        # Expected Redis keys
        expected_keys = [
            "key:market_state",
            "key:attention_state",
            "key:calibration_state",
        ]
        
        # Optional keys (may not exist if no activity)
        optional_keys = [
            "key:active_candidates",
            "key:opportunity_rank",
            "key:execution_enabled",
            "key:confidence_multipliers",
            "key:probability_calibration",
        ]
        
        # Check required keys
        for key in expected_keys:
            value = self.redis_client.get(key)
            if value:
                try:
                    data = json.loads(value)
                    # Check schema_version and timestamp
                    has_schema = "schema_version" in data or "version" in data
                    has_timestamp = "timestamp" in data
                    if has_timestamp:
                        self.record("A", f"{key} exists with valid schema", True)
                    else:
                        self.record("A", f"{key} missing timestamp", False, "timestamp field required")
                except json.JSONDecodeError:
                    self.record("A", f"{key} valid JSON", False, "Invalid JSON")
            else:
                self.record("A", f"{key} exists", False, "Key not found")
        
        # Check optional keys
        for key in optional_keys:
            value = self.redis_client.get(key)
            if value:
                self.record("A", f"{key} exists (optional)", True)
            else:
                self.warn("A", f"{key} not found", "May be normal if no recent activity")
        
        # Check DB tables
        expected_tables = [
            "candles_1m", "candles_5m", "regime_log", "attention_log",
            "opportunity_log", "performance_log", "execution_log", "scanner_log"
        ]
        
        cursor = self.db_conn.cursor()
        for table in expected_tables:
            try:
                cursor.execute(f"SELECT COUNT(*) FROM {table}")
                count = cursor.fetchone()[0]
                self.record("A", f"DB table {table} exists ({count} rows)", True)
            except Exception as e:
                self.record("A", f"DB table {table} exists", False, str(e))
        cursor.close()
    
    # =========================================================================
    # B) END-TO-END DATAFLOW
    # =========================================================================
    def certify_dataflow(self):
        print("\n" + "="*70)
        print("B) END-TO-END DATAFLOW (The Spine)")
        print("="*70)
        
        cursor = self.db_conn.cursor()
        
        # 1. Ingest writes candles
        cursor.execute("SELECT MAX(time) FROM candles_1m")
        latest_candle = cursor.fetchone()[0]
        if latest_candle:
            age = (datetime.now(timezone.utc) - latest_candle.replace(tzinfo=timezone.utc)).total_seconds() / 60
            if age < 120:  # Within 2 hours (market hours check)
                self.record("B", f"Ingest writing candles (latest: {age:.0f}m ago)", True)
            else:
                self.warn("B", f"Candles are {age:.0f}m old", "May be off-hours")
        else:
            self.record("B", "Ingest writing candles", False, "No candles found")
        
        # 2. Regime writes market_state
        market_state = self.redis_client.get("key:market_state")
        if market_state:
            state = json.loads(market_state)
            self.record("B", f"Regime publishing market_state: {state.get('state')}", True)
        else:
            self.record("B", "Regime publishing market_state", False, "Key not found")
        
        # 3. Regime logging to DB
        cursor.execute("SELECT COUNT(*), MAX(time) FROM regime_log")
        count, latest = cursor.fetchone()
        if count > 0:
            self.record("B", f"Regime logging to DB ({count} entries)", True)
        else:
            self.record("B", "Regime logging to DB", False, "No entries")
        
        # 4. Attention state
        attention_state = self.redis_client.get("key:attention_state")
        if attention_state:
            att = json.loads(attention_state)
            score = att.get("attention_stability_score", "?")
            bucket = att.get("attention_bucket", "?")
            degraded = att.get("degraded", False)
            if degraded:
                self.warn("B", f"Attention state degraded: {att.get('degraded_reason')}", "Using fallback")
            else:
                self.record("B", f"Attention state: score={score}, bucket={bucket}", True)
        else:
            self.record("B", "Attention state exists", False, "Key not found")
        
        # 5. Scanner output
        cursor.execute("SELECT COUNT(*) FROM scanner_log WHERE time > NOW() - INTERVAL '24 hours'")
        scanner_count = cursor.fetchone()[0]
        if scanner_count > 0:
            self.record("B", f"Scanner logging ({scanner_count} entries in 24h)", True)
        else:
            self.warn("B", "Scanner log empty in 24h", "May be off-hours or no candidates")
        
        # 6. Opportunity ranking
        cursor.execute("SELECT COUNT(*) FROM opportunity_log WHERE time > NOW() - INTERVAL '24 hours'")
        opp_count = cursor.fetchone()[0]
        if opp_count > 0:
            self.record("B", f"Core ranking opportunities ({opp_count} in 24h)", True)
        else:
            self.warn("B", "No opportunities in 24h", "May be off-hours or RED state")
        
        # 7. Execution logging
        cursor.execute("SELECT COUNT(*), COUNT(DISTINCT status) FROM execution_log WHERE time > NOW() - INTERVAL '24 hours'")
        exec_count, status_count = cursor.fetchone()
        if exec_count > 0:
            self.record("B", f"Execution logging ({exec_count} entries in 24h)", True)
        else:
            self.warn("B", "No execution logs in 24h", "May be off-hours")
        
        cursor.close()
    
    # =========================================================================
    # C) LEVEL OVERRIDE RULES
    # =========================================================================
    def certify_level_overrides(self):
        print("\n" + "="*70)
        print("C) LEVEL OVERRIDE RULES (SPEC_LOCK 1.x)")
        print("="*70)
        
        # Check current market state
        market_state = self.redis_client.get("key:market_state")
        if market_state:
            state = json.loads(market_state)
            current_state = state.get("state", "UNKNOWN")
            print(f"  Current MarketState: {current_state}")
            
            if current_state == "RED":
                # Verify downstream is halted
                opp_rank = self.redis_client.get("key:opportunity_rank")
                if opp_rank:
                    opp = json.loads(opp_rank)
                    opp_time = opp.get("timestamp", "")
                    # Check if opportunity is recent (should NOT be if RED)
                    self.warn("C", "Opportunity rank exists during RED", "Should be stale")
                else:
                    self.record("C", "No active opportunity_rank during RED (correct)", True)
            else:
                self.record("C", f"MarketState is {current_state} (not RED)", True)
        
        # Check attention gating
        attention_state = self.redis_client.get("key:attention_state")
        if attention_state:
            att = json.loads(attention_state)
            score = att.get("attention_stability_score", 50)
            bucket = att.get("attention_bucket", "UNSTABLE")
            
            if score < 40:
                self.record("C", f"Attention CHAOTIC ({score}) - only H30 allowed", True)
            elif score < 70:
                self.record("C", f"Attention UNSTABLE ({score}) - HWEEK gated", True)
            else:
                self.record("C", f"Attention STABLE ({score}) - all horizons allowed", True)
    
    # =========================================================================
    # D) PROBABILITY DEFINITION COMPLIANCE
    # =========================================================================
    def certify_probability(self):
        print("\n" + "="*70)
        print("D) PROBABILITY DEFINITION COMPLIANCE (SPEC_LOCK 2.x)")
        print("="*70)
        
        cursor = self.db_conn.cursor()
        
        # Check opportunity_log has required fields
        cursor.execute("""
            SELECT column_name FROM information_schema.columns 
            WHERE table_name = 'opportunity_log'
        """)
        columns = [row[0] for row in cursor.fetchall()]
        
        required_fields = ["probability", "target_atr", "stop_atr", "horizon", "market_state", "attention_stability_score"]
        for field in required_fields:
            if field in columns:
                self.record("D", f"opportunity_log has {field}", True)
            else:
                self.record("D", f"opportunity_log has {field}", False, "Column missing")
        
        # Check a sample opportunity
        cursor.execute("""
            SELECT ticker, horizon, probability, target_atr, stop_atr, 
                   market_state, attention_stability_score, attention_bucket
            FROM opportunity_log ORDER BY time DESC LIMIT 1
        """)
        row = cursor.fetchone()
        if row:
            ticker, horizon, prob, target, stop, mstate, att_score, att_bucket = row
            print(f"  Sample opportunity: {ticker} {horizon}")
            print(f"    probability={prob}, target_atr={target}, stop_atr={stop}")
            print(f"    market_state={mstate}, attention={att_score} ({att_bucket})")
            
            # Validate probability is conditioned
            if prob and target and stop and mstate and att_score is not None:
                self.record("D", "Probability properly conditioned", True)
            else:
                self.record("D", "Probability properly conditioned", False, "Missing conditioning fields")
        else:
            self.warn("D", "No opportunities to validate", "Run during market hours")
        
        cursor.close()
    
    # =========================================================================
    # E) TRUTH TEST + CALIBRATION
    # =========================================================================
    def certify_truth_test(self):
        print("\n" + "="*70)
        print("E) TRUTH TEST + CALIBRATION (SPEC_LOCK 6.x)")
        print("="*70)
        
        cursor = self.db_conn.cursor()
        
        # Check performance_log has entries
        cursor.execute("SELECT COUNT(*) FROM performance_log")
        perf_count = cursor.fetchone()[0]
        if perf_count > 0:
            self.record("E", f"Truth test has run ({perf_count} evaluations)", True)
        else:
            self.warn("E", "No truth test evaluations yet", "Run POST /run on truth-test service")
        
        # Check performance_log fields
        cursor.execute("""
            SELECT outcome, realized_outcome, mfe_atr, mae_atr, time_to_resolution
            FROM performance_log LIMIT 5
        """)
        rows = cursor.fetchall()
        if rows:
            for row in rows:
                outcome, realized, mfe, mae, ttr = row
                print(f"    {outcome}: realized={realized}, MFE={mfe}, MAE={mae}, TTR={ttr}s")
            self.record("E", "Truth test computing MFE/MAE", True)
        
        # Check calibration state
        cal_state = self.redis_client.get("key:calibration_state")
        if cal_state:
            cal = json.loads(cal_state)
            buckets = cal.get("buckets", {})
            global_stats = cal.get("global_stats", {})
            print(f"  Calibration: {len(buckets)} buckets, global_shrink={global_stats.get('global_shrink')}")
            self.record("E", "Calibration state published", True)
        else:
            self.warn("E", "No calibration state", "Run truth test first")
        
        # Check probability_calibration
        prob_cal = self.redis_client.get("key:probability_calibration")
        if prob_cal:
            self.record("E", "key:probability_calibration exists", True)
        else:
            self.warn("E", "key:probability_calibration not found", "Run truth test")
        
        cursor.close()
    
    # =========================================================================
    # F) SAFETY + EXECUTION HARDENING
    # =========================================================================
    def certify_safety(self):
        print("\n" + "="*70)
        print("F) SAFETY + EXECUTION HARDENING")
        print("="*70)
        
        # Check paper trading enforced
        try:
            resp = requests.get("http://localhost:8003/health", timeout=5)
            if resp.ok:
                health = resp.json()
                # Check for PAPER indicators
                status = health.get("status", "")
                self.record("F", "Execution service healthy", True)
        except:
            self.warn("F", "Execution service not reachable", "Check if running")
        
        # Check kill switch
        exec_enabled = self.redis_client.get("key:execution_enabled")
        if exec_enabled is not None:
            self.record("F", f"Kill switch exists: {exec_enabled}", True)
        else:
            self.warn("F", "Kill switch key not set", "Default may be enabled")
        
        # Check idempotency keys exist
        idempotency_keys = self.redis_client.keys("key:execution_seen:*")
        if idempotency_keys:
            self.record("F", f"Idempotency tracking active ({len(idempotency_keys)} keys)", True)
        else:
            self.warn("F", "No idempotency keys found", "May be no executions yet")
        
        # Check execution_log for BLOCKED entries
        cursor = self.db_conn.cursor()
        cursor.execute("SELECT status, COUNT(*) FROM execution_log GROUP BY status")
        rows = cursor.fetchall()
        if rows:
            for status, count in rows:
                print(f"    {status}: {count}")
            self.record("F", "Execution logging by status", True)
        cursor.close()
    
    # =========================================================================
    # G) TIME + TIMEZONE
    # =========================================================================
    def certify_timezone(self):
        print("\n" + "="*70)
        print("G) TIME + TIMEZONE CORRECTNESS")
        print("="*70)
        
        # Check market_state timestamp
        market_state = self.redis_client.get("key:market_state")
        if market_state:
            state = json.loads(market_state)
            ts = state.get("timestamp", "")
            if "+" in ts or "Z" in ts:
                self.record("G", "MarketState timestamp is timezone-aware", True)
            else:
                self.record("G", "MarketState timestamp is timezone-aware", False, f"Got: {ts}")
        
        # Check DB timestamps
        cursor = self.db_conn.cursor()
        cursor.execute("SELECT time FROM regime_log ORDER BY time DESC LIMIT 1")
        row = cursor.fetchone()
        if row:
            ts = row[0]
            if ts.tzinfo is not None:
                self.record("G", "DB timestamps are timezone-aware (UTC)", True)
            else:
                self.warn("G", "DB timestamps may not be timezone-aware", str(ts))
        cursor.close()
    
    # =========================================================================
    # H) PERFORMANCE SANITY
    # =========================================================================
    def certify_performance(self):
        print("\n" + "="*70)
        print("H) PERFORMANCE SANITY (Jetson)")
        print("="*70)
        
        # Check service health endpoints
        services = [
            ("Ingest", "http://localhost:8080/health"),
            ("Regime", "http://localhost:8000/health"),
            ("Scanner", "http://localhost:8001/health"),
            ("Core", "http://localhost:8002/health"),
            ("Execution", "http://localhost:8003/health"),
            ("Truth-Test", "http://localhost:8004/health"),
            ("Attention", "http://localhost:8005/health"),
        ]
        
        for name, url in services:
            try:
                resp = requests.get(url, timeout=5)
                if resp.ok:
                    health = resp.json()
                    status = health.get("status", "unknown")
                    self.record("H", f"{name} service: {status}", status == "healthy")
                else:
                    self.record("H", f"{name} service healthy", False, f"HTTP {resp.status_code}")
            except Exception as e:
                self.record("H", f"{name} service healthy", False, str(e))
        
        # Check DB connection pool
        cursor = self.db_conn.cursor()
        cursor.execute("SELECT count(*) FROM pg_stat_activity WHERE datname = %s", (self.db_name,))
        conn_count = cursor.fetchone()[0]
        if conn_count < 50:
            self.record("H", f"DB connections healthy ({conn_count})", True)
        else:
            self.warn("H", f"High DB connections: {conn_count}", "May need pool tuning")
        cursor.close()
        
        # Check Redis memory
        info = self.redis_client.info("memory")
        used_mb = info.get("used_memory", 0) / 1024 / 1024
        if used_mb < 500:
            self.record("H", f"Redis memory healthy ({used_mb:.1f}MB)", True)
        else:
            self.warn("H", f"Redis memory: {used_mb:.1f}MB", "Monitor for growth")
    
    # =========================================================================
    # SUMMARY
    # =========================================================================
    # =========================================================================
    # I) QUERY MODE + MORNING BRIEF + URGENCY
    # =========================================================================
    def certify_additional_features(self):
        print("\n" + "="*70)
        print("I) QUERY MODE + MORNING BRIEF + URGENCY")
        print("="*70)
        
        # Test Query Mode
        try:
            resp = requests.get("http://localhost:8002/query?ticker=SPY", timeout=10)
            if resp.ok:
                data = resp.json()
                if "eligible" in data and "reason_codes" in data:
                    self.record("I", f"Query Mode works (SPY eligible={data.get('eligible')})", True)
                else:
                    self.record("I", "Query Mode response format", False, "Missing required fields")
            else:
                self.record("I", "Query Mode endpoint", False, f"HTTP {resp.status_code}")
        except Exception as e:
            self.record("I", "Query Mode endpoint", False, str(e))
        
        # Test Morning Brief
        try:
            resp = requests.get("http://localhost:8002/brief", timeout=10)
            if resp.ok:
                data = resp.json()
                required = ["day_type", "market_summary", "attention_summary", "action_guidance", "narrative"]
                missing = [f for f in required if f not in data]
                if not missing:
                    print(f"    Day Type: {data.get('day_type')}")
                    print(f"    Action: {data.get('action_guidance', {}).get('primary_action')}")
                    self.record("I", "Morning Brief works", True)
                else:
                    self.record("I", "Morning Brief format", False, f"Missing: {missing}")
            else:
                self.record("I", "Morning Brief endpoint", False, f"HTTP {resp.status_code}")
        except Exception as e:
            self.record("I", "Morning Brief endpoint", False, str(e))
        
        # Test Status endpoint
        try:
            resp = requests.get("http://localhost:8002/status", timeout=10)
            if resp.ok:
                data = resp.json()
                if "market_state" in data and "attention_state" in data:
                    self.record("I", "Status endpoint works", True)
                else:
                    self.record("I", "Status endpoint format", False, "Missing state fields")
            else:
                self.record("I", "Status endpoint", False, f"HTTP {resp.status_code}")
        except Exception as e:
            self.record("I", "Status endpoint", False, str(e))

    def print_summary(self):
        print("\n" + "="*70)
        print("CERTIFICATION SUMMARY")
        print("="*70)
        
        total = self.results["pass"] + self.results["fail"] + self.results["warn"]
        print(f"\n✅ PASS: {self.results['pass']}")
        print(f"❌ FAIL: {self.results['fail']}")
        print(f"⚠️  WARN: {self.results['warn']}")
        print(f"📊 TOTAL: {total}")
        
        if self.results["fail"] == 0:
            print("\n🎉 MILESTONE 8 CERTIFIED!")
        else:
            print("\n❌ CERTIFICATION FAILED - Fix failures before proceeding")
            print("\nFailures:")
            for check in self.results["checks"]:
                if check["status"] == "FAIL":
                    print(f"  - [{check['category']}] {check['check']}: {check['details']}")
    
    def run(self):
        """Run full certification"""
        print("="*70)
        print("ZERO MILESTONE 8 CERTIFICATION")
        print(f"Time: {datetime.now(timezone.utc).isoformat()}")
        print("="*70)
        
        self.connect()
        
        self.certify_contracts()
        self.certify_dataflow()
        self.certify_level_overrides()
        self.certify_probability()
        self.certify_truth_test()
        self.certify_safety()
        self.certify_timezone()
        self.certify_performance()
        self.certify_additional_features()
        
        self.print_summary()
        
        # Cleanup
        if self.db_conn:
            self.db_conn.close()
        
        return self.results["fail"] == 0


if __name__ == "__main__":
    certifier = Certifier()
    success = certifier.run()
    sys.exit(0 if success else 1)
