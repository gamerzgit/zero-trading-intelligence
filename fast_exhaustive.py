#!/usr/bin/env python3
"""
================================================================================
    BACKTEST EXHAUSTIVO OPTIMIZADO
================================================================================
    Versión rápida pero completa
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
import json


def load_config():
    with open("config.yaml", 'r') as f:
        return yaml.safe_load(f)


def calculate_indicators(df):
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
    df['macd'] = ema_fast - ema_slow
    df['macd_signal'] = df['macd'].ewm(span=5).mean()
    df['macd_hist'] = df['macd'] - df['macd_signal']
    
    df['ema9'] = close.ewm(span=9).mean()
    df['ema21'] = close.ewm(span=21).mean()
    df['ema50'] = close.ewm(span=50).mean()
    
    tr = pd.concat([
        high - low,
        abs(high - close.shift()),
        abs(low - close.shift())
    ], axis=1).max(axis=1)
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
    df['mom_5'] = close.pct_change(5) * 100
    
    return df


def count_signals(row):
    bullish = 0
    bearish = 0
    
    if row['close'] > row['vwap']:
        bullish += 1
    else:
        bearish += 1
    
    if row['ema9'] > row['ema21']:
        bullish += 1
    else:
        bearish += 1
    
    if row['ema9'] > row['ema21'] > row['ema50']:
        bullish += 1
    elif row['ema9'] < row['ema21'] < row['ema50']:
        bearish += 1
    
    if row['macd_hist'] > 0:
        bullish += 1
    elif row['macd_hist'] < 0:
        bearish += 1
    
    rsi = row['rsi']
    if 50 < rsi < 70:
        bullish += 1
    elif 30 < rsi < 50:
        bearish += 1
    
    mom = row['mom_5']
    if mom > 0.1:
        bullish += 1
    elif mom < -0.1:
        bearish += 1
    
    vol = row['vol_ratio']
    if vol > 1.2:
        if bullish > bearish:
            bullish += 1
        elif bearish > bullish:
            bearish += 1
    
    return bullish, bearish


def backtest_config(all_data, hours, min_adx, min_score, target_mult, stop_mult):
    wins = 0
    losses = 0
    total_gain = 0
    total_loss = 0
    returns = []
    
    for symbol, df in all_data.items():
        for i in range(50, len(df) - 4):
            row = df.iloc[i]
            future = df.iloc[i:i+4]
            
            if len(future) < 4:
                continue
            
            hour = row.name.hour
            if hour not in hours:
                continue
            
            adx = row['adx']
            if pd.isna(adx) or adx < min_adx:
                continue
            
            bullish, bearish = count_signals(row)
            
            if bullish > bearish and bullish >= min_score:
                if row['close'] <= row['vwap'] or row['ema9'] <= row['ema21']:
                    continue
                direction = 'CALL'
            elif bearish > bullish and bearish >= min_score:
                if row['close'] >= row['vwap'] or row['ema9'] >= row['ema21']:
                    continue
                direction = 'PUT'
            else:
                continue
            
            entry = float(row['close'])
            atr = float(row['atr'])
            
            if direction == 'CALL':
                target = entry + atr * target_mult
                stop = entry - atr * stop_mult
                max_p = float(future['high'].max())
                min_p = float(future['low'].min())
                
                if max_p >= target:
                    pct = (target - entry) / entry * 100
                    win = True
                elif min_p <= stop:
                    pct = (stop - entry) / entry * 100
                    win = False
                else:
                    final = float(future['close'].iloc[-1])
                    pct = (final - entry) / entry * 100
                    win = pct > 0
            else:
                target = entry - atr * target_mult
                stop = entry + atr * stop_mult
                max_p = float(future['high'].max())
                min_p = float(future['low'].min())
                
                if min_p <= target:
                    pct = (entry - target) / entry * 100
                    win = True
                elif max_p >= stop:
                    pct = (entry - stop) / entry * 100
                    win = False
                else:
                    final = float(future['close'].iloc[-1])
                    pct = (entry - final) / entry * 100
                    win = pct > 0
            
            returns.append(pct if win else -abs(pct))
            if win:
                wins += 1
                total_gain += pct
            else:
                losses += 1
                total_loss += abs(pct)
    
    total = wins + losses
    if total < 30:
        return None
    
    win_rate = wins / total * 100
    avg_win = total_gain / max(wins, 1)
    avg_loss = total_loss / max(losses, 1)
    ev = (win_rate/100 * avg_win) - ((100-win_rate)/100 * avg_loss)
    pf = total_gain / max(total_loss, 0.01)
    
    returns_arr = np.array(returns)
    sharpe = returns_arr.mean() / returns_arr.std() * np.sqrt(252*6) if len(returns_arr) > 0 and returns_arr.std() > 0 else 0
    
    return {
        'trades': total,
        'win_rate': win_rate,
        'avg_win': avg_win,
        'avg_loss': avg_loss,
        'ev': ev,
        'pf': pf,
        'sharpe': sharpe,
        'total_return': sum(returns)
    }


def main():
    print("=" * 80)
    print("    BACKTEST EXHAUSTIVO - 180 DIAS")
    print("=" * 80)
    
    config = load_config()
    alpaca = config.get('alpaca', {})
    
    client = StockHistoricalDataClient(
        alpaca.get('api_key', ''),
        alpaca.get('api_secret', '')
    )
    
    symbols = ['SPY', 'QQQ', 'AAPL', 'MSFT', 'NVDA', 'TSLA', 'AMD', 'META']
    
    print(f"\n[DATA] Descargando 180 dias...")
    
    all_data = {}
    for symbol in symbols:
        try:
            request = StockBarsRequest(
                symbol_or_symbols=symbol,
                timeframe=TimeFrame(15, TimeFrameUnit.Minute),
                start=datetime.now() - timedelta(days=180)
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
                    'vwap': bar.vwap
                } for bar in bars.data[symbol]])
                
                df['timestamp'] = pd.to_datetime(df['timestamp'])
                df.set_index('timestamp', inplace=True)
                df = calculate_indicators(df)
                df.dropna(inplace=True)
                all_data[symbol] = df
                print(f"  {symbol}: {len(df)} candles")
        except Exception as e:
            print(f"  {symbol}: Error")
    
    # Combinaciones a probar
    hour_combos = [
        ('9-10 (OPEN)', [9, 10]),
        ('10-11', [10, 11]),
        ('11-12', [11, 12]),
        ('12-13', [12, 13]),
        ('13-14', [13, 14]),
        ('14-15', [14, 15]),
        ('9-11 (MORNING)', [9, 10, 11]),
        ('11-13 (MIDDAY)', [11, 12, 13]),
        ('12-14 (LUNCH)', [12, 13, 14]),
        ('13-15 (AFTERNOON)', [13, 14, 15]),
        ('10-14 (PRIME)', [10, 11, 12, 13, 14]),
        ('9-15 (FULL)', [9, 10, 11, 12, 13, 14, 15]),
    ]
    
    adx_vals = [20, 25, 30, 35]
    score_vals = [3, 4, 5, 6]
    target_vals = [1.0, 1.5, 2.0]
    stop_vals = [0.5, 0.75, 1.0]
    
    total = len(hour_combos) * len(adx_vals) * len(score_vals) * len(target_vals) * len(stop_vals)
    print(f"\n[TEST] Probando {total} combinaciones...")
    
    results = []
    tested = 0
    
    for hour_name, hours in hour_combos:
        for adx in adx_vals:
            for score in score_vals:
                for target in target_vals:
                    for stop in stop_vals:
                        r = backtest_config(all_data, hours, adx, score, target, stop)
                        if r:
                            r['hours'] = hour_name
                            r['adx'] = adx
                            r['score'] = score
                            r['target'] = target
                            r['stop'] = stop
                            results.append(r)
                        
                        tested += 1
                        if tested % 100 == 0:
                            print(f"  {tested}/{total} ({tested/total*100:.0f}%)")
    
    print(f"\n[DONE] Configuraciones validas: {len(results)}")
    
    # TOP POR EV
    print("\n" + "=" * 80)
    print("    TOP 15 POR EXPECTED VALUE")
    print("=" * 80)
    
    by_ev = sorted(results, key=lambda x: x['ev'], reverse=True)[:15]
    
    print(f"\n{'#':<3} {'Horas':<18} {'ADX':<5} {'Sc':<4} {'T/S':<8} {'Trades':<7} {'Win%':<7} {'EV':<12} {'PF':<6}")
    print("-" * 80)
    
    for i, r in enumerate(by_ev, 1):
        ev_str = f"+{r['ev']:.4f}%" if r['ev'] > 0 else f"{r['ev']:.4f}%"
        print(f"{i:<3} {r['hours']:<18} {r['adx']:<5} {r['score']:<4} {r['target']}/{r['stop']:<5} {r['trades']:<7} {r['win_rate']:<6.1f}% {ev_str:<12} {r['pf']:<.2f}")
    
    # TOP POR PROFIT FACTOR
    print("\n" + "=" * 80)
    print("    TOP 15 POR PROFIT FACTOR")
    print("=" * 80)
    
    by_pf = sorted(results, key=lambda x: x['pf'], reverse=True)[:15]
    
    print(f"\n{'#':<3} {'Horas':<18} {'ADX':<5} {'Sc':<4} {'T/S':<8} {'Trades':<7} {'Win%':<7} {'EV':<12} {'PF':<6}")
    print("-" * 80)
    
    for i, r in enumerate(by_pf, 1):
        ev_str = f"+{r['ev']:.4f}%" if r['ev'] > 0 else f"{r['ev']:.4f}%"
        print(f"{i:<3} {r['hours']:<18} {r['adx']:<5} {r['score']:<4} {r['target']}/{r['stop']:<5} {r['trades']:<7} {r['win_rate']:<6.1f}% {ev_str:<12} {r['pf']:<.2f}")
    
    # BALANCEADO (EV > 0, PF > 1.3, Trades > 100)
    print("\n" + "=" * 80)
    print("    MEJORES BALANCEADOS (EV>0, PF>1.3, Trades>100)")
    print("=" * 80)
    
    balanced = [r for r in results if r['ev'] > 0 and r['pf'] > 1.3 and r['trades'] > 100]
    balanced = sorted(balanced, key=lambda x: x['ev'] * x['pf'], reverse=True)[:15]
    
    if balanced:
        print(f"\n{'#':<3} {'Horas':<18} {'ADX':<5} {'Sc':<4} {'T/S':<8} {'Trades':<7} {'Win%':<7} {'EV':<12} {'PF':<6} {'Sharpe':<7}")
        print("-" * 90)
        
        for i, r in enumerate(balanced, 1):
            ev_str = f"+{r['ev']:.4f}%"
            print(f"{i:<3} {r['hours']:<18} {r['adx']:<5} {r['score']:<4} {r['target']}/{r['stop']:<5} {r['trades']:<7} {r['win_rate']:<6.1f}% {ev_str:<12} {r['pf']:<.2f} {r['sharpe']:<.2f}")
        
        # MEJOR CONFIGURACION
        best = balanced[0]
        
        print("\n" + "=" * 80)
        print("    CONFIGURACION OPTIMA")
        print("=" * 80)
        print(f"""
    HORARIO: {best['hours']} ET
    
    PARAMETROS:
      ADX minimo: {best['adx']}
      Score minimo: {best['score']}
      Target: {best['target']} x ATR
      Stop: {best['stop']} x ATR
    
    RENDIMIENTO (180 dias):
      Trades: {best['trades']}
      Win Rate: {best['win_rate']:.1f}%
      EV: +{best['ev']:.4f}% por trade
      Profit Factor: {best['pf']:.2f}
      Sharpe: {best['sharpe']:.2f}
      Retorno Total: {best['total_return']:.2f}%
    
    PROYECCION:
      Trades/dia: {best['trades']/180:.1f}
      EV mensual: +{best['ev'] * (best['trades']/180) * 20:.2f}%
      Con $5,000 + opciones (5x): ${5000 * best['ev'] * (best['trades']/180) * 20 * 5 / 100:.0f}/mes
