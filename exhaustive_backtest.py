#!/usr/bin/env python3
"""
================================================================================
    BACKTEST EXHAUSTIVO - ANÁLISIS MULTIVARIANTE
================================================================================
    
    Probando TODAS las combinaciones posibles:
    
    VARIABLES:
    - Horas del día (cada hora individual y combinaciones)
    - ADX threshold (15, 20, 25, 30, 35, 40)
    - Score mínimo (3, 4, 5, 6, 7)
    - Target multiplier (1.0, 1.5, 2.0, 2.5, 3.0)
    - Stop multiplier (0.5, 0.75, 1.0)
    - RSI filters (none, 30-70, 40-60)
    - Volume filter (none, >1.2x, >1.5x)
    
    Datos: 180 días
    Símbolos: 8 principales
    
    Output: La MEJOR configuración basada en:
    - Expected Value (EV)
    - Profit Factor
    - Win Rate
    - Número de trades (sample size)
    - Sharpe Ratio aproximado
    
================================================================================
"""

import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from itertools import product
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
    """Calcula todos los indicadores"""
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


def count_signals(row, rsi_filter=None, vol_filter=None):
    """
    Cuenta señales bullish y bearish
    Retorna (bullish_score, bearish_score)
    """
    bullish = 0
    bearish = 0
    
    # 1. VWAP
    if row['close'] > row['vwap']:
        bullish += 1
    else:
        bearish += 1
    
    # 2. EMA trend
    if row['ema9'] > row['ema21']:
        bullish += 1
    else:
        bearish += 1
    
    # 3. EMA stack
    if row['ema9'] > row['ema21'] > row['ema50']:
        bullish += 1
    elif row['ema9'] < row['ema21'] < row['ema50']:
        bearish += 1
    
    # 4. MACD
    if row['macd_hist'] > 0:
        bullish += 1
    elif row['macd_hist'] < 0:
        bearish += 1
    
    # 5. RSI
    rsi = row['rsi']
    if rsi_filter:
        rsi_low, rsi_high = rsi_filter
        if rsi_low < rsi < rsi_high:
            if rsi > 50:
                bullish += 1
            else:
                bearish += 1
    else:
        if 50 < rsi < 70:
            bullish += 1
        elif 30 < rsi < 50:
            bearish += 1
    
    # 6. Momentum
    mom = row['mom_5']
    if mom > 0.1:
        bullish += 1
    elif mom < -0.1:
        bearish += 1
    
    # 7. Volume (si hay filtro)
    vol = row['vol_ratio']
    if vol_filter:
        if vol > vol_filter:
            # Alto volumen confirma la dirección dominante
            if bullish > bearish:
                bullish += 1
            elif bearish > bullish:
                bearish += 1
    else:
        if vol > 1.2:
            if bullish > bearish:
                bullish += 1
            elif bearish > bullish:
                bearish += 1
    
    return bullish, bearish


def backtest_config(all_data, config):
    """
    Backtestea una configuración específica
    
    config = {
        'hours': [9, 10, 11, ...],
        'min_adx': 25,
        'min_score': 4,
        'target_mult': 1.5,
        'stop_mult': 0.75,
        'rsi_filter': None or (30, 70),
        'vol_filter': None or 1.2,
    }
    """
    results = {
        'wins': 0,
        'losses': 0,
        'total_gain': 0,
        'total_loss': 0,
        'returns': []
    }
    
    hours = config['hours']
    min_adx = config['min_adx']
    min_score = config['min_score']
    target_mult = config['target_mult']
    stop_mult = config['stop_mult']
    rsi_filter = config.get('rsi_filter')
    vol_filter = config.get('vol_filter')
    
    for symbol, df in all_data.items():
        for i in range(50, len(df) - 4):
            row = df.iloc[i]
            future = df.iloc[i:i+4]  # 1 hora (4 x 15min)
            
            if len(future) < 4:
                continue
            
            # Filtro de hora
            hour = row.name.hour
            if hour not in hours:
                continue
            
            # Filtro de ADX
            adx = row['adx']
            if pd.isna(adx) or adx < min_adx:
                continue
            
            # Contar señales
            bullish, bearish = count_signals(row, rsi_filter, vol_filter)
            
            # Determinar dirección
            if bullish > bearish and bullish >= min_score:
                direction = 'CALL'
                score = bullish
            elif bearish > bullish and bearish >= min_score:
                direction = 'PUT'
                score = bearish
            else:
                continue
            
            # Filtros adicionales obligatorios
            if direction == 'CALL':
                if row['close'] <= row['vwap'] or row['ema9'] <= row['ema21']:
                    continue
            else:
                if row['close'] >= row['vwap'] or row['ema9'] >= row['ema21']:
                    continue
            
            # Calcular outcome
            entry = float(row['close'])
            atr = float(row['atr'])
            
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
            
            results['returns'].append(pct if win else -abs(pct))
            
            if win:
                results['wins'] += 1
                results['total_gain'] += pct
            else:
                results['losses'] += 1
                results['total_loss'] += abs(pct)
    
    return results


