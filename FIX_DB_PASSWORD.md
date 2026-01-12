# Fix DB Password Issue on Jetson

## Problem
Docker Compose isn't reading the `.env` file, so containers get empty passwords.

## Quick Fix

**Option 1: Use --env-file explicitly (Recommended)**

Update your commands to explicitly specify the .env file:

```bash
# Stop services
docker compose --env-file .env -f infra/docker-compose.yml down

# Start services  
docker compose --env-file .env -f infra/docker-compose.yml up -d

# Or use make (after we fix Makefile)
make up
```

**Option 2: Copy .env to infra/ directory (Temporary workaround)**

```bash
# Copy .env to infra directory (Docker Compose might look there)
cp .env infra/.env

# Then run normally
make up
```

**Option 3: Verify .env file location and format**

```bash
# Make sure you're in project root
cd ~/zero-trading-intelligence
pwd  # Should show: /home/gamerzdesktop/zero-trading-intelligence

# Check .env exists
ls -la .env

# Verify passwords are set (should show values, not empty)
grep -E "^POSTGRES_PASSWORD=|^DB_PASSWORD=" .env

# Check file format (no Windows line endings)
file .env
```

## Why This Happens

Docker Compose automatically loads `.env` from the directory where you run the command, but sometimes it doesn't work due to:
- Working directory issues
- File permissions
- File format (Windows vs Linux line endings)

Using `--env-file .env` explicitly tells Docker Compose where to find the file.
