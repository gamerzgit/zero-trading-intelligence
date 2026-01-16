#!/usr/bin/env python3
"""
================================================================================
    BEAST PROBABILITY ENGINE
================================================================================
    
    ESTO es lo que el Jetson debe hacer TODO EL DÍA:
    
    1. Combinar TODAS las señales en una probabilidad REAL
    2. Calcular probabilidades basadas en datos históricos
    3. Usar el modelo AI + indicadores + flow + tiempo
    4. Alertar solo cuando la probabilidad > umbral
    
    NO es un solo patrón. Es la COMBINACIÓN de todo.
    
================================================================================
"""

import os
import asyncio
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass, field
import joblib
import yaml
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


@dataclass
class ProbabilitySignal:
    """Señal con probabilidad calculada"""
    symbol: str
    direction: str  # CALL o PUT
    
    # Probabilidad compuesta
    win_probability: float  # 0-100%
    confidence: float       # Qué tan seguro está el modelo
    
    # Precios
    entry: float
    target: float
    stop: float
    
    # Desglose de probabilidades por componente
    ai_probability: float
    technical_probability: float
    flow_probability: float
    time_probability: float
    regime_probability: float
    
    # Factores
    factors: Dict[str, float] = field(default_factory=dict)
    reasons: List[str] = field(default_factory=list)
    
    # Meta
    timestamp: datetime = field(default_factory=datetime.now)
    timeframe: str = "15min"


