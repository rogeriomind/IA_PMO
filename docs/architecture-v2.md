# Arquitetura V2 do PMO Agent

## Visao Geral

A API v2 transforma a IA em uma camada conversacional orientada a estado. O worker continua responsavel por Telegram, fila, debounce e renderizacao; a API passa a manter memoria, menus, mapas de selecao, rascunhos, pending actions, confirmacoes e auditoria.

```mermaid
flowchart TD
  A["Worker / Telegram"] --> B["POST /v2/agent/events"]
  B --> C["Auth + event envelope"]
  C --> D["Lock por tenant_id + thread_id"]
  D --> E["LangGraph main graph"]
  E --> F["Subgrafo menu"]
  E --> G["Subgrafo status"]
  E --> H["Subgrafo criacao"]
  E --> I["Subgrafo atualizacao"]
  E --> J["Subgrafo confirmacao"]
  G --> K["MCP Gateway leitura"]
  H --> L["Pending action"]
  I --> L
  J --> M["MCP Gateway escrita aprovada"]
  E --> N["PostgreSQL memory/audit/events"]
```

## Persistencia

PostgreSQL e a fonte de verdade em producao. As tabelas novas ficam modeladas em `app/storage/repository.py` e migradas por Alembic em `app/infrastructure/database/migrations`.

Tabelas principais:

- `agent_threads`: estado resumido por `tenant_id + thread_id`.
- `agent_task_selection_maps`: mapa temporario numero -> `task_id`.
- `agent_drafts`: rascunhos de criacao e atualizacao.
- `pending_actions`: evoluida para payload v2, operacoes, expiracao, status e versao.
- `agent_events`: replay/idempotencia de `event_id`.
- `agent_graph_checkpoints`: checkpoint serializavel preparado para LangGraph.

## MCP Gateway

A v2 reaproveita o gateway existente:

- registry allowlist;
- schemas Pydantic por tool;
- permissao por roles;
- retry apenas para leitura;
- escrita sem retry automatico;
- idempotencia por operacao;
- auditoria de tool call;
- read-after-write apos confirmacao.

Tools permitidas seguem restritas a:

`board_search_tasks`, `board_get_task`, `board_create_task`, `board_update_task`, `board_move_task`, `board_add_comment`, `board_get_project_status`, `board_list_blockers`, `board_list_my_tasks`.

## Seguranca

Todos os endpoints v2 exigem `Authorization: Bearer <AGENT_API_TOKEN>`. Em producao, `AGENT_API_TOKEN` e `DATABASE_URL` PostgreSQL sao obrigatorios. O valor padrao de roles e vazio; roles enviadas por header so fazem sentido quando vindas do worker autenticado.

Redis e opcional para lock distribuido:

```mermaid
flowchart LR
  A["REDIS_ENABLED=false"] --> B["ThreadLockManager em memoria"]
  C["REDIS_ENABLED=true"] --> D["RedisThreadLockManager"]
  B --> E["Apenas desenvolvimento/single replica"]
  D --> F["Multiplas replicas"]
```

## Observabilidade

Langfuse recebe payloads sanitizados. O modulo `app/infrastructure/observability/metrics.py` declara os nomes preparados para Prometheus:

- `agent_events_total`
- `agent_event_duration_seconds`
- `agent_flow_transitions_total`
- `agent_llm_calls_total`
- `agent_mcp_calls_total`
- `agent_confirmations_total`
- `agent_pending_actions_total`
- `agent_idempotency_hits_total`
- `agent_errors_total`
