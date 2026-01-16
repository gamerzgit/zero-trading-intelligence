#!/usr/bin/env python3
"""
================================================================================
    VALIDACION REFINADA - Basada en datos reales del backtest anterior
================================================================================
    
    DESCUBRIMIENTOS:
    - Power Hour (15:00) tiene EV NEGATIVO (-0.059)
    - Las mejores horas son 12:00-14:00 (EV +0.05 a +0.10)
    - Más señales no significa mejor rendimiento
    
    NUEVA ESTRATEGIA:
    1. Filtrar por horas rentables (12:00-14:00)
    2. Targets más conservadores (ATR * 1.5)
    3. Filtro de tendencia (ADX > 25)
    4. Combinacion especifica de indicadores
    
================================================================================
"""

import numpy as np
import pandas as pd
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings('ignore')

from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
import yaml


def load_config():
    with open("config.yaml", 'r') as f:
        return yaml.safe_load(f)


def calculate_indicators(df):
    close = df['close']
    high = df['high']
    low = df['low']
    volume = df['volume']
    
    # RSI
    delta = close.diff()
    gain = delta.where(delta > 0, 0).rolling(7).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(7).mean()
    rs = gain / loss.replace(0, np.nan)
    df['rsi'] = 100 - (100 / (1 + rs))
    
    # MACD
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
    
    return df


def check_call_setup(row):
    """
    Setup CALL refinado basado en datos
    Retorna (is_valid, strength_score)
    """
    score = 0
    
    # MUST HAVE: Price > VWAP
    if row['close'] <= row['vwap']:
        return False, 0
    score += 1
    
    # MUST HAVE: EMA9 > EMA21
    if row['ema9'] <= row['ema21']:
        return False, 0
    score += 1
    
    # BONUS: Full EMA stack
    if row['ema9'] > row['ema21'] > row['ema50']:
        score += 1
    
    # BONUS: MACD bullish
    if row['macd_hist'] > 0:
        score += 1
    
    # BONUS: RSI not overbought
    if 40 < row['rsi'] < 65:
        score += 1
    
    # BONUS: Trending (ADX > 25)
    if row['adx'] > 25:
        score += 1
    
    # BONUS: Volume
    if row['vol_ratio'] > 1.2:
        score += 1
    
    # BONUS: Momentum positive
    if row['mom_5'] > 0.1:
        score += 1
    
    return score >= 4, score


def check_put_setup(row):
    """
    Setup PUT refinado basado en datos
    """
    score = 0
    
    # MUST HAVE: Price < VWAP
    if row['close'] >= row['vwap']:
        return False, 0
    score += 1
    
    # MUST HAVE: EMA9 < EMA21
    if row['ema9'] >= row['ema21']:
        return False, 0
    score += 1
    
    # BONUS: Full bearish EMA stack
    if row['ema9'] < row['ema21'] < row['ema50']:
        score += 1
    
    # BONUS: MACD bearish
    if row['macd_hist'] < 0:
        score += 1
    
    # BONUS: RSI not oversold
    if 35 < row['rsi'] < 60:
        score += 1
    
    # BONUS: Trending
    if row['adx'] > 25:
        score += 1
    
    # BONUS: Volume
    if row['vol_ratio'] > 1.2:
        score += 1
    
    # BONUS: Momentum negative
    if row['mom_5'] < -0.1:
        score += 1
    
    return score >= 4, score


