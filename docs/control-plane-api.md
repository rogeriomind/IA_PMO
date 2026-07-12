# Control Plane API

All routes require service token auth and admin roles.

```text
POST   /admin/v1/tenants
GET    /admin/v1/tenants
GET    /admin/v1/tenants/{tenant_id}
PATCH  /admin/v1/tenants/{tenant_id}

GET    /admin/v1/tenants/{tenant_id}/configuration
PUT    /admin/v1/tenants/{tenant_id}/configuration

GET    /admin/v1/tenants/{tenant_id}/branding
PUT    /admin/v1/tenants/{tenant_id}/branding

GET    /admin/v1/tenants/{tenant_id}/channels
POST   /admin/v1/tenants/{tenant_id}/channels
PATCH  /admin/v1/tenants/{tenant_id}/channels/{channel_id}
POST   /admin/v1/tenants/{tenant_id}/channels/{channel_id}/test

GET    /admin/v1/tenants/{tenant_id}/ai-config
PUT    /admin/v1/tenants/{tenant_id}/ai-config
POST   /admin/v1/tenants/{tenant_id}/ai-config/test

GET    /admin/v1/tenants/{tenant_id}/integrations
POST   /admin/v1/tenants/{tenant_id}/integrations
PATCH  /admin/v1/tenants/{tenant_id}/integrations/{integration_id}
POST   /admin/v1/tenants/{tenant_id}/integrations/{integration_id}/test

GET    /admin/v1/tenants/{tenant_id}/users
POST   /admin/v1/tenants/{tenant_id}/users
PATCH  /admin/v1/tenants/{tenant_id}/users/{user_id}

GET    /admin/v1/tenants/{tenant_id}/policies
PUT    /admin/v1/tenants/{tenant_id}/policies

POST   /admin/v1/tenants/{tenant_id}/secrets/{secret_name}
POST   /admin/v1/tenants/{tenant_id}/secrets/{secret_name}/rotate

POST   /admin/v1/tenants/{tenant_id}/publish
GET    /admin/v1/tenants/{tenant_id}/versions
POST   /admin/v1/tenants/{tenant_id}/versions/{version}/rollback
```

Use `X-Tenant-ID` with `tenant.admin`. Platform admins can manage any tenant.
