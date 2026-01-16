#!/usr/bin/env python3
"""
================================================================================
    BEAST LIVE - EL SISTEMA COMPLETO QUE CORRE TODO EL DÍA
================================================================================
    
    Este es el sistema final que:
    1. Corre continuamente durante market hours
    2. Calcula probabilidades cada 30 segundos
    3. Combina AI + Técnicos + Flow + Tiempo + Régimen
    4. Alerta por Telegram cuando hay consenso
    5. Registra todo para validación
    
================================================================================
"""

import os
import sys
import asyncio
import json
import numpy as np
import pandas as pd
from datetime import datetime, timedelta, time as dtime
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field, asdict
import joblib
import yaml
import aiohttp
import warnings
warnings.filterwarnings('ignore')

from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit

try:
    import yfinance as yf
    YF_AVAILABLE = True
except:
    YF_AVAILABLE = False


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class Signal:
    symbol: str
    direction: str  # CALL / PUT
    probability: float
    confidence: float
    entry: float
    target: float
    stop: float
    
    # Component probabilities
    ai_prob: float
    tech_prob: float
    flow_prob: float
    time_prob: float
    regime_prob: float
    
    # Alignment
    signals_aligned: int
    total_signals: int
    
    # Factors
    factors: Dict = field(default_factory=dict)
    reasons: List[str] = field(default_factory=list)
    
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class TradeLog:
    signal: Signal
    outcome: Optional[str] = None  # WIN / LOSS / PENDING
    actual_return: Optional[float] = None
    logged_at: datetime = field(default_factory=datetime.now)


# =============================================================================
# BEAST LIVE ENGINE
# =============================================================================

