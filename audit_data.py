#!/usr/bin/env python3
"""
AUDITORIA DE DATOS - Verificacion de fuentes
"""

import yaml
import yfinance as yf
from datetime import datetime, timedelta
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit

print('=' * 70)
print('    AUDITORIA DE DATOS - VERIFICACION')
print('=' * 70)

symbol = 'SPY'

# 1. ALPACA - Precio
print()
print('1. PRECIO (Alpaca API)')
print('-' * 70)

with open('config.yaml', 'r') as f:
    config = yaml.safe_load(f)

client = StockHistoricalDataClient(
    config['alpaca']['api_key'],
    config['alpaca']['api_secret']
)

req = StockBarsRequest(
    symbol_or_symbols=symbol,
    timeframe=TimeFrame(1, TimeFrameUnit.Minute),
    start=datetime.now() - timedelta(minutes=10)
)
bars = client.get_stock_bars(req)
last_bar = bars.data[symbol][-1]

print(f'   Fuente: Alpaca Markets API')
print(f'   Tipo: Datos de mercado')
print(f'   Timestamp: {last_bar.timestamp}')
print(f'   Open:  {last_bar.open}')
print(f'   High:  {last_bar.high}')
print(f'   Low:   {last_bar.low}')
print(f'   Close: {last_bar.close}')
print(f'   VWAP:  {last_bar.vwap}')
print(f'   Volume: {last_bar.volume}')
print()
print('   VERIFICAR: https://alpaca.markets')
print('              https://www.tradingview.com/symbols/SPY')

# 2. YAHOO FINANCE - Opciones
print()
print('2. OPCIONES (Yahoo Finance API)')
print('-' * 70)

ticker = yf.Ticker(symbol)
exp = ticker.options[0]
chain = ticker.option_chain(exp)

print(f'   Fuente: Yahoo Finance (yfinance library)')
print(f'   Tipo: Datos de opciones publicos')
print(f'   Expiracion: {exp}')
print(f'   Total Calls en cadena: {len(chain.calls)}')
print(f'   Total Puts en cadena: {len(chain.puts)}')
print()

# Muestra ejemplo de datos reales
print('   EJEMPLO - Call Strike 693:')
call_example = chain.calls[chain.calls['strike'] == 693.0]
if not call_example.empty:
    c = call_example.iloc[0]
    print(f'     Strike: {c.strike}')
    print(f'     Last Price: ${c.lastPrice}')
    print(f'     Bid: ${c.bid}')
    print(f'     Ask: ${c.ask}')
    print(f'     Volume: {c.volume}')
    print(f'     Open Interest: {c.openInterest}')
    iv = c.impliedVolatility * 100
    print(f'     Implied Vol: {iv:.1f}%')
print()
print('   VERIFICAR: https://finance.yahoo.com/quote/SPY/options')

# 3. CALCULOS
print()
print('3. MIS CALCULOS')
print('-' * 70)

price = float(last_bar.close)

# Put/Call Ratio
calls_near = chain.calls[(chain.calls['strike'] >= price - 20) & (chain.calls['strike'] <= price + 20)]
puts_near = chain.puts[(chain.puts['strike'] >= price - 20) & (chain.puts['strike'] <= price + 20)]

call_vol = calls_near['volume'].sum()
put_vol = puts_near['volume'].sum()
pcr = put_vol / call_vol if call_vol > 0 else 0

print(f'   PUT/CALL RATIO:')
print(f'     Formula: Put Volume / Call Volume')
print(f'     Put Volume (near strikes): {put_vol:,.0f}')
print(f'     Call Volume (near strikes): {call_vol:,.0f}')
print(f'     Resultado: {put_vol:,.0f} / {call_vol:,.0f} = {pcr:.4f}')
print()

# Walls
call_wall_idx = calls_near['openInterest'].idxmax()
put_wall_idx = puts_near['openInterest'].idxmax()

call_wall_row = calls_near.loc[call_wall_idx]
put_wall_row = puts_near.loc[put_wall_idx]

print(f'   CALL WALL:')
print(f'     Formula: Strike con MAYOR Open Interest en Calls')
print(f'     Strike: ${call_wall_row.strike}')
print(f'     Open Interest: {call_wall_row.openInterest:,.0f} contratos')
print()
print(f'   PUT WALL:')
print(f'     Formula: Strike con MAYOR Open Interest en Puts')
print(f'     Strike: ${put_wall_row.strike}')
print(f'     Open Interest: {put_wall_row.openInterest:,.0f} contratos')
print()

print('=' * 70)
print('    LIMITACIONES - SE HONESTO')
print('=' * 70)
print('''
   1. DELAY: Los datos pueden tener 1-15 minutos de retraso
   
   2. OPEN INTEREST: Se actualiza 1 vez al dia (no intraday)
      - El OI que ves es del cierre de AYER
      - El volume SI es de hoy
   
   3. MAX PAIN: Es un CALCULO, no dato oficial
      - Diferentes sitios dan diferentes valores
      - Es una APROXIMACION
   
   4. PREDICCIONES: Son PROBABILIDADES, no garantias
      - El mercado puede hacer lo contrario
      - Smart money puede estar equivocado
   
   5. YAHOO FINANCE: Datos gratuitos, puede haber errores
      - Para trading real, usar datos de tu broker
''')

print('=' * 70)
print('    COMO VERIFICAR TU MISMO')
print('=' * 70)
print('''
   PRECIO:
   - TradingView: tradingview.com/symbols/SPY
   - Yahoo: finance.yahoo.com/quote/SPY
   - Tu broker
   
   OPCIONES:
   - Yahoo: finance.yahoo.com/quote/SPY/options
   - CBOE: cboe.com
   - Tu broker
   
   MAX PAIN:
   - maximum-pain.com/options/spy
   - swaggystocks.com/dashboard/options-max-pain/SPY
   
   FLOW (de pago):
   - unusualwhales.com
   - flowdark.com
   - cheddarflow.com
''')

print('=' * 70)
print('    CONCLUSION')
print('=' * 70)
print('''
   Los DATOS son reales (de APIs publicas).
   Los CALCULOS son correctos matematicamente.
   Las PREDICCIONES son probabilidades, NO certezas.
   
   SIEMPRE verifica con tu broker antes de operar.
''')
print('=' * 70)
