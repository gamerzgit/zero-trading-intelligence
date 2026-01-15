"""
ZERO Truth Test - Database Access Layer
"""

import asyncpg
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
import json

logger = logging.getLogger(__name__)


class TruthTestDB:
    """Database access for truth test operations"""
    
    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool
    
    async def get_unevaluated_opportunities(self, before_time: datetime) -> List[Dict[str, Any]]:
        """
        Get opportunities that haven't been evaluated yet.
        Only returns opportunities issued before the given time (to ensure horizon has elapsed).
        """
        query = """
            SELECT 
                o.id, o.time, o.ticker, o.horizon, o.opportunity_score,
                o.probability, o.target_atr, o.stop_atr, o.market_state,
                o.attention_stability_score, o.attention_bucket
            FROM opportunity_log o
            LEFT JOIN performance_log p ON o.id = p.opportunity_id
            WHERE p.id IS NULL
              AND o.time < $1
            ORDER BY o.time ASC
        """
        
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, before_time)
            return [dict(row) for row in rows]
    
    async def get_candles_for_evaluation(
        self, 
        ticker: str, 
        start_time: datetime, 
        end_time: datetime,
        timeframe: str = "1m"
    ) -> List[Dict[str, Any]]:
        """
        Get candles for MFE/MAE evaluation.
        Falls back to 5m if 1m not available.
        """
        table = "candles_1m" if timeframe == "1m" else "candles_5m"
        
        query = f"""
            SELECT time, open, high, low, close, volume
            FROM {table}
            WHERE ticker = $1
              AND time >= $2
              AND time <= $3
            ORDER BY time ASC
        """
        
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, ticker, start_time, end_time)
            
            # If no 1m data, try 5m
            if not rows and timeframe == "1m":
                logger.info(f"No 1m candles for {ticker}, trying 5m")
                return await self.get_candles_for_evaluation(ticker, start_time, end_time, "5m")
            
            return [dict(row) for row in rows]
    
    async def get_entry_candle(
        self, 
        ticker: str, 
        issue_time: datetime,
        max_delay_minutes: int = 2
    ) -> Optional[Dict[str, Any]]:
        """
        Get the entry reference candle (1m close at or immediately after issue time).
        Returns None if no candle found within max_delay_minutes.
        """
        end_time = issue_time + timedelta(minutes=max_delay_minutes)
        
        query = """
            SELECT time, open, high, low, close, volume
            FROM candles_1m
            WHERE ticker = $1
              AND time >= $2
              AND time <= $3
            ORDER BY time ASC
            LIMIT 1
        """
        
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(query, ticker, issue_time, end_time)
            return dict(row) if row else None
    
    async def compute_atr(
        self, 
        ticker: str, 
        as_of_time: datetime,
        period: int = 14
    ) -> Optional[float]:
        """
        Compute ATR at a given time using 5m candles.
        Returns None if insufficient data.
        """
        # Need period+1 candles to compute ATR
        lookback = timedelta(hours=period * 5 / 60 + 2)  # Extra buffer
        
        query = """
            SELECT time, high, low, close
            FROM candles_5m
            WHERE ticker = $1
              AND time <= $2
              AND time >= $3
            ORDER BY time DESC
            LIMIT $4
        """
        
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                query, 
                ticker, 
                as_of_time, 
                as_of_time - lookback,
                period + 1
            )
            
            if len(rows) < period + 1:
                logger.warning(f"Insufficient data for ATR: {ticker} has {len(rows)} candles, need {period + 1}")
                return None
            
            # Calculate True Range for each period
            true_ranges = []
            rows = list(reversed(rows))  # Oldest first
            
            for i in range(1, len(rows)):
                high = float(rows[i]['high'])
                low = float(rows[i]['low'])
                prev_close = float(rows[i-1]['close'])
                
                tr = max(
                    high - low,
                    abs(high - prev_close),
                    abs(low - prev_close)
                )
                true_ranges.append(tr)
            
            # Simple moving average of TR
            if len(true_ranges) >= period:
                atr = sum(true_ranges[-period:]) / period
                return atr
            
            return None
    
    async def insert_performance_result(self, result: Dict[str, Any]) -> int:
        """Insert a truth test result into performance_log"""
        query = """
            INSERT INTO performance_log (
                opportunity_id, ticker, horizon, issued_time, regime_state,
                attention_stability_score, attention_bucket,
                probability_issued, target_atr, stop_atr, atr_value,
                entry_price, realized_mfe, realized_mae, mfe_atr, mae_atr,
                outcome, target_hit_first, stop_hit_first, neither_hit,
                evaluation_time, debug_json
            ) VALUES (
                $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, $19, $20, $21, $22
            )
            RETURNING id
        """
        
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                query,
                result['opportunity_id'],
                result['ticker'],
                result['horizon'],
                result['issued_time'],
                result['regime_state'],
                result['attention_stability_score'],
                result.get('attention_bucket'),
                result.get('probability_issued'),
                result.get('target_atr'),
                result.get('stop_atr'),
                result.get('atr_value'),
                result.get('entry_price'),
                result.get('realized_mfe'),
                result.get('realized_mae'),
                result.get('mfe_atr'),
                result.get('mae_atr'),
                result['outcome'],
                result.get('target_hit_first'),
                result.get('stop_hit_first'),
                result.get('neither_hit'),
                result['evaluation_time'],
                json.dumps(result.get('debug_json')) if result.get('debug_json') else None
            )
            return row['id']
    
    async def get_calibration_data(
        self, 
        lookback_days: int = 30
    ) -> List[Dict[str, Any]]:
        """
        Get performance data for calibration aggregation.
        Groups by horizon, market_state, attention_bucket.
        """
        cutoff = datetime.utcnow() - timedelta(days=lookback_days)
        
        query = """
            SELECT 
                horizon,
                regime_state,
                attention_bucket,
                COUNT(*) as total_signals,
                COUNT(*) FILTER (WHERE outcome = 'PASS') as pass_count,
                COUNT(*) FILTER (WHERE outcome = 'FAIL') as fail_count,
                COUNT(*) FILTER (WHERE outcome = 'EXPIRED') as expired_count,
                COUNT(*) FILTER (WHERE outcome = 'NO_DATA') as no_data_count,
                AVG(probability_issued) as avg_probability,
                AVG(CASE WHEN outcome = 'PASS' THEN 1.0 ELSE 0.0 END) as actual_pass_rate
            FROM performance_log
            WHERE evaluation_time >= $1
              AND outcome IN ('PASS', 'FAIL')
            GROUP BY horizon, regime_state, attention_bucket
            ORDER BY horizon, regime_state, attention_bucket
        """
        
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, cutoff)
            return [dict(row) for row in rows]
