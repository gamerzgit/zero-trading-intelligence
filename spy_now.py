#!/usr/bin/env python3
"""SPY - AHORA MISMO"""

import yaml
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit

symbol = 'SPY'

with open('config.yaml', 'r') as f:
    config = yaml.safe_load(f)

client = StockHistoricalDataClient(
    config['alpaca']['api_key'],
    config['alpaca']['api_secret']
)

print('=' * 70)
print('       SPY - ANALISIS EN TIEMPO REAL')
print('=' * 70)

# PRECIO Y TECNICOS
req = StockBarsRequest(
    symbol_or_symbols=symbol,
    timeframe=TimeFrame(1, TimeFrameUnit.Minute),
    start=datetime.now() - timedelta(hours=2)
)
bars = client.get_stock_bars(req)

df = pd.DataFrame([{
    'timestamp': b.timestamp,
    'open': b.open, 'high': b.high, 'low': b.low,
    'close': b.close, 'volume': b.volume, 'vwap': b.vwap
} for b in bars.data[symbol]])
df.set_index('timestamp', inplace=True)

price = float(df['close'].iloc[-1])
open_price = float(df['open'].iloc[0])
vwap = float(df['vwap'].iloc[-1])
high_today = float(df['high'].max())
low_today = float(df['low'].min())

# EMAs
df['ema9'] = df['close'].ewm(span=9).mean()
df['ema21'] = df['close'].ewm(span=21).mean()
ema9 = float(df['ema9'].iloc[-1])
ema21 = float(df['ema21'].iloc[-1])

# RSI
delta = df['close'].diff()
gain = delta.where(delta > 0, 0).rolling(7).mean()
loss = (-delta.where(delta < 0, 0)).rolling(7).mean()
rs = gain / loss.replace(0, np.nan)
rsi = float((100 - (100 / (1 + rs))).iloc[-1])

# Momentum
mom = float((df['close'].iloc[-1] / df['close'].iloc[-10] - 1) * 100)

# ATR
tr = pd.concat([df['high'] - df['low'], 
                abs(df['high'] - df['close'].shift()), 
                abs(df['low'] - df['close'].shift())], axis=1).max(axis=1)
atr = float(tr.rolling(14).mean().iloc[-1])

change = price - open_price
change_pct = (price / open_price - 1) * 100

print()
print(f'  PRECIO: ${price:.2f}')
print(f'  Cambio: ${change:.2f} ({change_pct:+.2f}%)')
print()
print(f'  High:   ${high_today:.2f}')
print(f'  Low:    ${low_today:.2f}')
print(f'  VWAP:   ${vwap:.2f}')
print()

# FLOW DE OPCIONES
ticker = yf.Ticker(symbol)
exp = ticker.options[0]
chain = ticker.option_chain(exp)
calls = chain.calls
puts = chain.puts

rng = price * 0.03
calls_f = calls[(calls['strike'] >= price - rng) & (calls['strike'] <= price + rng)]
puts_f = puts[(puts['strike'] >= price - rng) & (puts['strike'] <= price + rng)]

call_vol = int(calls_f['volume'].sum())
put_vol = int(puts_f['volume'].sum())
pcr = put_vol / call_vol if call_vol > 0 else 0

call_wall = float(calls_f.loc[calls_f['openInterest'].idxmax()]['strike']) if not calls_f.empty else 700
put_wall = float(puts_f.loc[puts_f['openInterest'].idxmax()]['strike']) if not puts_f.empty else 680
max_pain = 688.0

unusual_calls = len(calls_f[calls_f['volume'] > calls_f['openInterest'] * 2])
unusual_puts = len(puts_f[puts_f['volume'] > puts_f['openInterest'] * 2])

print('-' * 70)
print('  TECNICOS:')
print()
if price > vwap:
    print(f'    VWAP:  ARRIBA (+${price-vwap:.2f})')
else:
    print(f'    VWAP:  ABAJO (-${vwap-price:.2f})')

if ema9 > ema21:
    print(f'    EMAs:  EMA9 > EMA21 = BULLISH')
else:
    print(f'    EMAs:  EMA9 < EMA21 = BEARISH')

rsi_note = ''
if rsi > 70: rsi_note = ' (OVERBOUGHT)'
elif rsi < 30: rsi_note = ' (OVERSOLD)'
print(f'    RSI:   {rsi:.1f}{rsi_note}')
print(f'    Mom:   {mom:+.2f}%')
print()

