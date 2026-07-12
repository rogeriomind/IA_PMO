# Tenant Security

## Authorization

Admin routes require a valid `Authorization: Bearer <AGENT_API_TOKEN>` header.

Roles:

- `platform.admin`, `agent.admin` or `admin`: can administer all tenants.
- `tenant.admin`: can administer only the tenant from `X-Tenant-ID`.
- `tenant.manager`: can manage tenant settings but cannot change secrets.

Board write tools continue to require board write roles in the agent layer.

## Secrets

Tenant secrets are stored in `tenant_secrets` encrypted with AES-GCM. Configure:

```env
ENCRYPTION_KEY=<32-byte-base64-or-hex-key>
```

Secret APIs return only:

```json
{
  "configured": true,
  "masked": "********abcd",
  "last_rotated_at": "..."
}
```

Secrets must not be logged, sent to Langfuse, or returned to frontends.
