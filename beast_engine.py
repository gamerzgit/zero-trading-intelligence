#!/usr/bin/env python3
"""
================================================================================
    BEAST ENGINE - THE ULTIMATE 0DTE TRADING INTELLIGENCE
================================================================================
    
    Combining the best of:
    - Pine Script Indicators (Project Zero, Ultimate 0DTE Machine, God Mode)
    - ELVA Neural Brain (RF + XGBoost + LightGBM ensemble)
    - Trading AI Platform strategies
    - Real-time option flow analysis
    
    Built for Jetson Orin AGX 64GB
    
    Author: Zero Trading Intelligence
    Version: 1.0.0 BEAST MODE
================================================================================
"""

import os
import sys
import asyncio
import logging
import warnings
from datetime import datetime, timedelta, time as dtime
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass, field
from enum import Enum
import json
import yaml
from collections import deque

# Suppress warnings
warnings.filterwarnings('ignore')

# Data & ML
import numpy as np
import pandas as pd
import joblib
from scipy import stats

# Technical Analysis
try:
    import talib
    TALIB_AVAILABLE = True
except ImportError:
    TALIB_AVAILABLE = False
    print("[WARNING] TA-Lib not available, using pandas-ta")

try:
    import pandas_ta as ta
except ImportError:
    ta = None

# Market Data
from alpaca.data.historical import StockHistoricalDataClient, OptionHistoricalDataClient
from alpaca.data.requests import StockBarsRequest, StockLatestQuoteRequest, OptionChainRequest
from alpaca.data.timeframe import TimeFrame
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import GetAssetsRequest
from alpaca.trading.enums import AssetClass

# Option flow
try:
    import yfinance as yf
    YF_AVAILABLE = True
except ImportError:
    YF_AVAILABLE = False

# Telegram
import aiohttp

# =============================================================================
# CONFIGURATION
# =============================================================================

@dataclass
class Config:
    """Beast Engine Configuration"""
    # Alpaca API
    alpaca_api_key: str = ""
    alpaca_api_secret: str = ""
    alpaca_paper: bool = True
    
    # Telegram
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    
    # Trading Parameters
    min_quality_score: int = 18  # Minimum quality to consider (0-100)
    min_strength_score: int = 6   # Minimum strength (0-10)
    min_confidence: float = 65.0  # Minimum AI confidence %
    
    # Risk Management
    max_daily_trades: int = 10
    max_loss_per_trade: float = 500.0
    position_size_percent: float = 10.0
    
    # VIX Thresholds
    vix_green_max: float = 18.0    # GREEN market
    vix_yellow_max: float = 25.0   # YELLOW market (caution)
    # Above 25 = RED (no new trades)
    
    # Time Windows
    orb_minutes: int = 15          # Opening Range Breakout window
    power_hour_start: int = 15     # Power hour starts at 3 PM ET
    cutoff_hour: int = 15          # No new trades after 3:30 PM
    cutoff_minute: int = 30
    
    # Scanner
    scan_interval_seconds: int = 60
    max_symbols_to_scan: int = 100
    
    # Model paths
    model_0dte_path: str = "models/ai_0dte_model.pkl"
    model_ensemble_path: str = "models/ai_ensemble.pkl"
    model_swing_path: str = "models/ai_swing_model.pkl"

# =============================================================================
# ENUMS & DATA CLASSES
# =============================================================================

class Direction(Enum):
    CALL = "CALL"
    PUT = "PUT"
    NEUTRAL = "NEUTRAL"

class SignalType(Enum):
    POWER_HOUR = "POWER_HOUR"      # Highest confidence
    ORB_BREAKOUT = "ORB_BREAKOUT"  # Opening range breakout
    TRAP = "TRAP"                   # Bull/Bear trap reversal
    EARLY_WARNING = "EARLY_WARNING" # Divergence signal
    CAPITULATION = "CAPITULATION"   # Extreme reversal
    REGULAR = "REGULAR"             # Standard signal

class MarketRegime(Enum):
    GREEN = "GREEN"      # Full risk-on
    YELLOW = "YELLOW"    # Reduced size
    RED = "RED"          # No new trades

class TimePhase(Enum):
    PREMARKET = "PREMARKET"
    ORB = "ORB"              # First 15 min
    BREAKOUT = "BREAKOUT"    # 9:45 - 11:00
    REVERSAL = "REVERSAL"    # 11:00 - 14:00
    POWER = "POWER"          # 15:00 - 16:00
    CLOSED = "CLOSED"

@dataclass
class Signal:
    """Trading Signal"""
    symbol: str
    direction: Direction
    signal_type: SignalType
    strength_score: int          # 0-10 (from Pine Script)
    quality_score: int           # 0-100
    ai_confidence: float         # 0-100
    entry_price: float
    target_price: float
    stop_price: float
    strike: Optional[float] = None
    reasons: List[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.now)
    
    # Option flow data
    call_pct: float = 50.0
    put_pct: float = 50.0
    magnet_strike: Optional[float] = None
    unusual_activity: bool = False
    
    # Technical levels
    vwap: float = 0.0
    poc: float = 0.0  # Point of Control
    orb_high: float = 0.0
    orb_low: float = 0.0
    pivot: float = 0.0
    r1: float = 0.0
    s1: float = 0.0

@dataclass 
class MarketState:
    """Current Market State"""
    regime: MarketRegime = MarketRegime.GREEN
    vix: float = 15.0
    spy_price: float = 0.0
    spy_change_pct: float = 0.0
    phase: TimePhase = TimePhase.CLOSED
    is_trading_day: bool = True

# =============================================================================
# BEAST ENGINE - MAIN CLASS
# =============================================================================

