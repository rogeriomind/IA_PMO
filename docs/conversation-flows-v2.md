# Fluxos Conversacionais V2

## Grafo Principal

```mermaid
flowchart TD
  START --> validate_event
  validate_event --> load_identity
  load_identity --> load_thread_memory
  load_thread_memory --> normalize_event
  normalize_event --> handle_global_commands
  handle_global_commands --> resolve_current_flow
  resolve_current_flow --> route_to_subgraph
  route_to_subgraph --> persist_session_summary
  persist_session_summary --> build_api_response
  build_api_response --> END
```

Comandos globais aceitos em qualquer fluxo: `cancelar`, `voltar`, `menu`, `inicio`, `reiniciar`, alem dos callbacks `global:cancel`, `global:back`, `global:menu`, `global:reset`.

## Menu

Deterministico. `welcome` ou `global:menu` retorna:

- Status: `menu:status`
- Criar atividade: `menu:create`
- Atualizar atividade: `menu:update`
- Duvidas: `menu:questions`

## Status

```mermaid
flowchart TD
  A["menu:status"] --> B["board_list_my_tasks"]
  B --> C["board_list_blockers"]
  C --> D["Combinar sem duplicar"]
  D --> E["Classificar bloqueadas / atrasadas / hoje"]
  E --> F["Persistir mapa numero -> task_id"]
  F --> G["Retornar numbered_list"]
  G --> H["status:task:N"]
  H --> I["board_get_task"]
  I --> J["Resumo + Atualizar atividade"]
```

O numero exibido nunca e tratado como ID real. Ele e resolvido por `agent_task_selection_maps`.

## Criacao

```mermaid
sequenceDiagram
  participant U as Usuario
  participant API as API V2
  participant DB as PostgreSQL
  participant MCP as MCP Gateway
  U->>API: texto com titulo/data
  API->>API: extracao estruturada
  API->>DB: salva draft
  API->>DB: cria pending action
  API-->>U: preview + confirmacao
  U->>API: confirmation:approve
  API->>DB: pending -> executing
  API->>MCP: board_create_task
  API->>MCP: board_get_task
  API->>DB: completed
  API-->>U: resultado
```

Obrigatorios: `title`, `due_date`. Opcionais: `description`, `assignee`, `priority`, `project_id`.

## Atualizacao

Entradas aceitas:

- selecionar por lista `update:list_tasks` + `update:task:N`;
- enviar indice numerico atual;
- enviar codigo real do board;
- buscar por texto, com lista de escolha quando ambiguo.

Campos liberados agora:

- `due_date`
- `assignee`, apenas quando resolvido com seguranca
- `comment`

Uma mensagem pode gerar varias operacoes. Exemplo:

```json
[
  {
    "tool_name": "board_update_task",
    "arguments": {
      "task_id": "TASK-123",
      "fields": {"due_date": "2026-07-17"}
    }
  },
  {
    "tool_name": "board_add_comment",
    "arguments": {
      "task_id": "TASK-123",
      "comment": "Aguardando retorno do CRM."
    }
  }
]
```

## Confirmacao

Estados persistidos: `pending`, `executing`, `completed`, `partial`, `rejected`, `expired`, `failed`, `unknown`.

Callbacks:

- `confirmation:approve:{id}`
- `confirmation:edit:{id}`
- `confirmation:reject:{id}`

Textos aceitos deterministamente:

- aprovacao: `sim`, `confirmo`, `confirmar`, `pode executar`, `aprovar`;
- rejeicao: `nao`, `cancelar`, `rejeitar`, `nao confirmar`.

Confirmacao reutilizada, expirada, de outro usuario, outra thread ou outro tenant nao executa escrita.

## Duvidas

Fluxo mockado por enquanto. Nao chama LLM nem MCP e retorna apenas `Voltar ao menu`.
