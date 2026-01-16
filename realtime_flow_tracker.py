#!/usr/bin/env python3
"""
================================================================================
    REAL-TIME FLOW TRACKER - Bulls vs Bears
================================================================================
    
    Monitorea en tiempo real:
    - Cambios en Put/Call ratio
    - Movimiento de Open Interest
    - Unusual Activity nueva
    - Distancia a Max Pain
    - Presión compradora vs vendedora
    
================================================================================
"""

import yaml
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import yfinance as yf
import time
import sys
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit


def get_flow_snapshot(symbol: str, current_price: float):
    """Obtiene snapshot del flow actual"""
    
    ticker = yf.Ticker(symbol)
    expirations = ticker.options
    
    if not expirations:
        return None
    
    # Buscar 0DTE o más cercana
    today = datetime.now().strftime('%Y-%m-%d')
    exp = expirations[0]  # Más cercana
    
    chain = ticker.option_chain(exp)
    calls = chain.calls
    puts = chain.puts
    
    # Filtrar strikes relevantes
    rng = current_price * 0.03  # 3%
    calls = calls[(calls['strike'] >= current_price - rng) & 
                  (calls['strike'] <= current_price + rng)]
    puts = puts[(puts['strike'] >= current_price - rng) & 
                (puts['strike'] <= current_price + rng)]
    
    # Calcular métricas
    call_vol = int(calls['volume'].sum()) if not calls.empty else 0
    put_vol = int(puts['volume'].sum()) if not puts.empty else 0
    call_oi = int(calls['openInterest'].sum()) if not calls.empty else 0
    put_oi = int(puts['openInterest'].sum()) if not puts.empty else 0
    
    # Max Pain
    all_strikes = sorted(set(calls['strike'].tolist() + puts['strike'].tolist()))
    max_pain = current_price
    min_pain_val = float('inf')
    
    for strike in all_strikes:
        pain = 0
        for _, c in calls.iterrows():
            if strike > c['strike']:
                pain += (strike - c['strike']) * c['openInterest']
        for _, p in puts.iterrows():
            if strike < p['strike']:
                pain += (p['strike'] - strike) * p['openInterest']
        if pain < min_pain_val:
            min_pain_val = pain
            max_pain = strike
    
    # Call Wall / Put Wall
    call_wall = float(calls.loc[calls['openInterest'].idxmax()]['strike']) if not calls.empty else 0
    put_wall = float(puts.loc[puts['openInterest'].idxmax()]['strike']) if not puts.empty else 0
    
    # Unusual activity count
    unusual_calls = len(calls[calls['volume'] > calls['openInterest'] * 2])
    unusual_puts = len(puts[puts['volume'] > puts['openInterest'] * 2])
    
    return {
        'timestamp': datetime.now(),
        'price': current_price,
        'expiration': exp,
        'call_vol': call_vol,
        'put_vol': put_vol,
        'call_oi': call_oi,
        'put_oi': put_oi,
        'pcr_vol': put_vol / call_vol if call_vol > 0 else 0,
        'pcr_oi': put_oi / call_oi if call_oi > 0 else 0,
        'max_pain': max_pain,
        'call_wall': call_wall,
        'put_wall': put_wall,
        'unusual_calls': unusual_calls,
        'unusual_puts': unusual_puts,
    }


def calculate_pressure(snapshot, prev_snapshot=None):
    """Calcula presión compradora/vendedora"""
    
    bull_pressure = 0
    bear_pressure = 0
    reasons = []
    
    price = snapshot['price']
    
    # 1. Put/Call Volume Ratio
    pcr = snapshot['pcr_vol']
    if pcr < 0.7:
        bull_pressure += 3
        reasons.append(f"PCR bajo ({pcr:.2f}) = BULLS dominan")
    elif pcr > 1.2:
        bear_pressure += 3
        reasons.append(f"PCR alto ({pcr:.2f}) = BEARS dominan")
    elif pcr < 1.0:
        bull_pressure += 1
        reasons.append(f"PCR <1 ({pcr:.2f}) = Bulls leve")
    else:
        bear_pressure += 1
        reasons.append(f"PCR >1 ({pcr:.2f}) = Bears leve")
    
    # 2. Distancia a Max Pain
    mp = snapshot['max_pain']
    dist_mp = price - mp
    pct_mp = abs(dist_mp) / price * 100
    
    if dist_mp > 0 and pct_mp > 0.3:
        bear_pressure += 2
        reasons.append(f"ARRIBA de Max Pain (+{dist_mp:.2f}) = Presion bajista")
    elif dist_mp < 0 and pct_mp > 0.3:
        bull_pressure += 2
        reasons.append(f"ABAJO de Max Pain ({dist_mp:.2f}) = Presion alcista")
    
    # 3. Distancia a Walls
    cw = snapshot['call_wall']
    pw = snapshot['put_wall']
    
    dist_cw = cw - price
    dist_pw = price - pw
    
    if dist_cw > 0 and dist_cw < dist_pw:
        bear_pressure += 1
        reasons.append(f"Cerca de CALL WALL ({cw:.0f}) = Resistencia")
    elif dist_pw > 0 and dist_pw < dist_cw:
        bull_pressure += 1
        reasons.append(f"Cerca de PUT WALL ({pw:.0f}) = Soporte")
    
    # 4. Unusual Activity
    uc = snapshot['unusual_calls']
    up = snapshot['unusual_puts']
    
    if uc > up + 2:
        bull_pressure += 2
        reasons.append(f"Unusual CALLS ({uc}) > PUTS ({up}) = Smart money bullish")
    elif up > uc + 2:
        bear_pressure += 2
        reasons.append(f"Unusual PUTS ({up}) > CALLS ({uc}) = Smart money bearish")
    
    # 5. Cambios vs anterior (si existe)
    if prev_snapshot:
        # Cambio en volumen
        call_vol_change = snapshot['call_vol'] - prev_snapshot['call_vol']
        put_vol_change = snapshot['put_vol'] - prev_snapshot['put_vol']
        
        if call_vol_change > put_vol_change * 1.5:
            bull_pressure += 1
            reasons.append(f"Calls acelerando (+{call_vol_change:,})")
        elif put_vol_change > call_vol_change * 1.5:
            bear_pressure += 1
            reasons.append(f"Puts acelerando (+{put_vol_change:,})")
    
    return {
        'bull': bull_pressure,
        'bear': bear_pressure,
        'reasons': reasons
    }


