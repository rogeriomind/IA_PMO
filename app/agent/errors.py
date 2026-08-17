from __future__ import annotations


class AgentError(Exception):
    code = "AGENT_ERROR"
    user_message = "Nao foi possivel processar sua mensagem agora."

    def __init__(self, message: str | None = None, *, code: str | None = None):
        super().__init__(message or self.user_message)
        if code:
            self.code = code


class IntentClassificationError(AgentError):
    code = "INTENT_CLASSIFICATION_ERROR"
    user_message = "Nao consegui entender a solicitacao com seguranca."


class AuthorizationError(AgentError):
    code = "AUTHORIZATION_ERROR"
    user_message = "Voce nao tem permissao para executar esta acao."


class ToolNotAllowedError(AgentError):
    code = "TOOL_NOT_ALLOWED"
    user_message = "A ferramenta solicitada nao e permitida para esta intencao."


class ToolValidationError(AgentError):
    code = "TOOL_VALIDATION_ERROR"
    user_message = "Os dados enviados para a ferramenta estao incompletos ou invalidos."


class MCPTimeoutError(AgentError):
    code = "MCP_TIMEOUT"
    user_message = "Nao foi possivel consultar o board neste momento."


class MCPTransientError(AgentError):
    code = "MCP_TRANSIENT_ERROR"
    user_message = "O board esta temporariamente indisponivel."


class MCPPermanentError(AgentError):
    code = "MCP_PERMANENT_ERROR"
    user_message = "Nao consegui executar a acao no board."


class ConfirmationRequiredError(AgentError):
    code = "CONFIRMATION_REQUIRED"
    user_message = "Esta acao precisa de confirmacao antes de ser executada."


class IdempotencyConflictError(AgentError):
    code = "IDEMPOTENCY_CONFLICT"
    user_message = "Esta acao ja foi processada com outros dados."


class TenantContextMissingError(AgentError):
    code = "TENANT_NOT_FOUND"
    user_message = "Nao consegui identificar o tenant desta conversa."


class ProjectContextMissingError(AgentError):
    code = "PROJECT_NOT_FOUND"
    user_message = "Preciso saber em qual projeto voce quer trabalhar."


class ProjectContextAmbiguousError(AgentError):
    code = "PROJECT_AMBIGUOUS"
    user_message = "Encontrei mais de um projeto com essa referencia. Qual deles voce quer usar?"


class ProjectAccessDeniedError(AgentError):
    code = "PROJECT_ACCESS_DENIED"
    user_message = "Voce nao tem acesso a esse projeto."


class ActivityProjectMismatchError(AgentError):
    code = "ACTIVITY_NOT_IN_PROJECT"
    user_message = "Essa atividade nao pertence ao projeto ativo."


class BoardContractError(AgentError):
    code = "BOARD_CONTRACT_ERROR"
    user_message = "Nao consegui montar uma chamada valida para o Board."


class ThreadLockedError(AgentError):
    code = "THREAD_LOCKED"
    user_message = "Esta conversa ja esta sendo processada. Tente novamente em instantes."
