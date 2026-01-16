# 🦁 BEAST ENGINE

## THE ULTIMATE 0DTE TRADING INTELLIGENCE

Built for **Jetson Orin AGX 64GB** - Combining AI, Technical Analysis, and Option Flow into one powerful trading assistant.

---

## 🎯 What It Does

BEAST ENGINE is your AI-powered trading analyst that:

1. **Scans the entire market** for 0DTE opportunities (50+ stocks with liquid options)
2. **Calculates Strength Score (0-10)** based on Pine Script indicators
3. **Calculates Quality Score (0-100)** combining all signals
4. **AI Prediction** using trained ML ensemble (Random Forest + XGBoost + LightGBM)
5. **Analyzes Option Flow** (call/put ratios, unusual activity, magnet strikes)
6. **Sends Telegram Alerts** with exact entry, target, and stop prices

---

## 📊 Signal Types

| Type | Description | Priority |
|------|-------------|----------|
| ⚡ **POWER_HOUR** | 3-4 PM signals - Highest conviction | 1 |
| 💥 **ORB_BREAKOUT** | Opening Range Breakout (first 15 min) | 2 |
| 🌊 **CAPITULATION** | Extreme RSI reversals | 3 |
| 🪤 **TRAP** | Bull/Bear trap reversals | 4 |
| ⚠️ **EARLY_WARNING** | Divergence signals | 5 |
| 📊 **REGULAR** | Standard technical signals | 6 |

---

## 🚀 Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure API Keys

Edit `config.yaml` with your:
- Alpaca API keys (paper trading)
- Telegram bot token and chat ID

### 3. Run

```bash
# Continuous scanning (main mode)
python beast_engine.py

# Single scan
python beast_engine.py scan

# Query specific symbol
python beast_engine.py query SPY

# Send morning brief
python beast_engine.py brief
```

---

## 🐳 Docker (Jetson)

```bash
# Build
docker compose build

# Run
docker compose up -d

# View logs
docker compose logs -f beast
```

---

## 📱 Telegram Alerts

You'll receive alerts like this:

```
🟢 BEAST SIGNAL: SPY 🟢

Direction: CALL
Signal Type: ⚡ POWER_HOUR

Scores:
├─ Strength: 8/10
├─ Quality: 75/100
└─ AI Confidence: 72%

Levels:
├─ Entry: $580.50
├─ Target: $582.20
└─ Stop: $579.65

Option Flow:
├─ Calls: 65% | Puts: 35%
├─ Magnet Strike: $580
└─ Unusual Activity: YES ⚡

Reasons:
• AI: CALL (72%)
• Price > VWAP
• Bullish EMA stack
• MACD bullish
• Options: 65% calls
```

---

## 🧠 AI Model

The engine uses a trained ensemble model:

- **Random Forest** (35% weight)
- **XGBoost** (35% weight)
- **LightGBM** (30% weight)

Features include:
- Price returns (1, 5, 10 bar)
- RSI, MACD, ADX
- Price vs EMAs (9, 21, 50)
- Volume ratio
- ATR percentage
- Time of day features

---

## 📈 Technical Indicators

From Pine Script indicators:

- **ZLEMA** (8, 21) - Zero Lag EMA
- **EMA Stack** (9, 20, 21, 50, 100, 200)
- **MACD** (6, 26, 5) - Optimized for 0DTE
- **RSI** (7) - Aggressive period
- **ADX** - Trend strength
- **ATR** - Volatility
- **VWAP** - Volume Weighted Average Price
- **Daily Pivots** (P, R1, R2, S1, S2)
- **ORB Levels** - Opening Range Breakout

---

## ⚙️ Market Regimes

| VIX Level | Regime | Action |
|-----------|--------|--------|
| < 18 | 🟢 GREEN | Full risk-on, normal positions |
| 18-25 | 🟡 YELLOW | Caution, reduce size 50% |
| > 25 | 🔴 RED | No new trades |

---

## 📁 Project Structure

```
zero-trading-intelligence/
├── beast_engine.py      # THE MAIN ENGINE
├── config.yaml          # Configuration
├── requirements.txt     # Dependencies
├── Dockerfile           # For Jetson
├── docker-compose.yml   # Docker setup
├── models/
│   ├── ai_0dte_model.pkl    # Primary 0DTE model
│   ├── ai_ensemble.pkl      # ELVA ensemble
│   └── ai_swing_model.pkl   # Swing trade model
├── logs/                # Runtime logs
└── README.md            # This file
```

---

## 🎮 Commands

| Command | Description |
|---------|-------------|
| `python beast_engine.py` | Run continuous scanning |
| `python beast_engine.py scan` | Single market scan |
| `python beast_engine.py query SPY` | Detailed analysis of SPY |
| `python beast_engine.py brief` | Send morning intelligence brief |

---

## 📋 Requirements

- Python 3.10+
- Alpaca API account (paper trading)
- Telegram Bot (for alerts)
- Jetson Orin AGX (recommended) or any Linux/Windows machine

---

## 🔒 Disclaimer

This software is for educational and informational purposes only. Trading 0DTE options is extremely risky. Always do your own research and never trade money you can't afford to lose.

---

## 🦁 BEAST MODE ACTIVATED

*"The market is a battlefield. BEAST ENGINE is your weapon."*
