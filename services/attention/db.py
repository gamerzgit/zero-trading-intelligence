"""
ZERO Attention Engine - Database Access Layer
"""

import asyncpg
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
import json

logger = logging.getLogger(__name__)


class AttentionDB:
    """Database access for attention engine"""
    
    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool
    
    async def get_recent_candles(
        self,
        symbols: List[str],
        minutes: int = 60,
        table: str = "candles_5m"
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Get recent candles for multiple symbols.
        Returns dict: {symbol: [candles]}
        
        During off-hours, extends lookback to find most recent available data.
        """
        cutoff = datetime.utcnow() - timedelta(minutes=minutes)
        
        # First try with requested window
        # If no data found, extend to 24 hours (for off-hours)
        extended_cutoff = datetime.utcnow() - timedelta(hours=24)
        
        query = f"""
            SELECT ticker, time, open, high, low, close, volume
            FROM {table}
            WHERE ticker = ANY($1)
              AND time >= $2
            ORDER BY ticker, time ASC
        """
        
        result = {s: [] for s in symbols}
        
        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch(query, symbols, cutoff)
                
                # If no data found, try extended lookback (off-hours fallback)
                if not rows:
                    logger.info(f"No candles in {minutes}m window, trying 24h lookback")
                    rows = await conn.fetch(query, symbols, extended_cutoff)
                
                for row in rows:
                    ticker = row['ticker']
                    if ticker in result:
                        result[ticker].append(dict(row))
                
                logger.debug(f"Fetched candles: {[(s, len(c)) for s, c in result.items()]}")
                return result
                
        except Exception as e:
            logger.error(f"Error fetching candles: {e}")
            return result
    
    async def get_available_symbols(self, symbols: List[str]) -> List[str]:
        """Check which symbols have recent data"""
        cutoff = datetime.utcnow() - timedelta(hours=24)
        
        query = """
            SELECT DISTINCT ticker
            FROM candles_5m
            WHERE ticker = ANY($1)
              AND time >= $2
        """
        
        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch(query, symbols, cutoff)
                return [row['ticker'] for row in rows]
        except Exception as e:
            logger.error(f"Error checking available symbols: {e}")
            return []
    
    async def insert_attention_log(
        self,
        attention_state: Dict[str, Any]
    ) -> Optional[int]:
        """Insert attention state into attention_log"""
        query = """
            INSERT INTO attention_log (
                time, dominant_sectors, attention_concentration,
                attention_stability, risk_on_off_state, correlation_regime
            ) VALUES ($1, $2, $3, $4, $5, $6)
            RETURNING id
        """
        
        try:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow(
                    query,
                    datetime.utcnow(),
                    json.dumps(attention_state.get('dominant_sectors')),
                    attention_state.get('attention_concentration'),
                    attention_state.get('attention_stability_score'),
                    attention_state.get('risk_on_off_state'),
                    attention_state.get('correlation_regime')
                )
                return row['id']
        except Exception as e:
            logger.error(f"Error inserting attention log: {e}")
            return None