def print_dashboard(snapshot, pressure, prev_price=None):
    """Imprime dashboard"""
    
    price = snapshot['price']
    change = ""
    if prev_price:
        diff = price - prev_price
        change = f" ({diff:+.2f})"
    
    # Calcular barra de presión
    total = pressure['bull'] + pressure['bear']
    if total > 0:
        bull_pct = pressure['bull'] / total * 100
        bear_pct = pressure['bear'] / total * 100
    else:
        bull_pct = bear_pct = 50
    
    bar_len = 40
    bull_bars = int(bull_pct / 100 * bar_len)
    bear_bars = bar_len - bull_bars
    
    print("\033[2J\033[H")  # Clear screen
    print("=" * 70)
    print(f"    {snapshot['expiration']} FLOW TRACKER - {datetime.now().strftime('%H:%M:%S')}")
    print("=" * 70)
    print()
    print(f"  PRECIO: ${price:.2f}{change}")
    print()
    print("  BULLS vs BEARS:")
    print(f"  [{'#' * bull_bars}{'-' * bear_bars}]")
    print(f"   BULLS: {pressure['bull']}          BEARS: {pressure['bear']}")
    print()
    print("-" * 70)
    print("  METRICAS:")
    print(f"    Put/Call Vol:  {snapshot['pcr_vol']:.2f}")
    print(f"    Put/Call OI:   {snapshot['pcr_oi']:.2f}")
    print(f"    Max Pain:      ${snapshot['max_pain']:.2f} ({snapshot['price'] - snapshot['max_pain']:+.2f})")
    print(f"    Call Wall:     ${snapshot['call_wall']:.2f}")
    print(f"    Put Wall:      ${snapshot['put_wall']:.2f}")
    print(f"    Unusual Calls: {snapshot['unusual_calls']}")
    print(f"    Unusual Puts:  {snapshot['unusual_puts']}")
    print()
    print("-" * 70)
    print("  SENALES:")
    for reason in pressure['reasons']:
        print(f"    - {reason}")
    print()
    print("-" * 70)
    
    # Predicción
    if pressure['bull'] > pressure['bear'] + 3:
        direction = "FUERTE ALCISTA - Probable que SUBA"
        arrow = ">>>"
    elif pressure['bull'] > pressure['bear']:
        direction = "ALCISTA - Tendencia a subir"
        arrow = ">"
    elif pressure['bear'] > pressure['bull'] + 3:
        direction = "FUERTE BAJISTA - Probable que BAJE"
        arrow = "<<<"
    elif pressure['bear'] > pressure['bull']:
        direction = "BAJISTA - Tendencia a bajar"
        arrow = "<"
    else:
        direction = "NEUTRAL - Sin direccion clara"
        arrow = "="
    
    print(f"  PREDICCION: {arrow} {direction}")
    print()
    print("  TARGETS:")
    print(f"    Resistencia: ${snapshot['call_wall']:.2f}")
    print(f"    Magneto:     ${snapshot['max_pain']:.2f}")
    print(f"    Soporte:     ${snapshot['put_wall']:.2f}")
    print()
    print("=" * 70)
    print("  Ctrl+C para salir")


def main():
    symbol = 'SPY'
    
    print("Iniciando Flow Tracker...")
    print("Cargando configuracion...")
    
    with open('config.yaml', 'r') as f:
        config = yaml.safe_load(f)
    
    client = StockHistoricalDataClient(
        config['alpaca']['api_key'],
        config['alpaca']['api_secret']
    )
    
    prev_snapshot = None
    prev_price = None
    
    try:
        while True:
            # Obtener precio actual
            req = StockBarsRequest(
                symbol_or_symbols=symbol,
                timeframe=TimeFrame(1, TimeFrameUnit.Minute),
                start=datetime.now() - timedelta(minutes=5)
            )
            bars = client.get_stock_bars(req)
            
            if symbol not in bars.data:
                print("Error obteniendo precio")
                time.sleep(10)
                continue
            
            current_price = float(bars.data[symbol][-1].close)
            
            # Obtener flow
            snapshot = get_flow_snapshot(symbol, current_price)
            
            if not snapshot:
                print("Error obteniendo opciones")
                time.sleep(10)
                continue
            
            # Calcular presión
            pressure = calculate_pressure(snapshot, prev_snapshot)
            
            # Mostrar dashboard
            print_dashboard(snapshot, pressure, prev_price)
            
            prev_snapshot = snapshot
            prev_price = current_price
            
            # Esperar 30 segundos
            time.sleep(30)
            
    except KeyboardInterrupt:
        print("\n\nDetenido por usuario.")


if __name__ == "__main__":
    main()
