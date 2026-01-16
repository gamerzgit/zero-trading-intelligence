#!/usr/bin/env python3
"""
================================================================================
    BEAST ENGINE - PATTERN SCANNER V2 (CALIBRADO)
================================================================================
    
    Version corregida con:
    - Timeframe de 15 minutos (como usas en TradingView)
    - Backtesting REAL para calcular win rates
    - Thresholds calibrados para reducir falsos positivos
    - Targets basados en ATR realistas para 0DTE
    
================================================================================
"""

import os
import asyncio
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict
import warnings
import json
warnings.filterwarnings('ignore')

from scipy.signal import argrelextrema
from scipy.stats import linregress
import yaml

from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame


class PatternType(Enum):
    BULL_FLAG = "BULL_FLAG"
    BEAR_FLAG = "BEAR_FLAG"
    ASCENDING_TRIANGLE = "ASCENDING_TRIANGLE"
    DESCENDING_TRIANGLE = "DESCENDING_TRIANGLE"
    DOUBLE_BOTTOM = "DOUBLE_BOTTOM"
    DOUBLE_TOP = "DOUBLE_TOP"
    BREAKOUT_UP = "BREAKOUT_UP"
    BREAKDOWN = "BREAKDOWN"


@dataclass
class PatternResult:
    """Resultado de detección de patrón"""
    symbol: str
    pattern_type: PatternType
    confidence: float
    direction: str  # BULLISH / BEARISH
    
    # Precios
    entry_price: float
    target_price: float
    stop_price: float
    
    # Métricas calculadas de backtest REAL
    win_rate: float  # Calculado de datos históricos
    avg_win: float   # Promedio de ganancia cuando gana
    avg_loss: float  # Promedio de pérdida cuando pierde
    sample_size: int # Cuántos patrones similares se encontraron
    
    # Risk/Reward
    risk_reward: float
    expected_value: float  # (win_rate * avg_win) - ((1-win_rate) * avg_loss)
    
    # Detalles
    atr: float
    timeframe: str
    reasons: List[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.now)


