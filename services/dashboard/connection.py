"""
ZERO Dashboard - Redis Connection Helper
Handles Redis connections and data fetching
"""

import os
import json
import redis
from typing import Optional, Dict, Any
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class RedisConnection:
    """Redis connection manager for dashboard"""
    
    def __init__(self):
        self.host = os.getenv('REDIS_HOST', 'redis')
        self.port = int(os.getenv('REDIS_PORT', '6379'))
        self.client: Optional[redis.Redis] = None
        self._connect()
    
    def _connect(self):
        """Connect to Redis"""
        try:
            self.client = redis.Redis(
                host=self.host,
                port=self.port,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5
            )
            # Test connection
            self.client.ping()
            logger.info(f"✅ Connected to Redis at {self.host}:{self.port}")
        except Exception as e:
            logger.error(f"❌ Failed to connect to Redis: {e}")
            self.client = None
    
    def get_market_state(self) -> Optional[Dict[str, Any]]:
        """Get current market state from Redis"""
        if not self.client:
            return None
        
        try:
            data = self.client.get('key:market_state')
            if data:
                return json.loads(data)
        except Exception as e:
            logger.warning(f"⚠️  Failed to get market state: {e}")
        
        return None
    
    def get_opportunity_rank(self) -> Optional[Dict[str, Any]]:
        """Get current opportunity rank from Redis"""
        if not self.client:
            return None
        
        try:
            data = self.client.get('key:opportunity_rank')
            if data:
                return json.loads(data)
        except Exception as e:
            logger.warning(f"⚠️  Failed to get opportunity rank: {e}")
        
        return None
    
    def get_active_candidates(self) -> Optional[Dict[str, Any]]:
        """Get active candidates from Redis"""
        if not self.client:
            return None
        
        try:
            data = self.client.get('key:active_candidates')
            if data:
                return json.loads(data)
        except Exception as e:
            logger.warning(f"⚠️  Failed to get active candidates: {e}")
        
        return None
    
    def is_connected(self) -> bool:
        """Check if Redis is connected"""
        if not self.client:
            return False
        try:
            self.client.ping()
            return True
        except:
            return False
