#!/usr/bin/env python3
"""
================================================================================
    ANALISIS DE FLOW DE OPCIONES + TECNICOS
================================================================================
    
    Combina:
    1. CALL WALL / PUT WALL - Donde hay más open interest
    2. MAX PAIN - Precio donde más opciones expiran sin valor
    3. PUT/CALL RATIO - Sentimiento del mercado
    4. GAMMA EXPOSURE - Niveles magneto
    5. UNUSUAL ACTIVITY - Apuestas grandes
    
    + Indicadores técnicos para confirmar dirección
    
================================================================================
"""

import yaml
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import yfinance as yf
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit


def get_options_flow(symbol: str, current_price: float):
    """Analiza el flow de opciones para determinar dirección"""
    
    ticker = yf.Ticker(symbol)
    
    # Obtener fechas de expiración
    expirations = ticker.options
    if not expirations:
        return None
    
    # Usar expiración más cercana (0DTE o próxima)
    exp = expirations[0]
    
    chain = ticker.option_chain(exp)
    calls = chain.calls
    puts = chain.puts
    
    # Filtrar strikes relevantes (±5% del precio)
    strike_range = current_price * 0.05
    calls = calls[(calls['strike'] >= current_price - strike_range) & 
                  (calls['strike'] <= current_price + strike_range)]
    puts = puts[(puts['strike'] >= current_price - strike_range) & 
                (puts['strike'] <= current_price + strike_range)]
    
    result = {
        'expiration': exp,
        'current_price': current_price,
    }
    
    # 1. CALL WALL - Strike con más open interest en calls
    if not calls.empty:
        call_wall_idx = calls['openInterest'].idxmax()
        call_wall = calls.loc[call_wall_idx]
        result['call_wall'] = {
            'strike': float(call_wall['strike']),
            'oi': int(call_wall['openInterest']),
            'volume': int(call_wall['volume']) if not pd.isna(call_wall['volume']) else 0
        }
    
    # 2. PUT WALL - Strike con más open interest en puts
    if not puts.empty:
        put_wall_idx = puts['openInterest'].idxmax()
        put_wall = puts.loc[put_wall_idx]
        result['put_wall'] = {
            'strike': float(put_wall['strike']),
            'oi': int(put_wall['openInterest']),
            'volume': int(put_wall['volume']) if not pd.isna(put_wall['volume']) else 0
        }
    
    # 3. PUT/CALL RATIO
    total_call_vol = calls['volume'].sum() if not calls.empty else 0
    total_put_vol = puts['volume'].sum() if not puts.empty else 0
    total_call_oi = calls['openInterest'].sum() if not calls.empty else 0
    total_put_oi = puts['openInterest'].sum() if not puts.empty else 0
    
    result['volume'] = {
        'calls': int(total_call_vol) if not pd.isna(total_call_vol) else 0,
        'puts': int(total_put_vol) if not pd.isna(total_put_vol) else 0,
        'ratio': float(total_put_vol / total_call_vol) if total_call_vol > 0 else 0
    }
    
    result['open_interest'] = {
        'calls': int(total_call_oi),
        'puts': int(total_put_oi),
        'ratio': float(total_put_oi / total_call_oi) if total_call_oi > 0 else 0
    }
    
    # 4. MAX PAIN - Precio donde más opciones expiran sin valor
    strikes = sorted(set(calls['strike'].tolist() + puts['strike'].tolist()))
    max_pain_strike = None
    min_pain_value = float('inf')
    
    for strike in strikes:
        # Para cada strike, calcular el "dolor" total
        call_pain = 0
        put_pain = 0
        
        for _, call in calls.iterrows():
            if strike > call['strike']:
                call_pain += (strike - call['strike']) * call['openInterest']
        
        for _, put in puts.iterrows():
            if strike < put['strike']:
                put_pain += (put['strike'] - strike) * put['openInterest']
        
        total_pain = call_pain + put_pain
        
        if total_pain < min_pain_value:
            min_pain_value = total_pain
            max_pain_strike = strike
    
    result['max_pain'] = float(max_pain_strike) if max_pain_strike else current_price
    
    # 5. GAMMA LEVELS - Strikes con alto OI que actúan como magnetos
    all_strikes = []
    for _, row in calls.iterrows():
        all_strikes.append({
            'strike': float(row['strike']),
            'oi': int(row['openInterest']),
            'type': 'CALL'
        })
    for _, row in puts.iterrows():
        all_strikes.append({
            'strike': float(row['strike']),
            'oi': int(row['openInterest']),
            'type': 'PUT'
        })
    
    # Top 5 por OI
    all_strikes.sort(key=lambda x: x['oi'], reverse=True)
    result['gamma_levels'] = all_strikes[:5]
    
    # 6. UNUSUAL ACTIVITY - Volume >> Open Interest
    unusual = []
    for _, row in calls.iterrows():
        vol = row['volume'] if not pd.isna(row['volume']) else 0
        oi = row['openInterest']
        if oi > 0 and vol > oi * 2:  # Volume es más de 2x el OI
            unusual.append({
                'strike': float(row['strike']),
                'type': 'CALL',
                'volume': int(vol),
                'oi': int(oi),
                'ratio': float(vol/oi)
            })
    for _, row in puts.iterrows():
        vol = row['volume'] if not pd.isna(row['volume']) else 0
        oi = row['openInterest']
        if oi > 0 and vol > oi * 2:
            unusual.append({
                'strike': float(row['strike']),
                'type': 'PUT',
                'volume': int(vol),
                'oi': int(oi),
                'ratio': float(vol/oi)
            })
    
    unusual.sort(key=lambda x: x['ratio'], reverse=True)
    result['unusual_activity'] = unusual[:5]
    
    return result


