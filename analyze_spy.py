#!/usr/bin/env python3
"""Analisis SPY en tiempo real"""

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
print('    ANALISIS SPY EN TIEMPO REAL')
print('=' * 60)

req = StockBarsRequest(
    symbol_or_symbols='SPY',
    timeframe=TimeFrame(15, TimeFrameUnit.Minute),
    start=datetime.now() - timedelta(days=2)
)
bars = client.get_stock_bars(req)

df = pd.DataFrame([{
    'timestamp': b.timestamp,
    'open': b.open, 'high': b.high, 'low': b.low,
    'close': b.close, 'volume': b.volume, 'vwap': b.vwap
} for b in bars.data['SPY']])
df['timestamp'] = pd.to_datetime(df['timestamp'])
df.set_index('timestamp', inplace=True)

close = df['close']
high = df['high']
low = df['low']

# RSI
delta = close.diff()
gain = delta.where(delta > 0, 0).rolling(7).mean()
loss = (-delta.where(delta < 0, 0)).rolling(7).mean()
rs = gain / loss.replace(0, np.nan)
df['rsi'] = 100 - (100 / (1 + rs))

# MACD
ema_fast = close.ewm(span=6).mean()
ema_slow = close.ewm(span=13).mean()
df['macd_hist'] = ema_fast - ema_slow - (ema_fast - ema_slow).ewm(span=5).mean()

# EMAs
df['ema9'] = close.ewm(span=9).mean()
df['ema21'] = close.ewm(span=21).mean()
df['ema50'] = close.ewm(span=50).mean()

# ATR
tr = pd.concat([high - low, abs(high - close.shift()), abs(low - close.shift())], axis=1).max(axis=1)
df['atr'] = tr.rolling(14).mean()

# ADX
plus_dm = high.diff()
minus_dm = -low.diff()
plus_dm = plus_dm.where((plus_dm > minus_dm) & (plus_dm > 0), 0)
minus_dm = minus_dm.where((minus_dm > plus_dm) & (minus_dm > 0), 0)
atr_calc = df['atr'].replace(0, np.nan)
plus_di = 100 * (plus_dm.rolling(14).mean() / atr_calc)
minus_di = 100 * (minus_dm.rolling(14).mean() / atr_calc)
dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di).replace(0, np.nan)
df['adx'] = dx.rolling(14).mean()

# Volume
df['vol_sma'] = df['volume'].rolling(20).mean()
df['vol_ratio'] = df['volume'] / df['vol_sma'].replace(0, np.nan)
df['mom'] = close.pct_change(5) * 100

# Current and previous
row = df.iloc[-1]
prev = df.iloc[-2]

price = float(row['close'])
vwap = float(row['vwap'])
ema9 = float(row['ema9'])
ema21 = float(row['ema21'])
ema50 = float(row['ema50'])
rsi = float(row['rsi'])
adx = float(row['adx'])
macd = float(row['macd_hist'])
atr = float(row['atr'])
vol = float(row['vol_ratio'])
mom = float(row['mom'])

