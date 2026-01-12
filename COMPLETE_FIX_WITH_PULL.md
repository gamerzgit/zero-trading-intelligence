# Complete Fix - Start Here! 🔧

## Always Pull Latest Code First!

**Before running any fixes, always pull the latest code:**

```bash
git pull
```

This ensures you have all the latest fixes and changes.

---

## Complete Fix for Current Issues

```bash
# STEP 0: Pull latest code from GitHub (IMPORTANT!)
git pull

# STEP 1: Stop all services
make down

# STEP 2: Force remove old ingest image
docker rmi -f infra-zero-ingest-price

# STEP 3: Rebuild ingest service (will install redis package)
docker compose --env-file .env -f infra/docker-compose.yml build --no-cache zero-ingest-price

# STEP 4: Start all services
make up

# STEP 5: Wait 30 seconds, then check status
sleep 30
make status

# STEP 6: Check ingest logs (should have NO redis errors)
docker compose --env-file .env -f infra/docker-compose.yml logs zero-ingest-price --tail=30

# STEP 7: Restart regime service (to clear old table error)
docker compose --env-file .env -f infra/docker-compose.yml restart zero-regime

# STEP 8: Verify everything works
python scripts/verify_state.py
```

---

## Expected Results

After running this:
- ✅ Ingest service: No redis import errors, service starts successfully
- ✅ Regime service: Connected to DB, state changes working
- ✅ Scanner service: Connected, subscribed, working
- ✅ Verification script: Most checks should pass

---

## Why Git Pull First?

All fixes and improvements are being pushed to GitHub as we work. Always pull first to ensure you have:
- Latest code fixes
- Updated Dockerfiles
- Latest documentation
- All improvements

**Never skip the git pull step!**