class BeastEngine:
    """
    The Ultimate 0DTE Trading Intelligence Engine
    
    Combines:
    - Pine Script indicators (ZLEMA, Strength, Quality, etc.)
    - AI Models (Random Forest, XGBoost, LightGBM ensemble)
    - Option Flow Analysis
    - Real-time market scanning
    """
    
    def __init__(self, config: Config):
        self.config = config
        self.logger = self._setup_logging()
        
        # Initialize Alpaca clients
        self.stock_client = StockHistoricalDataClient(
            config.alpaca_api_key, 
            config.alpaca_api_secret
        )
        self.option_client = OptionHistoricalDataClient(
            config.alpaca_api_key,
            config.alpaca_api_secret
        )
        self.trading_client = TradingClient(
            config.alpaca_api_key,
            config.alpaca_api_secret,
            paper=config.alpaca_paper
        )
        
        # Load AI Models
        self.models = self._load_models()
        
        # State tracking
        self.market_state = MarketState()
        self.daily_trades = 0
        self.signals_today: List[Signal] = []
        self.strength_history: Dict[str, deque] = {}  # For reversal detection
        
        # Cache for ORB levels
        self.orb_cache: Dict[str, Dict] = {}
        
        # Universe of tradeable symbols
        self.universe: List[str] = []
        
        self.logger.info("=" * 60)
        self.logger.info("    BEAST ENGINE INITIALIZED")
        self.logger.info("=" * 60)
    
    def _setup_logging(self) -> logging.Logger:
        """Setup logging"""
        logger = logging.getLogger("BeastEngine")
        logger.setLevel(logging.INFO)
        
        # Console handler
        ch = logging.StreamHandler()
        ch.setLevel(logging.INFO)
        formatter = logging.Formatter(
            '%(asctime)s | %(levelname)s | %(message)s',
            datefmt='%H:%M:%S'
        )
        ch.setFormatter(formatter)
        logger.addHandler(ch)
        
        # File handler
        os.makedirs("logs", exist_ok=True)
        fh = logging.FileHandler(f"logs/beast_{datetime.now().strftime('%Y%m%d')}.log")
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(formatter)
        logger.addHandler(fh)
        
        return logger
    
    def _load_models(self) -> Dict[str, Any]:
        """Load AI models"""
        models = {}
        
        # Load 0DTE model (primary)
        if os.path.exists(self.config.model_0dte_path):
            try:
                data = joblib.load(self.config.model_0dte_path)
                models['0dte'] = {
                    'rf': data.get('rf_model'),
                    'xgb': data.get('xgb_model'),
                    'lgb': data.get('lgb_model'),
                    'features': data.get('feature_names', [])
                }
                self.logger.info(f"[MODEL] Loaded 0DTE model ({len(models['0dte']['features'])} features)")
            except Exception as e:
                self.logger.error(f"[MODEL] Failed to load 0DTE model: {e}")
        
        # Load ensemble model
        if os.path.exists(self.config.model_ensemble_path):
            try:
                data = joblib.load(self.config.model_ensemble_path)
                models['ensemble'] = data
                self.logger.info("[MODEL] Loaded ensemble model")
            except Exception as e:
                self.logger.error(f"[MODEL] Failed to load ensemble: {e}")
        
        return models
    
    # =========================================================================
    # MARKET DATA
    # =========================================================================
    
    async def fetch_bars(self, symbol: str, timeframe: str = "1Min", 
                        days: int = 1) -> pd.DataFrame:
        """Fetch OHLCV bars for a symbol"""
        try:
            tf_map = {
                "1Min": TimeFrame.Minute,
                "5Min": TimeFrame(5, "Min"),
                "15Min": TimeFrame(15, "Min"),
                "1Hour": TimeFrame.Hour,
                "1Day": TimeFrame.Day
            }
            
            request = StockBarsRequest(
                symbol_or_symbols=symbol,
                timeframe=tf_map.get(timeframe, TimeFrame.Minute),
                start=datetime.now() - timedelta(days=days)
            )
            
            bars = self.stock_client.get_stock_bars(request)
            
            if symbol in bars.data:
                df = pd.DataFrame([{
                    'timestamp': bar.timestamp,
                    'open': bar.open,
                    'high': bar.high,
                    'low': bar.low,
                    'close': bar.close,
                    'volume': bar.volume,
                    'vwap': bar.vwap
                } for bar in bars.data[symbol]])
                
                df.set_index('timestamp', inplace=True)
                return df
            
            return pd.DataFrame()
            
        except Exception as e:
            self.logger.error(f"[DATA] Error fetching {symbol}: {e}")
            return pd.DataFrame()
    
    async def get_vix(self) -> float:
        """Get current VIX price"""
        try:
            if YF_AVAILABLE:
                vix = yf.Ticker("^VIX")
                hist = vix.history(period="1d")
                if not hist.empty:
                    return float(hist['Close'].iloc[-1])
            
            # Fallback: use VIXY ETF
            df = await self.fetch_bars("VIXY", "1Min", 1)
            if not df.empty:
                # VIXY roughly tracks VIX/10
                return float(df['close'].iloc[-1]) * 10
            
            return 20.0  # Default
            
        except Exception as e:
            self.logger.warning(f"[VIX] Error getting VIX: {e}")
            return 20.0
    
    # =========================================================================
    # TECHNICAL INDICATORS (Pine Script Logic)
    # =========================================================================
    
    def calculate_zlema(self, series: pd.Series, period: int) -> pd.Series:
        """Zero-Lag Exponential Moving Average"""
        lag = (period - 1) // 2
        ema_data = 2 * series - series.shift(lag)
        return ema_data.ewm(span=period, adjust=False).mean()
    
    def calculate_ema_stack(self, df: pd.DataFrame) -> Dict[str, pd.Series]:
        """Calculate EMA stack (9, 20, 21, 50, 100, 200)"""
        close = df['close']
        return {
            'ema9': close.ewm(span=9, adjust=False).mean(),
            'ema20': close.ewm(span=20, adjust=False).mean(),
            'ema21': close.ewm(span=21, adjust=False).mean(),
            'ema50': close.ewm(span=50, adjust=False).mean(),
            'ema100': close.ewm(span=100, adjust=False).mean(),
            'ema200': close.ewm(span=200, adjust=False).mean(),
        }
    
    def calculate_macd(self, close: pd.Series, 
                       fast: int = 6, slow: int = 26, signal: int = 5) -> Dict:
        """MACD with 0DTE-optimized parameters (faster than standard)"""
        ema_fast = close.ewm(span=fast, adjust=False).mean()
        ema_slow = close.ewm(span=slow, adjust=False).mean()
        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=signal, adjust=False).mean()
        histogram = macd_line - signal_line
        
        return {
            'macd': macd_line,
            'signal': signal_line,
            'histogram': histogram
        }
    
    def calculate_rsi(self, close: pd.Series, period: int = 7) -> pd.Series:
        """RSI with aggressive period for 0DTE"""
        delta = close.diff()
        gain = delta.where(delta > 0, 0).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss.replace(0, np.nan)
        return 100 - (100 / (1 + rs))
    
    def calculate_atr(self, df: pd.DataFrame, period: int = 14) -> pd.Series:
        """Average True Range"""
        high = df['high']
        low = df['low']
        close = df['close']
        
        tr1 = high - low
        tr2 = abs(high - close.shift())
        tr3 = abs(low - close.shift())
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        
        return tr.rolling(window=period).mean()
    
    def calculate_adx(self, df: pd.DataFrame, period: int = 14) -> pd.Series:
        """Average Directional Index (trend strength)"""
        high = df['high']
        low = df['low']
        close = df['close']
        
        plus_dm = high.diff()
        minus_dm = -low.diff()
        
        plus_dm = plus_dm.where((plus_dm > minus_dm) & (plus_dm > 0), 0)
        minus_dm = minus_dm.where((minus_dm > plus_dm) & (minus_dm > 0), 0)
        
        atr = self.calculate_atr(df, period)
        
        plus_di = 100 * (plus_dm.rolling(period).mean() / atr)
        minus_di = 100 * (minus_dm.rolling(period).mean() / atr)
        
        dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di)
        adx = dx.rolling(period).mean()
        
        return adx
    
    def calculate_vwap(self, df: pd.DataFrame) -> pd.Series:
        """Volume Weighted Average Price"""
        typical_price = (df['high'] + df['low'] + df['close']) / 3
        cumulative_tp_vol = (typical_price * df['volume']).cumsum()
        cumulative_vol = df['volume'].cumsum()
        return cumulative_tp_vol / cumulative_vol
    
    def calculate_pivots(self, df: pd.DataFrame) -> Dict[str, float]:
        """Daily Pivot Points"""
        # Use previous day's data
        if len(df) < 2:
            return {'pivot': 0, 'r1': 0, 'r2': 0, 's1': 0, 's2': 0}
        
        # Get daily aggregation
        daily = df.resample('D').agg({
            'high': 'max',
            'low': 'min', 
            'close': 'last'
        }).dropna()
        
        if len(daily) < 1:
            return {'pivot': 0, 'r1': 0, 'r2': 0, 's1': 0, 's2': 0}
        
        prev = daily.iloc[-1]
        h, l, c = prev['high'], prev['low'], prev['close']
        
        pivot = (h + l + c) / 3
        r1 = 2 * pivot - l
        r2 = pivot + (h - l)
        s1 = 2 * pivot - h
        s2 = pivot - (h - l)
        
        return {'pivot': pivot, 'r1': r1, 'r2': r2, 's1': s1, 's2': s2}
    
    def calculate_orb(self, df: pd.DataFrame, minutes: int = 15) -> Dict[str, float]:
        """Opening Range Breakout levels"""
        today = datetime.now().date()
        
        # Filter for today's data
        today_df = df[df.index.date == today]
        
        if len(today_df) < minutes:
            return {'orb_high': 0, 'orb_low': 0}
        
        # First N minutes
        orb_df = today_df.head(minutes)
        
        return {
            'orb_high': float(orb_df['high'].max()),
            'orb_low': float(orb_df['low'].min())
        }
    
    # =========================================================================
    # STRENGTH & QUALITY SCORES (From Pine Script)
    # =========================================================================
    
    def calculate_strength_score(self, df: pd.DataFrame, 
                                  indicators: Dict) -> int:
        """
        Calculate Strength Score (0-10)
        Based on Ultimate 0DTE Machine Pine Script
        """
        score = 0
        close = df['close'].iloc[-1]
        
        emas = indicators.get('emas', {})
        macd = indicators.get('macd', {})
        rsi = indicators.get('rsi', 50)
        vwap = indicators.get('vwap', close)
        adx = indicators.get('adx', 20)
        
        # 1. Price vs VWAP
        if close > vwap:
            score += 1
        
        # 2. Price vs EMA9
        if 'ema9' in emas and close > emas['ema9'].iloc[-1]:
            score += 1
        
        # 3. Price vs EMA21
        if 'ema21' in emas and close > emas['ema21'].iloc[-1]:
            score += 1
        
        # 4. Price vs EMA50
        if 'ema50' in emas and close > emas['ema50'].iloc[-1]:
            score += 1
        
        # 5. EMA9 > EMA21 (short-term trend)
        if 'ema9' in emas and 'ema21' in emas:
            if emas['ema9'].iloc[-1] > emas['ema21'].iloc[-1]:
                score += 1
        
        # 6. EMA21 > EMA50 (medium-term trend)
        if 'ema21' in emas and 'ema50' in emas:
            if emas['ema21'].iloc[-1] > emas['ema50'].iloc[-1]:
                score += 1
        
        # 7. MACD positive
        if 'histogram' in macd and macd['histogram'].iloc[-1] > 0:
            score += 1
        
        # 8. MACD rising
        if 'histogram' in macd and len(macd['histogram']) > 1:
            if macd['histogram'].iloc[-1] > macd['histogram'].iloc[-2]:
                score += 1
        
        # 9. RSI favorable (40-70 for calls, 30-60 for puts)
        if 40 <= rsi <= 70:
            score += 1
        
        # 10. Volume confirmation
        if len(df) > 20:
            vol_sma = df['volume'].rolling(20).mean().iloc[-1]
            if df['volume'].iloc[-1] > vol_sma * 1.2:
                score += 1
        
        return min(score, 10)
    
    def calculate_quality_score(self, strength: int, indicators: Dict,
                                 option_flow: Dict, market_state: MarketState) -> int:
        """
        Calculate Quality Score (0-100)
        Based on Ultimate 0DTE Machine + God Mode
        """
        score = 0
        
        # Base from strength (0-10 -> 0-50)
        score += strength * 5
        
        # ADX trend strength (0-15)
        adx = indicators.get('adx', 20)
        if adx > 25:
            score += 10
        elif adx > 20:
            score += 7
        elif adx > 15:
            score += 5
        
        # RSI position (0-10)
        rsi = indicators.get('rsi', 50)
        if 30 <= rsi <= 70:
            score += 5
        if 40 <= rsi <= 60:
            score += 5
        
        # MACD confirmation (0-10)
        macd = indicators.get('macd', {})
        if 'histogram' in macd:
            hist = macd['histogram'].iloc[-1]
            if abs(hist) > 0.1:
                score += 5
            if len(macd['histogram']) > 1:
                if (hist > 0 and hist > macd['histogram'].iloc[-2]) or \
                   (hist < 0 and hist < macd['histogram'].iloc[-2]):
                    score += 5
        
        # Option flow confirmation (0-10)
        call_pct = option_flow.get('call_pct', 50)
        if call_pct > 60:  # Bullish flow
            score += 5
        if option_flow.get('unusual_activity', False):
            score += 5
        
        # Market regime adjustment
        if market_state.regime == MarketRegime.GREEN:
            score = int(score * 1.1)
        elif market_state.regime == MarketRegime.RED:
            score = int(score * 0.7)
        
        # Time phase bonus
        if market_state.phase == TimePhase.POWER:
            score += 10  # Power hour bonus
        elif market_state.phase == TimePhase.ORB:
            score += 5   # ORB bonus
        
        return min(score, 100)
    
    # =========================================================================
    # AI PREDICTION
    # =========================================================================
    
    def ai_predict(self, features: Dict[str, float]) -> Tuple[Direction, float]:
        """
        Get AI prediction from ensemble model
        Returns: (Direction, Confidence%)
        """
        if '0dte' not in self.models:
            return Direction.NEUTRAL, 50.0
        
        model_data = self.models['0dte']
        feature_names = model_data.get('features', [])
        
        # Prepare feature vector
        X = np.zeros((1, len(feature_names)))
        for i, name in enumerate(feature_names):
            X[0, i] = features.get(name, 0)
        
        predictions = []
        confidences = []
        
        # Random Forest
        if model_data.get('rf'):
            try:
                pred = model_data['rf'].predict(X)[0]
                proba = model_data['rf'].predict_proba(X)[0]
                predictions.append(pred)
                confidences.append(max(proba) * 100)
            except:
                pass
        
        # XGBoost
        if model_data.get('xgb'):
            try:
                pred = model_data['xgb'].predict(X)[0]
                proba = model_data['xgb'].predict_proba(X)[0]
                predictions.append(pred)
                confidences.append(max(proba) * 100)
            except:
                pass
        
        # LightGBM
        if model_data.get('lgb'):
            try:
                pred = model_data['lgb'].predict(X)[0]
                proba = model_data['lgb'].predict_proba(X)[0]
                predictions.append(pred)
                confidences.append(max(proba) * 100)
            except:
                pass
        
        if not predictions:
            return Direction.NEUTRAL, 50.0
        
        # Ensemble voting
        avg_pred = np.mean(predictions)
        avg_conf = np.mean(confidences)
        
        # Map to direction (assuming 0=down, 1=neutral, 2=up)
        if avg_pred >= 1.5:
            return Direction.CALL, avg_conf
        elif avg_pred <= 0.5:
            return Direction.PUT, avg_conf
        else:
            return Direction.NEUTRAL, avg_conf
    
    def prepare_ai_features(self, df: pd.DataFrame, 
                            indicators: Dict) -> Dict[str, float]:
        """Prepare features for AI model"""
        features = {}
        
        close = df['close']
        volume = df['volume']
        
        # Price features
        features['close'] = float(close.iloc[-1])
        features['returns_1'] = float(close.pct_change().iloc[-1] * 100) if len(close) > 1 else 0
        features['returns_5'] = float(close.pct_change(5).iloc[-1] * 100) if len(close) > 5 else 0
        features['returns_10'] = float(close.pct_change(10).iloc[-1] * 100) if len(close) > 10 else 0
        
        # Technical indicators
        emas = indicators.get('emas', {})
        macd = indicators.get('macd', {})
        
        features['rsi'] = float(indicators.get('rsi', 50))
        features['adx'] = float(indicators.get('adx', 20))
        
        if 'ema9' in emas:
            features['price_to_ema9'] = float(close.iloc[-1] / emas['ema9'].iloc[-1])
        if 'ema21' in emas:
            features['price_to_ema21'] = float(close.iloc[-1] / emas['ema21'].iloc[-1])
        if 'ema50' in emas:
            features['price_to_ema50'] = float(close.iloc[-1] / emas['ema50'].iloc[-1])
        
        if 'histogram' in macd:
            features['macd_hist'] = float(macd['histogram'].iloc[-1])
        
        # Volume features
        if len(volume) > 20:
            vol_sma = volume.rolling(20).mean().iloc[-1]
            features['volume_ratio'] = float(volume.iloc[-1] / vol_sma) if vol_sma > 0 else 1.0
        
        # Volatility
        features['atr'] = float(indicators.get('atr', 1.0))
        features['atr_pct'] = float(features['atr'] / close.iloc[-1] * 100)
        
        # Time features
        now = datetime.now()
        features['hour'] = float(now.hour)
        features['minute'] = float(now.minute)
        features['minutes_to_close'] = float(max(0, (16 * 60 - (now.hour * 60 + now.minute))))
        
        return features
    
    # =========================================================================
    # OPTION FLOW ANALYSIS
    # =========================================================================
    
    async def analyze_option_flow(self, symbol: str, 
                                   current_price: float) -> Dict:
        """Analyze option flow for a symbol"""
        result = {
            'call_pct': 50.0,
            'put_pct': 50.0,
            'magnet_strike': None,
            'unusual_activity': False,
            'institutional_bias': 'NEUTRAL'
        }
        
        try:
            # Try yfinance first
            if YF_AVAILABLE:
                ticker = yf.Ticker(symbol)
                
                # Get 0DTE expiration
                expirations = ticker.options
                if not expirations:
                    return result
                
                # Find today's expiration or nearest
                today = datetime.now().strftime('%Y-%m-%d')
                target_exp = expirations[0]  # Default to nearest
                
                for exp in expirations:
                    if exp == today:
                        target_exp = exp
                        break
                
                # Get option chain
                chain = ticker.option_chain(target_exp)
                calls = chain.calls
                puts = chain.puts
                
                if calls.empty or puts.empty:
                    return result
                
                # Filter strikes near current price (+/- 5%)
                strike_range = current_price * 0.05
                calls = calls[(calls['strike'] >= current_price - strike_range) & 
                             (calls['strike'] <= current_price + strike_range)]
                puts = puts[(puts['strike'] >= current_price - strike_range) & 
                           (puts['strike'] <= current_price + strike_range)]
                
                # Calculate call/put ratio
                total_call_vol = float(calls['volume'].sum()) if not calls.empty else 0
                total_put_vol = float(puts['volume'].sum()) if not puts.empty else 0
                total_vol = total_call_vol + total_put_vol
                
                if total_vol > 0:
                    result['call_pct'] = total_call_vol / total_vol * 100
                    result['put_pct'] = total_put_vol / total_vol * 100
                
                # Find magnet strike (highest open interest)
                if not calls.empty and not puts.empty:
                    all_strikes = pd.concat([
                        calls[['strike', 'openInterest']],
                        puts[['strike', 'openInterest']]
                    ])
                    
                    if not all_strikes.empty and all_strikes['openInterest'].sum() > 0:
                        magnet_idx = all_strikes['openInterest'].idxmax()
                        result['magnet_strike'] = float(all_strikes.loc[magnet_idx, 'strike'])
                
                # Detect unusual activity
                num_options = len(calls) + len(puts)
                avg_vol = total_vol / num_options if num_options > 0 else 0
                max_call_vol = float(calls['volume'].max()) if not calls.empty and len(calls) > 0 else 0
                max_put_vol = float(puts['volume'].max()) if not puts.empty and len(puts) > 0 else 0
                max_vol = max(max_call_vol, max_put_vol)
                
                if max_vol > avg_vol * 3:
                    result['unusual_activity'] = True
                
                # Institutional bias
                if result['call_pct'] > 60:
                    result['institutional_bias'] = 'BULLISH'
                elif result['put_pct'] > 60:
                    result['institutional_bias'] = 'BEARISH'
                
        except Exception as e:
            self.logger.warning(f"[FLOW] Error analyzing {symbol}: {e}")
        
        return result
    
    # =========================================================================
    # SIGNAL DETECTION
    # =========================================================================
    
    def detect_signal_type(self, df: pd.DataFrame, indicators: Dict,
                           strength_score: int) -> Tuple[SignalType, List[str]]:
        """Detect the type of signal based on conditions"""
        reasons = []
        now = datetime.now()
        
        close = df['close'].iloc[-1]
        
        # Check Power Hour (3 PM - 4 PM ET)
        if now.hour >= 15:
            reasons.append("POWER HOUR - High conviction time")
            return SignalType.POWER_HOUR, reasons
        
        # Check ORB Breakout
        orb = indicators.get('orb', {})
        if orb.get('orb_high', 0) > 0:
            if close > orb['orb_high']:
                reasons.append(f"ORB Breakout above {orb['orb_high']:.2f}")
                return SignalType.ORB_BREAKOUT, reasons
            elif close < orb['orb_low']:
                reasons.append(f"ORB Breakdown below {orb['orb_low']:.2f}")
                return SignalType.ORB_BREAKOUT, reasons
        
        # Check for Trap (failed breakout reversal)
        if len(df) >= 5:
            recent_high = df['high'].iloc[-5:].max()
            recent_low = df['low'].iloc[-5:].min()
            
            # Bull trap: broke high then reversed down
            if df['high'].iloc[-3] >= recent_high and close < df['close'].iloc[-3]:
                reasons.append("Bull Trap detected - reversal signal")
                return SignalType.TRAP, reasons
            
            # Bear trap: broke low then reversed up
            if df['low'].iloc[-3] <= recent_low and close > df['close'].iloc[-3]:
                reasons.append("Bear Trap detected - reversal signal")
                return SignalType.TRAP, reasons
        
        # Check for Early Warning (divergence)
        rsi = indicators.get('rsi', 50)
        if len(df) >= 10:
            price_trend = df['close'].iloc[-1] > df['close'].iloc[-10]
            rsi_trend = rsi > 50
            
            if price_trend and not rsi_trend:
                reasons.append("Bearish divergence - early warning")
                return SignalType.EARLY_WARNING, reasons
            elif not price_trend and rsi_trend:
                reasons.append("Bullish divergence - early warning")
                return SignalType.EARLY_WARNING, reasons
        
        # Check for Capitulation (extreme moves)
        if rsi < 20 or rsi > 80:
            if rsi < 20:
                reasons.append(f"Oversold capitulation (RSI: {rsi:.1f})")
            else:
                reasons.append(f"Overbought capitulation (RSI: {rsi:.1f})")
            return SignalType.CAPITULATION, reasons
        
        # Regular signal
        reasons.append("Regular signal based on technicals")
        return SignalType.REGULAR, reasons
    
    def determine_direction(self, df: pd.DataFrame, indicators: Dict,
                            option_flow: Dict, ai_direction: Direction,
                            ai_confidence: float) -> Tuple[Direction, List[str]]:
        """
        Determine trade direction using all available signals
        """
        reasons = []
        bullish_votes = 0
        bearish_votes = 0
        
        close = df['close'].iloc[-1]
        emas = indicators.get('emas', {})
        macd = indicators.get('macd', {})
        rsi = indicators.get('rsi', 50)
        vwap = indicators.get('vwap', close)
        
        # 1. AI Model vote (weight: 3)
        if ai_direction == Direction.CALL and ai_confidence >= 60:
            bullish_votes += 3
            reasons.append(f"AI: CALL ({ai_confidence:.0f}%)")
        elif ai_direction == Direction.PUT and ai_confidence >= 60:
            bearish_votes += 3
            reasons.append(f"AI: PUT ({ai_confidence:.0f}%)")
        
        # 2. Price vs VWAP (weight: 2)
        if close > vwap * 1.001:
            bullish_votes += 2
            reasons.append("Price > VWAP")
        elif close < vwap * 0.999:
            bearish_votes += 2
            reasons.append("Price < VWAP")
        
        # 3. EMA alignment (weight: 2)
        if 'ema9' in emas and 'ema21' in emas:
            ema9 = emas['ema9'].iloc[-1]
            ema21 = emas['ema21'].iloc[-1]
            
            if ema9 > ema21 and close > ema9:
                bullish_votes += 2
                reasons.append("Bullish EMA stack")
            elif ema9 < ema21 and close < ema9:
                bearish_votes += 2
                reasons.append("Bearish EMA stack")
        
        # 4. MACD (weight: 2)
        if 'histogram' in macd:
            hist = macd['histogram'].iloc[-1]
            if hist > 0:
                bullish_votes += 2
                reasons.append("MACD bullish")
            elif hist < 0:
                bearish_votes += 2
                reasons.append("MACD bearish")
        
        # 5. RSI (weight: 1)
        if rsi > 50 and rsi < 70:
            bullish_votes += 1
            reasons.append(f"RSI bullish ({rsi:.0f})")
        elif rsi < 50 and rsi > 30:
            bearish_votes += 1
            reasons.append(f"RSI bearish ({rsi:.0f})")
        
        # 6. Option flow (weight: 2)
        call_pct = option_flow.get('call_pct', 50)
        if call_pct > 60:
            bullish_votes += 2
            reasons.append(f"Options: {call_pct:.0f}% calls")
        elif call_pct < 40:
            bearish_votes += 2
            reasons.append(f"Options: {100-call_pct:.0f}% puts")
        
        # 7. Recent momentum (weight: 1)
        if len(df) >= 5:
            momentum = (close - df['close'].iloc[-5]) / df['close'].iloc[-5] * 100
            if momentum > 0.1:
                bullish_votes += 1
                reasons.append(f"Momentum +{momentum:.1f}%")
            elif momentum < -0.1:
                bearish_votes += 1
                reasons.append(f"Momentum {momentum:.1f}%")
        
        # Final decision
        total_votes = bullish_votes + bearish_votes
        if total_votes == 0:
            return Direction.NEUTRAL, reasons
        
        # Need at least 60% agreement
        if bullish_votes >= bearish_votes * 1.5:
            return Direction.CALL, reasons
        elif bearish_votes >= bullish_votes * 1.5:
            return Direction.PUT, reasons
        else:
            return Direction.NEUTRAL, reasons
    
    def calculate_targets(self, df: pd.DataFrame, direction: Direction,
                          indicators: Dict) -> Tuple[float, float]:
        """Calculate target and stop prices"""
        close = float(df['close'].iloc[-1])
        atr = indicators.get('atr', close * 0.01)
        
        # Ensure ATR is at least 0.3% of price for 0DTE
        min_atr = close * 0.003
        atr = max(float(atr), min_atr)
        
        if direction == Direction.CALL:
            target = close + (atr * 2.0)   # 2 ATR target
            stop = close - (atr * 1.0)     # 1 ATR stop
        else:
            target = close - (atr * 2.0)
            stop = close + (atr * 1.0)
        
        return round(target, 2), round(stop, 2)
    
    # =========================================================================
    # MARKET STATE
    # =========================================================================
    
    async def update_market_state(self) -> MarketState:
        """Update current market state"""
        now = datetime.now()
        
        # Get VIX
        vix = await self.get_vix()
        
        # Determine regime
        if vix <= self.config.vix_green_max:
            regime = MarketRegime.GREEN
        elif vix <= self.config.vix_yellow_max:
            regime = MarketRegime.YELLOW
        else:
            regime = MarketRegime.RED
        
        # Determine time phase
        hour = now.hour
        minute = now.minute
        
        if hour < 9 or (hour == 9 and minute < 30):
            phase = TimePhase.PREMARKET
        elif hour == 9 and minute < 45:
            phase = TimePhase.ORB
        elif hour < 11:
            phase = TimePhase.BREAKOUT
        elif hour < 15:
            phase = TimePhase.REVERSAL
        elif hour < 16:
            phase = TimePhase.POWER
        else:
            phase = TimePhase.CLOSED
        
        # Get SPY data
        spy_df = await self.fetch_bars("SPY", "1Min", 1)
        spy_price = float(spy_df['close'].iloc[-1]) if not spy_df.empty else 0
        spy_open = float(spy_df['open'].iloc[0]) if not spy_df.empty else spy_price
        spy_change = ((spy_price - spy_open) / spy_open * 100) if spy_open > 0 else 0
        
        self.market_state = MarketState(
            regime=regime,
            vix=vix,
            spy_price=spy_price,
            spy_change_pct=spy_change,
            phase=phase,
            is_trading_day=True  # TODO: Check trading calendar
        )
        
        return self.market_state
    
    # =========================================================================
    # SCANNER
    # =========================================================================
    
    async def load_universe(self) -> List[str]:
        """Load tradeable universe (stocks with 0DTE options)"""
        # Core universe - most liquid 0DTE options
        core = [
            # Indices
            "SPY", "QQQ", "IWM", "DIA",
            # Tech
            "AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA", "AMD", "NFLX",
            # Finance
            "JPM", "BAC", "GS", "MS", "C",
            # Energy
            "XOM", "CVX", "OXY",
            # Healthcare
            "UNH", "JNJ", "PFE", "MRNA",
            # Consumer
            "WMT", "HD", "NKE", "MCD", "SBUX",
            # Other high volume
            "BA", "CAT", "DIS", "V", "MA", "PYPL", "SQ", "COIN",
            # Memes / High volatility
            "GME", "AMC", "PLTR", "SOFI", "RIVN", "LCID"
        ]
        
        self.universe = core
        self.logger.info(f"[SCANNER] Loaded {len(self.universe)} symbols")
        return self.universe
    
    async def scan_symbol(self, symbol: str) -> Optional[Signal]:
        """Scan a single symbol for trading opportunities"""
        try:
            # Fetch data
            df = await self.fetch_bars(symbol, "1Min", 2)
            if df.empty or len(df) < 50:
                return None
            
            # Calculate indicators
            emas = self.calculate_ema_stack(df)
            macd = self.calculate_macd(df['close'])
            rsi = float(self.calculate_rsi(df['close']).iloc[-1])
            atr = float(self.calculate_atr(df).iloc[-1])
            adx = float(self.calculate_adx(df).iloc[-1])
            vwap = float(self.calculate_vwap(df).iloc[-1])
            pivots = self.calculate_pivots(df)
            orb = self.calculate_orb(df, self.config.orb_minutes)
            
            indicators = {
                'emas': emas,
                'macd': macd,
                'rsi': rsi,
                'atr': atr,
                'adx': adx,
                'vwap': vwap,
                'pivots': pivots,
                'orb': orb
            }
            
            # Calculate strength score
            strength_score = self.calculate_strength_score(df, indicators)
            
            # Quick filter - minimum strength
            if strength_score < self.config.min_strength_score:
                return None
            
            # Get option flow
            current_price = float(df['close'].iloc[-1])
            option_flow = await self.analyze_option_flow(symbol, current_price)
            
            # AI prediction
            ai_features = self.prepare_ai_features(df, indicators)
            ai_direction, ai_confidence = self.ai_predict(ai_features)
            
            # Determine final direction
            direction, direction_reasons = self.determine_direction(
                df, indicators, option_flow, ai_direction, ai_confidence
            )
            
            # Skip neutral
            if direction == Direction.NEUTRAL:
                return None
            
            # Calculate quality score
            quality_score = self.calculate_quality_score(
                strength_score, indicators, option_flow, self.market_state
            )
            
            # Filter by minimum quality
            if quality_score < self.config.min_quality_score:
                return None
            
            # Detect signal type
            signal_type, type_reasons = self.detect_signal_type(
                df, indicators, strength_score
            )
            
            # Calculate targets
            target_price, stop_price = self.calculate_targets(df, direction, indicators)
            
            # Build signal
            signal = Signal(
                symbol=symbol,
                direction=direction,
                signal_type=signal_type,
                strength_score=strength_score,
                quality_score=quality_score,
                ai_confidence=ai_confidence,
                entry_price=current_price,
                target_price=target_price,
                stop_price=stop_price,
                reasons=direction_reasons + type_reasons,
                call_pct=option_flow.get('call_pct', 50),
                put_pct=option_flow.get('put_pct', 50),
                magnet_strike=option_flow.get('magnet_strike'),
                unusual_activity=option_flow.get('unusual_activity', False),
                vwap=vwap,
                orb_high=orb.get('orb_high', 0),
                orb_low=orb.get('orb_low', 0),
                pivot=pivots.get('pivot', 0),
                r1=pivots.get('r1', 0),
                s1=pivots.get('s1', 0)
            )
            
            return signal
            
        except Exception as e:
            self.logger.error(f"[SCAN] Error scanning {symbol}: {e}")
            return None
    
    async def scan_market(self) -> List[Signal]:
        """Scan entire market for opportunities"""
        self.logger.info("=" * 50)
        self.logger.info("    BEAST SCAN STARTING")
        self.logger.info("=" * 50)
        
        # Update market state
        await self.update_market_state()
        
        self.logger.info(f"[MARKET] VIX: {self.market_state.vix:.1f} | "
                        f"Regime: {self.market_state.regime.value} | "
                        f"Phase: {self.market_state.phase.value} | "
                        f"SPY: ${self.market_state.spy_price:.2f} ({self.market_state.spy_change_pct:+.2f}%)")
        
        # Check if we should trade
        if self.market_state.regime == MarketRegime.RED:
            self.logger.warning("[MARKET] RED REGIME - No scanning")
            return []
        
        if self.market_state.phase in [TimePhase.PREMARKET, TimePhase.CLOSED]:
            self.logger.info(f"[MARKET] {self.market_state.phase.value} - No scanning")
            return []
        
        # Load universe if needed
        if not self.universe:
            await self.load_universe()
        
        # Scan all symbols
        signals: List[Signal] = []
        
        for symbol in self.universe:
            signal = await self.scan_symbol(symbol)
            if signal:
                signals.append(signal)
                self.logger.info(f"[SIGNAL] {symbol}: {signal.direction.value} | "
                               f"Strength: {signal.strength_score}/10 | "
                               f"Quality: {signal.quality_score}/100 | "
                               f"AI: {signal.ai_confidence:.0f}%")
        
        # Sort by quality score
        signals.sort(key=lambda s: s.quality_score, reverse=True)
        
        self.logger.info(f"[SCAN] Found {len(signals)} signals")
        
        return signals
    
    # =========================================================================
    # TELEGRAM ALERTS
    # =========================================================================
    
    async def send_telegram(self, message: str):
        """Send Telegram message"""
        if not self.config.telegram_bot_token or not self.config.telegram_chat_id:
            return
        
        try:
            url = f"https://api.telegram.org/bot{self.config.telegram_bot_token}/sendMessage"
            
            async with aiohttp.ClientSession() as session:
                await session.post(url, json={
                    'chat_id': self.config.telegram_chat_id,
                    'text': message,
                    'parse_mode': 'HTML'
                })
                
        except Exception as e:
            self.logger.error(f"[TELEGRAM] Error: {e}")
    
    def format_signal_alert(self, signal: Signal) -> str:
        """Format signal for Telegram alert"""
        emoji = "[CALL]" if signal.direction == Direction.CALL else "[PUT]"
        type_emoji = {
            SignalType.POWER_HOUR: "[PWR]",
            SignalType.ORB_BREAKOUT: "[ORB]",
            SignalType.TRAP: "[TRAP]",
            SignalType.CAPITULATION: "[CAP]",
            SignalType.EARLY_WARNING: "[WARN]",
            SignalType.REGULAR: "[REG]"
        }
        
        msg = f"""
{emoji} <b>BEAST SIGNAL: {signal.symbol}</b> {emoji}

<b>Direction:</b> {signal.direction.value}
<b>Signal Type:</b> {type_emoji.get(signal.signal_type, "[REG]")} {signal.signal_type.value}

<b>Scores:</b>
- Strength: {signal.strength_score}/10
- Quality: {signal.quality_score}/100
- AI Confidence: {signal.ai_confidence:.0f}%

<b>Levels:</b>
- Entry: ${signal.entry_price:.2f}
- Target: ${signal.target_price:.2f}
- Stop: ${signal.stop_price:.2f}

<b>Option Flow:</b>
- Calls: {signal.call_pct:.0f}% | Puts: {signal.put_pct:.0f}%
- Magnet Strike: ${'%.0f' % signal.magnet_strike if signal.magnet_strike else 'N/A'}
- Unusual Activity: {'YES!' if signal.unusual_activity else 'No'}

<b>Key Levels:</b>
- VWAP: ${signal.vwap:.2f}
- ORB: ${signal.orb_low:.2f} - ${signal.orb_high:.2f}
- Pivot: ${signal.pivot:.2f}

<b>Reasons:</b>
{chr(10).join(['* ' + r for r in signal.reasons[:5]])}

Time: {signal.timestamp.strftime('%H:%M:%S')}
"""
        return msg
    
    async def send_signal_alert(self, signal: Signal):
        """Send signal alert via Telegram"""
        msg = self.format_signal_alert(signal)
        await self.send_telegram(msg)
    
    # =========================================================================
    # MORNING BRIEF
    # =========================================================================
    
    async def generate_morning_brief(self) -> str:
        """Generate morning intelligence brief"""
        await self.update_market_state()
        
        # Get key market data
        spy_df = await self.fetch_bars("SPY", "1Day", 5)
        qqq_df = await self.fetch_bars("QQQ", "1Day", 5)
        
        # Calculate key metrics
        spy_5d_change = 0
        qqq_5d_change = 0
        
        if not spy_df.empty and len(spy_df) >= 5:
            spy_5d_change = ((spy_df['close'].iloc[-1] - spy_df['close'].iloc[0]) / 
                           spy_df['close'].iloc[0] * 100)
        
        if not qqq_df.empty and len(qqq_df) >= 5:
            qqq_5d_change = ((qqq_df['close'].iloc[-1] - qqq_df['close'].iloc[0]) / 
                           qqq_df['close'].iloc[0] * 100)
        
        regime_emoji = {
            MarketRegime.GREEN: "[GREEN]",
            MarketRegime.YELLOW: "[YELLOW]",
            MarketRegime.RED: "[RED]"
        }
        
        brief = f"""
===================================
    BEAST MORNING BRIEF
===================================

{datetime.now().strftime('%A, %B %d, %Y')}
{datetime.now().strftime('%H:%M:%S')} ET

<b>MARKET REGIME:</b> {regime_emoji[self.market_state.regime]} {self.market_state.regime.value}
<b>VIX:</b> {self.market_state.vix:.1f}

<b>INDICES:</b>
- SPY: ${self.market_state.spy_price:.2f} ({self.market_state.spy_change_pct:+.2f}% today, {spy_5d_change:+.1f}% 5D)
- QQQ: {qqq_5d_change:+.1f}% 5D

<b>TODAY'S PLAYBOOK:</b>
"""
        
        if self.market_state.regime == MarketRegime.GREEN:
            brief += """
[OK] Full risk-on mode
[OK] Normal position sizes
[OK] All signal types valid
"""
        elif self.market_state.regime == MarketRegime.YELLOW:
            brief += """
[!!] Elevated volatility
[!!] Reduce position sizes 50%
[!!] Focus on Power Hour signals only
"""
        else:
            brief += """
[XX] HIGH VOLATILITY - CAUTION
[XX] No new trades recommended
[XX] Wait for VIX to cool down
"""
        
        brief += """
<b>KEY TIMES TODAY:</b>
- 9:30-9:45: ORB Phase (watch breakouts)
- 9:45-11:00: Breakout Phase (best momentum)
- 11:00-15:00: Reversal Phase (mean reversion)
- 15:00-16:00: Power Hour (highest conviction)

<b>FOCUS SYMBOLS:</b>
SPY, QQQ, NVDA, TSLA, AMD, META

===================================
        BEAST ENGINE READY
===================================
"""
        
        return brief
    
    async def send_morning_brief(self):
        """Send morning brief via Telegram"""
        brief = await self.generate_morning_brief()
        await self.send_telegram(brief)
        self.logger.info("[BRIEF] Morning brief sent")
    
    # =========================================================================
    # MAIN LOOP
    # =========================================================================
    
    async def run(self):
        """Main execution loop"""
        self.logger.info("=" * 60)
        self.logger.info("    BEAST ENGINE STARTING")
        self.logger.info("=" * 60)
        
        # Load universe
        await self.load_universe()
        
        # Send morning brief if market is about to open
        now = datetime.now()
        if now.hour == 9 and now.minute < 30:
            await self.send_morning_brief()
        
        # Main scanning loop
        while True:
            try:
                now = datetime.now()
                
                # Check if market is open
                if now.weekday() >= 5:  # Weekend
                    self.logger.info("[MARKET] Weekend - sleeping 1 hour")
                    await asyncio.sleep(3600)
                    continue
                
                # Market hours check (9:30 AM - 4:00 PM ET)
                market_open = dtime(9, 30)
                market_close = dtime(16, 0)
                current_time = now.time()
                
                if current_time < market_open:
                    wait_seconds = (datetime.combine(now.date(), market_open) - now).seconds
                    self.logger.info(f"[MARKET] Pre-market - waiting {wait_seconds//60} minutes")
                    
                    # Send morning brief 5 min before open
                    if wait_seconds <= 300:
                        await self.send_morning_brief()
                    
                    await asyncio.sleep(min(wait_seconds, 300))
                    continue
                
                if current_time > market_close:
                    self.logger.info("[MARKET] Market closed - done for today")
                    break
                
                # Cutoff time - no new scans
                cutoff = dtime(self.config.cutoff_hour, self.config.cutoff_minute)
                if current_time > cutoff:
                    self.logger.info("[MARKET] Past cutoff - no new scans")
                    await asyncio.sleep(60)
                    continue
                
                # Run scan
                signals = await self.scan_market()
                
                # Send alerts for top signals
                for signal in signals[:3]:  # Top 3 signals
                    await self.send_signal_alert(signal)
                    self.signals_today.append(signal)
                
                # Wait for next scan
                self.logger.info(f"[SCAN] Next scan in {self.config.scan_interval_seconds} seconds")
                await asyncio.sleep(self.config.scan_interval_seconds)
                
            except KeyboardInterrupt:
                self.logger.info("[ENGINE] Shutdown requested")
                break
            except Exception as e:
                self.logger.error(f"[ENGINE] Error: {e}")
                await asyncio.sleep(30)
        
        self.logger.info("=" * 60)
        self.logger.info("    BEAST ENGINE STOPPED")
        self.logger.info("=" * 60)
    
    # =========================================================================
    # QUERY MODE
    # =========================================================================
    
    async def query_symbol(self, symbol: str) -> str:
        """Query a specific symbol for detailed analysis"""
        self.logger.info(f"[QUERY] Analyzing {symbol}...")
        
        signal = await self.scan_symbol(symbol)
        
        if not signal:
            return f"""
<b>{symbol} Analysis</b>

[X] No valid signal found

Possible reasons:
* Strength score too low
* No clear direction
* Quality score below threshold
"""
        
        # Get additional data
        df = await self.fetch_bars(symbol, "1Min", 2)
        daily = await self.fetch_bars(symbol, "1Day", 30)
        
        # Calculate more metrics
        daily_change = 0
        weekly_change = 0
        monthly_change = 0
        
        if not daily.empty:
            if len(daily) >= 2:
                daily_change = ((daily['close'].iloc[-1] - daily['close'].iloc[-2]) / 
                               daily['close'].iloc[-2] * 100)
            if len(daily) >= 5:
                weekly_change = ((daily['close'].iloc[-1] - daily['close'].iloc[-5]) / 
                                daily['close'].iloc[-5] * 100)
            if len(daily) >= 22:
                monthly_change = ((daily['close'].iloc[-1] - daily['close'].iloc[-22]) / 
                                 daily['close'].iloc[-22] * 100)
        
        analysis = f"""
===================================
    BEAST ANALYSIS: {symbol}
===================================

<b>CURRENT PRICE:</b> ${signal.entry_price:.2f}
<b>DIRECTION:</b> {'[CALL]' if signal.direction == Direction.CALL else '[PUT]'} {signal.direction.value}

<b>SCORES:</b>
- Strength: {'#' * signal.strength_score}{'-' * (10-signal.strength_score)} {signal.strength_score}/10
- Quality: {signal.quality_score}/100
- AI Confidence: {signal.ai_confidence:.0f}%

<b>TRADE SETUP:</b>
- Entry: ${signal.entry_price:.2f}
- Target: ${signal.target_price:.2f} ({((signal.target_price-signal.entry_price)/signal.entry_price*100):+.1f}%)
- Stop: ${signal.stop_price:.2f} ({((signal.stop_price-signal.entry_price)/signal.entry_price*100):+.1f}%)

<b>OPTION FLOW:</b>
- Call Volume: {signal.call_pct:.0f}%
- Put Volume: {signal.put_pct:.0f}%
- Magnet Strike: ${'%.0f' % signal.magnet_strike if signal.magnet_strike else 'N/A'}
- Unusual Activity: {'YES!' if signal.unusual_activity else 'No'}

<b>TECHNICAL LEVELS:</b>
- VWAP: ${signal.vwap:.2f}
- ORB High: ${signal.orb_high:.2f}
- ORB Low: ${signal.orb_low:.2f}
- Pivot: ${signal.pivot:.2f}
- R1: ${signal.r1:.2f}
- S1: ${signal.s1:.2f}

<b>PERFORMANCE:</b>
- Today: {daily_change:+.2f}%
- Week: {weekly_change:+.2f}%
- Month: {monthly_change:+.2f}%

<b>SIGNAL TYPE:</b> {signal.signal_type.value}

<b>REASONS:</b>
{chr(10).join(['* ' + r for r in signal.reasons])}

===================================
"""
        
        return analysis


