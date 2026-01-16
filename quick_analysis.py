#!/usr/bin/env python3
"""
ANALISIS RAPIDO - Con progreso en tiempo real
"""

import numpy as np
import pandas as pd
from datetime import datetime, timedelta
import sys
import yaml

from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit


def log(msg):
    print(msg)
    sys.stdout.flush()


def calc_indicators(df):
    close = df['close']
    high = df['high']
    low = df['low']
    volume = df['volume']
    
    delta = close.diff()
    gain = delta.where(delta > 0, 0).rolling(7).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(7).mean()
    rs = gain / loss.replace(0, np.nan)
    df['rsi'] = 100 - (100 / (1 + rs))
    
    ema_fast = close.ewm(span=6).mean()
    ema_slow = close.ewm(span=13).mean()
    df['macd_hist'] = ema_fast - ema_slow - (ema_fast - ema_slow).ewm(span=5).mean()
    
    df['ema9'] = close.ewm(span=9).mean()
    df['ema21'] = close.ewm(span=21).mean()
    df['ema50'] = close.ewm(span=50).mean()
    
    tr = pd.concat([high - low, abs(high - close.shift()), abs(low - close.shift())], axis=1).max(axis=1)
    df['atr'] = tr.rolling(14).mean()
    
    plus_dm = high.diff()
    minus_dm = -low.diff()
    plus_dm = plus_dm.where((plus_dm > minus_dm) & (plus_dm > 0), 0)
    minus_dm = minus_dm.where((minus_dm > plus_dm) & (minus_dm > 0), 0)
    atr = df['atr'].replace(0, np.nan)
    plus_di = 100 * (plus_dm.rolling(14).mean() / atr)
    minus_di = 100 * (minus_dm.rolling(14).mean() / atr)
    dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di).replace(0, np.nan)
    df['adx'] = dx.rolling(14).mean()
    
    df['vol_sma'] = volume.rolling(20).mean()
    df['vol_ratio'] = volume / df['vol_sma'].replace(0, np.nan)
    df['mom'] = close.pct_change(5) * 100
    
    return df


def count_signals(row):
    b, s = 0, 0
    if row['close'] > row['vwap']: b += 1
    else: s += 1
    if row['ema9'] > row['ema21']: b += 1
    else: s += 1
    if row['ema9'] > row['ema21'] > row['ema50']: b += 1
    elif row['ema9'] < row['ema21'] < row['ema50']: s += 1
    if row['macd_hist'] > 0: b += 1
    elif row['macd_hist'] < 0: s += 1
    if 50 < row['rsi'] < 70: b += 1
    elif 30 < row['rsi'] < 50: s += 1
    if row['mom'] > 0.1: b += 1
    elif row['mom'] < -0.1: s += 1
    if row['vol_ratio'] > 1.2:
        if b > s: b += 1
        elif s > b: s += 1
    return b, s


def test_config(data, hours, adx, score, target, stop):
    wins, losses, gain, loss = 0, 0, 0, 0
    
    for sym, df in data.items():
        for i in range(50, len(df) - 4):
            row = df.iloc[i]
            future = df.iloc[i:i+4]
            if len(future) < 4: continue
            
            if row.name.hour not in hours: continue
            if pd.isna(row['adx']) or row['adx'] < adx: continue
            
            b, s = count_signals(row)
            
            if b > s and b >= score:
                if row['close'] <= row['vwap'] or row['ema9'] <= row['ema21']: continue
                direction = 'CALL'
            elif s > b and s >= score:
                if row['close'] >= row['vwap'] or row['ema9'] >= row['ema21']: continue
                direction = 'PUT'
            else:
                continue
            
            entry = float(row['close'])
            atr = float(row['atr'])
            
            if direction == 'CALL':
                tgt = entry + atr * target
                stp = entry - atr * stop
                mx, mn = float(future['high'].max()), float(future['low'].min())
                if mx >= tgt:
                    wins += 1
                    gain += (tgt - entry) / entry * 100
                elif mn <= stp:
                    losses += 1
                    loss += abs((stp - entry) / entry * 100)
                else:
                    pct = (float(future['close'].iloc[-1]) - entry) / entry * 100
                    if pct > 0:
                        wins += 1
                        gain += pct
                    else:
                        losses += 1
                        loss += abs(pct)
            else:
                tgt = entry - atr * target
                stp = entry + atr * stop
                mx, mn = float(future['high'].max()), float(future['low'].min())
                if mn <= tgt:
                    wins += 1
                    gain += (entry - tgt) / entry * 100
                elif mx >= stp:
                    losses += 1
                    loss += abs((entry - stp) / entry * 100)
                else:
                    pct = (entry - float(future['close'].iloc[-1])) / entry * 100
                    if pct > 0:
                        wins += 1
                        gain += pct
                    else:
                        losses += 1
                        loss += abs(pct)
    
    total = wins + losses
    if total < 30: return None
    
    wr = wins / total * 100
    aw = gain / max(wins, 1)
    al = loss / max(losses, 1)
    ev = (wr/100 * aw) - ((100-wr)/100 * al)
    pf = gain / max(loss, 0.01)
    
    return {'trades': total, 'win_rate': wr, 'ev': ev, 'pf': pf}


