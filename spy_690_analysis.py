#!/usr/bin/env python3
"""Analisis: SPY va a bajar a 690?"""

import yaml
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit

with open('config.yaml', 'r') as f:
    config = yaml.safe_load(f)

client = StockHistoricalDataClient(
    config['alpaca']['api_key'],
    config['alpaca']['api_secret']
)

print('=' * 60)
print('    ANALISIS: SPY VA A BAJAR A 690?')
print('=' * 60)

req = StockBarsRequest(
    symbol_or_symbols='SPY',
    timeframe=TimeFrame(15, TimeFrameUnit.Minute),
    start=datetime.now() - timedelta(days=5)
)
bars = client.get_stock_bars(req)

df = pd.DataFrame([{
    'timestamp': b.timestamp,
    'open': b.open, 'high': b.high, 'low': b.low,
    'close': b.close, 'volume': b.volume, 'vwap': b.vwap
} for b in bars.data['SPY']])
df['timestamp'] = pd.to_datetime(df['timestamp'])
df.set_index('timestamp', inplace=True)

# ATR
high = df['high']
low = df['low']
close = df['close']
tr = pd.concat([high - low, abs(high - close.shift()), abs(low - close.shift())], axis=1).max(axis=1)
df['atr'] = tr.rolling(14).mean()

# Datos actuales
current = float(df['close'].iloc[-1])
atr = float(df['atr'].iloc[-1])
target = 690.0

# Calculos
distance = current - target
distance_pct = distance / current * 100
atr_moves = distance / atr

# Historico de hoy
today = df[df.index.date == df.index[-1].date()]
today_high = float(today['high'].max())
today_low = float(today['low'].min())
today_range = today_high - today_low

print()
print(f'PRECIO ACTUAL: {current:.2f}')
print(f'TARGET: 690.00')
print()
print('DISTANCIA:')
print(f'  Dolares: {distance:.2f}')
print(f'  Porcentaje: {distance_pct:.2f}%')
print(f'  ATRs: {atr_moves:.1f} (ATR = {atr:.2f})')
print()
print('HOY:')
print(f'  High: {today_high:.2f}')
print(f'  Low: {today_low:.2f}')
print(f'  Rango: {today_range:.2f}')
print()
print('MOVIMIENTO TIPICO (ATR):')
print(f'  1 ATR = {atr:.2f}')
print(f'  2 ATR = {atr*2:.2f}')
print(f'  3 ATR = {atr*3:.2f}')
print()
print(f'PARA LLEGAR A 690:')
print(f'  Necesita bajar {distance:.2f} ({distance_pct:.2f}%)')
print(f'  Eso es {atr_moves:.1f} ATRs de movimiento')
print()

# Probabilidad basada en ATR
if atr_moves <= 1:
    prob = 'ALTA (dentro de 1 ATR)'
elif atr_moves <= 2:
    prob = 'MEDIA (dentro de 2 ATRs)'
elif atr_moves <= 3:
    prob = 'BAJA (necesita 3 ATRs)'
else:
    prob = 'MUY BAJA (necesita mas de 3 ATRs)'

print(f'PROBABILIDAD HOY: {prob}')
print()

# Analisis tecnico
ema9 = float(df['close'].ewm(span=9).mean().iloc[-1])
ema21 = float(df['close'].ewm(span=21).mean().iloc[-1])
ema50 = float(df['close'].ewm(span=50).mean().iloc[-1])

print('ANALISIS TECNICO:')
if current < ema9 < ema21 < ema50:
    print('  EMA Stack: BEARISH - Favorece caida')
    bear_stack = True
elif current > ema9 > ema21 > ema50:
    print('  EMA Stack: BULLISH - NO favorece caida')
    bear_stack = False
else:
    print('  EMA Stack: MIXTO - Sin direccion clara')
    bear_stack = False

# RSI
delta = df['close'].diff()
gain = delta.where(delta > 0, 0).rolling(7).mean()
loss = (-delta.where(delta < 0, 0)).rolling(7).mean()
rs = gain / loss.replace(0, np.nan)
rsi = float((100 - (100 / (1 + rs))).iloc[-1])

if rsi > 70:
    print(f'  RSI: {rsi:.1f} - OVERBOUGHT, posible correccion hacia abajo')
    rsi_bearish = True
elif rsi < 30:
    print(f'  RSI: {rsi:.1f} - OVERSOLD, posible rebote hacia arriba')
    rsi_bearish = False
else:
    print(f'  RSI: {rsi:.1f} - Neutral')
    rsi_bearish = False

# VWAP
vwap = float(df['vwap'].iloc[-1])
if current < vwap:
    print(f'  VWAP: Precio DEBAJO de {vwap:.2f} - Favorece caida')
    vwap_bearish = True
else:
    print(f'  VWAP: Precio ARRIBA de {vwap:.2f} - NO favorece caida')
    vwap_bearish = False

print()
print('=' * 60)
print('    VEREDICTO')
print('=' * 60)

bearish_signals = sum([bear_stack, rsi_bearish, vwap_bearish])

if atr_moves > 4:
    print()
    print('  690 esta MUY LEJOS')
    print(f'  Distancia: {distance:.2f} ({atr_moves:.1f} ATRs)')
    print()
    print('  Para que SPY llegue a 690 HOY necesitaria:')
    print('  - Crash del mercado')
    print('  - Bad news de Fed/economía')
    print('  - Evento inesperado')
    print()
    print('  RESPUESTA: IMPROBABLE en condiciones normales')
elif atr_moves > 2:
    print()
    print('  690 es DIFICIL pero no imposible')
    print(f'  Distancia: {distance:.2f} ({atr_moves:.1f} ATRs)')
    print()
    if bearish_signals >= 2:
        print('  Senales bearish presentes, POSIBLE si:')
        print('  - Rompe soporte clave')
        print('  - Aumenta volumen de venta')
        print('  - News negativas')
    else:
        print('  No hay suficientes senales bearish')
        print('  RESPUESTA: POCO PROBABLE')
elif atr_moves > 1:
    print()
    print('  690 esta ALCANZABLE')
    print(f'  Distancia: {distance:.2f} ({atr_moves:.1f} ATRs)')
    print()
    if bearish_signals >= 2:
        print('  HAY senales bearish:')
        print('  RESPUESTA: POSIBLE si confirma rompimiento')
    else:
        print('  Pero NO hay confirmacion bearish')
        print('  RESPUESTA: Esperar confirmacion')
else:
    print()
    print('  690 esta MUY CERCA')
    print(f'  Distancia: {distance:.2f} (solo {atr_moves:.1f} ATRs)')
    print()
    print('  RESPUESTA: PROBABLE si confirma direccion')

print()
print('=' * 60)
print('DISCLAIMER: Esto es analisis tecnico, NO prediccion.')
print('El mercado puede hacer cualquier cosa.')
print('=' * 60)