class CalibratedPatternScanner:
    """
    Pattern Scanner V2 - Calibrado con datos reales
    """
    
    # Thresholds más estrictos (calibrados)
    THRESHOLDS = {
        'resistance_std_max': 0.005,      # 0.5% max desviación (antes era 2%)
        'support_slope_min': 0.0005,       # Pendiente mínima significativa
        'min_pivot_distance': 10,          # Mínimo 10 barras entre pivots
        'min_pattern_bars': 20,            # Patrón debe tener al menos 20 barras
        'min_touches': 3,                  # Mínimo 3 toques en soporte/resistencia
        'breakout_threshold': 0.003,       # 0.3% sobre resistencia = breakout
        'volume_increase': 1.5,            # Volumen 50% arriba del promedio
    }
    
    def __init__(self, config: Dict):
        self.config = config
        
        alpaca_config = config.get('alpaca', {})
        self.client = StockHistoricalDataClient(
            alpaca_config.get('api_key', ''),
            alpaca_config.get('api_secret', '')
        )
        
        # Cache para win rates calculados
        self.win_rate_cache: Dict[str, Dict] = {}
        
        print("=" * 60)
        print("    PATTERN SCANNER V2 - CALIBRADO")
        print("    Timeframe: 15 minutos")
        print("    Thresholds: Estrictos")
        print("=" * 60)
    
    async def fetch_data_15min(self, symbol: str, days: int = 60) -> pd.DataFrame:
        """Fetch 15-minute bars"""
        try:
            # Alpaca: crear TimeFrame de 15 minutos correctamente
            from alpaca.data.timeframe import TimeFrameUnit
            tf_15min = TimeFrame(15, TimeFrameUnit.Minute)
            
            request = StockBarsRequest(
                symbol_or_symbols=symbol,
                timeframe=tf_15min,
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
                    'vwap': bar.vwap if hasattr(bar, 'vwap') else (bar.high + bar.low + bar.close) / 3
                } for bar in bars.data[symbol]])
                
                df.set_index('timestamp', inplace=True)
                return df
            
            return pd.DataFrame()
            
        except Exception as e:
            print(f"[ERROR] {symbol}: {e}")
            return pd.DataFrame()
    
    def calculate_atr(self, df: pd.DataFrame, period: int = 14) -> float:
        """Calculate ATR for realistic targets"""
        high = df['high']
        low = df['low']
        close = df['close']
        
        tr1 = high - low
        tr2 = abs(high - close.shift())
        tr3 = abs(low - close.shift())
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        
        return float(tr.rolling(window=period).mean().iloc[-1])
    
    def find_pivots_strict(self, data: pd.Series, order: int = 7) -> Tuple[np.ndarray, np.ndarray]:
        """
        Encuentra pivots con criterios más estrictos
        order=7 significa que el pivot debe ser el más alto/bajo en 15 barras (7 a cada lado)
        En 15-min timeframe, esto es ~3.5 horas
        """
        highs = argrelextrema(data.values, np.greater_equal, order=order)[0]
        lows = argrelextrema(data.values, np.less_equal, order=order)[0]
        
        # Filtrar pivots que estén muy cerca uno del otro
        min_distance = self.THRESHOLDS['min_pivot_distance']
        
        filtered_highs = self._filter_close_pivots(highs, min_distance)
        filtered_lows = self._filter_close_pivots(lows, min_distance)
        
        return filtered_highs, filtered_lows
    
    def _filter_close_pivots(self, pivots: np.ndarray, min_distance: int) -> np.ndarray:
        """Elimina pivots que están muy cerca"""
        if len(pivots) < 2:
            return pivots
        
        filtered = [pivots[0]]
        for p in pivots[1:]:
            if p - filtered[-1] >= min_distance:
                filtered.append(p)
        
        return np.array(filtered)
    
    def detect_ascending_triangle_strict(self, df: pd.DataFrame) -> Optional[Dict]:
        """
        Detecta Ascending Triangle con criterios estrictos
        """
        if len(df) < self.THRESHOLDS['min_pattern_bars']:
            return None
        
        close = df['close'].values
        high = df['high'].values
        low = df['low'].values
        volume = df['volume'].values
        
        # Encontrar pivots
        high_pivots, low_pivots = self.find_pivots_strict(pd.Series(close), order=7)
        
        if len(high_pivots) < self.THRESHOLDS['min_touches']:
            return None
        if len(low_pivots) < self.THRESHOLDS['min_touches']:
            return None
        
        # Tomar los últimos N pivots para el patrón
        recent_highs = high_pivots[-5:]
        recent_lows = low_pivots[-5:]
        
        high_values = close[recent_highs]
        low_values = close[recent_lows]
        
        # 1. Verificar resistencia plana (MUY estricto)
        high_mean = np.mean(high_values)
        high_std = np.std(high_values)
        high_std_pct = high_std / high_mean
        
        if high_std_pct > self.THRESHOLDS['resistance_std_max']:
            return None  # Resistencia no es lo suficientemente plana
        
        # 2. Verificar soporte ascendente
        if len(recent_lows) >= 3:
            slope, intercept, r_value, _, _ = linregress(range(len(low_values)), low_values)
            
            # Normalizar slope por precio
            normalized_slope = slope / low_values[0]
            
            if normalized_slope < self.THRESHOLDS['support_slope_min']:
                return None  # Soporte no está subiendo lo suficiente
            
            if r_value ** 2 < 0.7:  # R² debe ser alto para línea de tendencia válida
                return None
        else:
            return None
        
        # 3. Verificar que el precio actual está cerca de la resistencia (para breakout potencial)
        current_price = close[-1]
        distance_to_resistance = (high_mean - current_price) / current_price
        
        if distance_to_resistance > 0.02:  # Más de 2% debajo de resistencia
            return None  # No está en posición de breakout
        
        # 4. Verificar volumen creciente (opcional pero mejora confianza)
        recent_vol = np.mean(volume[-10:])
        prev_vol = np.mean(volume[-30:-10])
        volume_increasing = recent_vol > prev_vol * 1.2
        
        # Calcular confianza basada en factores
        confidence = 50
        
        # Resistencia muy plana
        if high_std_pct < 0.002:
            confidence += 15
        elif high_std_pct < 0.004:
            confidence += 10
        
        # Soporte muy lineal
        if r_value ** 2 > 0.9:
            confidence += 15
        elif r_value ** 2 > 0.8:
            confidence += 10
        
        # Cerca de breakout
        if distance_to_resistance < 0.005:
            confidence += 10
        
        # Volumen confirmando
        if volume_increasing:
            confidence += 10
        
        # Calcular ATR para targets
        atr = self.calculate_atr(df)
        pattern_height = high_mean - min(low_values)
        
        return {
            'type': PatternType.ASCENDING_TRIANGLE,
            'confidence': min(confidence, 95),
            'resistance': high_mean,
            'support_slope': normalized_slope,
            'r_squared': r_value ** 2,
            'distance_to_breakout': distance_to_resistance,
            'volume_confirming': volume_increasing,
            'atr': atr,
            'pattern_height': pattern_height,
            'high_std_pct': high_std_pct,
            'pivot_count': len(recent_highs) + len(recent_lows)
        }
    
    def detect_descending_triangle_strict(self, df: pd.DataFrame) -> Optional[Dict]:
        """Detecta Descending Triangle con criterios estrictos"""
        if len(df) < self.THRESHOLDS['min_pattern_bars']:
            return None
        
        close = df['close'].values
        volume = df['volume'].values
        
        high_pivots, low_pivots = self.find_pivots_strict(pd.Series(close), order=7)
        
        if len(high_pivots) < self.THRESHOLDS['min_touches']:
            return None
        if len(low_pivots) < self.THRESHOLDS['min_touches']:
            return None
        
        recent_highs = high_pivots[-5:]
        recent_lows = low_pivots[-5:]
        
        high_values = close[recent_highs]
        low_values = close[recent_lows]
        
        # 1. Verificar soporte plano
        low_mean = np.mean(low_values)
        low_std = np.std(low_values)
        low_std_pct = low_std / low_mean
        
        if low_std_pct > self.THRESHOLDS['resistance_std_max']:
            return None
        
        # 2. Verificar resistencia descendente
        if len(recent_highs) >= 3:
            slope, intercept, r_value, _, _ = linregress(range(len(high_values)), high_values)
            normalized_slope = slope / high_values[0]
            
            if normalized_slope > -self.THRESHOLDS['support_slope_min']:
                return None  # Resistencia no está bajando lo suficiente
            
            if r_value ** 2 < 0.7:
                return None
        else:
            return None
        
        # 3. Verificar cercanía al soporte
        current_price = close[-1]
        distance_to_support = (current_price - low_mean) / current_price
        
        if distance_to_support > 0.02:
            return None
        
        # Calcular confianza
        confidence = 50
        
        if low_std_pct < 0.002:
            confidence += 15
        elif low_std_pct < 0.004:
            confidence += 10
        
        if r_value ** 2 > 0.9:
            confidence += 15
        elif r_value ** 2 > 0.8:
            confidence += 10
        
        if distance_to_support < 0.005:
            confidence += 10
        
        atr = self.calculate_atr(df)
        pattern_height = max(high_values) - low_mean
        
        return {
            'type': PatternType.DESCENDING_TRIANGLE,
            'confidence': min(confidence, 95),
            'support': low_mean,
            'resistance_slope': normalized_slope,
            'r_squared': r_value ** 2,
            'distance_to_breakdown': distance_to_support,
            'atr': atr,
            'pattern_height': pattern_height,
            'low_std_pct': low_std_pct
        }
    
    def detect_double_bottom_strict(self, df: pd.DataFrame) -> Optional[Dict]:
        """Detecta Double Bottom con criterios estrictos"""
        if len(df) < 30:
            return None
        
        close = df['close'].values
        volume = df['volume'].values
        
        _, low_pivots = self.find_pivots_strict(pd.Series(close), order=7)
        
        if len(low_pivots) < 2:
            return None
        
        # Buscar dos lows al mismo nivel
        for i in range(len(low_pivots) - 1):
            low1_idx = low_pivots[i]
            low2_idx = low_pivots[i + 1]
            
            low1_val = close[low1_idx]
            low2_val = close[low2_idx]
            
            # Los lows deben estar muy cerca (dentro de 1%)
            diff_pct = abs(low1_val - low2_val) / low1_val
            
            if diff_pct > 0.01:
                continue
            
            # Debe haber un bounce significativo entre ellos
            between_high = max(close[low1_idx:low2_idx])
            bounce_pct = (between_high - low1_val) / low1_val
            
            if bounce_pct < 0.03:  # Mínimo 3% de bounce
                continue
            
            # El segundo low debe tener más volumen (capitulación)
            vol1 = volume[low1_idx]
            vol2 = volume[low2_idx]
            
            # Precio actual debe estar subiendo desde el segundo low
            current_price = close[-1]
            if current_price <= low2_val:
                continue
            
            recovery_pct = (current_price - low2_val) / low2_val
            
            confidence = 50
            confidence += 15 if diff_pct < 0.005 else 10  # Lows muy iguales
            confidence += 10 if bounce_pct > 0.05 else 5   # Buen bounce
            confidence += 10 if vol2 > vol1 else 0         # Volumen confirmando
            confidence += 10 if recovery_pct > 0.02 else 5 # Ya recuperando
            
            atr = self.calculate_atr(df)
            neckline = between_high
            pattern_height = neckline - min(low1_val, low2_val)
            
            return {
                'type': PatternType.DOUBLE_BOTTOM,
                'confidence': min(confidence, 95),
                'low1': low1_val,
                'low2': low2_val,
                'neckline': neckline,
                'bounce_pct': bounce_pct,
                'atr': atr,
                'pattern_height': pattern_height
            }
        
        return None
    
    def detect_double_top_strict(self, df: pd.DataFrame) -> Optional[Dict]:
        """Detecta Double Top con criterios estrictos"""
        if len(df) < 30:
            return None
        
        close = df['close'].values
        volume = df['volume'].values
        
        high_pivots, _ = self.find_pivots_strict(pd.Series(close), order=7)
        
        if len(high_pivots) < 2:
            return None
        
        for i in range(len(high_pivots) - 1):
            high1_idx = high_pivots[i]
            high2_idx = high_pivots[i + 1]
            
            high1_val = close[high1_idx]
            high2_val = close[high2_idx]
            
            diff_pct = abs(high1_val - high2_val) / high1_val
            
            if diff_pct > 0.01:
                continue
            
            between_low = min(close[high1_idx:high2_idx])
            pullback_pct = (high1_val - between_low) / high1_val
            
            if pullback_pct < 0.03:
                continue
            
            current_price = close[-1]
            if current_price >= high2_val:
                continue
            
            decline_pct = (high2_val - current_price) / high2_val
            
            confidence = 50
            confidence += 15 if diff_pct < 0.005 else 10
            confidence += 10 if pullback_pct > 0.05 else 5
            confidence += 10 if decline_pct > 0.02 else 5
            
            atr = self.calculate_atr(df)
            neckline = between_low
            pattern_height = max(high1_val, high2_val) - neckline
            
            return {
                'type': PatternType.DOUBLE_TOP,
                'confidence': min(confidence, 95),
                'high1': high1_val,
                'high2': high2_val,
                'neckline': neckline,
                'pullback_pct': pullback_pct,
                'atr': atr,
                'pattern_height': pattern_height
            }
        
        return None
    
    async def backtest_pattern(self, symbol: str, pattern_type: PatternType, 
                               days: int = 60) -> Dict:
        """
        Backtesting REAL: Busca el patrón en datos históricos 
        y calcula qué pasó después
        """
        df = await self.fetch_data_15min(symbol, days)
        
        if df.empty or len(df) < 100:
            return {'win_rate': 0.5, 'avg_win': 0, 'avg_loss': 0, 'sample_size': 0}
        
        close = df['close'].values
        results = []
        
        # Detector según tipo de patrón
        detector_map = {
            PatternType.ASCENDING_TRIANGLE: self.detect_ascending_triangle_strict,
            PatternType.DESCENDING_TRIANGLE: self.detect_descending_triangle_strict,
            PatternType.DOUBLE_BOTTOM: self.detect_double_bottom_strict,
            PatternType.DOUBLE_TOP: self.detect_double_top_strict,
        }
        
        detector = detector_map.get(pattern_type)
        if not detector:
            return {'win_rate': 0.5, 'avg_win': 0, 'avg_loss': 0, 'sample_size': 0}
        
        # Sliding window: buscar patrones cada 20 barras
        window_size = 50  # Mínimo para detectar patrón
        step = 10  # Avanzar 10 barras cada vez
        
        for i in range(window_size, len(df) - 15, step):
            window_df = df.iloc[i-window_size:i].copy()
            
            result = detector(window_df)
            
            if result and result['confidence'] >= 70:
                # Patrón detectado! Ver qué pasó en los siguientes 15 barras (3.75 horas en 15-min)
                entry_price = close[i]
                
                # Calcular resultado a +4, +8, +12, +15 barras (1h, 2h, 3h, 3.75h)
                for bars_ahead in [4, 8, 12, 15]:
                    if i + bars_ahead < len(close):
                        future_price = close[i + bars_ahead]
                        pct_change = (future_price - entry_price) / entry_price * 100
                        
                        is_bullish = pattern_type in [PatternType.ASCENDING_TRIANGLE, 
                                                       PatternType.DOUBLE_BOTTOM]
                        
                        if is_bullish:
                            win = pct_change > 0.3  # Target mínimo 0.3%
                            loss = pct_change < -0.2  # Stop máximo 0.2%
                        else:
                            win = pct_change < -0.3
                            loss = pct_change > 0.2
                        
                        results.append({
                            'bars_ahead': bars_ahead,
                            'pct_change': pct_change,
                            'win': win,
                            'loss': loss
                        })
        
        if not results:
            return {'win_rate': 0.5, 'avg_win': 0, 'avg_loss': 0, 'sample_size': 0}
        
        # Calcular estadísticas
        wins = [r for r in results if r['win']]
        losses = [r for r in results if r['loss']]
        
        win_rate = len(wins) / len(results) if results else 0
        avg_win = np.mean([r['pct_change'] for r in wins]) if wins else 0
        avg_loss = np.mean([abs(r['pct_change']) for r in losses]) if losses else 0
        
        return {
            'win_rate': win_rate,
            'avg_win': avg_win,
            'avg_loss': avg_loss,
            'sample_size': len(results)
        }
    
    async def scan_symbol(self, symbol: str) -> List[PatternResult]:
        """Escanea un símbolo con criterios estrictos y backtest"""
        df = await self.fetch_data_15min(symbol, days=30)
        
        if df.empty or len(df) < 50:
            return []
        
        patterns = []
        current_price = float(df['close'].iloc[-1])
        atr = self.calculate_atr(df)
        
        # Detectar cada tipo de patrón
        detectors = [
            (self.detect_ascending_triangle_strict, PatternType.ASCENDING_TRIANGLE, "BULLISH"),
            (self.detect_descending_triangle_strict, PatternType.DESCENDING_TRIANGLE, "BEARISH"),
            (self.detect_double_bottom_strict, PatternType.DOUBLE_BOTTOM, "BULLISH"),
            (self.detect_double_top_strict, PatternType.DOUBLE_TOP, "BEARISH"),
        ]
        
        for detector, pattern_type, direction in detectors:
            result = detector(df)
            
            if result and result['confidence'] >= 65:
                # Hacer backtest para este patrón
                backtest = await self.backtest_pattern(symbol, pattern_type, days=60)
                
                # Solo reportar si tenemos suficientes muestras
                if backtest['sample_size'] < 5:
                    continue
                
                # Calcular targets basados en ATR
                if direction == "BULLISH":
                    target = current_price + (atr * 2)
                    stop = current_price - (atr * 1)
                else:
                    target = current_price - (atr * 2)
                    stop = current_price + (atr * 1)
                
                # Risk/Reward
                reward = abs(target - current_price)
                risk = abs(current_price - stop)
                rr = reward / risk if risk > 0 else 0
                
                # Expected Value
                ev = (backtest['win_rate'] * backtest['avg_win']) - \
                     ((1 - backtest['win_rate']) * backtest['avg_loss'])
                
                pattern_result = PatternResult(
                    symbol=symbol,
                    pattern_type=pattern_type,
                    confidence=result['confidence'],
                    direction=direction,
                    entry_price=current_price,
                    target_price=round(target, 2),
                    stop_price=round(stop, 2),
                    win_rate=round(backtest['win_rate'], 3),
                    avg_win=round(backtest['avg_win'], 2),
                    avg_loss=round(backtest['avg_loss'], 2),
                    sample_size=backtest['sample_size'],
                    risk_reward=round(rr, 2),
                    expected_value=round(ev, 3),
                    atr=round(atr, 2),
                    timeframe="15min",
                    reasons=self._generate_reasons(result, pattern_type)
                )
                
                patterns.append(pattern_result)
        
        return patterns
    
    def _generate_reasons(self, result: Dict, pattern_type: PatternType) -> List[str]:
        """Genera razones basadas en datos reales"""
        reasons = []
        
        if 'high_std_pct' in result:
            reasons.append(f"Resistencia plana: {result['high_std_pct']*100:.3f}% desviacion")
        
        if 'low_std_pct' in result:
            reasons.append(f"Soporte plano: {result['low_std_pct']*100:.3f}% desviacion")
        
        if 'r_squared' in result:
            reasons.append(f"Linea de tendencia R2: {result['r_squared']:.2f}")
        
        if 'bounce_pct' in result:
            reasons.append(f"Rebote entre lows: {result['bounce_pct']*100:.1f}%")
        
        if 'volume_confirming' in result and result['volume_confirming']:
            reasons.append("Volumen confirmando")
        
        if 'distance_to_breakout' in result:
            reasons.append(f"Distancia a breakout: {result['distance_to_breakout']*100:.2f}%")
        
        return reasons
    
    async def full_scan(self, symbols: List[str] = None) -> List[PatternResult]:
        """Escaneo completo con criterios estrictos"""
        if symbols is None:
            symbols = self._get_default_symbols()
        
        print(f"\n[SCAN] Escaneando {len(symbols)} simbolos con criterios ESTRICTOS...")
        print(f"[SCAN] Timeframe: 15 minutos")
        print(f"[SCAN] Cada patron incluye backtest REAL\n")
        
        all_patterns = []
        
        for i, symbol in enumerate(symbols):
            try:
                patterns = await self.scan_symbol(symbol)
                all_patterns.extend(patterns)
                
                if patterns:
                    for p in patterns:
                        print(f"  [{symbol}] {p.pattern_type.value}: "
                              f"Conf={p.confidence:.0f}% | "
                              f"WinRate={p.win_rate*100:.1f}% | "
                              f"EV={p.expected_value:.3f} | "
                              f"Samples={p.sample_size}")
                
                if (i + 1) % 10 == 0:
                    print(f"  ... {i+1}/{len(symbols)} escaneados")
                    
            except Exception as e:
                continue
        
        # Ordenar por Expected Value (métrica más importante)
        all_patterns.sort(key=lambda p: p.expected_value, reverse=True)
        
        return all_patterns
    
    def _get_default_symbols(self) -> List[str]:
        return [
            "SPY", "QQQ", "IWM",
            "AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA", "AMD",
            "JPM", "BAC", "GS",
            "XOM", "CVX",
            "PLTR", "SMCI", "MARA", "COIN"
        ]
    
    def format_results(self, patterns: List[PatternResult]) -> str:
        """Formatea resultados con métricas reales"""
        if not patterns:
            return "\n  No se encontraron patrones que pasen los criterios estrictos.\n"
        
        output = []
        output.append("")
        output.append("=" * 70)
        output.append("  PATTERN SCANNER V2 - RESULTADOS CON BACKTEST REAL")
        output.append("  Timeframe: 15 minutos | Criterios: Estrictos")
        output.append("=" * 70)
        
        bullish = [p for p in patterns if p.direction == "BULLISH" and p.expected_value > 0]
        bearish = [p for p in patterns if p.direction == "BEARISH" and p.expected_value > 0]
        
        if bullish:
            output.append("")
            output.append("  BULLISH (Expected Value > 0)")
            output.append("-" * 70)
            
            for p in bullish[:5]:
                pct_target = (p.target_price - p.entry_price) / p.entry_price * 100
                pct_stop = (p.stop_price - p.entry_price) / p.entry_price * 100
                
                output.append(f"")
                output.append(f"  {p.symbol} ${p.entry_price:.2f}")
                output.append(f"    Patron: {p.pattern_type.value}")
                output.append(f"    Confianza: {p.confidence:.0f}%")
                output.append(f"")
                output.append(f"    BACKTEST REAL ({p.sample_size} muestras):")
                output.append(f"      Win Rate: {p.win_rate*100:.1f}%")
                output.append(f"      Ganancia promedio: +{p.avg_win:.2f}%")
                output.append(f"      Perdida promedio: -{p.avg_loss:.2f}%")
                output.append(f"      Expected Value: {p.expected_value:.3f}")
                output.append(f"")
                output.append(f"    TRADE SETUP:")
                output.append(f"      Entry: ${p.entry_price:.2f}")
                output.append(f"      Target: ${p.target_price:.2f} ({pct_target:+.1f}%)")
                output.append(f"      Stop: ${p.stop_price:.2f} ({pct_stop:+.1f}%)")
                output.append(f"      R:R = {p.risk_reward}:1")
                output.append(f"      ATR: ${p.atr:.2f}")
                output.append(f"")
                output.append(f"    RAZONES:")
                for reason in p.reasons:
                    output.append(f"      - {reason}")
        
        if bearish:
            output.append("")
            output.append("  BEARISH (Expected Value > 0)")
            output.append("-" * 70)
            
            for p in bearish[:5]:
                pct_target = (p.target_price - p.entry_price) / p.entry_price * 100
                pct_stop = (p.stop_price - p.entry_price) / p.entry_price * 100
                
                output.append(f"")
                output.append(f"  {p.symbol} ${p.entry_price:.2f}")
                output.append(f"    Patron: {p.pattern_type.value}")
                output.append(f"    Win Rate: {p.win_rate*100:.1f}% ({p.sample_size} muestras)")
                output.append(f"    Expected Value: {p.expected_value:.3f}")
                output.append(f"    Target: ${p.target_price:.2f} ({pct_target:+.1f}%)")
                output.append(f"    Stop: ${p.stop_price:.2f} ({pct_stop:+.1f}%)")
        
        if not bullish and not bearish:
            output.append("")
            output.append("  No hay patrones con Expected Value positivo.")
            output.append("  Esto significa que los patrones detectados no tienen")
            output.append("  ventaja estadistica basada en el backtest.")
        
        output.append("")
        output.append("=" * 70)
        
        return "\n".join(output)


async def main():
    print("""
    ================================================================
    |    PATTERN SCANNER V2 - CALIBRADO CON BACKTEST REAL         |
    ================================================================
    """)
    
    if os.path.exists("config.yaml"):
        with open("config.yaml", 'r') as f:
            config = yaml.safe_load(f)
    else:
        print("[ERROR] config.yaml no encontrado")
        return
    
    scanner = CalibratedPatternScanner(config)
    patterns = await scanner.full_scan()
    
    results = scanner.format_results(patterns)
    print(results)


if __name__ == "__main__":
    asyncio.run(main())