def main():
    log("=" * 70)
    log("    ANALISIS EXHAUSTIVO - 90 DIAS")
    log("=" * 70)
    
    with open("config.yaml", 'r') as f:
        config = yaml.safe_load(f)
    
    client = StockHistoricalDataClient(
        config['alpaca']['api_key'],
        config['alpaca']['api_secret']
    )
    
    symbols = ['SPY', 'QQQ', 'AAPL', 'NVDA', 'TSLA', 'AMD']
    
    log(f"\n[1/3] Descargando datos...")
    
    data = {}
    for sym in symbols:
        log(f"  {sym}...")
        try:
            req = StockBarsRequest(
                symbol_or_symbols=sym,
                timeframe=TimeFrame(15, TimeFrameUnit.Minute),
                start=datetime.now() - timedelta(days=90)
            )
            bars = client.get_stock_bars(req)
            if sym in bars.data:
                df = pd.DataFrame([{
                    'timestamp': b.timestamp,
                    'open': b.open, 'high': b.high, 'low': b.low,
                    'close': b.close, 'volume': b.volume, 'vwap': b.vwap
                } for b in bars.data[sym]])
                df['timestamp'] = pd.to_datetime(df['timestamp'])
                df.set_index('timestamp', inplace=True)
                df = calc_indicators(df)
                df.dropna(inplace=True)
                data[sym] = df
                log(f"    OK: {len(df)} candles")
        except Exception as e:
            log(f"    Error: {e}")
    
    log(f"\n[2/3] Probando combinaciones...")
    
    # Combinaciones reducidas pero completas
    hour_sets = [
        ('6:30-8 PST', [9, 10]),
        ('8-9 PST', [11]),
        ('9-11 PST', [12, 13]),
        ('11-12 PST', [14]),
        ('12-13 PST', [15]),
        ('6:30-9 PST', [9, 10, 11]),
        ('9-12 PST', [12, 13, 14]),
        ('9-11 PST', [12, 13]),
        ('10-12 PST', [13, 14]),
        ('ALL', [9, 10, 11, 12, 13, 14, 15]),
    ]
    
    adx_vals = [20, 25, 30, 35]
    score_vals = [3, 4, 5, 6]
    target_vals = [1.0, 1.5, 2.0]
    stop_vals = [0.5, 0.75, 1.0]
    
    total = len(hour_sets) * len(adx_vals) * len(score_vals) * len(target_vals) * len(stop_vals)
    log(f"  Total: {total} combinaciones")
    
    results = []
    n = 0
    
    for hname, hours in hour_sets:
        for adx in adx_vals:
            for score in score_vals:
                for target in target_vals:
                    for stop in stop_vals:
                        r = test_config(data, hours, adx, score, target, stop)
                        if r:
                            r['hours'] = hname
                            r['adx'] = adx
                            r['score'] = score
                            r['target'] = target
                            r['stop'] = stop
                            results.append(r)
                        n += 1
                        if n % 50 == 0:
                            log(f"  {n}/{total} ({n/total*100:.0f}%)")
    
    log(f"\n[3/3] RESULTADOS")
    log("=" * 70)
    
    if not results:
        log("No hay configuraciones validas")
        return
    
    # Por EV
    log("\nTOP 10 POR EXPECTED VALUE:")
    log("-" * 70)
    by_ev = sorted(results, key=lambda x: x['ev'], reverse=True)[:10]
    
    log(f"{'#':<3} {'Horas PST':<15} {'ADX':<5} {'Sc':<4} {'T/S':<7} {'Trades':<7} {'Win%':<7} {'EV':<12} {'PF':<6}")
    
    for i, r in enumerate(by_ev, 1):
        ev = f"+{r['ev']:.4f}%" if r['ev'] > 0 else f"{r['ev']:.4f}%"
        log(f"{i:<3} {r['hours']:<15} {r['adx']:<5} {r['score']:<4} {r['target']}/{r['stop']:<4} {r['trades']:<7} {r['win_rate']:<6.1f}% {ev:<12} {r['pf']:<.2f}")
    
    # Balanceado
    balanced = [r for r in results if r['ev'] > 0 and r['pf'] > 1.2 and r['trades'] > 50]
    
    if balanced:
        log("\n" + "=" * 70)
        log("MEJORES BALANCEADOS (EV>0, PF>1.2, Trades>50):")
        log("-" * 70)
        
        balanced = sorted(balanced, key=lambda x: x['ev'] * r['pf'], reverse=True)[:10]
        
        for i, r in enumerate(balanced, 1):
            ev = f"+{r['ev']:.4f}%"
            log(f"{i:<3} {r['hours']:<15} ADX>{r['adx']} Sc>{r['score']} T/S={r['target']}/{r['stop']} | {r['trades']} trades | {r['win_rate']:.1f}% win | EV={ev} | PF={r['pf']:.2f}")
        
        best = balanced[0]
        log("\n" + "=" * 70)
        log("MEJOR CONFIGURACION:")
        log("=" * 70)
        log(f"""
  HORAS: {best['hours']} (horario PST)
  
  PARAMETROS:
    ADX minimo: {best['adx']}
    Score minimo: {best['score']}
    Target: {best['target']} x ATR
    Stop: {best['stop']} x ATR
  
  RENDIMIENTO:
    Trades (90 dias): {best['trades']}
    Win Rate: {best['win_rate']:.1f}%
    EV: +{best['ev']:.4f}% por trade
    Profit Factor: {best['pf']:.2f}
  
  PROYECCION MENSUAL:
    Trades/dia: {best['trades']/90:.1f}
    EV mensual: +{best['ev'] * (best['trades']/90) * 20:.2f}%
    Con $5,000 + opciones (5x): ${5000 * best['ev'] * (best['trades']/90) * 20 * 5 / 100:.0f}
""")
    else:
        log("\nNo hay configuraciones con EV positivo y PF > 1.2")
        log("Mostrando las mejores disponibles arriba.")


if __name__ == "__main__":
    main()
