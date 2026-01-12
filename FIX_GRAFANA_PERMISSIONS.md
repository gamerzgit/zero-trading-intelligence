# Fix Grafana Permissions Issue

## Problem
Grafana container can't write to `/var/lib/grafana` (mapped to `./data_nvme/grafana`)

## Solution

Run these commands on your Jetson:

```bash
# 1. Stop Grafana
docker compose --env-file .env -f infra/docker-compose.yml stop grafana

# 2. Remove old data (if corrupted)
sudo rm -rf data_nvme/grafana/*

# 3. Set correct permissions (Grafana runs as user ID 472)
sudo chown -R 472:472 data_nvme/grafana

# 4. Ensure directory is writable
chmod -R 755 data_nvme/grafana

# 5. Restart Grafana
docker compose --env-file .env -f infra/docker-compose.yml up -d grafana

# 6. Wait a few seconds, then check status
docker compose --env-file .env -f infra/docker-compose.yml ps grafana

# 7. Check logs to verify it started
docker compose --env-file .env -f infra/docker-compose.yml logs grafana --tail=20
```

## Alternative: Use user namespace (if 472:472 doesn't work)

If the above doesn't work, you can make the directory writable by the container:

```bash
# Stop Grafana
docker compose --env-file .env -f infra/docker-compose.yml stop grafana

# Make directory writable by all (Grafana will create files with correct permissions)
sudo chmod -R 777 data_nvme/grafana

# Restart
docker compose --env-file .env -f infra/docker-compose.yml up -d grafana
```

## Verify

After fixing, test:
```bash
# Should return "OK" or similar
curl http://localhost:3000/api/health

# Check status
docker compose --env-file .env -f infra/docker-compose.yml ps grafana
# Should show "Up" not "Restarting"
```

## Access Grafana

Once running, access at:
- Local: `http://localhost:3000`
- Network: `http://192.168.1.72:3000` (your Jetson IP)

Login:
- User: `admin`
- Password: `ZeroGrafana2024!` (from your .env)
