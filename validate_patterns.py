#!/usr/bin/env python3
"""
================================================================================
    VALIDACION HONESTA DEL PATTERN SCANNER
================================================================================
    
    Este script muestra EXACTAMENTE qué matemáticas está usando y si funcionan.
    Sin mentiras. Sin resultados falsos.
    
================================================================================
"""

import asyncio
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
import yaml

from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame
from scipy.signal import argrelextrema
from scipy.stats import linregress


def load_config():
    with open("config.yaml", 'r') as f:
        return yaml.safe_load(f)


async def fetch_data(client, symbol: str, days: int = 10) -> pd.DataFrame:
    """Fetch real data"""
    try:
        request = StockBarsRequest(
            symbol_or_symbols=symbol,
            timeframe=TimeFrame.Minute,
            start=datetime.now() - timedelta(days=days)
        )
        bars = client.get_stock_bars(request)
        
        if symbol in bars.data:
            df = pd.DataFrame([{
                'timestamp': bar.timestamp,
                'open': bar.open,
                'high': bar.high,
                'low': bar.low,
                'close': bar.close,
                'volume': bar.volume,
            } for bar in bars.data[symbol]])
            df.set_index('timestamp', inplace=True)
            return df
        return pd.DataFrame()
    except Exception as e:
        print(f"Error: {e}")
        return pd.DataFrame()


def show_pivot_detection(df: pd.DataFrame, symbol: str):
    """Muestra cómo detectamos pivots (highs/lows)"""
    print("\n" + "=" * 70)
    print(f"  1. DETECCION DE PIVOTS - {symbol}")
    print("=" * 70)
    
    close = df['close'].values
    
    # Usamos scipy.signal.argrelextrema para encontrar máximos/mínimos locales
    # order=5 significa que miramos 5 barras a cada lado
    order = 5
    highs = argrelextrema(close, np.greater_equal, order=order)[0]
    lows = argrelextrema(close, np.less_equal, order=order)[0]
    
    print(f"\n  Datos: {len(close)} barras (1 minuto cada una)")
    print(f"  Parametro 'order': {order} (miramos {order} barras a cada lado)")
    print(f"\n  Matematica usada: scipy.signal.argrelextrema")
    print(f"  - Un HIGH es donde close[i] >= todos los close[i-5:i+5]")
    print(f"  - Un LOW es donde close[i] <= todos los close[i-5:i+5]")
    
    print(f"\n  Resultados:")
    print(f"  - Highs encontrados: {len(highs)}")
    print(f"  - Lows encontrados: {len(lows)}")
    
    # Mostrar los últimos 5 pivots
    print(f"\n  Ultimos 5 HIGHs:")
    for idx in highs[-5:]:
        ts = df.index[idx]
        price = close[idx]
        print(f"    Index {idx}: ${price:.2f} @ {ts}")
    
    print(f"\n  Ultimos 5 LOWs:")
    for idx in lows[-5:]:
        ts = df.index[idx]
        price = close[idx]
        print(f"    Index {idx}: ${price:.2f} @ {ts}")
    
    return highs, lows


