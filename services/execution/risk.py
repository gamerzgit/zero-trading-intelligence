"""
ZERO Execution Gateway - Risk Management & Safety Checks
Implements kill switch, veto, cooldown, and idempotency
"""

import os
import json
import redis.asyncio as redis
from typing import Optional, Dict, Any, Tuple
from datetime import datetime, timezone, timedelta
import logging

logger = logging.getLogger(__name__)


class RiskManager:
    """Risk management and safety checks for execution"""
    
    def __init__(self, redis_client: redis.Redis):
        self.redis_client = redis_client
        self.cooldown_minutes = 60  # Don't trade same ticker within 60 minutes
        self.idempotency_ttl_hours = 24  # Remember executions for 24 hours
    
    async def is_execution_enabled(self) -> bool:
        """Check if execution is enabled via kill switch"""
        if not self.redis_client:
            return False
        
        try:
            enabled = await self.redis_client.get("key:execution_enabled")
            if enabled:
                if isinstance(enabled, bytes):
                    enabled = enabled.decode('utf-8')
                return enabled.lower() == "true"
        except Exception as e:
            logger.warning(f"⚠️  Failed to check execution_enabled: {e}")
        
        return False
    
    async def get_market_state(self) -> Optional[Dict[str, Any]]:
        """Get current market state"""
        if not self.redis_client:
            return None
        
        try:
            state_json = await self.redis_client.get("key:market_state")
            if state_json:
                if isinstance(state_json, bytes):
                    state_json = state_json.decode('utf-8')
                return json.loads(state_json)
        except Exception as e:
            logger.warning(f"⚠️  Failed to get market state: {e}")
        
        return None
    
    async def is_market_green(self) -> Tuple[bool, Optional[str]]:
        """Check if market state is GREEN"""
        market_state = await self.get_market_state()
        if not market_state:
            return False, "Market state not available"
        
        state = market_state.get('state', 'UNKNOWN')
        if state != "GREEN":
            reason = market_state.get('reason', 'Unknown reason')
            return False, f"Market state is {state}: {reason}"
        
        return True, None
    
    def generate_execution_id(self, ticker: str, horizon: str, signal_time: datetime) -> str:
        """Generate deterministic execution ID for idempotency"""
        # Format: ticker:horizon:YYYY-MM-DDTHH:MM:SS
        signal_str = signal_time.strftime('%Y-%m-%dT%H:%M:%S')
        return f"{ticker}:{horizon}:{signal_str}"
    
    async def check_idempotency(self, execution_id: str) -> Tuple[bool, bool]:
        """
        Check if execution_id was already processed (idempotency)
        Returns: (is_new, was_set)
        """
        if not self.redis_client:
            return False, False
        
        try:
            key = f"key:execution_seen:{execution_id}"
            ttl_seconds = self.idempotency_ttl_hours * 3600
            
            # SETNX: Set if not exists
            was_set = await self.redis_client.set(
                key,
                "1",
                ex=ttl_seconds,
                nx=True  # Only set if not exists
            )
            
            is_new = was_set is True
            return is_new, was_set is True
        except Exception as e:
            logger.error(f"❌ Failed to check idempotency: {e}")
            # Fail safe: if we can't check, don't execute
            return False, False
    
    async def check_cooldown(self, ticker: str) -> Tuple[bool, Optional[datetime]]:
        """
        Check if ticker is in cooldown period
        Returns: (can_trade, last_trade_time)
        """
        if not self.redis_client:
            return False, None
        
        try:
            key = f"key:execution_cooldown:{ticker}"
            last_trade_str = await self.redis_client.get(key)
            
            if not last_trade_str:
                return True, None  # No previous trade, can trade
            
            if isinstance(last_trade_str, bytes):
                last_trade_str = last_trade_str.decode('utf-8')
            
            last_trade_time = datetime.fromisoformat(last_trade_str.replace('Z', '+00:00'))
            cooldown_end = last_trade_time + timedelta(minutes=self.cooldown_minutes)
            
            now = datetime.now(timezone.utc)
            if now < cooldown_end:
                return False, last_trade_time
            
            return True, last_trade_time
        except Exception as e:
            logger.warning(f"⚠️  Failed to check cooldown: {e}")
            # Fail safe: if we can't check, don't execute
            return False, None
    
    async def record_trade(self, ticker: str, execution_id: str):
        """Record that a trade was executed (for cooldown tracking)"""
        if not self.redis_client:
            return
        
        try:
            # Record execution time for cooldown
            cooldown_key = f"key:execution_cooldown:{ticker}"
            now = datetime.now(timezone.utc)
            await self.redis_client.setex(
                cooldown_key,
                self.cooldown_minutes * 60,
                now.isoformat()
            )
            logger.info(f"📝 Recorded trade for {ticker} (cooldown until {now + timedelta(minutes=self.cooldown_minutes)})")
        except Exception as e:
            logger.error(f"❌ Failed to record trade: {e}")
