# URGENT FIX - Redis Package Not Installing

The rebuild happened but redis package is STILL not in the container. This means the pip install step is either:
1. Failing silently
2. Using cached/wrong requirements.txt
3. Build cache issue

## Quick Diagnostic (Run on Jetson):

```bash
# Check if redis is installed in the running container
docker compose --env-file .env -f infra/docker-compose.yml run --rm zero-ingest-price pip list | grep redis

# If empty, redis isn't installed. Check build logs:
docker compose --env-file .env -f infra/docker-compose.yml build zero-ingest-price 2>&1 | grep -i redis

# Verify requirements.txt has redis
cat services/ingest/requirements.txt | grep redis
```

## If Redis NOT Installed - Force Rebuild with Verbose Output:

```bash
make down
docker rmi -f infra-zero-ingest-price

# Rebuild with verbose output to see pip install
docker compose --env-file .env -f infra/docker-compose.yml build --progress=plain --no-cache zero-ingest-price 2>&1 | tee build.log

# Check if redis installed successfully
grep -i "redis" build.log
grep -i "error" build.log
```

## Nuclear Option - Test Install Manually:

```bash
# Start container and try installing redis manually
docker compose --env-file .env -f infra/docker-compose.yml run --rm zero-ingest-price pip install redis>=5.0.0

# If that works, the issue is with the build process
# If that fails, there's a dependency/environment issue
```

Run the diagnostic commands first to see what's happening!