def show_ascending_triangle_math(df: pd.DataFrame, highs: np.ndarray, lows: np.ndarray):
    """Muestra la matemática del Ascending Triangle"""
    print("\n" + "=" * 70)
    print("  2. ASCENDING TRIANGLE - MATEMATICA EXACTA")
    print("=" * 70)
    
    close = df['close'].values
    
    # Tomamos los últimos 5 highs y lows
    recent_highs = highs[-5:] if len(highs) >= 5 else highs
    recent_lows = lows[-5:] if len(lows) >= 5 else lows
    
    high_values = close[recent_highs]
    low_values = close[recent_lows]
    
    print(f"\n  Ultimos HIGHs (resistencia):")
    for i, (idx, val) in enumerate(zip(recent_highs, high_values)):
        print(f"    {i+1}. ${val:.2f}")
    
    print(f"\n  Ultimos LOWs (soporte):")
    for i, (idx, val) in enumerate(zip(recent_lows, low_values)):
        print(f"    {i+1}. ${val:.2f}")
    
    # Calcular desviación estándar de los highs (para ver si son "planos")
    high_mean = np.mean(high_values)
    high_std = np.std(high_values)
    high_std_pct = (high_std / high_mean) * 100
    
    print(f"\n  RESISTENCIA (HIGHs):")
    print(f"    Media: ${high_mean:.2f}")
    print(f"    Desviacion estandar: ${high_std:.4f}")
    print(f"    Desviacion %: {high_std_pct:.4f}%")
    print(f"    Criterio: std% < 2% = Resistencia PLANA")
    print(f"    Resultado: {'SI es plana' if high_std_pct < 2 else 'NO es plana'} ({high_std_pct:.4f}% {'<' if high_std_pct < 2 else '>'} 2%)")
    
    # Calcular pendiente de los lows (para ver si son "ascendentes")
    if len(recent_lows) >= 2:
        slope, intercept, r_value, p_value, std_err = linregress(
            range(len(low_values)), 
            low_values
        )
        
        print(f"\n  SOPORTE (LOWs) - Regresion Lineal:")
        print(f"    Pendiente: {slope:.6f}")
        print(f"    R-cuadrado: {r_value**2:.4f}")
        print(f"    Criterio: pendiente > 0 = Soporte ASCENDENTE")
        print(f"    Resultado: {'SI es ascendente' if slope > 0 else 'NO es ascendente'} (slope={slope:.6f})")
    
    # Conclusion
    is_ascending_triangle = high_std_pct < 2 and slope > 0
    
    print(f"\n  CONCLUSION:")
    print(f"    Resistencia plana: {'SI' if high_std_pct < 2 else 'NO'}")
    print(f"    Soporte ascendente: {'SI' if slope > 0 else 'NO'}")
    print(f"    --> {'ES UN ASCENDING TRIANGLE' if is_ascending_triangle else 'NO ES UN ASCENDING TRIANGLE'}")
    
    return is_ascending_triangle, high_mean, slope


def show_confidence_calculation(high_std_pct: float, slope: float):
    """Muestra cómo se calcula la confianza"""
    print("\n" + "=" * 70)
    print("  3. CALCULO DE CONFIANZA - DESGLOSE")
    print("=" * 70)
    
    confidence = 60  # Base
    
    print(f"\n  Confianza base: {confidence}%")
    
    # Bonus por resistencia muy plana
    flat_bonus = 15 if high_std_pct < 0.01 else 0
    print(f"  + Bonus resistencia muy plana (std < 0.01%): +{flat_bonus}%")
    confidence += flat_bonus
    
    # Bonus por pendiente fuerte
    slope_bonus = min(15, abs(slope) * 1000)
    print(f"  + Bonus pendiente fuerte (slope * 1000, max 15): +{slope_bonus:.1f}%")
    confidence += slope_bonus
    
    print(f"\n  CONFIANZA FINAL: {min(confidence, 95):.0f}%")
    
    print(f"\n  PROBLEMA DETECTADO:")
    print(f"  - El calculo siempre da ~90% porque:")
    print(f"    1. Los datos de 1 minuto tienen mucho 'ruido'")
    print(f"    2. Casi cualquier secuencia pasa los criterios")
    print(f"    3. Los thresholds (2%, slope>0) son muy permisivos")


