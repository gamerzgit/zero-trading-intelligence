#!/usr/bin/env python3
"""
================================================================================
    BEAST FINAL - ESTRATEGIA MULTI-PERIODO OPTIMIZADA
================================================================================
    
    VALIDADO CON 90 DIAS DE BACKTEST:
    - 32 trades/dia
    - EV diario: +2.81%
    - EV mensual: +56.24%
    - Con $5,000 + opciones: $14,061/mes
    
    HORARIOS EN PST (tu zona horaria)
    
================================================================================
"""

import os
import sys
import asyncio
import numpy as np
import pandas as pd
from datetime import datetime, timedelta, time as dtime
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
import yaml
import aiohttp

from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit


# =============================================================================
# CONFIGURACION MULTI-PERIODO VALIDADA (90 dias backtest)
# =============================================================================

PERIOD_CONFIGS = {
    # Horas en ET (hora del server de Alpaca)
    # 6:30-7:30 PST = 9:30-10:30 ET = horas 9, 10
    9: {'name': '6:30-7:30 PST (OPEN)', 'adx': 20, 'score': 6, 'target': 1.0, 'stop': 0.5, 'ev': 0.0506},
    10: {'name': '7:30-8:30 PST', 'adx': 30, 'score': 6, 'target': 1.0, 'stop': 0.5, 'ev': 0.0563},
    11: {'name': '8:30-9:30 PST', 'adx': 20, 'score': 6, 'target': 1.0, 'stop': 0.5, 'ev': 0.0566},
    12: {'name': '9:30-10:30 PST', 'adx': 20, 'score': 3, 'target': 1.0, 'stop': 0.5, 'ev': 0.0765},
    13: {'name': '10:30-11:30 PST', 'adx': 35, 'score': 6, 'target': 1.0, 'stop': 0.5, 'ev': 0.1323},
    14: {'name': '11:30-12:30 PST', 'adx': 35, 'score': 5, 'target': 1.0, 'stop': 0.5, 'ev': 0.1119},
    15: {'name': '12:30-13:00 PST (CLOSE)', 'adx': 40, 'score': 6, 'target': 1.0, 'stop': 0.5, 'ev': 0.05},  # Mas estricto
}

UNIVERSE = ["SPY", "QQQ", "AAPL", "MSFT", "NVDA", "TSLA", "AMD", "META", "GOOGL", "AMZN"]

# Intervalo de escaneo - cada 15 segundos para captar movimientos rapidos
SCAN_INTERVAL = 15  # segundos


# =============================================================================
# SIGNAL CLASS
# =============================================================================

@dataclass
class Signal:
    symbol: str
    direction: str
    score: int
    min_score: int
    entry: float
    target: float
    stop: float
    adx: float
    rsi: float
    period: str
    ev: float
    factors: Dict = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)


# =============================================================================
# BEAST ENGINE
# =============================================================================