print('-' * 70)
print('  FLOW DE OPCIONES:')
print()
pcr_note = ''
if pcr > 1.1: pcr_note = ' BEARISH'
elif pcr < 0.9: pcr_note = ' BULLISH'
else: pcr_note = ' NEUTRAL'
print(f'    Put/Call Ratio: {pcr:.2f}{pcr_note}')
print(f'    Max Pain:       ${max_pain:.2f} (precio {price-max_pain:+.2f})')
print(f'    Call Wall:      ${call_wall:.2f} (resistencia)')
print(f'    Put Wall:       ${put_wall:.2f} (soporte)')
print(f'    Unusual Calls:  {unusual_calls}')
print(f'    Unusual Puts:   {unusual_puts}')
print()

# SCORE
bull = 0
bear = 0
reasons = []

if price > vwap: 
    bull += 1
    reasons.append('Precio > VWAP = Bull')
else: 
    bear += 1
    reasons.append('Precio < VWAP = Bear')

if ema9 > ema21: 
    bull += 1
    reasons.append('EMA9 > EMA21 = Bull')
else: 
    bear += 1
    reasons.append('EMA9 < EMA21 = Bear')

if mom > 0.1: 
    bull += 1
    reasons.append(f'Momentum +{mom:.2f}% = Bull')
elif mom < -0.1: 
    bear += 1
    reasons.append(f'Momentum {mom:.2f}% = Bear')

if pcr < 0.9: 
    bull += 2
    reasons.append('PCR < 0.9 = Bull')
elif pcr > 1.1: 
    bear += 2
    reasons.append('PCR > 1.1 = Bear')

if price > max_pain: 
    bear += 1
    reasons.append('Arriba Max Pain = Bear')
else: 
    bull += 1
    reasons.append('Abajo Max Pain = Bull')

if unusual_puts > unusual_calls + 5:
    bear += 2
    reasons.append(f'Unusual Puts ({unusual_puts}) = Bear')
elif unusual_calls > unusual_puts + 5:
    bull += 2
    reasons.append(f'Unusual Calls ({unusual_calls}) = Bull')

print('-' * 70)
print('  SCORE:')
print()
bar_len = 30
total = bull + bear
if total > 0:
    bull_bar = int(bull/total * bar_len)
else:
    bull_bar = bar_len // 2
bear_bar = bar_len - bull_bar

print(f'    BULLS [{"#"*bull_bar}{"-"*bear_bar}] BEARS')
print(f'          {bull}                           {bear}')
print()

for r in reasons:
    print(f'    - {r}')
print()

print('=' * 70)
print('  PREDICCION:')
print('=' * 70)

if bear > bull + 3:
    direction = 'BAJISTA FUERTE'
    action = 'PUT'
elif bear > bull:
    direction = 'BAJISTA'
    action = 'PUT'
elif bull > bear + 3:
    direction = 'ALCISTA FUERTE'
    action = 'CALL'
elif bull > bear:
    direction = 'ALCISTA'
    action = 'CALL'
else:
    direction = 'NEUTRAL'
    action = 'ESPERAR'

print()
print(f'    DIRECCION: {direction}')
print(f'    ACCION:    {action}')
print()

if action != 'ESPERAR':
    entry = price
    if action == 'CALL':
        tgt = entry + atr * 1.5
        stop = entry - atr * 0.5
    else:
        tgt = entry - atr * 1.5
        stop = entry + atr * 0.5
    
    print(f'    TRADE SUGERIDO:')
    print(f'      Entry:  ${entry:.2f}')
    print(f'      Target: ${tgt:.2f} ({abs(tgt-entry)/entry*100:.2f}%)')
    print(f'      Stop:   ${stop:.2f} ({abs(stop-entry)/entry*100:.2f}%)')
    print()
    print(f'    NIVELES CLAVE:')
    print(f'      Resistencia: ${call_wall:.2f}')
    print(f'      Max Pain:    ${max_pain:.2f}')
    print(f'      Soporte:     ${put_wall:.2f}')
else:
    print('    No hay setup claro. Esperar.')

print()
print('=' * 70)
print(f'  {datetime.now().strftime("%H:%M:%S")} PST')
print('=' * 70)