""")
        
        # Guardar
        with open("data/best_config.json", 'w') as f:
            json.dump(best, f, indent=2)
        print("    [SAVED] data/best_config.json")
    
    else:
        print("\n  No se encontraron configuraciones balanceadas.")
        print("  Mostrando mejores disponibles...")
        
        if by_ev:
            best = by_ev[0]
            print(f"\n  Mejor por EV: {best['hours']} - EV: {best['ev']:.4f}%")
    
    # Análisis por hora
    print("\n" + "=" * 80)
    print("    ANALISIS POR PERIODO (mejor config de cada uno)")
    print("=" * 80)
    
    by_period = {}
    for r in results:
        period = r['hours']
        if period not in by_period or r['ev'] > by_period[period]['ev']:
            by_period[period] = r
    
    print(f"\n{'Periodo':<20} {'Trades':<8} {'Win%':<8} {'EV':<12} {'PF':<6}")
    print("-" * 60)
    
    for period in sorted(by_period.keys()):
        r = by_period[period]
        ev_str = f"+{r['ev']:.4f}%" if r['ev'] > 0 else f"{r['ev']:.4f}%"
        marker = " ***" if r['ev'] > 0.03 else ""
        print(f"{period:<20} {r['trades']:<8} {r['win_rate']:<7.1f}% {ev_str:<12} {r['pf']:<.2f}{marker}")


if __name__ == "__main__":
    main()