# =============================================================================
# MAIN ENTRY POINT
# =============================================================================

def load_config() -> Config:
    """Load configuration from yaml or environment"""
    config = Config()
    
    # Try to load from config.yaml
    if os.path.exists("config.yaml"):
        with open("config.yaml", 'r') as f:
            yaml_config = yaml.safe_load(f)
            
            if 'alpaca' in yaml_config:
                config.alpaca_api_key = yaml_config['alpaca'].get('api_key', '')
                config.alpaca_api_secret = yaml_config['alpaca'].get('api_secret', '')
                config.alpaca_paper = yaml_config['alpaca'].get('paper', True)
            
            if 'telegram' in yaml_config:
                config.telegram_bot_token = yaml_config['telegram'].get('bot_token', '')
                config.telegram_chat_id = yaml_config['telegram'].get('chat_id', '')
            
            if 'trading' in yaml_config:
                config.min_quality_score = yaml_config['trading'].get('min_quality_score', 18)
                config.min_strength_score = yaml_config['trading'].get('min_strength_score', 6)
                config.min_confidence = yaml_config['trading'].get('min_confidence', 65.0)
    
    # Override with environment variables
    config.alpaca_api_key = os.getenv('ALPACA_API_KEY', config.alpaca_api_key)
    config.alpaca_api_secret = os.getenv('ALPACA_API_SECRET', config.alpaca_api_secret)
    config.telegram_bot_token = os.getenv('TELEGRAM_BOT_TOKEN', config.telegram_bot_token)
    config.telegram_chat_id = os.getenv('TELEGRAM_CHAT_ID', config.telegram_chat_id)
    
    return config