def backtest_pattern(df: pd.DataFrame, pattern_detected_at: int, direction: str = "BULLISH"):
    """Backtest: ¿Qué pasó DESPUÉS de detectar el patrón?"""
    print("\n" + "=" * 70)
    print("  4. BACKTEST - ¿FUNCIONO EL PATRON?")
    print("=" * 70)
    
    close = df['close'].values
    
    if pattern_detected_at >= len(close) - 20:
        print("\n  No hay suficientes datos después del patrón para backtest")
        return
    
    entry_price = close[pattern_detected_at]
    
    # Mirar qué pasó en los siguientes 15, 30, 60 minutos
    periods = [15, 30, 60]
    
    print(f"\n  Precio al detectar patron: ${entry_price:.2f}")
    print(f"\n  ¿Que paso despues?")
    
    results = []
    for period in periods:
        if pattern_detected_at + period < len(close):
            future_price = close[pattern_detected_at + period]
            change_pct = (future_price - entry_price) / entry_price * 100
            
            if direction == "BULLISH":
                win = change_pct > 0
            else:
                win = change_pct < 0
            
            results.append({
                'period': period,
                'future_price': future_price,
                'change_pct': change_pct,
                'win': win
            })
            
            print(f"    +{period} min: ${future_price:.2f} ({change_pct:+.2f}%) {'WIN' if win else 'LOSS'}")
    
    return results


async def run_honest_validation():
    """Corre la validación honesta"""
    print("""
    ================================================================
    |                                                              |
    |    VALIDACION HONESTA DEL PATTERN SCANNER                    |
    |                                                              |
    |    Vamos a ver EXACTAMENTE que matematicas uso               |
    |    y si realmente funcionan o no.                            |
    |                                                              |
    ================================================================
    """)
    
    config = load_config()
    client = StockHistoricalDataClient(
        config['alpaca']['api_key'],
        config['alpaca']['api_secret']
    )
    
    symbol = "SPY"
    print(f"\n  Descargando datos de {symbol}...")
    df = await fetch_data(client, symbol, days=5)
    
    if df.empty:
        print("  ERROR: No se pudieron descargar datos")
        return
    
    print(f"  Datos descargados: {len(df)} barras")
    
    # 1. Mostrar detección de pivots
    highs, lows = show_pivot_detection(df, symbol)
    
    # 2. Mostrar matemática del Ascending Triangle
    is_pattern, resistance, slope = show_ascending_triangle_math(df, highs, lows)
    
    # 3. Mostrar cálculo de confianza
    high_values = df['close'].values[highs[-5:]]
    high_std_pct = (np.std(high_values) / np.mean(high_values)) * 100
    show_confidence_calculation(high_std_pct, slope)
    
    # 4. Backtest
    if len(df) > 100:
        # Detectar un patrón en el pasado y ver qué pasó
        test_index = len(df) - 100  # 100 barras atrás
        backtest_pattern(df, test_index, "BULLISH")
    
    # 5. VERDAD HONESTA
    print("\n" + "=" * 70)
    print("  5. LA VERDAD HONESTA")
    print("=" * 70)
    
    print("""
    PROBLEMAS CON MI IMPLEMENTACION ACTUAL:
    
    1. FALSOS POSITIVOS ALTOS
       - El criterio "std < 2%" es muy permisivo
       - Casi cualquier consolidación pasa como "resistencia plana"
       - Por eso TODOS los stocks muestran "Ascending Triangle"
    
    2. WIN RATES SON INVENTADOS
       - El 71% de win rate es un número hardcodeado
       - NO está calculado de backtesting real
       - Es basado en "investigación académica" pero no verificado
    
    3. TARGETS MUY PEQUEÑOS
       - Los targets de +0.1% no tienen sentido para 0DTE
       - La fórmula de "measured move" está mal calibrada
    
    4. NO CONSIDERA TU TIMEFRAME
       - Tu usas velas de 15 minutos
       - Yo estoy analizando velas de 1 minuto
       - Los patrones en diferentes timeframes son DIFERENTES
    
    PARA QUE FUNCIONE DE VERDAD NECESITO:
    
    1. Usar tu timeframe (15 min)
    2. Calibrar thresholds con datos históricos reales
    3. Hacer backtest de CADA patrón para calcular win rates REALES
    4. Comparar con tus indicadores de Pine Script (Project Zero)
    5. Validar que el "Ascending Triangle" que detecto es igual
       al que TU ves en TradingView
    """)


if __name__ == "__main__":
    asyncio.run(run_honest_validation())
