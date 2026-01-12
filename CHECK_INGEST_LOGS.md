# Check Ingest Service Logs

The ingest service is rebuilding but still restarting. Check the logs to see what error it's hitting now:

```bash
docker compose --env-file .env -f infra/docker-compose.yml logs zero-ingest-price --tail=50
```

This will show us:
1. If redis package is now installed (should be, after rebuild)
2. What new error (if any) is causing the restart
3. Whether it's a different issue now

Common issues after rebuild:
- Still redis errors (package didn't install) - check requirements.txt
- Database connection errors - check DB credentials
- Configuration errors - check environment variables
- Import errors - check code structure

Run the command above and share the output!
