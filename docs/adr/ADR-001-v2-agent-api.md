# ADR-001: V2 Agent API as Canonical Architecture

Status: Accepted

## Decision

V2 becomes the canonical IA_PMO architecture.

Legacy and V1 APIs become compatibility layers.
New capabilities are implemented exclusively in V2.

The official production contract for agent events is:

```text
POST /v2/agent/events
```

## Motivation

The repository currently contains three agent surfaces: legacy `/agent/*`, V1 `/v1/agent/*`, and V2 `/v2/agent/events`. Keeping business logic across those paths increases maintenance cost, creates divergent behavior, and makes observability harder to reason about. V2 already owns the newer stateful conversation model, explicit event envelope, domain subgraphs, replay/idempotency, centralized confirmation, and MCP gateway path expected by ProductPulse.

## V1 and Legacy vs V2

Legacy endpoints (`/agent/invoke`, `/agent/process`, `/agent/confirm`) are compatibility endpoints for older workers. They use legacy schemas and, for invoke/confirm, still rely on the old graph/runtime.

V1 endpoints (`/v1/agent/messages`, `/v1/agent/confirmations`) introduced a workflow-first graph, deterministic routing, tool registry, MCPGateway, and persistent pending actions, but the HTTP contract is not the final ProductPulse event contract.

V2 (`/v2/agent/events`) uses a versioned event envelope with `event_id`, `request_id`, `correlation_id`, `thread_id`, tenant/user/channel context, explicit message types, stateful menus, domain subgraphs, V2 pending actions, and replay protection.

## Impact

New ProductPulse integration work must target V2. Legacy and V1 clients may continue during the compatibility window, but their endpoints are marked deprecated in OpenAPI and responses return deprecation headers pointing to `/v2/agent/events`.

No new business rule, prompt, tool call, confirmation behavior, or board workflow should be implemented only in legacy or V1 code. Temporary adapters should translate old payloads into the V2 application contract as the migration proceeds.

## Risks

The main risk is behavioral drift while old endpoints remain active. This is mitigated by characterization tests, version-labeled metrics, deprecation headers, and a phased adapter migration before any endpoint removal.

Another risk is removing an apparently idle endpoint too early. Removal must wait for measured legacy and V1 usage to reach zero for an agreed operational window.

## Deprecation Strategy

1. Publish V2 as official and mark legacy/V1 endpoints deprecated.
2. Measure usage with `api_version` labels for legacy, V1, and V2.
3. Move legacy and V1 execution behind compatibility adapters that call AgentService V2.
4. Keep compatibility behind feature flags during rollout.
5. Return `410 Gone` only after the team explicitly disables old APIs.
6. Physically remove endpoints, adapters, and legacy graph code only after usage is zero for the agreed window.

## Removal Criteria

Legacy and V1 can be removed only when all of these are true:

- ProductPulse uses only `POST /v2/agent/events`.
- `legacy_api_usage_total` / old-path request metrics are zero for the agreed window.
- V1 usage is zero for the agreed window.
- No production imports depend on `app.graph`.
- MCP calls go through `MCPGateway`.
- Confirmation and pending actions use the V2 infrastructure.
- Characterization, regression, architecture, and contract tests pass.
