"""
Database Writer for Candles
"""

import asyncpg
from typing import List, Optional
from datetime import datetime, timedelta
import os

from ..provider.base import Candle


class DatabaseWriter:
    """Writes candles to TimescaleDB"""
    
    def __init__(self, db_url: str):
        self.db_url = db_url
        self.pool: Optional[asyncpg.Pool] = None
        self.last_candle_time: dict[str, datetime] = {}
    
    async def connect(self) -> None:
        """Connect to database"""
        self.pool = await asyncpg.create_pool(self.db_url, min_size=2, max_size=10)
    
    async def disconnect(self) -> None:
        """Disconnect from database"""
        if self.pool:
            await self.pool.close()
    
    async def write_1m_candle(self, candle: Candle) -> None:
        """Write 1-minute candle to database"""
        async with self.pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO candles_1m (ticker, time, open, high, low, close, volume, source)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                ON CONFLICT (ticker, time) DO UPDATE SET
                    open = EXCLUDED.open,
                    high = EXCLUDED.high,
                    low = EXCLUDED.low,
                    close = EXCLUDED.close,
                    volume = EXCLUDED.volume,
                    source = EXCLUDED.source
            """, candle.ticker, candle.time, candle.open, candle.high, 
                candle.low, candle.close, candle.volume, candle.source)
        
        # Track last candle time for gap detection
        self.last_candle_time[candle.ticker] = candle.time
    
    async def write_1m_candles_batch(self, candles: List[Candle]) -> None:
        """Write multiple 1-minute candles in batch"""
        if not candles:
            return
        
        async with self.pool.acquire() as conn:
            await conn.executemany("""
                INSERT INTO candles_1m (ticker, time, open, high, low, close, volume, source)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                ON CONFLICT (ticker, time) DO UPDATE SET
                    open = EXCLUDED.open,
                    high = EXCLUDED.high,
                    low = EXCLUDED.low,
                    close = EXCLUDED.close,
                    volume = EXCLUDED.volume,
                    source = EXCLUDED.source
            """, [(c.ticker, c.time, c.open, c.high, c.low, c.close, c.volume, c.source) 
                  for c in candles])
        
        # Update last candle times
        for candle in candles:
            self.last_candle_time[candle.ticker] = candle.time
    
    async def aggregate_5m_candles(self, ticker: str, from_time: datetime, to_time: datetime) -> None:
        """Aggregate 1m candles into 5m candles"""
        async with self.pool.acquire() as conn:
            # Use date_trunc for 5-minute buckets (TimescaleDB compatible)
            await conn.execute("""
                INSERT INTO candles_5m (ticker, time, open, high, low, close, volume, source)
                SELECT
                    ticker,
                    date_trunc('minute', time) - (EXTRACT(MINUTE FROM time)::int % 5 || ' minutes')::interval AS time,
                    (array_agg(open ORDER BY time))[1] AS open,
                    max(high) AS high,
                    min(low) AS low,
                    (array_agg(close ORDER BY time DESC))[1] AS close,
                    sum(volume) AS volume,
                    (array_agg(source ORDER BY time))[1] AS source
                FROM candles_1m
                WHERE ticker = $1 AND time >= $2 AND time < $3
                GROUP BY ticker, date_trunc('minute', time) - (EXTRACT(MINUTE FROM time)::int % 5 || ' minutes')::interval
                ON CONFLICT (ticker, time) DO UPDATE SET
                    open = EXCLUDED.open,
                    high = EXCLUDED.high,
                    low = EXCLUDED.low,
                    close = EXCLUDED.close,
                    volume = EXCLUDED.volume,
                    source = EXCLUDED.source
            """, ticker, from_time, to_time)
    
    async def aggregate_1d_candles(self, ticker: str, date: datetime) -> None:
        """Aggregate 1m candles into daily candles"""
        # Normalize to 00:00:00Z
        day_start = date.replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day_start + timedelta(days=1)
        
        async with self.pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO candles_1d (ticker, time, open, high, low, close, volume, source)
                SELECT
                    ticker,
                    date_trunc('day', time) AS time,
                    (array_agg(open ORDER BY time))[1] AS open,
                    max(high) AS high,
                    min(low) AS low,
                    (array_agg(close ORDER BY time DESC))[1] AS close,
                    sum(volume) AS volume,
                    (array_agg(source ORDER BY time))[1] AS source
                FROM candles_1m
                WHERE ticker = $1 AND time >= $2 AND time < $3
                GROUP BY ticker, date_trunc('day', time)
                ON CONFLICT (ticker, time) DO UPDATE SET
                    open = EXCLUDED.open,
                    high = EXCLUDED.high,
                    low = EXCLUDED.low,
                    close = EXCLUDED.close,
                    volume = EXCLUDED.volume,
                    source = EXCLUDED.source
            """, ticker, day_start, day_end)
    
    async def detect_gaps(self, ticker: str, current_time: datetime) -> None:
        """Detect and log gaps in 1-minute candles"""
        last_time = self.last_candle_time.get(ticker)
        if not last_time:
            return
        
        # Check if there's a gap (missing minute)
        expected_next = last_time + timedelta(minutes=1)
        
        if current_time > expected_next + timedelta(minutes=1):
            # Gap detected
            gap_start = expected_next
            gap_end = current_time - timedelta(minutes=1)
            
            async with self.pool.acquire() as conn:
                # Use ON CONFLICT with unique constraint or check if gap already logged
                # Check if gap already logged to avoid duplicates
                existing = await conn.fetchval("""
                    SELECT COUNT(*) FROM ingest_gap_log
                    WHERE ticker = $1 AND timeframe = '1m'
                    AND gap_start = $2 AND gap_end = $3
                """, ticker, gap_start, gap_end)
                
                if not existing:
                    await conn.execute("""
                        INSERT INTO ingest_gap_log (ticker, timeframe, gap_start, gap_end, detection_time, reason)
                        VALUES ($1, '1m', $2, $3, $4, 'Missing candles detected')
                    """, ticker, gap_start, gap_end, datetime.utcnow())
    
    async def get_last_candle_time(self, ticker: str) -> Optional[datetime]:
        """Get the timestamp of the last candle for a ticker"""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT MAX(time) as last_time
                FROM candles_1m
                WHERE ticker = $1
            """, ticker)
            
            if row and row["last_time"]:
                return row["last_time"]
            return None
    
    async def get_candle_count(self, ticker: str) -> int:
        """Get count of candles for a ticker"""
        async with self.pool.acquire() as conn:
            count = await conn.fetchval("""
                SELECT COUNT(*) FROM candles_1m WHERE ticker = $1
            """, ticker)
            return count or 0

