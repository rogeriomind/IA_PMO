# Migration Guide

Run Alembic before starting the app in production:

```bash
alembic upgrade head
```

The migration `20260712_0002_tenant_control_plane.py` creates the control-plane tables and inserts:

```text
slug: default
name: Default Tenant
```

Existing agent state tables already include tenant columns for v2 state. Legacy rows without tenant context continue to work through `AGENT_DEFAULT_TENANT_ID`.

For PMO_productpulse, migrate in two phases:

1. Add nullable `tenant_id` to conversations, messages, queue, audit logs and locks.
2. Backfill with the default tenant.
3. Add indexes beginning with `tenant_id`.
4. Make `tenant_id` required.
5. Update unique constraints to include `tenant_id`.
