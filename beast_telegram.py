#!/usr/bin/env python3
"""
BEAST TELEGRAM BOT
==================
Asistente interactivo + Alertas inteligentes

MODO 1: CHAT - Tu preguntas, yo respondo
MODO 2: ALERTAS - Solo cuando TODO se alinea

Uso:
  python beast_telegram.py
"""

import yaml
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional
import pytz

from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

from beast_assistant import BeastAssistant

# Configurar logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)


class BeastTelegramBot:
    """Bot de Telegram con chat interactivo y alertas inteligentes"""
    
    def __init__(self):
        with open('config.yaml', 'r') as f:
            self.config = yaml.safe_load(f)
        
        self.assistant = BeastAssistant()
        # Support both config formats
        if 'notifications' in self.config:
            self.chat_id = self.config['notifications']['telegram']['chat_id']
            self.token = self.config['notifications']['telegram']['bot_token']
        else:
            self.chat_id = self.config['telegram']['chat_id']
            self.token = self.config['telegram']['bot_token']
        
        # Control de alertas
        self.last_alert = {}  # symbol -> timestamp
        self.alert_cooldown = 30 * 60  # 30 minutos entre alertas del mismo symbol
        
        # Configuracion de alertas
        self.min_score_for_alert = 7  # De 10
        self.min_confidence = 0.80  # 80%
        
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Comando /start"""
        welcome = """
🤖 BEAST TRADING ASSISTANT
   Entiendo Español e Inglés

Soy tu asistente de trading. Preguntame lo que quieras:

📊 ANALISIS:
  "analiza SPY" / "check QQQ"
  "como esta TSLA" / "revisa NVDA"

📈 OPCIONES:
  "SPY put 690" / "llegara a 688?"
  "flow QQQ" / "opciones AAPL"

💰 PRECIO:
  "precio SPY" / "cuanto esta TSLA"

🔮 DIRECCION:
  "va a subir?" / "sube o baja?"
  
⚙️ COMANDOS:
  /alerts on - Alertas automaticas
  /alerts off - Solo chat
  /status - Estado del sistema

Las alertas SOLO se envian cuando:
✅ Tecnicos alineados
✅ Flow alineado  
✅ Score > 7/10
✅ Confianza > 80%