def main():
    print("=" * 70)
    print("    VALIDACION REFINADA")
    print("    Estrategia optimizada con datos reales")
    print("=" * 70)
    
    config = load_config()
    alpaca = config.get('alpaca', {})
    
    client = StockHistoricalDataClient(
        alpaca.get('api_key', ''),
        alpaca.get('api_secret', '')
    )
    
    symbols = ['SPY', 'QQQ', 'AAPL', 'MSFT', 'NVDA', 'TSLA', 'AMD', 'META']
    
    # Test different configurations
    configs = [
        {'name': 'LUNCH (12:00-14:00) + ADX>25', 'hours': [12, 13, 14], 'adx_min': 25},
        {'name': 'AFTERNOON (13:00-15:00) + ADX>20', 'hours': [13, 14, 15], 'adx_min': 20},
        {'name': 'ALL HOURS + ADX>30', 'hours': list(range(9, 17)), 'adx_min': 30},
        {'name': 'MORNING (9:30-11:00) + High Vol', 'hours': [9, 10, 11], 'adx_min': 25},
        {'name': 'PRE-CLOSE (14:00-15:30)', 'hours': [14, 15], 'adx_min': 25},
    ]
    
    print(f"\n[DATA] Descargando 90 dias para {len(symbols)} simbolos...")
    
    all_data = {}
    for symbol in symbols:
        try:
            request = StockBarsRequest(
                symbol_or_symbols=symbol,
                timeframe=TimeFrame(15, TimeFrameUnit.Minute),
                start=datetime.now() - timedelta(days=90)
            )
            bars = client.get_stock_bars(request)
            
            if symbol not in bars.data:
                continue
            
            df = pd.DataFrame([{
                'timestamp': bar.timestamp,
                'open': bar.open,
                'high': bar.high,
                'low': bar.low,
                'close': bar.close,
                'volume': bar.volume,
                'vwap': bar.vwap
            } for bar in bars.data[symbol]])
            
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            df.set_index('timestamp', inplace=True)
            df = calculate_indicators(df)
            df.dropna(inplace=True)
            
            all_data[symbol] = df
            print(f"  {symbol}: {len(df)} candles")
            
        except Exception as e:
            print(f"  {symbol}: Error - {e}")
    
    # Test each configuration
    print("\n" + "=" * 70)
    print("    RESULTADOS POR CONFIGURACION")
    print("=" * 70)
    
    best_config = None
    best_ev = -999
    
    for cfg in configs:
        results = {'wins': 0, 'losses': 0, 'total_gain': 0, 'total_loss': 0}
        
        for symbol, df in all_data.items():
            for i in range(50, len(df) - 4):
                row = df.iloc[i]
                future = df.iloc[i:i+4]
                
                if len(future) < 4:
                    continue
                
                hour = row.name.hour
                
                # Filter by hour
                if hour not in cfg['hours']:
                    continue
                
                # Filter by ADX
                if row['adx'] < cfg['adx_min']:
                    continue
                
                # Check setups
                is_call, call_score = check_call_setup(row)
                is_put, put_score = check_put_setup(row)
                
                if not is_call and not is_put:
                    continue
                
                direction = 'CALL' if is_call else 'PUT'
                
                entry = float(row['close'])
                atr = float(row['atr'])
                
                # Use more conservative targets
                target_mult = 1.5  # Reduced from 2.0
                stop_mult = 0.75
                
                if direction == 'CALL':
                    target = entry + atr * target_mult
                    stop = entry - atr * stop_mult
                    
                    max_price = float(future['high'].max())
                    min_price = float(future['low'].min())
                    
                    if max_price >= target:
                        win = True
                        pct = (target - entry) / entry * 100
                    elif min_price <= stop:
                        win = False
                        pct = (stop - entry) / entry * 100
                    else:
                        final = float(future['close'].iloc[-1])
                        pct = (final - entry) / entry * 100
                        win = pct > 0
                else:
                    target = entry - atr * target_mult
                    stop = entry + atr * stop_mult
                    
                    max_price = float(future['high'].max())
                    min_price = float(future['low'].min())
                    
                    if min_price <= target:
                        win = True
                        pct = (entry - target) / entry * 100
                    elif max_price >= stop:
                        win = False
                        pct = (entry - stop) / entry * 100
                    else:
                        final = float(future['close'].iloc[-1])
                        pct = (entry - final) / entry * 100
                        win = pct > 0
                
                if win:
                    results['wins'] += 1
                    results['total_gain'] += pct
                else:
                    results['losses'] += 1
                    results['total_loss'] += abs(pct)
        
        # Calculate metrics
        total = results['wins'] + results['losses']
        
        if total < 50:
            print(f"\n{cfg['name']}: Insuficientes trades ({total})")
            continue
        
        win_rate = results['wins'] / total * 100
        avg_win = results['total_gain'] / max(results['wins'], 1)
        avg_loss = results['total_loss'] / max(results['losses'], 1)
        ev = (win_rate/100 * avg_win) - ((100-win_rate)/100 * avg_loss)
        pf = results['total_gain'] / max(results['total_loss'], 0.01)
        
        ev_str = f"+{ev:.4f}" if ev > 0 else f" {ev:.4f}"
        ev_flag = "***" if ev > 0.02 else ""
        
        print(f"\n{cfg['name']}:")
        print(f"  Trades: {total}")
        print(f"  Win Rate: {win_rate:.1f}%")
        print(f"  Avg Win: {avg_win:.3f}%")
        print(f"  Avg Loss: {avg_loss:.3f}%")
        print(f"  EV: {ev_str}% {ev_flag}")
        print(f"  Profit Factor: {pf:.2f}")
        
        if ev > best_ev:
            best_ev = ev
            best_config = cfg
    
    print("\n" + "=" * 70)
    print("    MEJOR CONFIGURACION ENCONTRADA")
    print("=" * 70)
    
    if best_config and best_ev > 0:
        print(f"""
    CONFIGURACION GANADORA: {best_config['name']}
    
    PARAMETROS:
    - Horas: {best_config['hours']}
    - ADX minimo: {best_config['adx_min']}
    
    RENDIMIENTO:
    - Expected Value: +{best_ev:.4f}% por trade
    
    CON 5 TRADES/DIA PROMEDIO:
    - EV diario: +{best_ev * 5:.4f}%
    - EV mensual (20 dias): +{best_ev * 5 * 20:.2f}%
    - Con apalancamiento opciones (5x): +{best_ev * 5 * 20 * 5:.1f}% mensual
    
    CON $5,000:
    - Ganancia mensual estimada: ${5000 * best_ev * 5 * 20 / 100:.0f}
    - Con opciones (5x): ${5000 * best_ev * 5 * 20 * 5 / 100:.0f}
""")
    else:
        print("""
    No se encontro configuracion con EV claramente positivo.
    
    OPCIONES:
    1. Usar targets mas conservadores
    2. Filtrar por volatilidad (ATR%)
    3. Agregar filtro de tendencia de mercado
    4. Combinar con AI model
""")


if __name__ == "__main__":
    main()
