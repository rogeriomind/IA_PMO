# Visualização LangGraph

A tela `/langgraph` usa React Flow para representar o fluxo de execução do agente IA PMO.

## Tipos visuais

- Início/Fim: verde.
- Agente LLM: roxo.
- Ferramenta MCP: azul.
- Decisão: laranja.
- Auditoria/Eventos: roxo escuro.
- Confirmação humana: amarelo.
- Erro: vermelho.

## Funcionalidades

- Seleção de versão ativa.
- Execução de teste em drawer.
- Lista de execuções.
- Exportação JSON do grafo.
- Zoom, centralização e fullscreen.
- Painel lateral do nó com parâmetros, rotas, métricas e últimas execuções.
- Destaque do caminho percorrido ao selecionar uma execução.

Nenhum secret é exibido no painel do nó.
