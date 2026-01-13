"""
Alpaca Market Data Provider
"""

import asyncio
from typing import List, AsyncIterator
from datetime import datetime, timedelta, timezone, date
import os

from .base import MarketDataProvider, Candle

try:
    from alpaca.data.historical import StockHistoricalDataClient
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame
    ALPACA_AVAILABLE = True
except ImportError:
    ALPACA_AVAILABLE = False


class AlpacaProvider(MarketDataProvider):
    """Alpaca API provider for market data"""
    
    def __init__(self, api_key: str, secret_key: str, paper: bool = True):
        if not ALPACA_AVAILABLE:
            raise ImportError("alpaca-py not installed. Install with: pip install alpaca-py")
        
        self.api_key = api_key
        self.secret_key = secret_key
        self.paper = paper
        self.client: StockHistoricalDataClient = None
        self.connected = False
        self.last_fetch_time: dict[str, datetime] = {}
    
    async def connect(self) -> None:
        """Connect to Alpaca API"""
        self.client = StockHistoricalDataClient(
            api_key=self.api_key,
            secret_key=self.secret_key,
            raw_data=False
        )
        self.connected = True
    
    async def disconnect(self) -> None:
        """Disconnect from Alpaca API"""
        self.connected = False
        # Alpaca client doesn't need explicit close
    
    async def stream_1m_candles(self, symbols: List[str]) -> AsyncIterator[Candle]:
        """Stream 1-minute candles via REST polling"""
        if not self.connected:
            raise RuntimeError("Provider not connected")
        
        import logging
        logger = logging.getLogger(__name__)
        backfill_done = False  # Track if we've done initial backfill
        
        while True:
            now = datetime.utcnow()
            # Round down to previous minute (Alpaca aggregates with delay)
            candle_time = (now - timedelta(minutes=1)).replace(second=0, microsecond=0)
            
            no_data_count = 0  # Count symbols with no data
            
            for symbol in symbols:
                try:
                    # Determine fetch window (last 2 minutes to catch any missed candles)
                    fetch_start = candle_time - timedelta(minutes=2)
                    fetch_end = candle_time + timedelta(minutes=1)
                    
                    request = StockBarsRequest(
                        symbol_or_symbols=[symbol],
                        timeframe=TimeFrame.Minute,
                        start=fetch_start,
                        end=fetch_end,
                        feed='iex'  # Use free IEX feed (no SIP subscription required)
                    )
                    
                    logger.info(f"Fetching {symbol} from Alpaca: {fetch_start} to {fetch_end}")
                    
                    bars = self.client.get_stock_bars(request)
                    
                    # Handle different response structures
                    bars_list = None
                    if bars:
                        if isinstance(bars, dict) and symbol in bars:
                            bars_list = bars[symbol]
                        elif hasattr(bars, symbol):
                            bars_list = getattr(bars, symbol)
                        elif hasattr(bars, 'data') and isinstance(bars.data, dict) and symbol in bars.data:
                            bars_list = bars.data[symbol]
                    
                    if bars_list and len(bars_list) > 0:
                        logger.info(f"✅ Received {len(bars_list)} bars for {symbol}")
                        for bar in bars_list:
                            # Only yield if we haven't seen this bar before
                            bar_time = bar.timestamp.replace(tzinfo=None) if bar.timestamp.tzinfo else bar.timestamp
                            
                            if symbol not in self.last_fetch_time or bar_time > self.last_fetch_time.get(symbol, datetime.min):
                                candle = Candle(
                                    ticker=symbol,
                                    time=bar_time,
                                    open=float(bar.open),
                                    high=float(bar.high),
                                    low=float(bar.low),
                                    close=float(bar.close),
                                    volume=int(bar.volume),
                                    source="alpaca"
                                )
                                
                                self.last_fetch_time[symbol] = bar_time
                                yield candle
                    else:
                        no_data_count += 1
                        if bars_list is not None:
                            logger.info(f"⚠️  No new bars for {symbol} (empty response)")
                        else:
                            logger.info(f"⚠️  No data returned for {symbol} (market may be closed or API returned None)")
                
                except Exception as e:
                    logger.warning(f"Error fetching {symbol} from Alpaca: {e}")
                    no_data_count += 1
                    # Continue with next symbol
            
            # If market is closed (no data for all symbols) and we haven't backfilled yet
            # Fetch historical data from the most recent trading day
            if no_data_count == len(symbols) and not backfill_done:
                logger.info("Market appears closed - fetching historical data from last trading day...")
                try:
                    # Find recent trading days (go back up to 7 days to find weekdays)
                    today = date.today()
                    trading_days = []
                    for i in range(1, 8):  # Check last 7 days
                        check_date = today - timedelta(days=i)
                        # Skip weekends (Saturday=5, Sunday=6)
                        if check_date.weekday() < 5:  # Monday=0, Friday=4
                            trading_days.append(check_date)
                    
                    if not trading_days:
                        logger.warning("Could not find any recent trading days for backfill")
                        backfill_done = True
                    else:
                        logger.info(f"Found {len(trading_days)} potential trading days: {trading_days}")
                        total_bars = 0
                        backfill_success = False
                        
                        # Try each trading day until we get data
                        for trading_day in trading_days:
                            if backfill_success:
                                break
                                
                            # Market hours: 9:30 AM - 4:00 PM ET
                            # Alpaca API expects timezone-aware datetimes in UTC
                            # ET is UTC-5 (EST) or UTC-4 (EDT), so 9:30 ET = 14:30 UTC (EST) or 13:30 UTC (EDT)
                            # For simplicity, use 14:30 UTC (EST assumption)
                            market_open_utc = datetime.combine(trading_day, datetime.min.time().replace(hour=14, minute=30)).replace(tzinfo=timezone.utc)
                            market_close_utc = datetime.combine(trading_day, datetime.min.time().replace(hour=21, minute=0)).replace(tzinfo=timezone.utc)
                            
                            logger.info(f"Trying backfill for {trading_day} (ET: 9:30-16:00, UTC: {market_open_utc} - {market_close_utc})")
                            
                            day_bars = 0
                            # Fetch full day of data for all symbols
                            for symbol in symbols:
                                try:
                                    # Try with IEX feed first (free, no SIP subscription)
                                    request = StockBarsRequest(
                                        symbol_or_symbols=[symbol],
                                        timeframe=TimeFrame.Minute,
                                        start=market_open_utc,
                                        end=market_close_utc,
                                        feed='iex'
                                    )
                                    
                                    bars = self.client.get_stock_bars(request)
                                    
                                    # Handle different response structures
                                    bars_list = None
                                    if bars:
                                        if isinstance(bars, dict) and symbol in bars:
                                            bars_list = bars[symbol]
                                        elif hasattr(bars, symbol):
                                            bars_list = getattr(bars, symbol)
                                        elif hasattr(bars, 'data') and isinstance(bars.data, dict) and symbol in bars.data:
                                            bars_list = bars.data[symbol]
                                    
                                    if bars_list and len(bars_list) > 0:
                                        logger.info(f"✅ Backfilling {len(bars_list)} bars for {symbol} from {trading_day}")
                                        day_bars += len(bars_list)
                                        total_bars += len(bars_list)
                                        for bar in bars_list:
                                            bar_time = bar.timestamp.replace(tzinfo=None) if bar.timestamp.tzinfo else bar.timestamp
                                            
                                            # Only yield if we haven't seen this bar before
                                            if symbol not in self.last_fetch_time or bar_time > self.last_fetch_time.get(symbol, datetime.min):
                                                candle = Candle(
                                                    ticker=symbol,
                                                    time=bar_time,
                                                    open=float(bar.open),
                                                    high=float(bar.high),
                                                    low=float(bar.low),
                                                    close=float(bar.close),
                                                    volume=int(bar.volume),
                                                    source="alpaca"
                                                )
                                                
                                                self.last_fetch_time[symbol] = bar_time
                                                yield candle
                                    else:
                                        logger.debug(f"No bars returned for {symbol} on {trading_day} (may be holiday)")
                                except Exception as e:
                                    logger.warning(f"Error backfilling {symbol} for {trading_day}: {e}")
                            
                            # If we got data for this day, mark as success
                            if day_bars > 0:
                                logger.info(f"✅ Successfully backfilled {day_bars} bars from {trading_day}")
                                backfill_success = True
                                break
                            else:
                                logger.info(f"⚠️  No data for {trading_day}, trying next trading day...")
                        
                        if total_bars > 0:
                            logger.info(f"✅ Historical backfill complete: {total_bars} total bars across {len(symbols)} symbols")
                        else:
                            logger.warning(f"⚠️  Historical backfill attempted but no data found for any trading day")
                        backfill_done = True
                except Exception as e:
                    logger.error(f"❌ Error during historical backfill: {e}", exc_info=True)
                    backfill_done = True  # Mark as done to avoid retrying
            
            # Poll every minute
            logger.info(f"Polling cycle complete (no_data_count={no_data_count}/{len(symbols)}), waiting 60 seconds...")
            await asyncio.sleep(60)
    
    async def health_check(self) -> bool:
        """Check if provider is healthy"""
        if not self.connected or not self.client:
            return False
        
        try:
            # Simple health check - try to fetch recent data for SPY
            # Use a shorter window (last hour) to avoid rate limits
            end_time = datetime.utcnow()
            start_time = end_time - timedelta(hours=1)
            
            request = StockBarsRequest(
                symbol_or_symbols=["SPY"],
                timeframe=TimeFrame.Minute,
                start=start_time,
                end=end_time,
                feed='iex'
            )
            
            bars = self.client.get_stock_bars(request)
            # Health check passes if we can make the API call (even if no data due to market closed)
            return True  # API call succeeded
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.debug(f"Alpaca health check failed: {e}")
            return False

