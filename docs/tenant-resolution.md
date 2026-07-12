# Tenant Resolution

Tenant IDs must be resolved by trusted backend code, not by end-user input.

Supported request headers for IA_PMO:

```http
Authorization: Bearer <AGENT_API_TOKEN>
X-Tenant-ID: <tenant-id>
X-Tenant-Slug: <tenant-slug>
X-User-ID: <user-id>
X-User-Roles: tenant.admin,board.read
X-Request-ID: <request-id>
X-Correlation-ID: <correlation-id>
X-Channel: telegram
```

Expected PMO_productpulse flow:

1. Identify inbound channel account.
2. Resolve tenant from `tenant_channels.external_identifier` or provider account id.
3. Reject suspended or unknown tenants.
4. Pass the resolved tenant context to IA_PMO with service authentication.

When `MULTI_TENANT_ENABLED=false`, integrations may temporarily use the default tenant for legacy compatibility.