def analyze_direction(flow_data, current_price):
    """Determina dirección probable basada en flow"""
    
    signals = {
        'bullish': 0,
        'bearish': 0,
        'reasons': []
    }
    
    # 1. Put/Call Volume Ratio
    pcr = flow_data['volume']['ratio']
    if pcr < 0.7:
        signals['bullish'] += 2
        signals['reasons'].append(f'Put/Call Ratio BAJO ({pcr:.2f}) = Bullish')
    elif pcr > 1.3:
        signals['bearish'] += 2
        signals['reasons'].append(f'Put/Call Ratio ALTO ({pcr:.2f}) = Bearish')
    elif pcr > 1.0:
        signals['bearish'] += 1
        signals['reasons'].append(f'Put/Call Ratio >1 ({pcr:.2f}) = Ligeramente Bearish')
    else:
        signals['bullish'] += 1
        signals['reasons'].append(f'Put/Call Ratio <1 ({pcr:.2f}) = Ligeramente Bullish')
    
    # 2. Max Pain
    max_pain = flow_data['max_pain']
    diff = current_price - max_pain
    diff_pct = diff / current_price * 100
    
    if diff > 0 and abs(diff_pct) > 0.3:
        signals['bearish'] += 1
        signals['reasons'].append(f'Precio ARRIBA de Max Pain ({max_pain:.2f}) = Puede bajar')
    elif diff < 0 and abs(diff_pct) > 0.3:
        signals['bullish'] += 1
        signals['reasons'].append(f'Precio ABAJO de Max Pain ({max_pain:.2f}) = Puede subir')
    else:
        signals['reasons'].append(f'Precio CERCA de Max Pain ({max_pain:.2f}) = Neutral')
    
    # 3. Call Wall vs Put Wall
    call_wall = flow_data.get('call_wall', {}).get('strike', 0)
    put_wall = flow_data.get('put_wall', {}).get('strike', 0)
    
    if call_wall and put_wall:
        # Si precio está más cerca del call wall, puede actuar como resistencia
        dist_to_call = call_wall - current_price
        dist_to_put = current_price - put_wall
        
        if dist_to_call < dist_to_put and dist_to_call > 0:
            signals['bearish'] += 1
            signals['reasons'].append(f'Cerca de CALL WALL ({call_wall:.2f}) = Resistencia')
        elif dist_to_put < dist_to_call and dist_to_put > 0:
            signals['bullish'] += 1
            signals['reasons'].append(f'Cerca de PUT WALL ({put_wall:.2f}) = Soporte')
    
    # 4. Unusual Activity
    unusual = flow_data.get('unusual_activity', [])
    call_unusual = sum(1 for u in unusual if u['type'] == 'CALL')
    put_unusual = sum(1 for u in unusual if u['type'] == 'PUT')
    
    if call_unusual > put_unusual:
        signals['bullish'] += 1
        signals['reasons'].append(f'Unusual Activity en CALLS ({call_unusual}) = Smart money bullish')
    elif put_unusual > call_unusual:
        signals['bearish'] += 1
        signals['reasons'].append(f'Unusual Activity en PUTS ({put_unusual}) = Smart money bearish')
    
    # 5. Open Interest Distribution
    oi_ratio = flow_data['open_interest']['ratio']
    if oi_ratio < 0.8:
        signals['bullish'] += 1
        signals['reasons'].append(f'OI Put/Call bajo ({oi_ratio:.2f}) = Posicionamiento bullish')
    elif oi_ratio > 1.2:
        signals['bearish'] += 1
        signals['reasons'].append(f'OI Put/Call alto ({oi_ratio:.2f}) = Posicionamiento bearish')
    
    return signals


