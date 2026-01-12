# Troubleshooting Guide

## TimescaleDB Container Unhealthy

### Symptoms
```
✘ Container zero-timescaledb    Error
dependency failed to start: container zero-timescaledb is unhealthy
```

### Diagnosis Steps

**1. Check TimescaleDB logs:**
```bash
docker compose -f infra/docker-compose.yml logs timescaledb
```

**2. Check data directory permissions:**
```bash
ls -la data_nvme/timescaledb
# Should show directory exists and has proper permissions
```

**3. Check disk space:**
```bash
df -h data_nvme/
# Ensure you have enough space (at least 5GB free)
```

### Common Fixes

**Fix 1: Permission Issues**
```bash
# Fix permissions on data directory
sudo chown -R $USER:$USER data_nvme/
chmod -R 755 data_nvme/

# If directory doesn't exist, create it
mkdir -p data_nvme/timescaledb
sudo chown -R $USER:$USER data_nvme/
```

**Fix 2: Clean Start (if database is corrupted)**
```bash
# STOP all services first
make down

# Remove TimescaleDB data (WARNING: Deletes all data)
sudo rm -rf data_nvme/timescaledb/*

# Recreate directory with proper permissions
mkdir -p data_nvme/timescaledb
sudo chown -R $USER:$USER data_nvme/

# Start again
make up
```

**Fix 3: Port Conflict**
```bash
# Check if port 5432 is already in use
sudo lsof -i :5432
# or
sudo netstat -tulpn | grep 5432

# If something is using it, stop that service or change POSTGRES_PORT in .env
```

**Fix 4: Check .env file**
```bash
# Verify DB_PASSWORD is set
cat .env | grep DB_PASSWORD
# Should show: DB_PASSWORD=your_password_here
```

### Quick Diagnostic Command

Run this to get all diagnostic info:
```bash
echo "=== TimescaleDB Logs ==="
docker compose -f infra/docker-compose.yml logs --tail=50 timescaledb
echo ""
echo "=== Data Directory ==="
ls -la data_nvme/timescaledb 2>&1 || echo "Directory does not exist"
echo ""
echo "=== Disk Space ==="
df -h data_nvme/ 2>&1 || df -h .
echo ""
echo "=== Port Check ==="
sudo lsof -i :5432 2>&1 || echo "Port 5432 not in use"
```
