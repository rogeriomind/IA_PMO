# Arquitetura Frontend

O `admin-web` é uma aplicação React, TypeScript e Vite organizada por páginas, serviços, contextos e componentes reutilizáveis.

## Camadas

- `src/App.tsx`: providers globais, router e rotas administrativas.
- `src/contexts`: `TenantContext` e `AuthContext`.
- `src/lib/api.ts`: client Axios central com interceptors para `Authorization`, `X-Tenant-ID`, `X-Request-ID` e `X-Correlation-ID`.
- Backend FastAPI: atende os contratos administrativos por `/api/admin/v1/*` quando publicado atras do reverse proxy.
- `src/services`: contratos de consumo da API administrativa.
- `src/mocks`: dados navegáveis quando `VITE_USE_MOCK_API=true`.
- `src/pages`: telas roteadas do produto.
- `src/components`: layout, navegação e componentes visuais.

## Multi-tenant

O tenant ativo é salvo em `localStorage` com a chave `ia-pmo-active-tenant`. Ao trocar a empresa, o contexto atualiza o header `X-Tenant-ID` e invalida as queries do TanStack Query.

## API

O front chama somente `VITE_API_BASE_URL`, que deve ser `/api` em produção. O navegador não deve acessar diretamente DeepSeek, OpenAI, Telegram, WhatsApp, MCP, Langfuse, Redis, PostgreSQL ou Docker.

## Estados

As telas usam `PageState` para loading, empty, error, unauthorized, forbidden, tenant suspenso e integração indisponível.
