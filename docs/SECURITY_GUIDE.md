# ZERO Platform - Security Guide

**Version:** 1.0  
**Last Updated:** 2026-01-11

---

## 🔐 API Key Security

### ✅ Current Security Status

**Your Alpaca API keys are SAFE:**

1. **`.env` file is gitignored** ✅
   - `.env` is listed in `.gitignore`
   - Never committed to GitHub
   - Only exists locally on your machine

2. **`.env.example` has placeholders only** ✅
   - No real keys in example file
   - Safe to commit to GitHub
   - Shows structure without secrets

3. **No hardcoded keys in code** ✅
   - All keys loaded from environment variables
   - No keys in source code
   - No keys in Docker images

4. **Keys loaded at runtime** ✅
   - Keys read from `.env` file
   - Passed to services via environment variables
   - Never logged or exposed

---

## 🚨 Security Checklist

### Before Deploying to Jetson

- [ ] **Verify `.env` is NOT in git**
  ```bash
  git ls-files | grep .env
  # Should return nothing
  ```

- [ ] **Verify `.env.example` has placeholders only**
  ```bash
  cat .env.example | grep ALPACA
  # Should show: ALPACA_API_KEY= (empty)
  ```

- [ ] **Check no keys in code**
  ```bash
  grep -r "PK[A-Z0-9]\{20\}" . --exclude-dir=.git
  # Should return nothing (no actual keys)
  ```

- [ ] **Verify keys are from environment**
  ```bash
  grep -r "os.getenv\|os.environ" services/
  # Should show keys loaded from env, not hardcoded
  ```

---

## 📋 Deployment to Jetson - Secure Process

### Step 1: Create `.env` on Jetson (NOT from git)

**On your Jetson:**

```bash
# Copy the example file
cp .env.example .env

# Edit with your actual keys (NEVER commit this)
nano .env
```

**Add your keys:**
```bash
ALPACA_API_KEY=your_actual_key_here
ALPACA_SECRET_KEY=your_actual_secret_here
ALPACA_PAPER=true
```

### Step 2: Verify `.env` is gitignored

```bash
# Check .gitignore
cat .gitignore | grep "\.env"
# Should show: .env

# Verify .env is not tracked
git status
# .env should NOT appear in "Changes to be committed"
```

### Step 3: Deploy Code (without keys)

```bash
# Clone/pull code (keys NOT included)
git clone https://github.com/gamerzgit/zero-trading-intelligence.git
cd zero-trading-intelligence

# Create .env locally (never commit)
cp .env.example .env
# Edit .env with your keys
```

---

## 🔒 Best Practices

### ✅ DO:

1. **Use `.env` file for local development**
   - Keep it gitignored
   - Never commit it

2. **Use environment variables in Docker**
   - Pass keys via `docker-compose.yml` environment section
   - Keys come from `.env` file (not hardcoded)

3. **Use paper trading keys for testing**
   - `ALPACA_PAPER=true` uses paper account
   - No real money at risk

4. **Rotate keys if exposed**
   - If keys ever leak, regenerate in Alpaca dashboard
   - Update `.env` with new keys

### ❌ DON'T:

1. **Never commit `.env` to git**
   - Even if it "looks safe"
   - Even if it's "just paper trading"

2. **Never hardcode keys in code**
   - Not in Python files
   - Not in Dockerfiles
   - Not in config files

3. **Never share `.env` file**
   - Don't email it
   - Don't paste in chat
   - Don't upload to cloud storage (unless encrypted)

4. **Never log keys**
   - Don't print API keys
   - Don't log them in files
   - Mask keys in error messages

---

## 🛡️ Alpaca Key Security

### Your Keys from ELVA

**Are they safe to use?**

✅ **YES** - If:
- They're paper trading keys (`ALPACA_PAPER=true`)
- They're stored only in `.env` (gitignored)
- They're not shared publicly

⚠️ **Consider regenerating if:**
- Keys were ever committed to git (check git history)
- Keys were shared with others
- You want fresh keys for ZERO

### How to Get New Keys (Optional)

1. **Log into Alpaca Dashboard**
   - https://app.alpaca.markets/

2. **Go to API Keys section**
   - Generate new paper trading keys

3. **Update `.env` file**
   - Replace old keys with new ones

4. **Test connection**
   ```bash
   python scripts/verify_system_standalone.py
   ```

---

## 🔍 Verification Commands

### Check if keys are exposed in git history

```bash
# Search git history for keys (be careful - this shows history)
git log -p --all -S "PK" | grep -A 5 -B 5 "ALPACA"
# If this shows actual keys, they were committed at some point
```

### Check current security status

```bash
# 1. Verify .env is gitignored
git check-ignore .env
# Should return: .env

# 2. Verify .env is not tracked
git ls-files .env
# Should return nothing

# 3. Check for hardcoded keys
grep -r "PK[A-Z0-9]\{20\}" . --exclude-dir=.git --exclude="*.md"
# Should return nothing
```

---

## 📝 Jetson Deployment Checklist

**Before deploying:**

- [ ] `.env` file created on Jetson (not from git)
- [ ] Keys added to `.env` manually
- [ ] `.env` verified as gitignored
- [ ] Paper trading keys used (`ALPACA_PAPER=true`)
- [ ] Connection tested with verification script

**After deploying:**

- [ ] Services start without key errors
- [ ] Data ingestion works
- [ ] No keys in logs
- [ ] Keys not exposed in Docker containers

---

## 🚨 If Keys Are Exposed

**If you accidentally commit keys:**

1. **Immediately regenerate keys in Alpaca dashboard**
2. **Remove from git history** (if possible):
   ```bash
   git filter-branch --force --index-filter \
     "git rm --cached --ignore-unmatch .env" \
     --prune-empty --tag-name-filter cat -- --all
   ```
3. **Force push** (destructive - be careful):
   ```bash
   git push origin --force --all
   ```
4. **Update `.env` with new keys**
5. **Add `.env` to `.gitignore`** (if not already)

**Note:** If keys are in public repo, assume they're compromised. Always regenerate.

---

## ✅ Summary

**Your current setup is SECURE:**

- ✅ `.env` is gitignored
- ✅ No keys in code
- ✅ Keys loaded from environment
- ✅ Safe to deploy to Jetson

**To deploy to Jetson:**

1. Clone code (no keys included)
2. Create `.env` manually on Jetson
3. Add your keys to `.env`
4. Never commit `.env`

**Your Alpaca keys from ELVA are safe to use** - just make sure they're only in `.env` (gitignored) and never committed to git.

---

**Remember: Security is a process, not a one-time check. Always verify before deploying.**