class BeastLive:
    """
    Sistema completo que corre todo el día
    """
    
    # Configuración
    SCAN_INTERVAL = 30  # segundos entre scans
    MIN_PROBABILITY = 58  # mínimo para alertar
    MIN_SIGNALS_ALIGNED = 4  # mínimo de señales alineadas
    
    # Universe de símbolos
    UNIVERSE = [
        "SPY", "QQQ", "IWM",
        "AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA", "AMD",
        "JPM", "BAC", "GS",
        "XOM", "CVX",
        "PLTR", "COIN", "MARA", "SMCI"
    ]
    
    # Pesos para probabilidad compuesta
    WEIGHTS = {
        'ai': 0.25,
        'tech': 0.20,
        'flow': 0.15,
        'time': 0.10,
        'regime': 0.15,
        'momentum': 0.15
    }
    
    # Probabilidades por hora (calibradas del backtest)
    HOURLY_WIN_RATES = {
        9: 0.48,   # Open - volátil
        10: 0.52,  # Post-open momentum
        11: 0.49,  # Mid-morning
        12: 0.47,  # Lunch lull
        13: 0.50,  # Early afternoon
        14: 0.51,  # Pre-power
        15: 0.56,  # Power hour (el mejor)
    }
    
    def __init__(self, config: Dict):
        self.config = config
        
        # Alpaca client
        alpaca = config.get('alpaca', {})
        self.client = StockHistoricalDataClient(
            alpaca.get('api_key', ''),
            alpaca.get('api_secret', '')
        )
        
        # Telegram
        tg = config.get('telegram', {})
        self.tg_token = tg.get('bot_token', '')
        self.tg_chat = tg.get('chat_id', '')
        
        # Load AI models
        self.models = self._load_models()
        
        # State
        self.signals_today: List[Signal] = []
        self.alerts_sent: int = 0
        self.last_vix: float = 20.0
        
        # Logging
        os.makedirs("logs", exist_ok=True)
        os.makedirs("data", exist_ok=True)
        
        self._log("=" * 60)
        self._log("    BEAST LIVE INICIADO")
        self._log("=" * 60)
    
    def _log(self, msg: str):
        """Log to console and file"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        full_msg = f"{timestamp} | {msg}"
        print(full_msg)
        
        log_file = f"logs/beast_live_{datetime.now().strftime('%Y%m%d')}.log"
        with open(log_file, 'a') as f:
            f.write(full_msg + "\n")
    
    def _load_models(self) -> Dict:
        """Load AI models"""
        models = {}
        path = "models/ai_0dte_model.pkl"
        
        if os.path.exists(path):
            try:
                data = joblib.load(path)
                models['rf'] = data.get('rf_model')
                models['xgb'] = data.get('xgb_model')
                models['lgb'] = data.get('lgb_model')
                models['features'] = data.get('feature_names', [])
                self._log(f"[AI] Modelos cargados ({len(models['features'])} features)")
            except Exception as e:
                self._log(f"[AI] Error: {e}")
        
        return models
    
    async def fetch_data(self, symbol: str, days: int = 3) -> pd.DataFrame:
        """Fetch market data"""
        try:
            request = StockBarsRequest(
                symbol_or_symbols=symbol,
                timeframe=TimeFrame(5, TimeFrameUnit.Minute),  # 5-min para más granularidad
                start=datetime.now() - timedelta(days=days)
            )
            bars = self.client.get_stock_bars(request)
            
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
        except:
            return pd.DataFrame()
    
    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculate all technical indicators"""
        if df.empty or len(df) < 20:
            return df
        
        close = df['close']
        high = df['high']
        low = df['low']
        volume = df['volume']
        
        # RSI (7)
        delta = close.diff()
        gain = delta.where(delta > 0, 0).rolling(7).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(7).mean()
        rs = gain / loss.replace(0, np.nan)
        df['rsi'] = 100 - (100 / (1 + rs))
        
        # MACD (6, 13, 5)
        ema_fast = close.ewm(span=6).mean()
        ema_slow = close.ewm(span=13).mean()
        df['macd'] = ema_fast - ema_slow
        df['macd_signal'] = df['macd'].ewm(span=5).mean()
        df['macd_hist'] = df['macd'] - df['macd_signal']
        
        # EMAs
        df['ema9'] = close.ewm(span=9).mean()
        df['ema21'] = close.ewm(span=21).mean()
        df['ema50'] = close.ewm(span=50).mean()
        
        # ATR
        tr = pd.concat([
            high - low,
            abs(high - close.shift()),
            abs(low - close.shift())
        ], axis=1).max(axis=1)
        df['atr'] = tr.rolling(14).mean()
        
        # ADX
        plus_dm = high.diff()
        minus_dm = -low.diff()
        plus_dm = plus_dm.where((plus_dm > minus_dm) & (plus_dm > 0), 0)
        minus_dm = minus_dm.where((minus_dm > plus_dm) & (minus_dm > 0), 0)
        atr = df['atr'].replace(0, np.nan)
        plus_di = 100 * (plus_dm.rolling(14).mean() / atr)
        minus_di = 100 * (minus_dm.rolling(14).mean() / atr)
        dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di).replace(0, np.nan)
        df['adx'] = dx.rolling(14).mean()
        
        # Volume
        df['vol_sma'] = volume.rolling(20).mean()
        df['vol_ratio'] = volume / df['vol_sma'].replace(0, np.nan)
        
        # Momentum
        df['mom_5'] = close.pct_change(5) * 100
        df['mom_10'] = close.pct_change(10) * 100
        
        return df
    
    def get_ai_prediction(self, df: pd.DataFrame) -> Tuple[str, float]:
        """Get AI model prediction"""
        if not self.models.get('rf'):
            return 'NEUTRAL', 50.0
        
        row = df.iloc[-1]
        features = {}
        
        # Prepare features
        features['close'] = float(row['close'])
        features['returns_1'] = float(df['close'].pct_change().iloc[-1] * 100)
        features['returns_5'] = float(df['close'].pct_change(5).iloc[-1] * 100) if len(df) > 5 else 0
        features['returns_10'] = float(df['close'].pct_change(10).iloc[-1] * 100) if len(df) > 10 else 0
        features['rsi'] = float(row.get('rsi', 50))
        features['adx'] = float(row.get('adx', 20))
        features['macd_hist'] = float(row.get('macd_hist', 0))
        features['volume_ratio'] = float(row.get('vol_ratio', 1))
        features['atr'] = float(row.get('atr', 1))
        features['atr_pct'] = features['atr'] / features['close'] * 100 if features['close'] > 0 else 0
        features['price_to_ema9'] = float(row['close'] / row['ema9']) if row.get('ema9') and row['ema9'] > 0 else 1
        features['price_to_ema21'] = float(row['close'] / row['ema21']) if row.get('ema21') and row['ema21'] > 0 else 1
        features['price_to_ema50'] = float(row['close'] / row['ema50']) if row.get('ema50') and row['ema50'] > 0 else 1
        
        now = datetime.now()
        features['hour'] = float(now.hour)
        features['minute'] = float(now.minute)
        features['minutes_to_close'] = float(max(0, (16 * 60 - (now.hour * 60 + now.minute))))
        features['day_of_week'] = float(now.weekday())
        
        # Build feature vector
        feature_names = self.models.get('features', [])
        X = np.zeros((1, len(feature_names)))
        for i, name in enumerate(feature_names):
            X[0, i] = features.get(name, 0)
        
        # Get predictions
        probas = []
        for model_name in ['rf', 'xgb', 'lgb']:
            model = self.models.get(model_name)
            if model:
                try:
                    proba = model.predict_proba(X)[0]
                    probas.append(proba)
                except:
                    pass
        
        if not probas:
            return 'NEUTRAL', 50.0
        
        avg = np.mean(probas, axis=0)
        
        if len(avg) >= 3:
            up = avg[2] * 100
            down = avg[0] * 100
            if up > down and up > 45:
                return 'CALL', up
            elif down > up and down > 45:
                return 'PUT', down
        
        return 'NEUTRAL', 50.0
    
    def get_technical_signal(self, df: pd.DataFrame) -> Tuple[str, float, int, Dict]:
        """Get technical analysis signal"""
        row = df.iloc[-1]
        
        bullish = 0
        bearish = 0
        factors = {}
        
        # 1. Price vs VWAP
        if row['close'] > row['vwap']:
            bullish += 1
            factors['vwap'] = 'above'
        else:
            bearish += 1
            factors['vwap'] = 'below'
        
        # 2. EMA Stack
        ema9 = row.get('ema9', 0)
        ema21 = row.get('ema21', 0)
        ema50 = row.get('ema50', 0)
        
        if ema9 > ema21 > ema50:
            bullish += 2
            factors['ema'] = 'bullish_stack'
        elif ema9 < ema21 < ema50:
            bearish += 2
            factors['ema'] = 'bearish_stack'
        else:
            factors['ema'] = 'mixed'
        
        # 3. MACD
        macd_hist = row.get('macd_hist', 0)
        if macd_hist > 0:
            bullish += 1
            factors['macd'] = 'bullish'
        elif macd_hist < 0:
            bearish += 1
            factors['macd'] = 'bearish'
        
        # 4. RSI
        rsi = row.get('rsi', 50)
        factors['rsi'] = f'{rsi:.0f}'
        if rsi < 30:
            bullish += 1  # Oversold reversal
        elif rsi > 70:
            bearish += 1  # Overbought reversal
        elif 50 < rsi < 65:
            bullish += 0.5
        elif 35 < rsi < 50:
            bearish += 0.5
        
        # 5. ADX (trend strength)
        adx = row.get('adx', 20)
        factors['adx'] = f'{adx:.0f}'
        if adx > 25:
            if bullish > bearish:
                bullish += 1
            else:
                bearish += 1
        
        # 6. Volume
        vol_ratio = row.get('vol_ratio', 1)
        factors['vol'] = f'{vol_ratio:.1f}x'
        if vol_ratio > 1.5:
            if bullish > bearish:
                bullish += 0.5
            else:
                bearish += 0.5
        
        # 7. Momentum
        mom = row.get('mom_5', 0)
        factors['mom'] = f'{mom:+.2f}%'
        if mom > 0.3:
            bullish += 1
        elif mom < -0.3:
            bearish += 1
        
        # Calculate
        total = bullish + bearish
        signals_aligned = max(int(bullish), int(bearish))
        
        if bullish > bearish:
            prob = 50 + (bullish / total * 25) if total > 0 else 50
            return 'CALL', min(prob, 75), signals_aligned, factors
        elif bearish > bullish:
            prob = 50 + (bearish / total * 25) if total > 0 else 50
            return 'PUT', min(prob, 75), signals_aligned, factors
        
        return 'NEUTRAL', 50, 0, factors
    
    async def get_option_flow(self, symbol: str, price: float) -> Tuple[str, float, Dict]:
        """Get option flow signal"""
        factors = {}
        
        if not YF_AVAILABLE:
            return 'NEUTRAL', 50, factors
        
        try:
            ticker = yf.Ticker(symbol)
            exps = ticker.options
            if not exps:
                return 'NEUTRAL', 50, factors
            
            chain = ticker.option_chain(exps[0])
            calls = chain.calls
            puts = chain.puts
            
            # Filter near the money
            rng = price * 0.03
            calls = calls[(calls['strike'] >= price - rng) & (calls['strike'] <= price + rng)]
            puts = puts[(puts['strike'] >= price - rng) & (puts['strike'] <= price + rng)]
            
            call_vol = float(calls['volume'].sum()) if not calls.empty else 0
            put_vol = float(puts['volume'].sum()) if not puts.empty else 0
            total = call_vol + put_vol
            
            if total == 0:
                return 'NEUTRAL', 50, factors
            
            call_pct = call_vol / total * 100
            put_pct = put_vol / total * 100
            
            factors['calls'] = f'{call_pct:.0f}%'
            factors['puts'] = f'{put_pct:.0f}%'
            
            if call_pct > 58:
                return 'CALL', 50 + (call_pct - 50) * 0.4, factors
            elif put_pct > 58:
                return 'PUT', 50 + (put_pct - 50) * 0.4, factors
            
            return 'NEUTRAL', 50, factors
            
        except:
            return 'NEUTRAL', 50, factors
    
    def get_time_probability(self) -> Tuple[str, float]:
        """Get time-based probability"""
        hour = datetime.now().hour
        base = self.HOURLY_WIN_RATES.get(hour, 0.50)
        
        if hour == 15:  # Power hour
            return 'TREND', base * 100
        elif hour == 9:  # Open volatility
            return 'VOLATILE', base * 100
        elif hour in [11, 12]:  # Lunch
            return 'CHOPPY', base * 100
        
        return 'NORMAL', base * 100
    
    async def get_vix_regime(self) -> Tuple[str, float]:
        """Get VIX regime"""
        try:
            if YF_AVAILABLE:
                vix = yf.Ticker("^VIX")
                hist = vix.history(period="1d")
                if not hist.empty:
                    self.last_vix = float(hist['Close'].iloc[-1])
            
            if self.last_vix < 15:
                return 'LOW_VOL', 58
            elif self.last_vix < 20:
                return 'NORMAL', 50
            elif self.last_vix < 28:
                return 'ELEVATED', 45
            else:
                return 'HIGH', 40
        except:
            return 'NORMAL', 50
    
    async def analyze_symbol(self, symbol: str) -> Optional[Signal]:
        """Full analysis of a symbol"""
        df = await self.fetch_data(symbol)
        if df.empty or len(df) < 30:
            return None
        
        df = self.calculate_indicators(df)
        price = float(df['close'].iloc[-1])
        atr = float(df['atr'].iloc[-1]) if not pd.isna(df['atr'].iloc[-1]) else price * 0.005
        
        # Get all signals
        ai_dir, ai_prob = self.get_ai_prediction(df)
        tech_dir, tech_prob, tech_aligned, factors = self.get_technical_signal(df)
        flow_dir, flow_prob, flow_factors = await self.get_option_flow(symbol, price)
        time_phase, time_prob = self.get_time_probability()
        regime, regime_prob = await self.get_vix_regime()
        
        factors.update(flow_factors)
        factors['regime'] = regime
        factors['phase'] = time_phase
        
        # Vote
        votes = {'CALL': 0, 'PUT': 0}
        aligned = 0
        total = 0
        reasons = []
        
        for name, direction, prob, weight in [
            ('AI', ai_dir, ai_prob, 0.30),
            ('Tech', tech_dir, tech_prob, 0.25),
            ('Flow', flow_dir, flow_prob, 0.20),
            ('Time', time_phase if time_phase == 'TREND' else 'NEUTRAL', time_prob, 0.10),
        ]:
            if direction in ['CALL', 'PUT']:
                votes[direction] += prob * weight
                total += 1
                reasons.append(f"{name}: {direction} ({prob:.0f}%)")
        
        # Determine direction
        if votes['CALL'] > votes['PUT'] and votes['CALL'] > 30:
            final_dir = 'CALL'
            for name, d, p, w in [('AI', ai_dir, ai_prob, 1), ('Tech', tech_dir, tech_prob, 1), 
                                   ('Flow', flow_dir, flow_prob, 1)]:
                if d == 'CALL':
                    aligned += 1
        elif votes['PUT'] > votes['CALL'] and votes['PUT'] > 30:
            final_dir = 'PUT'
            for name, d, p, w in [('AI', ai_dir, ai_prob, 1), ('Tech', tech_dir, tech_prob, 1), 
                                   ('Flow', flow_dir, flow_prob, 1)]:
                if d == 'PUT':
                    aligned += 1
        else:
            return None
        
        # Composite probability
        composite = (
            ai_prob * self.WEIGHTS['ai'] +
            tech_prob * self.WEIGHTS['tech'] +
            flow_prob * self.WEIGHTS['flow'] +
            time_prob * self.WEIGHTS['time'] +
            regime_prob * self.WEIGHTS['regime']
        )
        
        # Adjust by alignment
        if aligned >= 3:
            composite *= 1.15
        elif aligned == 2:
            composite *= 1.05
        
        # Adjust by regime
        if regime == 'LOW_VOL' and final_dir == 'CALL':
            composite *= 1.05
        elif regime == 'HIGH' and final_dir == 'PUT':
            composite *= 1.05
        
        # Calculate targets
        if final_dir == 'CALL':
            target = price + (atr * 2.5)
            stop = price - (atr * 1.0)
        else:
            target = price - (atr * 2.5)
            stop = price + (atr * 1.0)
        
        reasons.append(f"Regime: {regime} (VIX: {self.last_vix:.1f})")
        reasons.append(f"Aligned: {aligned}/3")
        
        return Signal(
            symbol=symbol,
            direction=final_dir,
            probability=round(min(composite, 85), 1),
            confidence=round(aligned / 3 * 100, 0),
            entry=round(price, 2),
            target=round(target, 2),
            stop=round(stop, 2),
            ai_prob=round(ai_prob, 1),
            tech_prob=round(tech_prob, 1),
            flow_prob=round(flow_prob, 1),
            time_prob=round(time_prob, 1),
            regime_prob=round(regime_prob, 1),
            signals_aligned=aligned,
            total_signals=total,
            factors=factors,
            reasons=reasons
        )
    
    async def send_telegram(self, message: str):
        """Send Telegram alert"""
        if not self.tg_token or not self.tg_chat:
            return
        
        try:
            url = f"https://api.telegram.org/bot{self.tg_token}/sendMessage"
            async with aiohttp.ClientSession() as session:
                await session.post(url, json={
                    'chat_id': self.tg_chat,
                    'text': message,
                    'parse_mode': 'HTML'
                })
        except:
            pass
    
    def format_alert(self, signal: Signal) -> str:
        """Format signal for Telegram"""
        pct_target = (signal.target - signal.entry) / signal.entry * 100
        pct_stop = (signal.stop - signal.entry) / signal.entry * 100
        
        return f"""
<b>BEAST SIGNAL: {signal.symbol} {signal.direction}</b>

<b>PROBABILIDAD: {signal.probability}%</b>
Confianza: {signal.confidence}%
Senales alineadas: {signal.signals_aligned}/{signal.total_signals}

<b>DESGLOSE:</b>
- AI Model: {signal.ai_prob}%
- Tecnicos: {signal.tech_prob}%
- Flow: {signal.flow_prob}%
- Tiempo: {signal.time_prob}%
- Regimen: {signal.regime_prob}%

<b>SETUP:</b>
- Entry: ${signal.entry}
- Target: ${signal.target} ({pct_target:+.1f}%)
- Stop: ${signal.stop} ({pct_stop:+.1f}%)

<b>FACTORES:</b>
{chr(10).join([f'- {k}: {v}' for k, v in list(signal.factors.items())[:6]])}

{datetime.now().strftime('%H:%M:%S')}
"""
    
    async def scan_market(self) -> List[Signal]:
        """Scan all symbols"""
        signals = []
        
        for symbol in self.UNIVERSE:
            try:
                signal = await self.analyze_symbol(symbol)
                
                if signal and signal.probability >= self.MIN_PROBABILITY:
                    if signal.signals_aligned >= self.MIN_SIGNALS_ALIGNED - 1:
                        signals.append(signal)
                        
            except Exception as e:
                continue
        
        signals.sort(key=lambda s: s.probability, reverse=True)
        return signals
    
    async def run_once(self):
        """Run one scan cycle"""
        now = datetime.now()
        
        self._log(f"[SCAN] Iniciando scan de {len(self.UNIVERSE)} simbolos...")
        
        signals = await self.scan_market()
        
        self._log(f"[SCAN] Encontradas {len(signals)} senales con prob >= {self.MIN_PROBABILITY}%")
        
        # Alert top signals
        for signal in signals[:3]:
            self._log(f"  [{signal.symbol}] {signal.direction}: {signal.probability}% | "
                     f"Aligned: {signal.signals_aligned}")
            
            # Send Telegram for high probability
            if signal.probability >= 62 and signal.signals_aligned >= 3:
                alert = self.format_alert(signal)
                await self.send_telegram(alert)
                self.alerts_sent += 1
                self._log(f"  [ALERT] Telegram enviado para {signal.symbol}")
            
            self.signals_today.append(signal)
        
        return signals
    
    def is_market_open(self) -> bool:
        """Check if market is open"""
        now = datetime.now()
        
        # Weekend
        if now.weekday() >= 5:
            return False
        
        # Market hours (9:30 AM - 4:00 PM ET)
        market_open = dtime(9, 30)
        market_close = dtime(16, 0)
        current = now.time()
        
        return market_open <= current <= market_close
    
    async def run(self):
        """Main loop"""
        self._log("=" * 60)
        self._log("    BEAST LIVE - INICIANDO")
        self._log(f"    Intervalo: {self.SCAN_INTERVAL}s")
        self._log(f"    Min Prob: {self.MIN_PROBABILITY}%")
        self._log(f"    Min Aligned: {self.MIN_SIGNALS_ALIGNED}")
        self._log("=" * 60)
        
        # Send startup message
        await self.send_telegram(f"""
<b>BEAST LIVE INICIADO</b>

Escaneando: {len(self.UNIVERSE)} simbolos
Intervalo: {self.SCAN_INTERVAL} segundos
Min Probabilidad: {self.MIN_PROBABILITY}%

<b>ESPERANDO MERCADO...</b>
""")
        
        while True:
            try:
                if self.is_market_open():
                    await self.run_once()
                    await asyncio.sleep(self.SCAN_INTERVAL)
                else:
                    now = datetime.now()
                    
                    # Before market
                    if now.time() < dtime(9, 30):
                        wait = (datetime.combine(now.date(), dtime(9, 30)) - now).seconds
                        self._log(f"[WAIT] Mercado abre en {wait//60} minutos")
                        
                        if wait <= 300:  # 5 min before open
                            await self.send_telegram("<b>MERCADO ABRE EN 5 MINUTOS</b>\nBEAST LISTO")
                        
                        await asyncio.sleep(min(wait, 60))
                    else:
                        # After close
                        self._log(f"[CLOSE] Mercado cerrado. Alertas hoy: {self.alerts_sent}")
                        
                        # Summary
                        if self.signals_today:
                            summary = f"""
<b>RESUMEN DEL DIA</b>

Scans realizados: {len(self.signals_today)}
Alertas enviadas: {self.alerts_sent}

Top senales:
"""
                            for s in sorted(self.signals_today, key=lambda x: x.probability, reverse=True)[:5]:
                                summary += f"- {s.symbol} {s.direction}: {s.probability}%\n"
                            
                            await self.send_telegram(summary)
                            self.signals_today = []
                            self.alerts_sent = 0
                        
                        # Wait until tomorrow
                        await asyncio.sleep(3600)
                        
            except KeyboardInterrupt:
                self._log("[STOP] Detenido por usuario")
                break
            except Exception as e:
                self._log(f"[ERROR] {e}")
                await asyncio.sleep(30)


async def main():
    print("""
    ================================================================
    |                                                              |
    |    BEAST LIVE - SISTEMA COMPLETO                            |
    |    Corriendo todo el dia, calculando probabilidades         |
    |                                                              |
    ================================================================
    """)
    
    if not os.path.exists("config.yaml"):
        print("[ERROR] config.yaml no encontrado")
        return
    
    with open("config.yaml", 'r') as f:
        config = yaml.safe_load(f)
    
    beast = BeastLive(config)
    await beast.run()


if __name__ == "__main__":
    asyncio.run(main())