def calculate_metrics(results):
    """Calcula métricas de rendimiento"""
    total = results['wins'] + results['losses']
    
    if total < 30:  # Mínimo sample size
        return None
    
    win_rate = results['wins'] / total * 100
    avg_win = results['total_gain'] / max(results['wins'], 1)
    avg_loss = results['total_loss'] / max(results['losses'], 1)
    
    ev = (win_rate/100 * avg_win) - ((100-win_rate)/100 * avg_loss)
    pf = results['total_gain'] / max(results['total_loss'], 0.01)
    
    # Sharpe aproximado
    returns = np.array(results['returns'])
    if len(returns) > 0 and returns.std() > 0:
        sharpe = returns.mean() / returns.std() * np.sqrt(252 * 6)  # Anualizado aprox
    else:
        sharpe = 0
    
    return {
        'trades': total,
        'win_rate': win_rate,
        'avg_win': avg_win,
        'avg_loss': avg_loss,
        'ev': ev,
        'pf': pf,
        'sharpe': sharpe,
        'total_return': sum(results['returns'])
    }


def main():
    print("=" * 80)
    print("    BACKTEST EXHAUSTIVO - ANÁLISIS MULTIVARIANTE")
    print("    Probando TODAS las combinaciones posibles")
    print("=" * 80)
    
    config = load_config()
    alpaca = config.get('alpaca', {})
    
    client = StockHistoricalDataClient(
        alpaca.get('api_key', ''),
        alpaca.get('api_secret', '')
    )
    
    symbols = ['SPY', 'QQQ', 'AAPL', 'MSFT', 'NVDA', 'TSLA', 'AMD', 'META']
    
    # Descargar datos
    print(f"\n[DATA] Descargando 180 días para {len(symbols)} símbolos...")
    
    all_data = {}
    for symbol in symbols:
        try:
            request = StockBarsRequest(
                symbol_or_symbols=symbol,
                timeframe=TimeFrame(15, TimeFrameUnit.Minute),
                start=datetime.now() - timedelta(days=180)
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
    
    # Definir todas las variables a probar
    print("\n[CONFIG] Definiendo combinaciones...")
    
    # Combinaciones de horas
    hour_combos = [
        ('MORNING', [9, 10]),
        ('LATE_MORNING', [10, 11]),
        ('MIDDAY', [11, 12]),
        ('LUNCH', [12, 13]),
        ('AFTERNOON', [13, 14]),
        ('LATE_AFTERNOON', [14, 15]),
        ('ALL_MORNING', [9, 10, 11]),
        ('ALL_MIDDAY', [11, 12, 13]),
        ('ALL_AFTERNOON', [13, 14, 15]),
        ('LUNCH_EXTENDED', [12, 13, 14]),
        ('PRIME_TIME', [10, 11, 12, 13]),
        ('FULL_DAY', [9, 10, 11, 12, 13, 14, 15]),
        ('AVOID_OPEN', [10, 11, 12, 13, 14, 15]),
        ('AVOID_CLOSE', [9, 10, 11, 12, 13, 14]),
    ]
    
    # Otros parámetros
    adx_values = [15, 20, 25, 30, 35]
    score_values = [3, 4, 5, 6]
    target_values = [1.0, 1.5, 2.0, 2.5]
    stop_values = [0.5, 0.75, 1.0]
    rsi_filters = [None, (30, 70), (35, 65), (40, 60)]
    vol_filters = [None, 1.2, 1.5]
    
    # Calcular total de combinaciones
    total_combos = (len(hour_combos) * len(adx_values) * len(score_values) * 
                   len(target_values) * len(stop_values) * len(rsi_filters) * len(vol_filters))
    
    print(f"[CONFIG] Total combinaciones: {total_combos}")
    print("\n[BACKTEST] Iniciando análisis exhaustivo...")
    
    results_list = []
    tested = 0
    
    for hour_name, hours in hour_combos:
        for adx in adx_values:
            for score in score_values:
                for target in target_values:
                    for stop in stop_values:
                        for rsi_f in rsi_filters:
                            for vol_f in vol_filters:
                                config_test = {
                                    'hours': hours,
                                    'min_adx': adx,
                                    'min_score': score,
                                    'target_mult': target,
                                    'stop_mult': stop,
                                    'rsi_filter': rsi_f,
                                    'vol_filter': vol_f,
                                    'hour_name': hour_name
                                }
                                
                                results = backtest_config(all_data, config_test)
                                metrics = calculate_metrics(results)
                                
                                if metrics:
                                    metrics['config'] = config_test
                                    results_list.append(metrics)
                                
                                tested += 1
                                if tested % 500 == 0:
                                    print(f"  Probadas: {tested}/{total_combos} ({tested/total_combos*100:.1f}%)")
    
    print(f"\n[DONE] Probadas {tested} combinaciones")
    print(f"[DONE] Configuraciones válidas: {len(results_list)}")
    
    if not results_list:
        print("\n[ERROR] No se encontraron configuraciones válidas")
        return
    
    # Ordenar por diferentes métricas
    print("\n" + "=" * 80)
    print("    RESULTADOS - TOP 10 POR EXPECTED VALUE")
    print("=" * 80)
    
    by_ev = sorted(results_list, key=lambda x: x['ev'], reverse=True)[:10]
    
    print(f"\n{'Rank':<5} {'Horas':<15} {'ADX':<5} {'Score':<6} {'T/S':<8} {'Trades':<8} {'Win%':<7} {'EV':<10} {'PF':<6}")
    print("-" * 80)
    
    for i, r in enumerate(by_ev, 1):
        c = r['config']
        ts = f"{c['target_mult']}/{c['stop_mult']}"
        ev_str = f"+{r['ev']:.4f}%" if r['ev'] > 0 else f"{r['ev']:.4f}%"
        print(f"{i:<5} {c['hour_name']:<15} {c['min_adx']:<5} {c['min_score']:<6} {ts:<8} {r['trades']:<8} {r['win_rate']:<6.1f}% {ev_str:<10} {r['pf']:<.2f}")
    
    # Top por Profit Factor
    print("\n" + "=" * 80)
    print("    RESULTADOS - TOP 10 POR PROFIT FACTOR")
    print("=" * 80)
    
    by_pf = sorted(results_list, key=lambda x: x['pf'], reverse=True)[:10]
    
    print(f"\n{'Rank':<5} {'Horas':<15} {'ADX':<5} {'Score':<6} {'T/S':<8} {'Trades':<8} {'Win%':<7} {'EV':<10} {'PF':<6}")
    print("-" * 80)
    
    for i, r in enumerate(by_pf, 1):
        c = r['config']
        ts = f"{c['target_mult']}/{c['stop_mult']}"
        ev_str = f"+{r['ev']:.4f}%" if r['ev'] > 0 else f"{r['ev']:.4f}%"
        print(f"{i:<5} {c['hour_name']:<15} {c['min_adx']:<5} {c['min_score']:<6} {ts:<8} {r['trades']:<8} {r['win_rate']:<6.1f}% {ev_str:<10} {r['pf']:<.2f}")
    
    # Top por Sharpe
    print("\n" + "=" * 80)
    print("    RESULTADOS - TOP 10 POR SHARPE RATIO")
    print("=" * 80)
    
    by_sharpe = sorted(results_list, key=lambda x: x['sharpe'], reverse=True)[:10]
    
    print(f"\n{'Rank':<5} {'Horas':<15} {'ADX':<5} {'Score':<6} {'T/S':<8} {'Trades':<8} {'Sharpe':<8} {'EV':<10}")
    print("-" * 80)
    
    for i, r in enumerate(by_sharpe, 1):
        c = r['config']
        ts = f"{c['target_mult']}/{c['stop_mult']}"
        ev_str = f"+{r['ev']:.4f}%" if r['ev'] > 0 else f"{r['ev']:.4f}%"
        print(f"{i:<5} {c['hour_name']:<15} {c['min_adx']:<5} {c['min_score']:<6} {ts:<8} {r['trades']:<8} {r['sharpe']:<7.2f} {ev_str:<10}")
    
    # Top balanceado (EV > 0 AND PF > 1.2 AND trades > 100)
    print("\n" + "=" * 80)
    print("    MEJORES CONFIGURACIONES BALANCEADAS")
    print("    (EV > 0, PF > 1.2, Trades > 100)")
    print("=" * 80)
    
    balanced = [r for r in results_list if r['ev'] > 0 and r['pf'] > 1.2 and r['trades'] > 100]
    balanced = sorted(balanced, key=lambda x: x['ev'] * x['pf'], reverse=True)[:15]
    
    print(f"\n{'Rank':<5} {'Horas':<15} {'ADX':<5} {'Score':<6} {'T/S':<8} {'RSI':<10} {'Vol':<6} {'Trades':<8} {'Win%':<7} {'EV':<10} {'PF':<6}")
    print("-" * 100)
    
    for i, r in enumerate(balanced, 1):
        c = r['config']
        ts = f"{c['target_mult']}/{c['stop_mult']}"
        rsi_str = f"{c['rsi_filter']}" if c['rsi_filter'] else "None"
        vol_str = f">{c['vol_filter']}" if c['vol_filter'] else "None"
        ev_str = f"+{r['ev']:.4f}%"
        print(f"{i:<5} {c['hour_name']:<15} {c['min_adx']:<5} {c['min_score']:<6} {ts:<8} {rsi_str:<10} {vol_str:<6} {r['trades']:<8} {r['win_rate']:<6.1f}% {ev_str:<10} {r['pf']:<.2f}")
    
    # Mejor configuración overall
    if balanced:
        best = balanced[0]
        c = best['config']
        
        print("\n" + "=" * 80)
        print("    MEJOR CONFIGURACIÓN ENCONTRADA")
        print("=" * 80)
        print(f"""
    HORARIO: {c['hour_name']} ({c['hours']} ET)
    
    FILTROS:
    - ADX mínimo: {c['min_adx']}
    - Score mínimo: {c['min_score']}
    - RSI filter: {c['rsi_filter']}
    - Volume filter: {c['vol_filter']}
    
    TARGETS:
    - Target multiplier: {c['target_mult']} x ATR
    - Stop multiplier: {c['stop_mult']} x ATR
    
    RENDIMIENTO (180 días):
    - Trades totales: {best['trades']}
    - Win Rate: {best['win_rate']:.1f}%
    - Expected Value: +{best['ev']:.4f}% por trade
    - Profit Factor: {best['pf']:.2f}
    - Sharpe Ratio: {best['sharpe']:.2f}
    - Retorno total: {best['total_return']:.2f}%
    
    PROYECCIÓN MENSUAL:
    - Trades/día estimados: {best['trades'] / 180:.1f}
    - EV mensual: +{best['ev'] * (best['trades']/180) * 20:.2f}%
    - Con $5,000 y opciones (5x): ${5000 * best['ev'] * (best['trades']/180) * 20 * 5 / 100:.0f}
""")
        
        # Guardar mejor configuración
        import json
        with open("data/best_config.json", 'w') as f:
            json.dump({
                'config': c,
                'metrics': {
                    'trades': best['trades'],
                    'win_rate': best['win_rate'],
                    'ev': best['ev'],
                    'pf': best['pf'],
                    'sharpe': best['sharpe']
                }
            }, f, indent=2, default=str)
        
        print(f"    [SAVED] Configuración guardada en data/best_config.json")
    
    # Análisis por hora individual
    print("\n" + "=" * 80)
    print("    ANÁLISIS POR HORA INDIVIDUAL")
    print("=" * 80)
    
    hour_analysis = {}
    for r in results_list:
        hours = tuple(r['config']['hours'])
        if len(hours) == 1 or len(hours) == 2:
            key = r['config']['hour_name']
            if key not in hour_analysis:
                hour_analysis[key] = []
            hour_analysis[key].append(r)
    
    print(f"\n{'Periodo':<20} {'Best EV':<12} {'Best PF':<10} {'Avg Trades':<12}")
    print("-" * 60)
    
    for period, configs in sorted(hour_analysis.items()):
        if configs:
            best_ev = max(c['ev'] for c in configs)
            best_pf = max(c['pf'] for c in configs)
            avg_trades = np.mean([c['trades'] for c in configs])
            ev_str = f"+{best_ev:.4f}%" if best_ev > 0 else f"{best_ev:.4f}%"
            print(f"{period:<20} {ev_str:<12} {best_pf:<9.2f} {avg_trades:<.0f}")


if __name__ == "__main__":
    main()
