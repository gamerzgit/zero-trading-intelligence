#!/usr/bin/env python3
"""
ANALISIS MULTI-PERIODO
Encuentra la MEJOR configuracion para CADA hora del dia
Para poder tradear TODO EL DIA con criterios optimos
"""

import numpy as np
import pandas as pd
from datetime import datetime, timedelta
import sys
import yaml
import json

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
                    wins += 1; gain += (tgt - entry) / entry * 100
                elif mn <= stp:
                    losses += 1; loss += abs((stp - entry) / entry * 100)
                else:
                    pct = (float(future['close'].iloc[-1]) - entry) / entry * 100
                    if pct > 0: wins += 1; gain += pct
                    else: losses += 1; loss += abs(pct)
            else:
                tgt = entry - atr * target
                stp = entry + atr * stop
                mx, mn = float(future['high'].max()), float(future['low'].min())
                if mn <= tgt:
                    wins += 1; gain += (entry - tgt) / entry * 100
                elif mx >= stp:
                    losses += 1; loss += abs((entry - stp) / entry * 100)
                else:
                    pct = (entry - float(future['close'].iloc[-1])) / entry * 100
                    if pct > 0: wins += 1; gain += pct
                    else: losses += 1; loss += abs(pct)
    
    total = wins + losses
    if total < 20: return None
    
    wr = wins / total * 100
    aw = gain / max(wins, 1)
    al = loss / max(losses, 1)
    ev = (wr/100 * aw) - ((100-wr)/100 * al)
    pf = gain / max(loss, 0.01)
    
    return {'trades': total, 'win_rate': wr, 'ev': ev, 'pf': pf, 'avg_win': aw, 'avg_loss': al}


def main():
    log("=" * 70)
    log("    ANALISIS MULTI-PERIODO")
    log("    Encontrar mejor config para CADA hora")
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
    
    log(f"\n[2/3] Analizando cada periodo...")
    
    # Periodos a analizar (horas ET)
    periods = {
        '6:30-7:30 PST (OPEN)': [9, 10],
        '7:30-8:30 PST': [10, 11],
        '8:30-9:30 PST': [11, 12],
        '9:30-10:30 PST': [12, 13],
        '10:30-11:30 PST': [13, 14],
        '11:30-12:30 PST': [14, 15],
    }
    
    adx_vals = [20, 25, 30, 35]
    score_vals = [3, 4, 5, 6]
    target_vals = [1.0, 1.5, 2.0]
    stop_vals = [0.5, 0.75, 1.0]
    
    best_by_period = {}
    
    for period_name, hours in periods.items():
        log(f"\n  Analizando {period_name}...")
        
        best = None
        best_score = -999
        
        for adx in adx_vals:
            for score in score_vals:
                for target in target_vals:
                    for stop in stop_vals:
                        r = test_config(data, hours, adx, score, target, stop)
                        if r and r['ev'] > 0:
                            # Score combinado: EV * PF * (1 si trades > 50 else 0.5)
                            combined = r['ev'] * r['pf'] * (1 if r['trades'] > 50 else 0.5)
                            if combined > best_score:
                                best_score = combined
                                best = {
                                    'period': period_name,
                                    'hours_et': hours,
                                    'adx': adx,
                                    'score': score,
                                    'target': target,
                                    'stop': stop,
                                    **r
                                }
        
        if best:
            best_by_period[period_name] = best
            log(f"    MEJOR: ADX>{best['adx']} Sc>{best['score']} T/S={best['target']}/{best['stop']}")
            log(f"           Trades={best['trades']} WinRate={best['win_rate']:.1f}% EV=+{best['ev']:.4f}% PF={best['pf']:.2f}")
        else:
            log(f"    No hay configuracion rentable para este periodo")
    
    log(f"\n[3/3] RESULTADOS FINALES")
    log("=" * 70)
    
    log("\nMEJOR CONFIGURACION POR PERIODO:")
    log("-" * 70)
    
    total_trades_day = 0
    total_ev_day = 0
    
    for period_name, cfg in best_by_period.items():
        trades_per_day = cfg['trades'] / 90
        ev_contribution = cfg['ev'] * trades_per_day
        total_trades_day += trades_per_day
        total_ev_day += ev_contribution
        
        log(f"\n{period_name}:")
        log(f"  ADX: {cfg['adx']} | Score: {cfg['score']} | Target: {cfg['target']}x | Stop: {cfg['stop']}x")
        log(f"  Trades: {cfg['trades']} ({trades_per_day:.1f}/dia)")
        log(f"  Win Rate: {cfg['win_rate']:.1f}%")
        log(f"  EV: +{cfg['ev']:.4f}%")
        log(f"  PF: {cfg['pf']:.2f}")
    
    log("\n" + "=" * 70)
    log("    PROYECCION COMBINADA (TODOS LOS PERIODOS)")
    log("=" * 70)
    
    log(f"""
    TRADES DIARIOS ESTIMADOS: {total_trades_day:.1f}
    
    EV DIARIO: +{total_ev_day:.4f}%
    EV MENSUAL (20 dias): +{total_ev_day * 20:.2f}%
    
    CON $5,000:
      Sin apalancamiento: ${5000 * total_ev_day * 20 / 100:.0f}/mes
      Con opciones (5x): ${5000 * total_ev_day * 20 * 5 / 100:.0f}/mes
      Con opciones (10x): ${5000 * total_ev_day * 20 * 10 / 100:.0f}/mes
""")
    
    # Guardar configuracion
    config_output = {
        'generated': datetime.now().isoformat(),
        'periods': best_by_period,
        'summary': {
            'trades_per_day': total_trades_day,
            'ev_daily': total_ev_day,
            'ev_monthly': total_ev_day * 20
        }
    }
    
    with open("data/multi_period_config.json", 'w') as f:
        json.dump(config_output, f, indent=2, default=str)
    
    log("\n[SAVED] data/multi_period_config.json")
    
    # Mostrar tabla resumen para implementar
    log("\n" + "=" * 70)
    log("    TABLA DE CONFIGURACION PARA IMPLEMENTAR")
    log("=" * 70)
    log(f"\n{'Periodo PST':<20} {'Horas ET':<12} {'ADX':<5} {'Score':<6} {'T/S':<8} {'WinRate':<8} {'EV':<10}")
    log("-" * 75)
    
    for period_name, cfg in best_by_period.items():
        pst = period_name.split('(')[0].strip()
        log(f"{pst:<20} {str(cfg['hours_et']):<12} {cfg['adx']:<5} {cfg['score']:<6} {cfg['target']}/{cfg['stop']:<5} {cfg['win_rate']:<7.1f}% +{cfg['ev']:.4f}%")


if __name__ == "__main__":
    main()
