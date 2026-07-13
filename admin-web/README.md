# IA PMO Admin Web

Front administrativo multi-tenant para operar o agente IA PMO, acompanhar conversas, visualizar o fluxo LangGraph e publicar configurações por empresa.

## Stack

React, TypeScript, Vite, React Router, TanStack Query, React Hook Form, Zod, Axios, React Flow, Recharts, Lucide React e Tailwind CSS.

## Como rodar com dados da VPS

```bash
npm install
npm run dev
```

Por padrão o front usa `VITE_API_BASE_URL=/api`. Em produção, essa rota deve apontar para o backend FastAPI por reverse proxy.

## API

A arquitetura esperada é React/Nginx chamando o backend FastAPI via `/api`. O frontend não acessa diretamente bancos, MCP, Langfuse, provedores LLM ou canais externos.

## Configuração local

```env
VITE_API_BASE_URL=/api
VITE_APP_NAME=IA PMO
VITE_USE_MOCK_API=true
```

## Modo mock

O mock permite navegar por todas as telas sem o backend administrativo pronto:

```bash
npm run dev
```

## Rotas

- `/`
- `/dashboard`
- `/conversations`
- `/conversations/:threadId`
- `/pending-actions`
- `/threads`
- `/langgraph`
- `/integrations`
- `/events`
- `/reports`
- `/settings`
- `/audit`
- `/users`
- `/admin`

## Build

```bash
npm run lint
npm run typecheck
npm run test
npm run build
```

## Testes

```bash
npm run test
```

Os testes usam `.env.test` e não acessam a VPS.

## Produção

```bash
docker build -t ia-pmo-admin-web .
docker run --rm -p 8080:80 ia-pmo-admin-web
```

Healthcheck:

```bash
wget -qO- http://localhost:8080/health
```
