# ZERO Platform - Branding & Naming Guide

**Version:** 1.0  
**Status:** MANDATORY - All code, docs, and outputs must follow this  
**Last Updated:** 2026-01-11

---

## 🚫 FORBIDDEN EXTERNAL REFERENCES

The following external names/concepts are **STRICTLY FORBIDDEN** in:
- Code (variables, functions, classes, comments)
- Documentation (README, docs, specs)
- User-facing text (UI, messages, logs)
- Configuration files
- API responses

**FORBIDDEN:**
- ❌ "ELVA" (any reference)
- ❌ "Anderson Zone" or "Anderson"
- ❌ "Pine Script" (as a named concept - use "Technical Engine")
- ❌ "Neural Brain" (use "Probability Engine")
- ❌ Any third-party strategy names
- ❌ Any external system references

---

## ✅ ZERO-NATIVE VOCABULARY

### Core Concepts

| External Reference | ZERO-Native Name | Usage |
|-------------------|------------------|-------|
| ELVA | ZERO Core | The core intelligence system |
| Anderson Zone | Prime Window | Optimal liquidity window (1-3 PM ET) |
| Pine Script Engine | Technical Engine | Technical indicator analysis |
| Neural Brain | Probability Engine | Core probability calculation |
| Brain Feedback | Truth & Calibration Engine | Learning and verification system |
| Strike Calculator | Options Context Engine | Options analysis (informational) |
| Pattern Engine | Market Structure Scanner | Pattern detection system |

### Time Windows (ET Timezone)

| External Name | ZERO Name | Description |
|--------------|-----------|-------------|
| Anderson Zone | Prime Window | 13:00-15:00 ET (optimal execution) |
| Opening | Opening Window | 09:30-10:30 ET (high volatility) |
| Lunch | Lunch Window | 11:00-13:00 ET (low volume/chop) |
| Closing | Closing Window | 15:00-16:00 ET (gamma/closing flows) |

### Regime States

| External Name | ZERO Name | VIX Range |
|--------------|-----------|-----------|
| CALM | Calm Regime | VIX < 15 |
| NORMAL | Normal Regime | VIX 15-20 |
| ELEVATED | Elevated Regime | VIX 20-25 |
| FEAR | Fear Regime | VIX 25-30 |
| PANIC | Panic Regime | VIX > 30 |

### Market Permission States

| State | Meaning | Action |
|-------|---------|-------|
| GREEN | Full Permission | All horizons allowed |
| YELLOW | Caution | Limited horizons (H30 only) |
| RED | Halt | No opportunities published |

---

## 📝 CODE NAMING CONVENTIONS

### Service Names
- `zero-regime` (not `elva-regime`)
- `zero-scanner` (not `elva-scanner`)
- `zero-probability` (not `neural-brain`)

### Class Names
- `RegimeCalculator` (not `ELVARegimeEngine`)
- `ProbabilityEngine` (not `NeuralBrain`)
- `PrimeWindowDetector` (not `AndersonZoneDetector`)

### Variable Names
- `prime_window_start` (not `anderson_zone_start`)
- `zero_core_weights` (not `elva_weights`)
- `probability_score` (not `neural_score`)

### Comments
```python
# ✅ CORRECT
# Prime Window: Optimal liquidity period (1-3 PM ET)
# ZERO Core probability calculation

# ❌ WRONG
# Anderson Zone: Best time to trade
# ELVA neural brain logic
```

---

## 🎯 USER-FACING TEXT

### ✅ CORRECT Examples

**Morning Brief:**
```
📊 ZERO Morning Brief
🟢 Market Status: GREEN (Risk ON)
⏰ Prime Window: Active (1-3 PM ET)
```

**Query Response:**
```
ZERO Analysis:
Probability: 68%
Timing: Prime Window approaching (optimal entry window)
```

**Log Messages:**
```
[ZERO] Market state: GREEN
[ZERO] Prime Window detected: 13:00-15:00 ET
[ZERO] Probability Engine: Calculating...
```

### ❌ WRONG Examples

```
❌ "Anderson Zone active"
❌ "ELVA profile loaded"
❌ "Neural Brain calculating"
❌ "Pine Script signal detected"
```

---

## 🔍 VERIFICATION CHECKLIST

Before committing code or documentation:

- [ ] No "ELVA" references
- [ ] No "Anderson" references
- [ ] No "Pine Script" as a named concept
- [ ] No "Neural Brain" references
- [ ] All time windows use ZERO names
- [ ] All engines use ZERO names
- [ ] All user-facing text uses ZERO vocabulary
- [ ] Code comments use ZERO terminology

---

## 📚 DOCUMENTATION STANDARDS

### README.md
- ✅ "ZERO Platform"
- ✅ "ZERO Core Intelligence"
- ✅ "Prime Window"
- ❌ No external references

### API Documentation
- ✅ "ZERO Probability Engine"
- ✅ "ZERO Regime Engine"
- ❌ No third-party names

### Code Comments
- ✅ "ZERO proprietary logic"
- ✅ "ZERO Core calculation"
- ❌ No external attributions

---

## 🎨 BRANDING PRINCIPLES

1. **Ownership First**: Everything is ZERO-native
2. **Professional Language**: Institutional-grade terminology
3. **Consistency**: Same concept = same name everywhere
4. **Clarity**: Names describe function, not origin
5. **Future-Proof**: Names work if you change underlying tools

---

## ⚠️ ENFORCEMENT

**This is non-negotiable.**

Any code, documentation, or output that violates this guide must be:
1. Immediately corrected
2. Re-reviewed before merge
3. Documented as a violation

**Why this matters:**
- Intellectual property protection
- Professional presentation
- Long-term maintainability
- Clear ownership

---

**Remember: ZERO is YOUR system. It speaks YOUR language.**