def main():
    symbol = 'SPY'
    
    print('=' * 70)
    print(f'    ANALISIS COMPLETO: {symbol}')
    print('    Técnicos + Flow de Opciones')
    print('=' * 70)
    
    # Obtener precio actual
    with open('config.yaml', 'r') as f:
        config = yaml.safe_load(f)
    
    client = StockHistoricalDataClient(
        config['alpaca']['api_key'],
        config['alpaca']['api_secret']
    )
    
    req = StockBarsRequest(
        symbol_or_symbols=symbol,
        timeframe=TimeFrame(15, TimeFrameUnit.Minute),
        start=datetime.now() - timedelta(days=2)
    )
    bars = client.get_stock_bars(req)
    
    df = pd.DataFrame([{
        'timestamp': b.timestamp,
        'open': b.open, 'high': b.high, 'low': b.low,
        'close': b.close, 'volume': b.volume, 'vwap': b.vwap
    } for b in bars.data[symbol]])
    df.set_index('timestamp', inplace=True)
    
    current_price = float(df['close'].iloc[-1])
    vwap = float(df['vwap'].iloc[-1])
    
    print(f'\nPRECIO ACTUAL: ${current_price:.2f}')
    print(f'VWAP: ${vwap:.2f}')
    print()
    
    # Obtener flow de opciones
    print('Analizando opciones...')
    flow = get_options_flow(symbol, current_price)
    
    if not flow:
        print('No se pudo obtener datos de opciones')
        return
    
    print()
    print('=' * 70)
    print('    FLOW DE OPCIONES')
    print('=' * 70)
    
    print(f'\nExpiracion: {flow["expiration"]}')
    
    # Call Wall
    if 'call_wall' in flow:
        cw = flow['call_wall']
        print(f'\nCALL WALL: ${cw["strike"]:.2f}')
        print(f'  Open Interest: {cw["oi"]:,}')
        print(f'  Volume: {cw["volume"]:,}')
        dist = cw["strike"] - current_price
        print(f'  Distancia: ${dist:.2f} ({dist/current_price*100:.2f}%)')
    
    # Put Wall
    if 'put_wall' in flow:
        pw = flow['put_wall']
        print(f'\nPUT WALL: ${pw["strike"]:.2f}')
        print(f'  Open Interest: {pw["oi"]:,}')
        print(f'  Volume: {pw["volume"]:,}')
        dist = current_price - pw["strike"]
        print(f'  Distancia: ${dist:.2f} ({dist/current_price*100:.2f}%)')
    
    # Max Pain
    print(f'\nMAX PAIN: ${flow["max_pain"]:.2f}')
    mp_dist = current_price - flow["max_pain"]
    print(f'  Precio vs Max Pain: ${mp_dist:+.2f}')
    if mp_dist > 0:
        print('  -> Precio ARRIBA de max pain (tiende a bajar)')
    else:
        print('  -> Precio ABAJO de max pain (tiende a subir)')
    
    # Volume
    print(f'\nVOLUMEN:')
    print(f'  Calls: {flow["volume"]["calls"]:,}')
    print(f'  Puts: {flow["volume"]["puts"]:,}')
    print(f'  Put/Call Ratio: {flow["volume"]["ratio"]:.2f}')
    
    # Open Interest
    print(f'\nOPEN INTEREST:')
    print(f'  Calls: {flow["open_interest"]["calls"]:,}')
    print(f'  Puts: {flow["open_interest"]["puts"]:,}')
    print(f'  Put/Call Ratio: {flow["open_interest"]["ratio"]:.2f}')
    
    # Gamma Levels
    print(f'\nGAMMA LEVELS (magnetos):')
    for level in flow['gamma_levels'][:5]:
        dist = level['strike'] - current_price
        print(f'  ${level["strike"]:.2f} ({level["type"]}) - OI: {level["oi"]:,} [{dist:+.2f}]')
    
    # Unusual Activity
    if flow['unusual_activity']:
        print(f'\nUNUSUAL ACTIVITY:')
        for ua in flow['unusual_activity'][:3]:
            print(f'  ${ua["strike"]:.2f} {ua["type"]} - Vol: {ua["volume"]:,} vs OI: {ua["oi"]:,} ({ua["ratio"]:.1f}x)')
    
    # Analizar dirección
    print()
    print('=' * 70)
    print('    ANALISIS DE DIRECCION')
    print('=' * 70)
    
    direction = analyze_direction(flow, current_price)
    
    print('\nSENALES:')
    for reason in direction['reasons']:
        print(f'  - {reason}')
    
    print(f'\nSCORE:')
    print(f'  Bullish: {direction["bullish"]}')
    print(f'  Bearish: {direction["bearish"]}')
    
    print()
    print('=' * 70)
    print('    PREDICCION')
    print('=' * 70)
    
    bull = direction['bullish']
    bear = direction['bearish']
    
    if bull > bear + 2:
        pred = 'FUERTE BULLISH - Alta probabilidad de subir'
        emoji = '🟢🟢🟢'
    elif bull > bear:
        pred = 'BULLISH - Probable que suba'
        emoji = '🟢'
    elif bear > bull + 2:
        pred = 'FUERTE BEARISH - Alta probabilidad de bajar'
        emoji = '🔴🔴🔴'
    elif bear > bull:
        pred = 'BEARISH - Probable que baje'
        emoji = '🔴'
    else:
        pred = 'NEUTRAL - Sin direccion clara'
        emoji = '⚪'
    
    print(f'\n{emoji} {pred}')
    
    # Targets basados en walls
    print('\nTARGETS PROBABLES:')
    if 'call_wall' in flow:
        print(f'  RESISTENCIA: ${flow["call_wall"]["strike"]:.2f} (Call Wall)')
    print(f'  MAGNETO: ${flow["max_pain"]:.2f} (Max Pain)')
    if 'put_wall' in flow:
        print(f'  SOPORTE: ${flow["put_wall"]["strike"]:.2f} (Put Wall)')
    
    print()
    print('=' * 70)


if __name__ == "__main__":
    main()