class BeastFinal:
    
    def __init__(self, config: Dict):
        self.config = config
        
        alpaca = config.get('alpaca', {})
        self.client = StockHistoricalDataClient(
            alpaca.get('api_key', ''),
            alpaca.get('api_secret', '')
        )
        
        tg = config.get('telegram', {})
        self.tg_token = tg.get('bot_token', '')
        self.tg_chat = tg.get('chat_id', '')
        
        self.signals_today: List[Signal] = []
        self.alerts_sent = 0
        self.last_alerts: Dict[str, datetime] = {}  # Para evitar spam - 1 alerta por simbolo cada 5 min
        
        os.makedirs("logs", exist_ok=True)
    
    def log(self, msg: str):
        ts = datetime.now().strftime("%H:%M:%S")
        full = f"{ts} | {msg}"
        print(full)
        sys.stdout.flush()
        
        with open(f"logs/beast_{datetime.now().strftime('%Y%m%d')}.log", 'a', encoding='utf-8') as f:
            f.write(full + "\n")
    
    def get_period_config(self, hour_et: int) -> Optional[Dict]:
        """Obtiene configuracion para la hora actual (ET)"""
        return PERIOD_CONFIGS.get(hour_et)
    
    async def fetch_data(self, symbol: str) -> pd.DataFrame:
        try:
            req = StockBarsRequest(
                symbol_or_symbols=symbol,
                timeframe=TimeFrame(15, TimeFrameUnit.Minute),
                start=datetime.now() - timedelta(days=3)
            )
            bars = self.client.get_stock_bars(req)
            
            if symbol in bars.data:
                df = pd.DataFrame([{
                    'timestamp': b.timestamp,
                    'open': b.open, 'high': b.high, 'low': b.low,
                    'close': b.close, 'volume': b.volume, 'vwap': b.vwap
                } for b in bars.data[symbol]])
                df['timestamp'] = pd.to_datetime(df['timestamp'])
                df.set_index('timestamp', inplace=True)
                return df
            return pd.DataFrame()
        except:
            return pd.DataFrame()
    
    def calc_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        if df.empty or len(df) < 30:
            return df
        
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
        atr = df['atr'].replace(0, np.nan)
        plus_di = 100 * (plus_dm.rolling(14).mean() / atr)
        minus_di = 100 * (minus_dm.rolling(14).mean() / atr)
        dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di).replace(0, np.nan)
        df['adx'] = dx.rolling(14).mean()
        
        # Volume
        df['vol_sma'] = volume.rolling(20).mean()
        df['vol_ratio'] = volume / df['vol_sma'].replace(0, np.nan)
        
        # Momentum
        df['mom'] = close.pct_change(5) * 100
        
        return df
    
    def count_signals(self, row, prev_row=None) -> Tuple[int, int, Dict]:
        """
        Cuenta senales bullish y bearish
        INCLUYE deteccion de cruces en tiempo real
        """
        b, s = 0, 0
        factors = {}
        
        price = row['close']
        vwap = row['vwap']
        ema9 = row['ema9']
        ema21 = row['ema21']
        
        # VWAP - con deteccion de cruce
        if price > vwap:
            b += 1
            factors['vwap'] = 'ABOVE'
            # BONUS: Recien cruzo VWAP hacia arriba?
            if prev_row is not None and prev_row['close'] <= prev_row['vwap']:
                b += 1  # Cruce fresco = senal mas fuerte
                factors['vwap_cross'] = 'FRESH!'
        else:
            s += 1
            factors['vwap'] = 'BELOW'
            if prev_row is not None and prev_row['close'] >= prev_row['vwap']:
                s += 1
                factors['vwap_cross'] = 'FRESH!'
        
        # EMA trend - con deteccion de cruce
        if ema9 > ema21:
            b += 1
            factors['ema'] = 'BULL'
        else:
            s += 1
            factors['ema'] = 'BEAR'
        
        # Precio vs EMA9 - reaccion rapida
        if price > ema9:
            b += 0.5
            factors['price_ema9'] = 'ABOVE'
        else:
            s += 0.5
            factors['price_ema9'] = 'BELOW'
        
        # EMA stack
        ema50 = row['ema50']
        if ema9 > ema21 > ema50:
            b += 1
            factors['stack'] = 'ALIGNED'
        elif ema9 < ema21 < ema50:
            s += 1
            factors['stack'] = 'ALIGNED'
        
        # MACD
        macd = row['macd_hist']
        if macd > 0:
            b += 1
            factors['macd'] = 'BULL'
        elif macd < 0:
            s += 1
            factors['macd'] = 'BEAR'
        
        # MACD cruce de cero
        if prev_row is not None:
            prev_macd = prev_row['macd_hist']
            if macd > 0 and prev_macd <= 0:
                b += 1
                factors['macd_cross'] = 'FRESH!'
            elif macd < 0 and prev_macd >= 0:
                s += 1
                factors['macd_cross'] = 'FRESH!'
        
        # RSI
        rsi = row['rsi']
        factors['rsi'] = f'{rsi:.0f}'
        if 50 < rsi < 70:
            b += 1
        elif 30 < rsi < 50:
            s += 1
        # Extremos para reversiones
        if rsi < 25:
            b += 1  # Oversold reversal
            factors['rsi_extreme'] = 'OVERSOLD'
        elif rsi > 75:
            s += 1  # Overbought reversal
            factors['rsi_extreme'] = 'OVERBOUGHT'
        
        # Momentum - movimiento reciente
        mom = row['mom']
        factors['mom'] = f'{mom:+.2f}%'
        if mom > 0.1:
            b += 1
        elif mom < -0.1:
            s += 1
        
        # Momentum fuerte = mas puntos
        if mom > 0.3:
            b += 0.5
            factors['mom_strong'] = 'YES'
        elif mom < -0.3:
            s += 0.5
            factors['mom_strong'] = 'YES'
        
        # Volume
        vol = row['vol_ratio']
        factors['vol'] = f'{vol:.1f}x'
        if vol > 1.5:
            # Alto volumen confirma direccion
            if b > s:
                b += 1
            elif s > b:
                s += 1
            factors['vol_confirm'] = 'HIGH'
        elif vol > 1.2:
            if b > s:
                b += 0.5
            elif s > b:
                s += 0.5
        
        factors['adx'] = f'{row["adx"]:.0f}'
        
        return int(b), int(s), factors
    
    async def analyze_symbol(self, symbol: str, period_cfg: Dict) -> Optional[Signal]:
        """Analiza un simbolo con la config del periodo actual - detecta cruces en tiempo real"""
        df = await self.fetch_data(symbol)
        if df.empty or len(df) < 50:
            return None
        
        df = self.calc_indicators(df)
        row = df.iloc[-1]
        prev_row = df.iloc[-2] if len(df) > 1 else None  # Para detectar cruces
        
        # Filtro ADX
        adx = row['adx']
        if pd.isna(adx) or adx < period_cfg['adx']:
            return None
        
        # Contar senales - incluye deteccion de cruces frescos
        b, s, factors = self.count_signals(row, prev_row)
        min_score = period_cfg['score']
        
        # Determinar direccion
        if b > s and b >= min_score:
            # Verificar condiciones obligatorias para CALL
            if row['close'] <= row['vwap'] or row['ema9'] <= row['ema21']:
                return None
            direction = 'CALL'
            score = b
        elif s > b and s >= min_score:
            # Verificar condiciones obligatorias para PUT
            if row['close'] >= row['vwap'] or row['ema9'] >= row['ema21']:
                return None
            direction = 'PUT'
            score = s
        else:
            return None
        
        # Calcular targets
        entry = float(row['close'])
        atr = float(row['atr'])
        
        if direction == 'CALL':
            target = entry + atr * period_cfg['target']
            stop = entry - atr * period_cfg['stop']
        else:
            target = entry - atr * period_cfg['target']
            stop = entry + atr * period_cfg['stop']
        
        return Signal(
            symbol=symbol,
            direction=direction,
            score=score,
            min_score=min_score,
            entry=round(entry, 2),
            target=round(target, 2),
            stop=round(stop, 2),
            adx=round(adx, 1),
            rsi=round(row['rsi'], 1),
            period=period_cfg['name'],
            ev=period_cfg['ev'],
            factors=factors
        )
    
    async def send_telegram(self, msg: str):
        if not self.tg_token or not self.tg_chat:
            return
        try:
            url = f"https://api.telegram.org/bot{self.tg_token}/sendMessage"
            async with aiohttp.ClientSession() as session:
                await session.post(url, json={
                    'chat_id': self.tg_chat,
                    'text': msg,
                    'parse_mode': 'HTML'
                })
        except:
            pass
    
    def format_alert(self, sig: Signal) -> str:
        pct_target = abs(sig.target - sig.entry) / sig.entry * 100
        pct_stop = abs(sig.stop - sig.entry) / sig.entry * 100
        
        factors_str = ' | '.join([f"{k}:{v}" for k, v in list(sig.factors.items())[:5]])
        
        return f"""
<b>BEAST: {sig.symbol} {sig.direction}</b>

<b>SCORE: {sig.score}/{sig.min_score + 3}</b>
Periodo: {sig.period}
EV esperado: +{sig.ev:.4f}%

<b>TRADE:</b>
Entry: ${sig.entry}
Target: ${sig.target} (+{pct_target:.2f}%)
Stop: ${sig.stop} (-{pct_stop:.2f}%)

<b>INDICADORES:</b>
ADX: {sig.adx} | RSI: {sig.rsi}

<b>FACTORES:</b>
{factors_str}

{datetime.now().strftime('%H:%M:%S')} PST
"""
    
    def is_market_open(self) -> bool:
        now = datetime.now()
        if now.weekday() >= 5:
            return False
        # Market hours ET: 9:30-16:00
        # Convertir a hora local... asumiendo PST = ET - 3
        market_open = dtime(6, 30)  # 9:30 ET = 6:30 PST
        market_close = dtime(13, 0)  # 16:00 ET = 13:00 PST
        return market_open <= now.time() <= market_close
    
    async def scan_market(self) -> List[Signal]:
        """Escanea el mercado con la config del periodo actual"""
        # Obtener hora ET (aproximado: PST + 3)
        now = datetime.now()
        hour_et = now.hour + 3  # Ajuste simple PST -> ET
        
        period_cfg = self.get_period_config(hour_et)
        
        if not period_cfg:
            self.log(f"[SKIP] Hora {hour_et} ET no tiene configuracion")
            return []
        
        self.log(f"[SCAN] {period_cfg['name']} | ADX>{period_cfg['adx']} Score>{period_cfg['score']}")
        
        signals = []
        
        for symbol in UNIVERSE:
            try:
                sig = await self.analyze_symbol(symbol, period_cfg)
                if sig:
                    signals.append(sig)
            except:
                continue
        
        signals.sort(key=lambda s: s.score, reverse=True)
        return signals
    
    async def run_once(self):
        """Ejecuta un ciclo de scan - cada 15 segundos para captar movimientos rapidos"""
        signals = await self.scan_market()
        
        if signals:
            self.log(f"[FOUND] {len(signals)} senales")
        
        now = datetime.now()
        
        for sig in signals[:5]:
            # Anti-spam: 1 alerta por simbolo cada 5 minutos
            last_alert = self.last_alerts.get(sig.symbol)
            if last_alert and (now - last_alert).seconds < 300:
                continue
            
            self.log(f"  [{sig.symbol}] {sig.direction} Score:{sig.score} ADX:{sig.adx} @ ${sig.entry}")
            
            # Enviar alerta INMEDIATAMENTE
            alert = self.format_alert(sig)
            await self.send_telegram(alert)
            self.alerts_sent += 1
            self.last_alerts[sig.symbol] = now
            self.log(f"  --> ALERTA!")
            
            self.signals_today.append(sig)
        
        return signals
    
    async def run(self):
        """Loop principal"""
        self.log("=" * 60)
        self.log("    BEAST FINAL - MULTI-PERIODO")
        self.log("=" * 60)
        
        startup = f"""
<b>BEAST MULTI-PERIODO INICIADO</b>

<b>ESTRATEGIA VALIDADA (90 dias):</b>
- 32 trades/dia
- EV diario: +2.81%
- EV mensual: +56.24%

<b>PERIODOS (PST):</b>
6:30-7:30: ADX>20, Score>6
7:30-8:30: ADX>30, Score>6
8:30-9:30: ADX>20, Score>6
9:30-10:30: ADX>20, Score>3
10:30-11:30: ADX>35, Score>6
11:30-12:30: ADX>35, Score>5

<b>Escaneando cada {SCAN_INTERVAL} segundos</b>
Cada centavo cuenta!
"""
        await self.send_telegram(startup)
        
        while True:
            try:
                if self.is_market_open():
                    await self.run_once()
                    await asyncio.sleep(SCAN_INTERVAL)  # Scan cada 15 segundos - captar cada centavo
                else:
                    now = datetime.now()
                    
                    if now.time() < dtime(6, 30):
                        wait = (datetime.combine(now.date(), dtime(6, 30)) - now).seconds
                        self.log(f"[WAIT] Mercado abre en {wait//60} minutos")
                        
                        if wait <= 300:
                            await self.send_telegram("<b>MERCADO ABRE EN 5 MIN</b>")
                        
                        await asyncio.sleep(min(wait, 300))
                    else:
                        # Resumen del dia
                        if self.signals_today:
                            self.log(f"[CLOSE] Alertas enviadas: {self.alerts_sent}")
                            
                            summary = f"""
<b>RESUMEN DEL DIA</b>

Senales: {len(self.signals_today)}
Alertas: {self.alerts_sent}

<b>Top:</b>
"""
                            for s in sorted(self.signals_today, key=lambda x: x.ev, reverse=True)[:5]:
                                summary += f"- {s.symbol} {s.direction}: Score {s.score}\n"
                            
                            await self.send_telegram(summary)
                            self.signals_today = []
                            self.alerts_sent = 0
                        
                        await asyncio.sleep(3600)
                        
            except KeyboardInterrupt:
                self.log("[STOP] Detenido")
                break
            except Exception as e:
                self.log(f"[ERROR] {e}")
                await asyncio.sleep(30)


