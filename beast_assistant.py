#!/usr/bin/env python3
"""
BEAST TRADING ASSISTANT
=======================
Asistente interactivo para analisis de trading.
Puede correr con o sin LLM local.

Uso:
  python beast_assistant.py              # Modo CLI
  python beast_assistant.py --telegram   # Modo Telegram Bot
"""

import yaml
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
import re
import sys

# Alpaca
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit

class BeastAssistant:
    """Asistente de trading interactivo"""
    
    def __init__(self):
        with open('config.yaml', 'r') as f:
            self.config = yaml.safe_load(f)
        
        self.client = StockHistoricalDataClient(
            self.config['alpaca']['api_key'],
            self.config['alpaca']['api_secret']
        )
        
        # Cache para no repetir llamadas
        self.cache = {}
        self.cache_time = {}
        
    def get_price_data(self, symbol: str, minutes: int = 60) -> pd.DataFrame:
        """Obtiene datos de precio con cache"""
        cache_key = f"{symbol}_{minutes}"
        now = datetime.now()
        
        # Cache de 1 minuto
        if cache_key in self.cache:
            if (now - self.cache_time[cache_key]).seconds < 60:
                return self.cache[cache_key]
        
        req = StockBarsRequest(
            symbol_or_symbols=symbol,
            timeframe=TimeFrame(1, TimeFrameUnit.Minute),
            start=now - timedelta(minutes=minutes)
        )
        bars = self.client.get_stock_bars(req)
        
        if symbol not in bars.data:
            return pd.DataFrame()
        
        df = pd.DataFrame([{
            'timestamp': b.timestamp,
            'open': float(b.open),
            'high': float(b.high),
            'low': float(b.low),
            'close': float(b.close),
            'volume': float(b.volume),
            'vwap': float(b.vwap)
        } for b in bars.data[symbol]])
        
        self.cache[cache_key] = df
        self.cache_time[cache_key] = now
        
        return df
    
    def get_options_data(self, symbol: str) -> Dict:
        """Obtiene datos de opciones"""
        try:
            ticker = yf.Ticker(symbol)
            exp = ticker.options[0]  # Primera expiracion (0DTE si existe)
            chain = ticker.option_chain(exp)
            
            return {
                'expiration': exp,
                'calls': chain.calls,
                'puts': chain.puts
            }
        except Exception as e:
            return {'error': str(e)}
    
    def analyze_symbol(self, symbol: str) -> str:
        """Analisis completo de un simbolo"""
        symbol = symbol.upper()
        df = self.get_price_data(symbol, 120)
        
        if df.empty:
            return f"No pude obtener datos para {symbol}"
        
        price = df['close'].iloc[-1]
        vwap = df['vwap'].iloc[-1]
        high = df['high'].max()
        low = df['low'].min()
        
        # Calculos tecnicos
        df['ema9'] = df['close'].ewm(span=9).mean()
        df['ema21'] = df['close'].ewm(span=21).mean()
        df['rsi'] = self._calc_rsi(df['close'])
        
        ema9 = df['ema9'].iloc[-1]
        ema21 = df['ema21'].iloc[-1]
        rsi = df['rsi'].iloc[-1]
        
        # Momentum
        momentum = ((price - df['close'].iloc[-10]) / df['close'].iloc[-10]) * 100
        
        # Construir respuesta
        lines = [
            f"{'='*50}",
            f"  {symbol} - ANALISIS",
            f"{'='*50}",
            f"",
            f"  PRECIO: ${price:.2f}",
            f"  VWAP:   ${vwap:.2f} {'(arriba)' if price > vwap else '(abajo)'}",
            f"  High:   ${high:.2f}",
            f"  Low:    ${low:.2f}",
            f"",
            f"  TECNICOS:",
            f"    EMA9:  ${ema9:.2f}",
            f"    EMA21: ${ema21:.2f}",
            f"    RSI:   {rsi:.1f}",
            f"    Mom:   {momentum:+.2f}%",
            f"",
        ]
        
        # Direccion
        bullish = 0
        bearish = 0
        
        if price > vwap:
            bullish += 1
        else:
            bearish += 1
            
        if ema9 > ema21:
            bullish += 1
        else:
            bearish += 1
            
        if rsi > 50:
            bullish += 1
        else:
            bearish += 1
            
        if momentum > 0:
            bullish += 1
        else:
            bearish += 1
        
        lines.append(f"  SCORE: Bulls {bullish} vs Bears {bearish}")
        lines.append(f"")
        
        if bullish > bearish:
            lines.append(f"  >> TENDENCIA: ALCISTA (CALL)")
        elif bearish > bullish:
            lines.append(f"  >> TENDENCIA: BAJISTA (PUT)")
        else:
            lines.append(f"  >> TENDENCIA: NEUTRAL")
        
        lines.append(f"{'='*50}")
        
        return "\n".join(lines)
    
    def analyze_option_target(self, symbol: str, strike: float, option_type: str = 'put') -> str:
        """Analiza probabilidad de llegar a un strike"""
        symbol = symbol.upper()
        df = self.get_price_data(symbol, 120)
        
        if df.empty:
            return f"No pude obtener datos para {symbol}"
        
        price = df['close'].iloc[-1]
        high = df['high'].max()
        low = df['low'].min()
        
        # Distancia
        if option_type.lower() == 'put':
            distance = price - strike
            direction = "bajar"
            favorable_if = price < strike
        else:
            distance = strike - price
            direction = "subir"
            favorable_if = price > strike
        
        # ATR aproximado
        df['tr'] = df['high'] - df['low']
        atr = df['tr'].mean()
        
        # Cuantos ATRs necesita moverse
        atrs_needed = abs(distance) / atr if atr > 0 else 999
        
        # Probabilidad basica
        if atrs_needed <= 1:
            prob = "ALTA (70%+)"
        elif atrs_needed <= 2:
            prob = "MEDIA (40-60%)"
        elif atrs_needed <= 3:
            prob = "BAJA (20-40%)"
        else:
            prob = "MUY BAJA (<20%)"
        
        # Ya lo toco hoy?
        if option_type.lower() == 'put':
            touched = low <= strike
            closest = low
        else:
            touched = high >= strike
            closest = high
        
        lines = [
            f"{'='*50}",
            f"  {symbol} {option_type.upper()} ${strike}",
            f"{'='*50}",
            f"",
            f"  Precio actual: ${price:.2f}",
            f"  Target:        ${strike:.2f}",
            f"  Distancia:     ${abs(distance):.2f} ({abs(distance)/price*100:.2f}%)",
            f"  ATRs needed:   {atrs_needed:.1f}",
            f"",
            f"  Mas cercano hoy: ${closest:.2f}",
            f"  Ya toco target?: {'SI!' if touched else 'NO'}",
            f"",
            f"  PROBABILIDAD: {prob}",
            f"",
        ]
        
        if touched:
            lines.append(f"  >> Ya llego una vez, PUEDE volver")
        elif atrs_needed <= 2:
            lines.append(f"  >> Alcanzable pero necesita momentum")
        else:
            lines.append(f"  >> Dificil, necesita catalizador fuerte")
        
        lines.append(f"{'='*50}")
        
        return "\n".join(lines)
    
    def get_flow_analysis(self, symbol: str) -> str:
        """Analisis de flow de opciones"""
        symbol = symbol.upper()
        opts = self.get_options_data(symbol)
        
        if 'error' in opts:
            return f"Error obteniendo opciones: {opts['error']}"
        
        df = self.get_price_data(symbol, 10)
        if df.empty:
            return f"No pude obtener precio para {symbol}"
        
        price = df['close'].iloc[-1]
        calls = opts['calls']
        puts = opts['puts']
        
        # Filtrar cerca del precio
        calls_near = calls[(calls['strike'] >= price - 15) & (calls['strike'] <= price + 15)]
        puts_near = puts[(puts['strike'] >= price - 15) & (puts['strike'] <= price + 15)]
        
        call_vol = calls_near['volume'].sum()
        put_vol = puts_near['volume'].sum()
        pcr = put_vol / call_vol if call_vol > 0 else 1
        
        # Walls
        call_wall = calls_near.loc[calls_near['openInterest'].idxmax()] if not calls_near.empty else None
        put_wall = puts_near.loc[puts_near['openInterest'].idxmax()] if not puts_near.empty else None
        
        # Max pain (simplificado)
        max_pain = puts_near.loc[puts_near['openInterest'].idxmax()]['strike'] if not puts_near.empty else price
        
        lines = [
            f"{'='*50}",
            f"  {symbol} - FLOW DE OPCIONES",
            f"{'='*50}",
            f"",
            f"  Expiracion: {opts['expiration']}",
            f"  Precio:     ${price:.2f}",
            f"",
            f"  VOLUMEN:",
            f"    Calls: {call_vol:,.0f}",
            f"    Puts:  {put_vol:,.0f}",
            f"    P/C Ratio: {pcr:.2f}",
            f"",
        ]
        
        if call_wall is not None:
            lines.append(f"  CALL WALL: ${call_wall['strike']:.0f} ({call_wall['openInterest']:,.0f} OI)")
        if put_wall is not None:
            lines.append(f"  PUT WALL:  ${put_wall['strike']:.0f} ({put_wall['openInterest']:,.0f} OI)")
        
        lines.append(f"  MAX PAIN:  ${max_pain:.0f}")
        lines.append(f"")
        
        # Score
        bulls = 0
        bears = 0
        
        if pcr < 0.9:
            bulls += 2
            lines.append(f"  + P/C < 0.9 = Bullish")
        elif pcr > 1.1:
            bears += 2
            lines.append(f"  + P/C > 1.1 = Bearish")
        
        if price > max_pain:
            bears += 1
            lines.append(f"  + Precio arriba de Max Pain = puede bajar")
        else:
            bulls += 1
            lines.append(f"  + Precio abajo de Max Pain = puede subir")
        
        lines.append(f"")
        lines.append(f"  SCORE: Bulls {bulls} vs Bears {bears}")
        
        if bulls > bears:
            lines.append(f"  >> FLOW FAVORECE: CALLS")
        elif bears > bulls:
            lines.append(f"  >> FLOW FAVORECE: PUTS")
        else:
            lines.append(f"  >> FLOW: NEUTRAL")
        
        lines.append(f"{'='*50}")
        
        return "\n".join(lines)
    
    def _calc_rsi(self, series: pd.Series, period: int = 14) -> pd.Series:
        delta = series.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        return 100 - (100 / (1 + rs))
    
    def process_query(self, query: str) -> str:
        """Procesa una pregunta en lenguaje natural"""
        query = query.lower().strip()
        
        # Detectar simbolo
        symbols = re.findall(r'\b([A-Za-z]{1,5})\b', query.upper())
        common_words = {'A', 'I', 'THE', 'TO', 'FOR', 'AND', 'OR', 'IF', 'MY', 'ME', 
                       'IT', 'IS', 'AT', 'ON', 'IN', 'UP', 'DO', 'GO', 'NO', 'SO',
                       'PUT', 'CALL', 'WILL', 'CAN', 'HOW', 'WHAT', 'CHECK', 'ANALYZE',
                       'NEED', 'MAKE', 'GET', 'BUY', 'SELL', 'FLOW', 'PRICE', 'TARGET'}
        symbols = [s for s in symbols if s not in common_words and len(s) >= 2]
        
        symbol = symbols[0] if symbols else 'SPY'
        
        # Detectar strike (numero)
        strikes = re.findall(r'\b(\d{2,4}(?:\.\d{1,2})?)\b', query)
        strike = float(strikes[0]) if strikes else None
        
        # Detectar tipo de opcion
        is_put = 'put' in query
        is_call = 'call' in query
        
        # Comandos
        if any(w in query for w in ['flow', 'opciones', 'options', 'wall', 'pain']):
            return self.get_flow_analysis(symbol)
        
        elif strike and (is_put or is_call):
            opt_type = 'put' if is_put else 'call'
            return self.analyze_option_target(symbol, strike, opt_type)
        
        elif any(w in query for w in ['llegara', 'will it', 'make it', 'target', 'reach']):
            if strike:
                opt_type = 'put' if strike < 700 else 'call'  # Heuristica
                return self.analyze_option_target(symbol, strike, opt_type)
            else:
                return self.analyze_symbol(symbol)
        
        elif any(w in query for w in ['analiza', 'analyze', 'check', 'como esta', 'how is']):
            return self.analyze_symbol(symbol)
        
        elif any(w in query for w in ['precio', 'price', 'cuanto', 'how much']):
            df = self.get_price_data(symbol, 10)
            if not df.empty:
                price = df['close'].iloc[-1]
                return f"{symbol}: ${price:.2f}"
            return f"No pude obtener precio de {symbol}"
        
        elif any(w in query for w in ['ayuda', 'help', 'comandos', 'commands']):
            return self.get_help()
        
        else:
            # Default: analisis
            return self.analyze_symbol(symbol)
    
    def get_help(self) -> str:
        return """
==================================================
  BEAST ASSISTANT - COMANDOS
==================================================

  ANALISIS:
    "analiza SPY"
    "check TSLA"
    "como esta QQQ"
    
  OPCIONES TARGET:
    "SPY put 690"
    "llegara a 690?"
    "will my 690 puts print?"
    
  FLOW:
    "flow SPY"
    "opciones de AAPL"
    "call wall TSLA"
    
  PRECIO:
    "precio SPY"
    "cuanto esta NVDA"
    
  OTROS:
    "ayuda" - Este mensaje
    "salir" - Terminar

==================================================
"""
    
    def run_cli(self):
        """Modo interactivo CLI"""
        print("\n" + "="*50)
        print("  BEAST TRADING ASSISTANT")
        print("  Escribe 'ayuda' para ver comandos")
        print("  Escribe 'salir' para terminar")
        print("="*50 + "\n")
        
        while True:
            try:
                query = input("\n> ").strip()
                
                if not query:
                    continue
                
                if query.lower() in ['salir', 'exit', 'quit', 'q']:
                    print("\nHasta luego!")
                    break
                
                response = self.process_query(query)
                print("\n" + response)
                
            except KeyboardInterrupt:
                print("\n\nHasta luego!")
                break
            except Exception as e:
                print(f"\nError: {e}")


def run_telegram_bot():
    """Corre el asistente como bot de Telegram"""
    from telegram import Update
    from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
    
    assistant = BeastAssistant()
    
    async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(assistant.get_help())
    
    async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.message.text
        response = assistant.process_query(query)
        # Telegram tiene limite de 4096 chars
        if len(response) > 4000:
            response = response[:4000] + "..."
        await update.message.reply_text(f"```\n{response}\n```", parse_mode='Markdown')
    
    with open('config.yaml', 'r') as f:
        config = yaml.safe_load(f)
    
    token = config['notifications']['telegram']['bot_token']
    
    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    print("Bot de Telegram iniciado...")
    print("Enviale mensajes a tu bot!")
    app.run_polling()


if __name__ == "__main__":
    if "--telegram" in sys.argv:
        run_telegram_bot()
    else:
        assistant = BeastAssistant()
        assistant.run_cli()
