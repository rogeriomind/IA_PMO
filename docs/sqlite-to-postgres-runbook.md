# SQLite to Postgres migration

Use this runbook during the controlled PMO Agent API maintenance window.

## Preconditions

- Gateway is running and can keep inbound Telegram messages queued.
- `/opt/pmo-ai-agent-api/pmo_agent.db` has been copied with `sha256sum`.
- `pmo-ai-agent-postgres` is healthy and has no agent data, or the import is a validated idempotent retry.
- Current API image and `.env` are recorded for rollback.

## Window

```bash
cd /opt/pmo-ai-agent-api
docker compose stop pmo-ai-agent-api

cp pmo_agent.db "/opt/backups/pmo_agent-$(date -u +%Y%m%dT%H%M%SZ).db"
sha256sum pmo_agent.db "/opt/backups/"*.db | tail

DATABASE_URL="postgresql+psycopg://pmo_agent:${POSTGRES_PASSWORD}@postgres:5432/pmo_agent" \
  docker compose run --rm pmo-ai-agent-api alembic upgrade head

docker compose run --rm \
  -e DATABASE_URL="postgresql+psycopg://pmo_agent:${POSTGRES_PASSWORD}@postgres:5432/pmo_agent" \
  pmo-ai-agent-api \
  python scripts/migrate_sqlite_to_postgres.py \
    --sqlite /app/pmo_agent.db \
    --target-url "postgresql+psycopg://pmo_agent:${POSTGRES_PASSWORD}@postgres:5432/pmo_agent" \
    --expect-min-threads 2
```

Then set `DATABASE_URL` and `APP_ENV=production` in `.env`, restart only the API, and validate:

```bash
docker compose up -d --no-deps pmo-ai-agent-api
curl -fsS http://localhost:${AGENT_API_PORT:-8010}/health
curl -fsS http://localhost:${AGENT_API_PORT:-8010}/ready
```

## Retry

If the import command exits before validation, inspect the error. A retry is allowed only after confirming the target contains the same rows:

```bash
python scripts/migrate_sqlite_to_postgres.py \
  --sqlite /app/pmo_agent.db \
  --target-url "$DATABASE_URL" \
  --idempotent \
  --expect-min-threads 2
```

## Rollback

Restore the previous `.env` values, removing `DATABASE_URL` or pointing it back to SQLite, then restart the same API image:

```bash
docker compose up -d --no-deps pmo-ai-agent-api
curl -fsS http://localhost:${AGENT_API_PORT:-8010}/ready
```