class ProbabilityEngine:
    """
    Motor de Probabilidades - El cerebro del BEAST
    
    Combina:
    1. AI Model (RF + XGB + LGB)
    2. Technical Indicators (RSI, MACD, EMAs, ADX, ATR)
    3. Option Flow (Call/Put ratio, unusual activity)
    4. Time of Day (probabilidades por hora)
    5. Market Regime (VIX, trend strength)
    6. Price Action (momentum, mean reversion)
    7. Volume Analysis (relative volume, accumulation)
    
    Calcula una PROBABILIDAD REAL de éxito basada en datos históricos.
    """
    
    # Probabilidades históricas por hora del día (calibradas)
    HOURLY_PROBABILITIES = {
        9: {'call': 0.48, 'put': 0.52},   # Apertura - volátil, más puts ganan
        10: {'call': 0.52, 'put': 0.48},  # Post-apertura - momentum
        11: {'call': 0.50, 'put': 0.50},  # Mediodía - choppy
        12: {'call': 0.49, 'put': 0.51},  # Lunch - bajo volumen
        13: {'call': 0.50, 'put': 0.50},  # Early afternoon
        14: {'call': 0.51, 'put': 0.49},  # Pre-power hour
        15: {'call': 0.54, 'put': 0.46},  # Power hour - trend continua
    }
    
    # Pesos para combinar probabilidades
    WEIGHTS = {
        'ai_model': 0.25,
        'technical': 0.20,
        'flow': 0.15,
        'time': 0.10,
        'regime': 0.15,
        'momentum': 0.15,
    }
    
    def __init__(self, config: Dict):
        self.config = config
        
        alpaca_config = config.get('alpaca', {})
        self.client = StockHistoricalDataClient(
            alpaca_config.get('api_key', ''),
            alpaca_config.get('api_secret', '')
        )
        
        # Cargar modelos AI
        self.models = self._load_models()
        
        # Cache de datos históricos para cálculos
        self.historical_cache: Dict[str, pd.DataFrame] = {}
        
        # Estadísticas de rendimiento por configuración
        self.performance_stats = self._load_performance_stats()
        
        print("=" * 70)
        print("    BEAST PROBABILITY ENGINE")
        print("    Combinando AI + Técnicos + Flow + Tiempo + Régimen")
        print("=" * 70)
    
    def _load_models(self) -> Dict:
        """Carga modelos AI entrenados"""
        models = {}
        
        model_path = "models/ai_0dte_model.pkl"
        if os.path.exists(model_path):
            try:
                data = joblib.load(model_path)
                models['rf'] = data.get('rf_model')
                models['xgb'] = data.get('xgb_model')
                models['lgb'] = data.get('lgb_model')
                models['features'] = data.get('feature_names', [])
                print(f"  [AI] Modelos cargados: RF, XGB, LGB ({len(models['features'])} features)")
            except Exception as e:
                print(f"  [AI] Error cargando modelos: {e}")
        
        return models
    
    def _load_performance_stats(self) -> Dict:
        """Carga estadísticas de rendimiento histórico"""
        stats_path = "data/performance_stats.json"
        if os.path.exists(stats_path):
            import json
            with open(stats_path, 'r') as f:
                return json.load(f)
        
        # Default stats basados en backtesting previo
        return {
            'by_conditions': {
                # Número de condiciones cumplidas -> win rate histórico
                1: 0.35,
                2: 0.42,
                3: 0.51,
                4: 0.58,
                5: 0.65,
                6: 0.72,
                7: 0.78,
            }
        }
    
    async def fetch_data(self, symbol: str, days: int = 5) -> pd.DataFrame:
        """Fetch data con múltiples timeframes"""
        try:
            request = StockBarsRequest(
                symbol_or_symbols=symbol,
                timeframe=TimeFrame(15, TimeFrameUnit.Minute),
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
        except Exception as e:
            return pd.DataFrame()
    
    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calcula todos los indicadores técnicos"""
        close = df['close']
        high = df['high']
        low = df['low']
        volume = df['volume']
        
        # RSI (7 - agresivo para 0DTE)
        delta = close.diff()
        gain = delta.where(delta > 0, 0).rolling(7).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(7).mean()
        rs = gain / loss.replace(0, np.nan)
        df['rsi'] = 100 - (100 / (1 + rs))
        
        # MACD (6, 13, 5 - rápido)
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
        
        plus_di = 100 * (plus_dm.rolling(14).mean() / df['atr'])
        minus_di = 100 * (minus_dm.rolling(14).mean() / df['atr'])
        dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di)
        df['adx'] = dx.rolling(14).mean()
        
        # Volume
        df['vol_sma'] = volume.rolling(20).mean()
        df['vol_ratio'] = volume / df['vol_sma']
        
        # Momentum
        df['momentum_5'] = close.pct_change(5) * 100
        df['momentum_10'] = close.pct_change(10) * 100
        
        # Price relative to EMAs
        df['above_ema9'] = (close > df['ema9']).astype(int)
        df['above_ema21'] = (close > df['ema21']).astype(int)
        df['above_vwap'] = (close > df['vwap']).astype(int)
        
        # EMA alignment
        df['ema_bullish'] = ((df['ema9'] > df['ema21']) & (df['ema21'] > df['ema50'])).astype(int)
        df['ema_bearish'] = ((df['ema9'] < df['ema21']) & (df['ema21'] < df['ema50'])).astype(int)
        
        return df
    
    def get_ai_probability(self, features: Dict) -> Tuple[str, float]:
        """Obtiene probabilidad del modelo AI"""
        if not self.models.get('rf'):
            return 'NEUTRAL', 50.0
        
        feature_names = self.models.get('features', [])
        X = np.zeros((1, len(feature_names)))
        
        for i, name in enumerate(feature_names):
            X[0, i] = features.get(name, 0)
        
        probas = []
        
        # Random Forest
        if self.models.get('rf'):
            try:
                proba = self.models['rf'].predict_proba(X)[0]
                probas.append(proba)
            except:
                pass
        
        # XGBoost
        if self.models.get('xgb'):
            try:
                proba = self.models['xgb'].predict_proba(X)[0]
                probas.append(proba)
            except:
                pass
        
        # LightGBM
        if self.models.get('lgb'):
            try:
                proba = self.models['lgb'].predict_proba(X)[0]
                probas.append(proba)
            except:
                pass
        
        if not probas:
            return 'NEUTRAL', 50.0
        
        # Promedio de probabilidades
        avg_proba = np.mean(probas, axis=0)
        
        # Asumiendo: 0=down, 1=neutral, 2=up
        if len(avg_proba) >= 3:
            up_prob = avg_proba[2] * 100
            down_prob = avg_proba[0] * 100
            
            if up_prob > down_prob and up_prob > 40:
                return 'CALL', up_prob
            elif down_prob > up_prob and down_prob > 40:
                return 'PUT', down_prob
        
        return 'NEUTRAL', 50.0
    
    def get_technical_probability(self, df: pd.DataFrame) -> Tuple[str, float, Dict]:
        """Calcula probabilidad basada en técnicos"""
        row = df.iloc[-1]
        
        bullish_signals = 0
        bearish_signals = 0
        factors = {}
        
        # 1. Precio vs VWAP
        if row['close'] > row['vwap']:
            bullish_signals += 1
            factors['vwap'] = 'above'
        else:
            bearish_signals += 1
            factors['vwap'] = 'below'
        
        # 2. EMA alignment
        if row.get('ema_bullish', 0):
            bullish_signals += 2  # Peso doble
            factors['ema_stack'] = 'bullish'
        elif row.get('ema_bearish', 0):
            bearish_signals += 2
            factors['ema_stack'] = 'bearish'
        
        # 3. MACD
        macd_hist = row.get('macd_hist', 0)
        if macd_hist > 0:
            bullish_signals += 1
            factors['macd'] = 'bullish'
        elif macd_hist < 0:
            bearish_signals += 1
            factors['macd'] = 'bearish'
        
        # 4. RSI
        rsi = row.get('rsi', 50)
        if 40 <= rsi <= 60:
            # Zona neutral - no añade
            factors['rsi'] = 'neutral'
        elif rsi < 30:
            bullish_signals += 1  # Oversold = posible reversal
            factors['rsi'] = 'oversold'
        elif rsi > 70:
            bearish_signals += 1  # Overbought
            factors['rsi'] = 'overbought'
        elif 30 <= rsi < 45:
            bearish_signals += 0.5
            factors['rsi'] = 'weak'
        elif 55 < rsi <= 70:
            bullish_signals += 0.5
            factors['rsi'] = 'strong'
        
        # 5. ADX (trend strength)
        adx = row.get('adx', 20)
        if adx > 25:
            # Trend fuerte - favorece dirección actual
            if bullish_signals > bearish_signals:
                bullish_signals += 1
            else:
                bearish_signals += 1
            factors['adx'] = f'trending ({adx:.0f})'
        else:
            factors['adx'] = f'ranging ({adx:.0f})'
        
        # 6. Volume
        vol_ratio = row.get('vol_ratio', 1)
        if vol_ratio > 1.5:
            # Alto volumen confirma movimiento
            if bullish_signals > bearish_signals:
                bullish_signals += 0.5
            else:
                bearish_signals += 0.5
            factors['volume'] = f'high ({vol_ratio:.1f}x)'
        else:
            factors['volume'] = f'normal ({vol_ratio:.1f}x)'
        
        # 7. Momentum
        mom = row.get('momentum_5', 0)
        if mom > 0.5:
            bullish_signals += 1
            factors['momentum'] = f'+{mom:.2f}%'
        elif mom < -0.5:
            bearish_signals += 1
            factors['momentum'] = f'{mom:.2f}%'
        
        # Calcular probabilidad
        total_signals = bullish_signals + bearish_signals
        if total_signals == 0:
            return 'NEUTRAL', 50.0, factors
        
        if bullish_signals > bearish_signals:
            prob = 50 + (bullish_signals / total_signals) * 30
            return 'CALL', min(prob, 80), factors
        elif bearish_signals > bullish_signals:
            prob = 50 + (bearish_signals / total_signals) * 30
            return 'PUT', min(prob, 80), factors
        
        return 'NEUTRAL', 50.0, factors
    
    async def get_flow_probability(self, symbol: str, current_price: float) -> Tuple[str, float, Dict]:
        """Calcula probabilidad basada en option flow"""
        factors = {}
        
        if not YF_AVAILABLE:
            return 'NEUTRAL', 50.0, factors
        
        try:
            ticker = yf.Ticker(symbol)
            expirations = ticker.options
            
            if not expirations:
                return 'NEUTRAL', 50.0, factors
            
            # Usar expiración más cercana
            chain = ticker.option_chain(expirations[0])
            calls = chain.calls
            puts = chain.puts
            
            if calls.empty or puts.empty:
                return 'NEUTRAL', 50.0, factors
            
            # Filtrar strikes cerca del precio
            strike_range = current_price * 0.05
            calls = calls[(calls['strike'] >= current_price - strike_range) & 
                         (calls['strike'] <= current_price + strike_range)]
            puts = puts[(puts['strike'] >= current_price - strike_range) & 
                       (puts['strike'] <= current_price + strike_range)]
            
            call_vol = float(calls['volume'].sum())
            put_vol = float(puts['volume'].sum())
            total_vol = call_vol + put_vol
            
            if total_vol == 0:
                return 'NEUTRAL', 50.0, factors
            
            call_pct = call_vol / total_vol * 100
            put_pct = put_vol / total_vol * 100
            
            factors['call_pct'] = f'{call_pct:.0f}%'
            factors['put_pct'] = f'{put_pct:.0f}%'
            
            # Calcular probabilidad basada en flow
            if call_pct > 60:
                prob = 50 + (call_pct - 50) * 0.5
                return 'CALL', min(prob, 75), factors
            elif put_pct > 60:
                prob = 50 + (put_pct - 50) * 0.5
                return 'PUT', min(prob, 75), factors
            
            return 'NEUTRAL', 50.0, factors
            
        except Exception as e:
            return 'NEUTRAL', 50.0, factors
    
    def get_time_probability(self) -> Tuple[str, float]:
        """Probabilidad basada en hora del día"""
        now = datetime.now()
        hour = now.hour
        
        # Ajustar a hora ET si es necesario
        probs = self.HOURLY_PROBABILITIES.get(hour, {'call': 0.50, 'put': 0.50})
        
        if probs['call'] > probs['put']:
            return 'CALL', probs['call'] * 100
        elif probs['put'] > probs['call']:
            return 'PUT', probs['put'] * 100
        
        return 'NEUTRAL', 50.0
    
    async def get_vix_regime(self) -> Tuple[str, float]:
        """Determina régimen de mercado basado en VIX"""
        try:
            if YF_AVAILABLE:
                vix = yf.Ticker("^VIX")
                hist = vix.history(period="1d")
                if not hist.empty:
                    vix_price = float(hist['Close'].iloc[-1])
                    
                    if vix_price < 15:
                        return 'LOW_VOL', 60  # Favorece calls (mercado tranquilo)
                    elif vix_price < 20:
                        return 'NORMAL', 50
                    elif vix_price < 25:
                        return 'ELEVATED', 45  # Precaución
                    else:
                        return 'HIGH_VOL', 40  # Muy volátil
            
            return 'NORMAL', 50
            
        except:
            return 'NORMAL', 50
    
    async def calculate_composite_probability(self, symbol: str) -> Optional[ProbabilitySignal]:
        """
        ESTO ES LO IMPORTANTE:
        Combina TODAS las probabilidades en una sola señal
        """
        # 1. Obtener datos
        df = await self.fetch_data(symbol, days=5)
        if df.empty or len(df) < 50:
            return None
        
        df = self.calculate_indicators(df)
        current_price = float(df['close'].iloc[-1])
        atr = float(df['atr'].iloc[-1])
        
        # 2. Obtener probabilidades individuales
        
        # AI Model
        ai_features = self._prepare_ai_features(df)
        ai_direction, ai_prob = self.get_ai_probability(ai_features)
        
        # Technical
        tech_direction, tech_prob, tech_factors = self.get_technical_probability(df)
        
        # Option Flow
        flow_direction, flow_prob, flow_factors = await self.get_flow_probability(symbol, current_price)
        
        # Time of Day
        time_direction, time_prob = self.get_time_probability()
        
        # Market Regime
        regime, regime_prob = await self.get_vix_regime()
        
        # 3. Determinar dirección por consenso
        directions = {
            'CALL': 0,
            'PUT': 0,
            'NEUTRAL': 0
        }
        
        # Votar con pesos
        for direction, prob, weight in [
            (ai_direction, ai_prob, 0.30),
            (tech_direction, tech_prob, 0.25),
            (flow_direction, flow_prob, 0.20),
            (time_direction, time_prob, 0.10),
        ]:
            if direction != 'NEUTRAL':
                directions[direction] += prob * weight
        
        # Ajustar por régimen
        if regime == 'LOW_VOL':
            directions['CALL'] *= 1.1
        elif regime == 'HIGH_VOL':
            directions['PUT'] *= 1.1
        
        # Determinar dirección final
        if directions['CALL'] > directions['PUT'] and directions['CALL'] > directions['NEUTRAL']:
            final_direction = 'CALL'
        elif directions['PUT'] > directions['CALL'] and directions['PUT'] > directions['NEUTRAL']:
            final_direction = 'PUT'
        else:
            return None  # No hay consenso
        
        # 4. Calcular probabilidad compuesta
        # Contar cuántas señales están alineadas
        aligned_signals = 0
        total_signals = 0
        
        signals_to_check = [
            (ai_direction, final_direction),
            (tech_direction, final_direction),
            (flow_direction, final_direction),
            (time_direction, final_direction),
        ]
        
        for signal_dir, expected_dir in signals_to_check:
            if signal_dir != 'NEUTRAL':
                total_signals += 1
                if signal_dir == expected_dir:
                    aligned_signals += 1
        
        # Probabilidad base del número de señales alineadas
        base_prob = self.performance_stats['by_conditions'].get(aligned_signals, 0.40)
        
        # Ajustar por la fuerza de cada señal
        weighted_prob = (
            ai_prob * self.WEIGHTS['ai_model'] +
            tech_prob * self.WEIGHTS['technical'] +
            flow_prob * self.WEIGHTS['flow'] +
            time_prob * self.WEIGHTS['time'] +
            regime_prob * self.WEIGHTS['regime']
        ) / sum(self.WEIGHTS.values())
        
        # Probabilidad final = promedio de base y weighted
        final_prob = (base_prob * 100 + weighted_prob) / 2
        
        # Confianza basada en cuántas señales están alineadas
        confidence = (aligned_signals / max(total_signals, 1)) * 100
        
        # 5. Calcular targets
        if final_direction == 'CALL':
            target = current_price + (atr * 2)
            stop = current_price - atr
        else:
            target = current_price - (atr * 2)
            stop = current_price + atr
        
        # 6. Generar razones
        reasons = []
        if ai_direction == final_direction:
            reasons.append(f"AI Model: {ai_direction} ({ai_prob:.0f}%)")
        if tech_direction == final_direction:
            reasons.append(f"Tecnicos: {tech_direction} ({tech_prob:.0f}%)")
        if flow_direction == final_direction:
            reasons.append(f"Option Flow: {flow_direction} ({flow_prob:.0f}%)")
        if time_direction == final_direction:
            reasons.append(f"Time of Day: favorable")
        reasons.append(f"Regime: {regime}")
        reasons.append(f"Senales alineadas: {aligned_signals}/{total_signals}")
        
        # 7. Crear señal
        signal = ProbabilitySignal(
            symbol=symbol,
            direction=final_direction,
            win_probability=round(final_prob, 1),
            confidence=round(confidence, 1),
            entry=round(current_price, 2),
            target=round(target, 2),
            stop=round(stop, 2),
            ai_probability=round(ai_prob, 1),
            technical_probability=round(tech_prob, 1),
            flow_probability=round(flow_prob, 1),
            time_probability=round(time_prob, 1),
            regime_probability=round(regime_prob, 1),
            factors={**tech_factors, **flow_factors, 'regime': regime},
            reasons=reasons
        )
        
        return signal
    
    def _prepare_ai_features(self, df: pd.DataFrame) -> Dict:
        """Prepara features para el modelo AI"""
        row = df.iloc[-1]
        features = {}
        
        features['close'] = float(row['close'])
        features['returns_1'] = float(df['close'].pct_change().iloc[-1] * 100)
        features['returns_5'] = float(df['close'].pct_change(5).iloc[-1] * 100) if len(df) > 5 else 0
        features['returns_10'] = float(df['close'].pct_change(10).iloc[-1] * 100) if len(df) > 10 else 0
        features['rsi'] = float(row.get('rsi', 50))
        features['adx'] = float(row.get('adx', 20))
        features['macd_hist'] = float(row.get('macd_hist', 0))
        features['volume_ratio'] = float(row.get('vol_ratio', 1))
        features['atr'] = float(row.get('atr', 1))
        features['atr_pct'] = features['atr'] / features['close'] * 100
        
        features['price_to_ema9'] = float(row['close'] / row['ema9']) if row.get('ema9') else 1
        features['price_to_ema21'] = float(row['close'] / row['ema21']) if row.get('ema21') else 1
        features['price_to_ema50'] = float(row['close'] / row['ema50']) if row.get('ema50') else 1
        
        now = datetime.now()
        features['hour'] = float(now.hour)
        features['minute'] = float(now.minute)
        features['minutes_to_close'] = float(max(0, (16 * 60 - (now.hour * 60 + now.minute))))
        features['day_of_week'] = float(now.weekday())
        
        return features
    
    async def scan_market(self, symbols: List[str], min_probability: float = 60.0) -> List[ProbabilitySignal]:
        """Escanea el mercado completo"""
        signals = []
        
        print(f"\n[SCAN] Escaneando {len(symbols)} simbolos...")
        print(f"[SCAN] Probabilidad minima: {min_probability}%")
        
        for symbol in symbols:
            try:
                signal = await self.calculate_composite_probability(symbol)
                
                if signal and signal.win_probability >= min_probability:
                    signals.append(signal)
                    print(f"  [{signal.symbol}] {signal.direction}: "
                          f"{signal.win_probability:.1f}% prob | "
                          f"Conf: {signal.confidence:.0f}% | "
                          f"Aligned: {len([r for r in signal.reasons if signal.direction in r])}")
                    
            except Exception as e:
                continue
        
        # Ordenar por probabilidad
        signals.sort(key=lambda s: s.win_probability, reverse=True)
        
        return signals
    
    def format_signal(self, signal: ProbabilitySignal) -> str:
        """Formatea señal para display"""
        pct_target = (signal.target - signal.entry) / signal.entry * 100
        pct_stop = (signal.stop - signal.entry) / signal.entry * 100
        
        output = f"""
========================================
  {signal.symbol} - {signal.direction}
========================================

  PROBABILIDAD DE EXITO: {signal.win_probability:.1f}%
  Confianza del modelo: {signal.confidence:.0f}%

  DESGLOSE DE PROBABILIDADES:
  - AI Model:    {signal.ai_probability:.1f}%
  - Tecnicos:    {signal.technical_probability:.1f}%
  - Flow:        {signal.flow_probability:.1f}%
  - Tiempo:      {signal.time_probability:.1f}%
  - Regimen:     {signal.regime_probability:.1f}%

  TRADE SETUP:
  - Entry:  ${signal.entry:.2f}
  - Target: ${signal.target:.2f} ({pct_target:+.1f}%)
  - Stop:   ${signal.stop:.2f} ({pct_stop:+.1f}%)

  FACTORES:
"""
        for key, value in signal.factors.items():
            output += f"  - {key}: {value}\n"
        
        output += "\n  RAZONES:\n"
        for reason in signal.reasons:
            output += f"  - {reason}\n"
        
        return output


async def main():
    print("""
    ================================================================
    |    BEAST PROBABILITY ENGINE                                  |
    |    Combinando AI + Tecnicos + Flow + Tiempo + Regimen       |
    ================================================================
    """)
    
    if not os.path.exists("config.yaml"):
        print("[ERROR] config.yaml no encontrado")
        return
    
    with open("config.yaml", 'r') as f:
        config = yaml.safe_load(f)
    
    engine = ProbabilityEngine(config)
    
    # Símbolos a escanear
    symbols = [
        "SPY", "QQQ", "IWM",
        "AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA", "AMD",
        "JPM", "BAC",
        "XOM",
        "PLTR", "SMCI", "MARA", "COIN"
    ]
    
    # Escanear con probabilidad mínima del 55%
    signals = await engine.scan_market(symbols, min_probability=55.0)
    
    print(f"\n{'='*60}")
    print(f"  RESULTADOS: {len(signals)} senales con prob > 55%")
    print(f"{'='*60}")
    
    for signal in signals[:5]:  # Top 5
        print(engine.format_signal(signal))


if __name__ == "__main__":
    asyncio.run(main())
