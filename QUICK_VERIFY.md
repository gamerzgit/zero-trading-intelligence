# Quick Verification - Is Everything Working? ✅

## 30-Second Health Check

Run these commands to verify everything is working:

```bash
# 1. Check all services are running
make status

# 2. Check for errors in logs
docker compose --env-file .env -f infra/docker-compose.yml logs --tail=30 | grep -i error

# 3. Test health endpoints
curl http://localhost:8000/health  # Regime
curl http://localhost:8001/health  # Scanner  
curl http://localhost:8080/health  # Ingest
```

## ✅ Success Indicators

**Services are healthy if:**
- ✅ `make status` shows all services as `healthy` (or `starting` briefly)
- ✅ No ERROR messages in logs (only INFO/WARNING are OK)
- ✅ Health endpoints return JSON with `status: "healthy"` or `status: "ok"`
- ✅ Database tables exist (run `make psql` then `\dt`)
- ✅ Redis has state (run `make redis-cli` then `KEYS *`)

## 🧪 Automated Verification

Run the verification script:
```bash
python scripts/verify_state.py
```

**PASS = Everything working!** 🎉

For detailed verification steps, see `HOW_TO_VERIFY.md`