print()
print(f'PRECIO ACTUAL: ${price:.2f}')
print(f'Timestamp: {row.name}')
print()
print('NIVELES CLAVE:')
vwap_pos = 'ARRIBA' if price > vwap else 'ABAJO'
ema9_pos = 'ARRIBA' if price > ema9 else 'ABAJO'
print(f'  VWAP:  ${vwap:.2f} <- Precio {vwap_pos}')
print(f'  EMA9:  ${ema9:.2f} <- Precio {ema9_pos}')
print(f'  EMA21: ${ema21:.2f}')
print(f'  EMA50: ${ema50:.2f}')
print()
print('INDICADORES:')
rsi_note = '(OVERSOLD)' if rsi < 30 else '(OVERBOUGHT)' if rsi > 70 else ''
adx_note = '(TRENDING)' if adx > 25 else '(NO TREND)'
macd_note = '(BULLISH)' if macd > 0 else '(BEARISH)'
vol_note = '(HIGH)' if vol > 1.5 else ''
print(f'  RSI:   {rsi:.1f} {rsi_note}')
print(f'  ADX:   {adx:.1f} {adx_note}')
print(f'  MACD:  {macd:.4f} {macd_note}')
print(f'  Vol:   {vol:.1f}x {vol_note}')
print(f'  Mom:   {mom:+.2f}%')
print()
print('EMA STACK:')
ema9_21 = 'SI' if ema9 > ema21 else 'NO'
ema21_50 = 'SI' if ema21 > ema50 else 'NO'
stack_bull = ema9 > ema21 > ema50
stack_bear = ema9 < ema21 < ema50
print(f'  EMA9 > EMA21: {ema9_21}')
print(f'  EMA21 > EMA50: {ema21_50}')
bull_str = 'SI' if stack_bull else 'NO'
bear_str = 'SI' if stack_bear else 'NO'
print(f'  Bullish Stack: {bull_str}')
print(f'  Bearish Stack: {bear_str}')
print()
print('CRUCES RECIENTES:')
vwap_cross_up = price > vwap and float(prev['close']) <= float(prev['vwap'])
vwap_cross_dn = price < vwap and float(prev['close']) >= float(prev['vwap'])
macd_cross_up = macd > 0 and float(prev['macd_hist']) <= 0
macd_cross_dn = macd < 0 and float(prev['macd_hist']) >= 0

vwap_cross_str = 'ALCISTA!' if vwap_cross_up else ('BAJISTA!' if vwap_cross_dn else 'No')
macd_cross_str = 'ALCISTA!' if macd_cross_up else ('BAJISTA!' if macd_cross_dn else 'No')
print(f'  VWAP cruce: {vwap_cross_str}')
print(f'  MACD cruce: {macd_cross_str}')
print()

# Count signals
b, s = 0, 0
if price > vwap: b += 1
else: s += 1
if ema9 > ema21: b += 1
else: s += 1
if stack_bull: b += 1
elif stack_bear: s += 1
if macd > 0: b += 1
elif macd < 0: s += 1
if 50 < rsi < 70: b += 1
elif 30 < rsi < 50: s += 1
if mom > 0.1: b += 1
elif mom < -0.1: s += 1
if vol > 1.2:
    if b > s: b += 1
    elif s > b: s += 1
if vwap_cross_up: b += 1
if vwap_cross_dn: s += 1
if macd_cross_up: b += 1
if macd_cross_dn: s += 1

print(f'SCORE: Bullish={b} vs Bearish={s}')
print()

if b > s and b >= 4 and adx > 20:
    target = price + atr * 1.0
    stop = price - atr * 0.5
    rr = (target-price)/(price-stop)
    print('*' * 40)
    print('*** SENAL: CALL ***')
    print('*' * 40)
    print(f'  Entry:  ${price:.2f}')
    print(f'  Target: ${target:.2f} (+${target-price:.2f})')
    print(f'  Stop:   ${stop:.2f} (-${price-stop:.2f})')
    print(f'  R:R     {rr:.1f}:1')
elif s > b and s >= 4 and adx > 20:
    target = price - atr * 1.0
    stop = price + atr * 0.5
    rr = (price-target)/(stop-price)
    print('*' * 40)
    print('*** SENAL: PUT ***')
    print('*' * 40)
    print(f'  Entry:  ${price:.2f}')
    print(f'  Target: ${target:.2f} (-${price-target:.2f})')
    print(f'  Stop:   ${stop:.2f} (+${stop-price:.2f})')
    print(f'  R:R     {rr:.1f}:1')
else:
    print('NO HAY SENAL CLARA')
    reason = []
    if adx <= 20:
        reason.append(f'ADX={adx:.1f} (necesita >20)')
    if max(b, s) < 4:
        reason.append(f'Score={max(b,s)} (necesita >=4)')
    if b == s:
        reason.append('Empate bullish/bearish')
    print(f'  Razon: {", ".join(reason)}')
    print()
    print('  Esperando mejor setup...')
