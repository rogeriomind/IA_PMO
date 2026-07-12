# Tenant Configuration

Tenant configuration is edited as mutable control-plane rows and activated through publish snapshots.

Main components:

- branding
- channels
- AI provider/model/prompt
- agent policies
- PMO Board, MCP, Langfuse and Redis integrations
- rate limits and debounce settings
- feature flags
- encrypted secrets

`TenantConfigurationService` returns an aggregate configuration and caches it by:

```text
tenant_id + active_version
```

Publishing invalidates the local cache and creates an immutable `tenant_configuration_versions` record.

Rollback restores a previous snapshot and publishes a new active version.
