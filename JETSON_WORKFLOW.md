# 🦁 BEAST ENGINE - Lo que el Jetson hace TODO EL DÍA

## ⏰ HORARIO COMPLETO (6:30 AM - 1:00 PM PST / 9:30 AM - 4:00 PM ET)

### 6:00 AM PST (Pre-Market)
```
JETSON EJECUTA:
├─ Descarga datos overnight
├─ Calcula gaps y pre-market movers
├─ Analiza VIX y régimen de mercado
├─ Genera MORNING BRIEF → Telegram
└─ Carga modelos AI en GPU
```

### 6:30 AM - 7:00 AM PST (Opening Range - ORB)
```
JETSON EJECUTA CADA 15 SEGUNDOS:
├─ Captura high/low de primeros 30 min
├─ Calcula ORB levels
├─ Monitorea volume spike
├─ Detecta dirección inicial
└─ Probabilidad de ORB breakout: XX%
```

### 7:00 AM - 9:00 AM PST (Momentum Phase)
```
JETSON EJECUTA CADA 30 SEGUNDOS:
├─ AI Model prediction (RF + XGB + LGB)
├─ Technical indicators (RSI, MACD, EMAs, ADX)
├─ Option flow analysis (Call/Put ratio)
├─ Volume analysis (relative volume)
├─ VWAP position tracking
│
├─ COMBINA TODO EN:
│   ├─ Probabilidad de CALL: XX%
│   ├─ Probabilidad de PUT: XX%
│   └─ Señales alineadas: X/7
│
└─ SI probabilidad > 60% Y señales > 4:
    └─ ALERTA TELEGRAM con entry/target/stop
```

### 9:00 AM - 12:00 PM PST (Chop/Reversal Phase)
```
JETSON EJECUTA CADA 1 MINUTO:
├─ Detecta rangos y consolidación
├─ Busca traps (failed breakouts)
├─ Monitorea divergencias RSI/MACD
├─ Calcula mean reversion levels
│
├─ PROBABILIDADES AJUSTADAS:
│   ├─ Reduce confianza en breakouts
│   ├─ Aumenta probabilidad de reversals
│   └─ Favorece trades cerca de VWAP
│
└─ Alertas solo si prob > 65% (más estricto)
```

### 12:00 PM - 1:00 PM PST (Power Hour)
```
JETSON EN MODO MÁXIMO:
├─ Escaneo cada 15 segundos
├─ Todos los indicadores activos
├─ AI modelo con máximo peso
├─ Flow analysis en tiempo real
│
├─ CONDICIONES PARA ALERTA:
│   ├─ Precio del lado correcto de VWAP
│   ├─ EMAs alineadas (9 > 21 para CALL)
│   ├─ MACD confirmando
│   ├─ RSI no en extremos
│   ├─ Volumen > 1.5x promedio
│   └─ AI confidence > 70%
│
└─ PROBABILIDAD COMBINADA > 55% = ALERTA
```

---

## 🧠 CÁLCULO DE PROBABILIDAD (Lo que hace la GPU)

```
PROBABILIDAD_FINAL = 
    (AI_MODEL * 0.25) +           # Random Forest + XGBoost + LightGBM
    (TECHNICAL * 0.20) +          # RSI, MACD, EMAs, ADX, ATR
    (OPTION_FLOW * 0.15) +        # Call/Put ratio, unusual activity
    (TIME_OF_DAY * 0.10) +        # Probabilidad histórica por hora
    (REGIME * 0.15) +             # VIX, trend strength
    (MOMENTUM * 0.15)             # Price action, volume

AJUSTES:
├─ Si VIX < 15: CALL probability +10%
├─ Si VIX > 25: PUT probability +10%
├─ Si Power Hour: Trend probability +15%
├─ Si Chop Phase: Reversal probability +10%
└─ Si Volume spike: Current direction +10%
```

---

## 📊 SEÑALES ALINEADAS (Consensus Scoring)

```
Cada señal que confirma = +1 punto

SEÑALES:
1. AI Model dice CALL/PUT
2. Precio > VWAP (CALL) o < VWAP (PUT)
3. EMA9 > EMA21 (CALL) o EMA9 < EMA21 (PUT)
4. MACD Histogram positivo (CALL) o negativo (PUT)
5. RSI en zona favorable (40-60)
6. ADX > 25 (trend) confirma dirección
7. Volume > 1.2x promedio

PUNTUACIÓN:
├─ 1-2 señales: NO TRADE (prob ~35%)
├─ 3-4 señales: WATCH (prob ~50%)
├─ 5-6 señales: POSIBLE (prob ~60%)
└─ 7 señales: STRONG (prob ~75%)
```

---

## 🎯 TARGETS BASADOS EN ATR

```
CALL:
├─ Entry: Precio actual
├─ Target 1: Entry + (ATR * 1.0)  # Conservative
├─ Target 2: Entry + (ATR * 2.0)  # Normal
├─ Target 3: Entry + (ATR * 3.0)  # Aggressive
└─ Stop: Entry - (ATR * 0.75)

PUT:
├─ Entry: Precio actual
├─ Target 1: Entry - (ATR * 1.0)
├─ Target 2: Entry - (ATR * 2.0)
├─ Target 3: Entry - (ATR * 3.0)
└─ Stop: Entry + (ATR * 0.75)

Para 0DTE (15-min timeframe):
├─ ATR típico SPY: $0.50 - $1.50
├─ Target 1: +$0.50 - $1.50 (+0.1% - 0.2%)
├─ Target 2: +$1.00 - $3.00 (+0.2% - 0.4%)
└─ En opciones ATM: Target 2 = +20% - +50% ganancia
```

---

## 📱 FORMATO DE ALERTA TELEGRAM

```
🦁 BEAST SIGNAL: SPY CALL

PROBABILIDAD: 67.3%
Señales alineadas: 5/7

DESGLOSE:
├─ AI Model: CALL (72%)
├─ Técnicos: CALL (68%)
├─ Flow: CALL (61%)
├─ Tiempo: Favorable
└─ Régimen: LOW_VOL

SETUP:
├─ Entry: $585.50
├─ Target 1: $586.00 (+$0.50)
├─ Target 2: $586.50 (+$1.00)
└─ Stop: $584.75 (-$0.75)

FACTORES:
├─ VWAP: Above ✓
├─ EMAs: 9>21>50 ✓
├─ MACD: Bullish ✓
├─ RSI: 55 (neutral zone) ✓
├─ ADX: 32 (trending) ✓
├─ Volume: 1.8x avg ✓
└─ Flow: 63% calls

⏰ 12:15 PM PST
```

---

## 🔥 ESTO ES LO QUE EL JETSON DEBE HACER

**NO solo esperar Power Hour.**

El Jetson debe estar:
1. Calculando probabilidades CONSTANTEMENTE
2. Combinando TODAS las señales
3. Alertando cuando hay CONSENSO
4. Ajustando por hora del día y régimen
5. Usando la GPU para inferencia AI en tiempo real
6. Monitoreando flow de opciones
7. Detectando cambios de tendencia

**El valor está en la COMBINACIÓN, no en un solo patrón.**