async def main():
    """Main entry point"""
    print("""
    ==============================================================
    |                                                            |
    |    BBBBB   EEEEE   AAA   SSSSS  TTTTT                     |
    |    B    B  E      A   A  S        T                        |
    |    BBBBB   EEEE   AAAAA  SSSSS    T                        |
    |    B    B  E      A   A      S    T                        |
    |    BBBBB   EEEEE  A   A  SSSSS    T                        |
    |                                                            |
    |         THE ULTIMATE 0DTE TRADING INTELLIGENCE             |
    |                                                            |
    ==============================================================
    """)
    
    # Load configuration
    config = load_config()
    
    # Initialize engine
    engine = BeastEngine(config)
    
    # Check for command line arguments
    if len(sys.argv) > 1:
        command = sys.argv[1].lower()
        
        if command == "scan":
            # Single scan
            signals = await engine.scan_market()
            for signal in signals:
                print(engine.format_signal_alert(signal))
        
        elif command == "query" and len(sys.argv) > 2:
            # Query specific symbol
            symbol = sys.argv[2].upper()
            analysis = await engine.query_symbol(symbol)
            print(analysis)
        
        elif command == "brief":
            # Send morning brief
            await engine.send_morning_brief()
        
        elif command == "patterns":
            # Run pattern scanner
            from pattern_scanner import PatternScanner
            scanner = PatternScanner(yaml.safe_load(open("config.yaml")))
            
            # Quick scan (top 50 stocks)
            symbols = scanner._get_fallback_universe()[:50]
            all_patterns = []
            
            print(f"\nScanning {len(symbols)} stocks for chart patterns...")
            
            for symbol in symbols:
                df = await scanner.fetch_data(symbol, days=5)
                if not df.empty:
                    patterns = await scanner.scan_symbol(symbol, df)
                    all_patterns.extend(patterns)
            
            # Sort by confidence
            all_patterns.sort(key=lambda p: p.confidence, reverse=True)
            
            # Display results
            results = scanner.format_scan_results(all_patterns[:20])
            print(results)
        
        else:
            print(f"Unknown command: {command}")
            print("Usage:")
            print("  python beast_engine.py           # Run continuous scanning")
            print("  python beast_engine.py scan      # Single scan")
            print("  python beast_engine.py query SPY # Query specific symbol")
            print("  python beast_engine.py brief     # Send morning brief")
            print("  python beast_engine.py patterns  # Scan for chart patterns")
    else:
        # Run continuous scanning
        await engine.run()


if __name__ == "__main__":
    asyncio.run(main())