Preguntame algo! 🚀
"""
        await update.message.reply_text(welcome)
    
    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Maneja mensajes de chat"""
        query = update.message.text
        logger.info(f"Query recibido: {query}")
        
        # Procesar con el asistente
        response = self.assistant.process_query(query)
        
        # Enviar respuesta (dividir si es muy larga)
        if len(response) > 4000:
            chunks = [response[i:i+4000] for i in range(0, len(response), 4000)]
            for chunk in chunks:
                await update.message.reply_text(f"```\n{chunk}\n```", parse_mode='Markdown')
        else:
            await update.message.reply_text(f"```\n{response}\n```", parse_mode='Markdown')
    
    async def alerts_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Comando /alerts"""
        args = context.args
        
        if not args:
            await update.message.reply_text(
                "Uso: /alerts on|off\n\n"
                "on = Recibir alertas cuando hay trade perfecto\n"
                "off = Solo chat, sin alertas"
            )
            return
        
        if args[0].lower() == 'on':
            context.user_data['alerts'] = True
            await update.message.reply_text(
                "✅ Alertas ACTIVADAS\n\n"
                "Te avisare SOLO cuando:\n"
                "- Tecnicos alineados\n"
                "- Flow alineado\n"
                "- Score > 7/10\n"
                "- Confianza > 80%"
            )
        elif args[0].lower() == 'off':
            context.user_data['alerts'] = False
            await update.message.reply_text(
                "🔕 Alertas DESACTIVADAS\n\n"
                "Solo respondere cuando me preguntes."
            )
    
    async def status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Comando /status"""
        now = datetime.now(pytz.timezone('US/Eastern'))
        market_open = 9 <= now.hour < 16
        
        status = f"""
📊 BEAST STATUS

Hora ET: {now.strftime('%H:%M:%S')}
Mercado: {'🟢 ABIERTO' if market_open else '🔴 CERRADO'}

Alertas: {'✅ ON' if context.user_data.get('alerts', True) else '🔕 OFF'}

Configuracion:
- Score minimo: {self.min_score_for_alert}/10
- Confianza minima: {self.min_confidence*100:.0f}%
- Cooldown: {self.alert_cooldown//60} min

Ultima alerta: {self.last_alert.get('SPY', 'Ninguna')}
"""
        await update.message.reply_text(status)
    
    async def check_for_alerts(self, app: Application):
        """Revisa el mercado y envia alertas si hay setup perfecto"""
        symbols = ['SPY', 'QQQ', 'TSLA', 'NVDA', 'AAPL', 'AMD']
        
        for symbol in symbols:
            try:
                # Verificar cooldown
                if symbol in self.last_alert:
                    elapsed = (datetime.now() - self.last_alert[symbol]).seconds
                    if elapsed < self.alert_cooldown:
                        continue
                
                # Analizar
                analysis = self.analyze_for_alert(symbol)
                
                if analysis and analysis['should_alert']:
                    await self.send_alert(app, analysis)
                    self.last_alert[symbol] = datetime.now()
                    
            except Exception as e:
                logger.error(f"Error checking {symbol}: {e}")
    
    def analyze_for_alert(self, symbol: str) -> Optional[dict]:
        """Analiza un simbolo y determina si merece alerta"""
        try:
            df = self.assistant.get_price_data(symbol, 120)
            if df.empty:
                return None
            
            price = df['close'].iloc[-1]
            vwap = df['vwap'].iloc[-1]
            
            # Calculos tecnicos
            df['ema9'] = df['close'].ewm(span=9).mean()
            df['ema21'] = df['close'].ewm(span=21).mean()
            df['ema50'] = df['close'].ewm(span=50).mean()
            
            ema9 = df['ema9'].iloc[-1]
            ema21 = df['ema21'].iloc[-1]
            ema50 = df['ema50'].iloc[-1]
            
            # RSI
            delta = df['close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
            rs = gain / loss
            rsi = (100 - (100 / (1 + rs))).iloc[-1]
            
            # Momentum
            momentum = ((price - df['close'].iloc[-10]) / df['close'].iloc[-10]) * 100
            
            # MACD
            ema12 = df['close'].ewm(span=12).mean()
            ema26 = df['close'].ewm(span=26).mean()
            macd = (ema12 - ema26).iloc[-1]
            
            # ADX (simplificado)
            tr = df['high'] - df['low']
            atr = tr.rolling(14).mean().iloc[-1]
            adx = min(abs(momentum) * 10, 50)  # Aproximacion
            
            # Score tecnico
            tech_score = 0
            direction = None
            reasons = []
            
            # BULLISH signals
            if price > vwap:
                tech_score += 1
                reasons.append("Precio > VWAP")
            if ema9 > ema21:
                tech_score += 1
                reasons.append("EMA9 > EMA21")
            if ema21 > ema50:
                tech_score += 1
                reasons.append("EMA21 > EMA50")
            if macd > 0:
                tech_score += 1
                reasons.append("MACD positivo")
            if momentum > 0.1:
                tech_score += 1
                reasons.append(f"Momentum +{momentum:.2f}%")
            if 30 < rsi < 70:
                tech_score += 0.5
            
            # BEARISH signals
            bearish_score = 0
            if price < vwap:
                bearish_score += 1
            if ema9 < ema21:
                bearish_score += 1
            if ema21 < ema50:
                bearish_score += 1
            if macd < 0:
                bearish_score += 1
            if momentum < -0.1:
                bearish_score += 1
            
            # Determinar direccion
            if tech_score >= 4:
                direction = "CALL"
                final_score = tech_score
            elif bearish_score >= 4:
                direction = "PUT"
                final_score = bearish_score
                reasons = [r.replace(">", "<") for r in reasons]
            else:
                return None  # No hay senal clara
            
            # Flow de opciones
            opts = self.assistant.get_options_data(symbol)
            flow_aligned = False
            flow_reasons = []
            
            if 'error' not in opts:
                calls = opts['calls']
                puts = opts['puts']
                
                calls_near = calls[(calls['strike'] >= price - 10) & (calls['strike'] <= price + 10)]
                puts_near = puts[(puts['strike'] >= price - 10) & (puts['strike'] <= price + 10)]
                
                call_vol = calls_near['volume'].sum()
                put_vol = puts_near['volume'].sum()
                pcr = put_vol / call_vol if call_vol > 0 else 1
                
                if direction == "CALL" and pcr < 0.9:
                    flow_aligned = True
                    flow_reasons.append(f"P/C Ratio {pcr:.2f} favorece calls")
                elif direction == "PUT" and pcr > 1.1:
                    flow_aligned = True
                    flow_reasons.append(f"P/C Ratio {pcr:.2f} favorece puts")
            
            # Calcular score final (de 10)
            total_score = final_score * 2  # Max 10
            if flow_aligned:
                total_score = min(10, total_score + 1)
            
            # Confianza
            confidence = total_score / 10
            
            # Determinar si alertar
            should_alert = (
                total_score >= self.min_score_for_alert and
                confidence >= self.min_confidence and
                flow_aligned and
                adx >= 20  # Necesita tendencia
            )
            
            if should_alert:
                # Calcular targets
                if direction == "CALL":
                    entry = price
                    target = price + (atr * 1.5)
                    stop = price - (atr * 0.5)
                else:
                    entry = price
                    target = price - (atr * 1.5)
                    stop = price + (atr * 0.5)
                
                return {
                    'should_alert': True,
                    'symbol': symbol,
                    'direction': direction,
                    'price': price,
                    'entry': entry,
                    'target': target,
                    'stop': stop,
                    'score': total_score,
                    'confidence': confidence,
                    'reasons': reasons + flow_reasons,
                    'rsi': rsi,
                    'adx': adx,
                    'momentum': momentum
                }
            
            return None
            
        except Exception as e:
            logger.error(f"Error analyzing {symbol}: {e}")
            return None
    
    async def send_alert(self, app: Application, analysis: dict):
        """Envia alerta de trade"""
        symbol = analysis['symbol']
        direction = analysis['direction']
        
        emoji = "🟢" if direction == "CALL" else "🔴"
        
        message = f"""
{emoji} ALERTA: {symbol} {direction} {emoji}

━━━━━━━━━━━━━━━━━━━━━━━━

SCORE: {analysis['score']}/10
CONFIANZA: {analysis['confidence']*100:.0f}%

TRADE:
  Entry:  ${analysis['entry']:.2f}
  Target: ${analysis['target']:.2f} ({((analysis['target']-analysis['entry'])/analysis['entry']*100):+.2f}%)
  Stop:   ${analysis['stop']:.2f} ({((analysis['stop']-analysis['entry'])/analysis['entry']*100):+.2f}%)

INDICADORES:
  RSI: {analysis['rsi']:.1f}
  ADX: {analysis['adx']:.1f}
  Mom: {analysis['momentum']:+.2f}%

RAZONES:
"""
        for reason in analysis['reasons']:
            message += f"  ✓ {reason}\n"
        
        message += f"""
━━━━━━━━━━━━━━━━━━━━━━━━

⚠️ TODO ALINEADO - Alta probabilidad
"""
        
        await app.bot.send_message(
            chat_id=self.chat_id,
            text=message
        )
        logger.info(f"Alert sent for {symbol} {direction}")
    
    async def scan_loop(self, app: Application):
        """Loop de escaneo en background"""
        while True:
            try:
                # Solo escanear durante market hours
                now = datetime.now(pytz.timezone('US/Eastern'))
                if 9 <= now.hour < 16 and now.weekday() < 5:
                    await self.check_for_alerts(app)
                
                # Esperar 5 minutos entre escaneos
                await asyncio.sleep(300)
                
            except Exception as e:
                logger.error(f"Scan loop error: {e}")
                await asyncio.sleep(60)
    
    def run(self):
        """Inicia el bot"""
        print("=" * 50)
        print("  BEAST TELEGRAM BOT")
        print("=" * 50)
        print()
        print("  Modos:")
        print("  - CHAT: Respondo a tus preguntas")
        print("  - ALERTAS: Solo cuando todo se alinea")
        print()
        print("  Iniciando...")
        print("=" * 50)
        
        # Crear aplicacion
        app = Application.builder().token(self.token).build()
        
        # Handlers
        app.add_handler(CommandHandler("start", self.start))
        app.add_handler(CommandHandler("help", self.start))
        app.add_handler(CommandHandler("alerts", self.alerts_command))
        app.add_handler(CommandHandler("status", self.status_command))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))
        
        # Iniciar scan loop en background
        async def post_init(application: Application):
            asyncio.create_task(self.scan_loop(application))
        
        app.post_init = post_init
        
        # Correr bot
        print("\nBot listo! Escribele en Telegram.")
        print("Ctrl+C para detener.\n")
        
        app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    bot = BeastTelegramBot()
    bot.run()