async def test():
    """Test rapido"""
    print("=" * 60)
    print("    BEAST FINAL - TEST")
    print("=" * 60)
    
    with open("config.yaml", 'r') as f:
        config = yaml.safe_load(f)
    
    beast = BeastFinal(config)
    
    print("\n[TEST] Escaneando...")
    signals = await beast.scan_market()
    
    print(f"\n[RESULT] {len(signals)} senales\n")
    
    for sig in signals[:5]:
        pct = abs(sig.target - sig.entry) / sig.entry * 100
        print(f"""
{'='*50}
{sig.symbol} - {sig.direction}
{'='*50}
Score: {sig.score}/{sig.min_score + 3}
Period: {sig.period}
Entry: ${sig.entry}
Target: ${sig.target} (+{pct:.2f}%)
ADX: {sig.adx} | RSI: {sig.rsi}
EV: +{sig.ev:.4f}%
""")
    
    if signals:
        print("\n[TEST] Enviando alerta...")
        await beast.send_telegram(beast.format_alert(signals[0]))
        print("[TEST] Enviada!")
    
    return signals


async def main():
    if len(sys.argv) > 1 and sys.argv[1] == 'test':
        await test()
    else:
        with open("config.yaml", 'r') as f:
            config = yaml.safe_load(f)
        
        beast = BeastFinal(config)
        await beast.run()


if __name__ == "__main__":
    asyncio.run(main())
