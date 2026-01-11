#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ZERO Gatekeeper Script - Milestone 0 & 1 Verification
Standalone script to verify infrastructure before Milestone 2
"""

import asyncio
import os
import sys
import subprocess
from datetime import datetime, timedelta
from typing import Optional, Tuple

# Fix Windows console encoding
if sys.platform == 'win32':
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

# Add project root to path
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(script_dir, '..'))
sys.path.insert(0, project_root)

# Load environment variables
try:
    from dotenv import load_dotenv
    env_path = os.path.join(project_root, '.env')
    if os.path.exists(env_path):
        load_dotenv(env_path)
except ImportError:
    pass


class GateKeeper:
    """Gatekeeper for Milestone 0 & 1 verification"""
    
    def __init__(self):
        self.db_host = os.getenv('DB_HOST', 'localhost')
        self.db_port = int(os.getenv('DB_PORT', '5432'))
        self.db_name = os.getenv('DB_NAME', 'zero_trading')
        self.db_user = os.getenv('DB_USER', 'zero_user')
        self.db_password = os.getenv('DB_PASSWORD', '')
        
        self.redis_host = os.getenv('REDIS_HOST', 'localhost')
        self.redis_port = int(os.getenv('REDIS_PORT', '6379'))
        
        self.results = {}
    
    def check_docker_services(self) -> Tuple[bool, str]:
        """Check if Docker services are running"""
        try:
            # Try docker compose ps
            result = subprocess.run(
                ['docker', 'compose', '-f', os.path.join(project_root, 'infra', 'docker-compose.yml'), 'ps'],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode != 0:
                return False, f"Docker compose failed: {result.stderr[:100]}"
            
            output = result.stdout
            lines = [line for line in output.split('\n') if line.strip() and 'NAME' not in line]
            
            if not lines:
                return False, "No services found"
            
            # Check each service is "Up"
            services_up = []
            services_down = []
            
            for line in lines:
                if 'zero-' in line or 'timescaledb' in line or 'redis' in line or 'grafana' in line:
                    if 'Up' in line or 'running' in line.lower():
                        service_name = line.split()[0] if line.split() else "unknown"
                        services_up.append(service_name)
                    else:
                        service_name = line.split()[0] if line.split() else "unknown"
                        services_down.append(service_name)
            
            if services_down:
                return False, f"Services down: {', '.join(services_down)}"
            
            if services_up:
                return True, f"All services up: {', '.join(services_up)}"
            else:
                return False, "No services detected"
                
        except FileNotFoundError:
            return False, "Docker not found (install Docker Desktop)"
        except subprocess.TimeoutExpired:
            return False, "Docker command timed out"
        except Exception as e:
            return False, f"Docker check error: {str(e)[:100]}"
    
    async def check_db_schema(self) -> Tuple[bool, str]:
        """Check that required tables exist in TimescaleDB"""
        try:
            import asyncpg
            
            conn = await asyncpg.connect(
                host=self.db_host,
                port=self.db_port,
                database=self.db_name,
                user=self.db_user,
                password=self.db_password,
                timeout=5
            )
            
            # Check for required tables
            required_tables = ['ticks', 'candles_1m', 'regime_log']
            existing_tables = []
            missing_tables = []
            
            for table in required_tables:
                result = await conn.fetchval(
                    """
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables 
                        WHERE table_schema = 'public' 
                        AND table_name = $1
                    )
                    """,
                    table
                )
                
                if result:
                    existing_tables.append(table)
                else:
                    missing_tables.append(table)
            
            await conn.close()
            
            if missing_tables:
                return False, f"Missing tables: {', '.join(missing_tables)}"
            
            return True, f"All tables exist: {', '.join(existing_tables)}"
            
        except ImportError:
            return False, "asyncpg not installed"
        except Exception as e:
            error_msg = str(e)
            if "password" in error_msg.lower() or "authentication" in error_msg.lower():
                return False, "DB authentication failed (check DB_PASSWORD)"
            elif "connection" in error_msg.lower() or "refused" in error_msg.lower():
                return False, f"DB connection refused (check DB_HOST={self.db_host}:{self.db_port})"
            else:
                return False, f"DB error: {error_msg[:100]}"
    
    async def check_data_flow(self) -> Tuple[bool, str, int]:
        """Check if data is flowing (recent ticks in last hour)"""
        try:
            import asyncpg
            
            conn = await asyncpg.connect(
                host=self.db_host,
                port=self.db_port,
                database=self.db_name,
                user=self.db_user,
                password=self.db_password,
                timeout=5
            )
            
            # Count ticks in last hour
            count = await conn.fetchval(
                """
                SELECT count(*) 
                FROM ticks 
                WHERE created_at > NOW() - INTERVAL '1 hour'
                """
            )
            
            await conn.close()
            
            if count > 0:
                return True, f"Data flowing: {count} ticks in last hour", count
            else:
                # This is a WARN, not a FAIL (market might be closed)
                return False, "No recent data (0 ticks in last hour - verify market hours)", 0
                
        except ImportError:
            return False, "asyncpg not installed", 0
        except Exception as e:
            error_msg = str(e)
            if "does not exist" in error_msg.lower():
                return False, "ticks table does not exist", 0
            else:
                return False, f"Data flow check error: {error_msg[:100]}", 0
    
    async def check_redis(self) -> Tuple[bool, str]:
        """Check Redis connectivity"""
        try:
            import redis.asyncio as aioredis
            
            redis_client = aioredis.Redis(
                host=self.redis_host,
                port=self.redis_port,
                decode_responses=False,
                socket_connect_timeout=5
            )
            
            result = await redis_client.ping()
            await redis_client.close()
            
            if result:
                return True, f"Redis connected: {self.redis_host}:{self.redis_port}"
            else:
                return False, "Redis ping failed"
                
        except ImportError:
            return False, "redis not installed"
        except Exception as e:
            error_msg = str(e)
            if "connection" in error_msg.lower() or "refused" in error_msg.lower():
                return False, f"Redis connection refused (check REDIS_HOST={self.redis_host}:{self.redis_port})"
            else:
                return False, f"Redis error: {error_msg[:100]}"
    
    def print_report(self):
        """Print beautiful ASCII report"""
        print("\n" + "="*70)
        print(" " * 20 + "ZERO GATEKEEPER REPORT")
        print(" " * 15 + "Milestone 0 & 1 Verification")
        print("="*70)
        print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"Project: {project_root}")
        print("="*70)
        print()
        
        # Docker Check
        docker_ok, docker_msg = self.results.get('docker', (False, "Not checked"))
        status = "[PASS]" if docker_ok else "[FAIL]"
        print(f"{status} Infrastructure (Docker Services)")
        print(f"      {docker_msg}")
        print()
        
        # DB Schema Check
        schema_ok, schema_msg = self.results.get('schema', (False, "Not checked"))
        status = "[PASS]" if schema_ok else "[FAIL]"
        print(f"{status} Database Schema")
        print(f"      {schema_msg}")
        print()
        
        # Redis Check
        redis_ok, redis_msg = self.results.get('redis', (False, "Not checked"))
        status = "[PASS]" if redis_ok else "[FAIL]"
        print(f"{status} Redis Connectivity")
        print(f"      {redis_msg}")
        print()
        
        # Data Flow Check
        data_ok, data_msg, data_count = self.results.get('data_flow', (False, "Not checked", 0))
        if data_ok:
            status = "[PASS]"
        elif data_count == 0:
            status = "[WARN]"
        else:
            status = "[FAIL]"
        
        print(f"{status} Recent Data Flow")
        print(f"      {data_msg}")
        print()
        
        print("="*70)
        
        # Summary
        critical_checks = ['docker', 'schema', 'redis']
        critical_passed = all(self.results.get(k, (False, ""))[0] for k in critical_checks)
        data_warn = not data_ok and data_count == 0  # WARN if no data but not critical
        
        if critical_passed and (data_ok or data_warn):
            print("\n✅ GATE PASSED: Ready for Milestone 2")
            if data_warn:
                print("   ⚠️  Note: No recent data (market may be closed)")
            return True
        else:
            print("\n❌ GATE FAILED: Fix issues before Milestone 2")
            failed = [k for k in critical_checks if not self.results.get(k, (False, ""))[0]]
            if failed:
                print(f"   Critical failures: {', '.join(failed)}")
            return False
    
    async def run_all_checks(self) -> bool:
        """Run all gatekeeper checks"""
        print("\n🔍 Running Gatekeeper Checks...\n")
        
        # Check 1: Docker Services
        print("Checking Docker services...")
        self.results['docker'] = self.check_docker_services()
        
        # Check 2: DB Schema
        print("Checking database schema...")
        self.results['schema'] = await self.check_db_schema()
        
        # Check 3: Redis
        print("Checking Redis...")
        self.results['redis'] = await self.check_redis()
        
        # Check 4: Data Flow
        print("Checking data flow...")
        self.results['data_flow'] = await self.check_data_flow()
        
        # Print report
        return self.print_report()


async def main():
    """Main entry point"""
    gatekeeper = GateKeeper()
    success = await gatekeeper.run_all_checks()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    asyncio.run(main())

