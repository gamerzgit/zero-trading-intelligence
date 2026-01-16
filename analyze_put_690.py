#!/usr/bin/env python3
"""
Analisis: PUT SPY $690 - Vale la pena?
"""

import yaml
import yfinance as yf
from datetime import datetime, timedelta
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit

symbol = 'SPY'
target_strike = 690.0

with open('config.yaml', 'r') as f:
    config = yaml.safe_load(f)

client = StockHistoricalDataClient(
    config['alpaca']['api_key'],
    config['alpaca']['api_secret']
)

# Precio actual
req = StockBarsRequest(
    symbol_or_symbols=symbol,
    timeframe=TimeFrame(1, TimeFrameUnit.Minute),
    start=datetime.now() - timedelta(hours=2)
)
bars = client.get_stock_bars(req)
price = float(bars.data[symbol][-1].close)
vwap = float(bars.data[symbol][-1].vwap)

# Datos de hoy
df_today = [b for b in bars.data[symbol]]
high_today = max(b.high for b in df_today)
low_today = min(b.low for b in df_today)

# Opciones
ticker = yf.Ticker(symbol)
exp = ticker.options[0]
chain = ticker.option_chain(exp)

# El put de 690
put_690 = chain.puts[chain.puts['strike'] == target_strike]

print('=' * 70)
print(f'    ANALISIS: PUT SPY 690 - 0DTE')
print('=' * 70)
print()
print(f'  PRECIO ACTUAL:  {price:.2f}')
print(f'  TARGET STRIKE:  {target_strike:.2f}')
print(f'  DISTANCIA:      {price - target_strike:.2f} ({(price - target_strike)/price*100:.2f}%)')
print()

if not put_690.empty:
    p = put_690.iloc[0]
    print(f'  PUT 690 DATOS ACTUALES:')
    print(f'    Bid:    {p.bid:.2f}')
    print(f'    Ask:    {p.ask:.2f}')
    print(f'    Last:   {p.lastPrice:.2f}')
    print(f'    Volume: {int(p.volume):,}')
    print(f'    OI:     {int(p.openInterest):,}')
    print()

print(f'  RANGO DE HOY:')
print(f'    High: {high_today:.2f}')
print(f'    Low:  {low_today:.2f}')
ya_toco = "SI!" if low_today <= 690 else "NO"
print(f'    Ya toco 690?: {ya_toco}')
print()

# Calculos
max_pain = 688.0
put_wall = 680.0

favorable = 0
unfavorable = 0

print('-' * 70)
print('  FACTORES A FAVOR (para que baje a 690):')
print('-' * 70)

# Max Pain
print(f'    + Max Pain (688) esta ABAJO de tu strike')
print(f'      El precio tiende a ir hacia max pain')
favorable += 1

# Put/Call ratio
calls_near = chain.calls[(chain.calls['strike'] >= price - 10) & (chain.calls['strike'] <= price + 10)]
puts_near = chain.puts[(chain.puts['strike'] >= price - 10) & (chain.puts['strike'] <= price + 10)]
call_vol = calls_near['volume'].sum()
put_vol = puts_near['volume'].sum()
pcr = put_vol / call_vol if call_vol > 0 else 1

if pcr > 1:
    print(f'    + Put/Call Ratio ({pcr:.2f}) = mas puts que calls')
    favorable += 1
else:
    print(f'    - Put/Call Ratio ({pcr:.2f}) no muy favorable')

# Unusual activity
unusual_puts = len(puts_near[puts_near['volume'] > puts_near['openInterest'] * 2])
if unusual_puts > 5:
    print(f'    + Unusual activity en puts ({unusual_puts} strikes)')
    print(f'      Smart money apostando a caida')
    favorable += 2
else:
    print(f'    + Unusual puts: {unusual_puts} strikes')

# Low del dia
if low_today <= target_strike + 1:
    print(f'    + Low del dia ({low_today:.2f}) cerca de tu strike')
    favorable += 2

print()
print('-' * 70)
print('  FACTORES EN CONTRA:')
print('-' * 70)

# VWAP
if price > vwap:
    print(f'    - Precio ({price:.2f}) arriba de VWAP ({vwap:.2f})')
    print(f'      Tecnicamente alcista')
    unfavorable += 1

# Distancia
dist = price - target_strike
if dist > 2:
    print(f'    - Distancia de {dist:.2f} es significativa para 0DTE')
    unfavorable += 1

# Tiempo restante
now = datetime.now()
# Market close es 1 PM PST / 4 PM ET
minutes_left = 30  # Aproximado ya que no se la hora exacta
print(f'    - Poco tiempo restante (0DTE)')
print(f'      Theta te come rapido')
unfavorable += 1

# OTM
print(f'    - El put 690 esta OTM (Out of The Money)')
print(f'      Necesita que SPY BAJE a 690 para valer algo')
unfavorable += 1

print()
print('=' * 70)
print('  EL TRADE')
print('=' * 70)

if not put_690.empty:
    p = put_690.iloc[0]
    cost = p.ask
    print()
    print(f'    SI COMPRAS PUT 690:')
    print(f'    ----------------------')
    print(f'    Costo: ~{cost:.2f} por contrato')
    print(f'    Por 1 contrato (100 acciones): {cost * 100:.0f} USD')
    print()
    print(f'    ESCENARIOS:')
    print()
    print(f'    1. SPY baja a 689:')
    print(f'       Put valdria ~1.00-1.50')
    print(f'       Ganancia: {((1.0 - cost)/cost)*100:.0f}% a {((1.5 - cost)/cost)*100:.0f}%')
    print()
    print(f'    2. SPY baja a 688 (max pain):')
    print(f'       Put valdria ~2.00-2.50')
    print(f'       Ganancia: {((2.0 - cost)/cost)*100:.0f}% a {((2.5 - cost)/cost)*100:.0f}%')
    print()
    print(f'    3. SPY se queda en 692-693:')
    print(f'       Put expira sin valor')
    print(f'       Pierdes: 100% ({cost * 100:.0f} USD)')
    print()
    print(f'    4. SPY sube a 695:')
    print(f'       Put expira sin valor')
    print(f'       Pierdes: 100% ({cost * 100:.0f} USD)')

print()
print('=' * 70)
print('  VEREDICTO')
print('=' * 70)
print()

score = favorable - unfavorable

if low_today <= 690.5:
    print('    SPY YA TOCO 690 HOY!')
    print('    Esto significa que SI puede volver a llegar.')
    print()
    print('    PERO: Si no ha vuelto, puede que los bulls')
    print('    esten defendiendo ese nivel.')
    prob = 'MEDIA-ALTA'
elif low_today <= 691:
    print(f'    Low de hoy: {low_today:.2f} (cerca de 690)')
    print('    POSIBLE que llegue, pero ajustado.')
    prob = 'MEDIA'
else:
    dist_to_low = low_today - 690
    print(f'    Low de hoy: {low_today:.2f}')
    print(f'    Necesita bajar {dist_to_low:.2f} mas para llegar a 690')
    if dist_to_low > 2:
        prob = 'BAJA'
        print('    Dificil en poco tiempo')
    else:
        prob = 'MEDIA'

print()
print(f'    PROBABILIDAD DE LLEGAR A 690: {prob}')
print()
print('    RIESGO/RECOMPENSA:')
print('    - Riesgo: Perder 100% de la prima')
print('    - Recompensa: 100-400% si llega')
print()
print('=' * 70)
print('    ESTO NO ES CONSEJO FINANCIERO')
print('    LA DECISION ES TUYA')
print('=' * 70)
