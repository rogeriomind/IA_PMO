# Agent Endpoint Inventory

Baseline captured for the V2 migration.

## Summary

| Endpoint | File | Status | Runtime path |
| --- | --- | --- | --- |
| `POST /agent/invoke` | `app/main.py` | Deprecated compatibility | Legacy `app.graph` invoke graph |
| `POST /agent/process` | `app/main.py` | Deprecated compatibility | Legacy ExternalAgentService classifier response |
| `POST /agent/confirm` | `app/main.py` | Deprecated compatibility | Legacy `app.graph` confirmation graph |
| `POST /v1/agent/messages` | `app/api/routes/agent_v1.py` | Deprecated compatibility | V1 `AgentWorkflowService` |
| `POST /v1/agent/confirmations` | `app/api/routes/agent_v1.py` | Deprecated compatibility | V1 `AgentWorkflowService` confirmation |
| `POST /v2/agent/events` | `app/api/routes/agent_v2.py` | Official | V2 `AgentV2Service` |
| `GET /v2/agent/threads/{thread_id}` | `app/api/routes/agent_v2.py` | V2 admin/support | V2 thread snapshot |

## Legacy `/agent/invoke`

- Method: `POST`
- Input schema: `AgentInvokeRequest`
- Output schema: `AgentInvokeResponse`
- Service/runtime: `api.state.invoke_graph`, built by `app.graph.builder.build_invoke_graph`
- Graph: legacy `app.graph`
- MCP tools: direct `BoardTools` calls from legacy graph nodes for status, task search, blockers, and my tasks
- Confirmation: creates legacy pending actions for writes; execution happens later through `/agent/confirm`
- External dependencies: LLM provider through `IntentService`, Board MCP through `BoardTools`, Langfuse, SQLite/Postgres repository

## Legacy `/agent/process`

- Method: `POST`
- Input schema: `ExternalAgentProcessRequest`
- Output schema: `ExternalAgentProcessResponse`
- Service/runtime: inline compatibility logic in `app/main.py`
- Graph: none
- MCP tools: none
- Confirmation: returns a legacy-style `board_action` preview only
- External dependencies: LLM provider through `IntentService`, Langfuse

## Legacy `/agent/confirm`

- Method: `POST`
- Input schema: `AgentConfirmRequest`
- Output schema: `AgentConfirmResponse`
- Service/runtime: `api.state.confirm_graph`, built by `app.graph.builder.build_confirmation_graph`
- Graph: legacy confirmation graph
- MCP tools: direct `BoardTools` write calls through legacy `ConfirmationService`
- Confirmation: loads legacy pending action and executes only when `confirmed=true`
- External dependencies: Board MCP through `BoardTools`, pending action repository, Langfuse

## V1 `/v1/agent/messages`

- Method: `POST`
- Input schema: `AgentMessageRequest`
- Output schema: `AgentV1Response`
- Service/runtime: `AgentWorkflowService.handle_message`
- Graph: `app.agent.graph` main graph with task/project subgraphs
- MCP tools: `MCPGateway` via `ToolRegistry`
- Confirmation: V1 pending action flow returns `awaiting_confirmation`
- External dependencies: LLM provider, Board MCP through `MCPGateway`, repository, Langfuse

## V1 `/v1/agent/confirmations`

- Method: `POST`
- Input schema: `AgentConfirmationRequest`
- Output schema: `AgentV1Response`
- Service/runtime: `AgentWorkflowService.handle_confirmation`
- Graph: no new graph invocation; executes persisted pending action flow
- MCP tools: `MCPGateway`
- Confirmation: explicit approval/rejection validation using V1 confirmation logic
- External dependencies: Board MCP through `MCPGateway`, repository, Langfuse

## V2 `/v2/agent/events`

- Method: `POST`
- Input schema: `AgentEventEnvelope`
- Output schema: `AgentV2Response`
- Service/runtime: `AgentV2Service.handle_event`
- Graph: `app.agent.main_graph` with welcome, status, create, update, questions, and confirmation subgraphs
- MCP tools: `MCPGateway`
- Confirmation: V2 pending actions and `AgentV2ConfirmationService`; confirmations arrive as `message_type="confirmation"`
- External dependencies: LLM provider for extraction/classification where needed, Board MCP through `MCPGateway`, repository, Langfuse, optional Redis thread locks

## V2 `/v2/agent/threads/{thread_id}`

- Method: `GET`
- Input schema: path `thread_id` plus authenticated admin context
- Output schema: `AgentThreadSnapshot`
- Service/runtime: `AgentV2Service.get_thread`
- Graph: none
- MCP tools: none
- Confirmation: none
- External dependencies: repository

## Current Observability Baseline

- Request metrics are labeled with `api_version="legacy|v1|v2"`.
- Deprecated legacy and V1 endpoints return `Deprecation: true` and a `Link` header pointing to `</v2/agent/events>; rel="successor-version"`.
- `Sunset` is emitted only when `LEGACY_API_SUNSET_DATE` is configured.
- Structured logs now accept `api_version`, `request_id`, `correlation_id`, `thread_id`, `tenant_id`, and `user_id` fields.
