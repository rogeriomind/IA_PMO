from __future__ import annotations

import asyncio
import json
import logging
import re
import shlex
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.config import Settings

logger = logging.getLogger(__name__)


class MCPToolUnavailableError(RuntimeError):
    pass


SEMANTIC_TOOL_ALIASES: dict[str, tuple[str, ...]] = {
    "search_tasks": (
        "board_search_tasks",
        "search_tasks",
        "find_tasks",
        "query_tasks",
        "buscar_tarefas",
        "pesquisar_tarefas",
        "list_tasks",
    ),
    "get_task": ("board_get_task", "get_task", "read_task", "task_get", "obter_tarefa", "consultar_tarefa"),
    "create_task": ("board_create_task", "create_task", "add_task", "create_card", "criar_tarefa", "adicionar_tarefa"),
    "update_task": ("board_update_task", "update_task", "edit_task", "patch_task", "atualizar_tarefa", "alterar_tarefa"),
    "move_task": ("board_move_task", "move_task", "move_card", "set_task_status", "mover_tarefa", "alterar_status_tarefa"),
    "add_comment": ("board_add_comment", "add_comment", "comment_task", "add_task_comment", "adicionar_comentario", "comentar_tarefa"),
    "get_project_status": (
        "board_get_project_status",
        "get_project_status",
        "project_status",
        "board_status",
        "status_board",
        "obter_status_projeto",
    ),
    "list_blockers": ("board_list_blockers", "list_blockers", "get_blockers", "listar_bloqueios", "bloqueios"),
    "list_my_tasks": ("board_list_my_tasks", "list_my_tasks", "my_tasks", "assigned_tasks", "minhas_tarefas"),
}

STOPWORDS = {
    "json",
    "http",
    "https",
    "true",
    "false",
    "null",
    "string",
    "number",
    "boolean",
    "object",
    "array",
    "request",
    "response",
    "example",
}


@dataclass
class BoardToolRegistry:
    loaded: bool
    source_path: str
    tools: set[str] = field(default_factory=set)
    semantic_map: dict[str, str] = field(default_factory=dict)
    error: str | None = None

    @classmethod
    def from_settings(cls, settings: Settings) -> "BoardToolRegistry":
        tools: set[str] = set()
        error = None
        loaded = False

        path = Path(settings.mcp_board_doc_path)
        if path.exists():
            try:
                text = path.read_text(encoding="utf-8")
                tools = cls._extract_tool_names(text)
                loaded = True
            except Exception as exc:
                error = str(exc)
                logger.exception("Failed to load MCP board documentation")
        else:
            error = f"MCP board documentation not found at {settings.mcp_board_doc_path}"
            logger.warning(error)

        semantic_map = cls._build_semantic_map(tools)
        semantic_map.update(cls._load_env_tool_map(settings.mcp_tool_map_json, tools))
        return cls(
            loaded=loaded,
            source_path=settings.mcp_board_doc_path,
            tools=tools,
            semantic_map=semantic_map,
            error=error,
        )

    @staticmethod
    def _extract_tool_names(markdown: str) -> set[str]:
        candidates: set[str] = set()
        patterns = [
            r"`([A-Za-z][A-Za-z0-9_.-]{2,})`",
            r'["\']name["\']\s*:\s*["\']([A-Za-z][A-Za-z0-9_.-]{2,})["\']',
            r"^\s{0,3}#{2,6}\s+([A-Za-z][A-Za-z0-9_.-]{2,})\s*$",
            r"^\s*[-*]\s+([A-Za-z][A-Za-z0-9_.-]{2,})\s*[:(-]",
            r"^\s*tool\s*:\s*([A-Za-z][A-Za-z0-9_.-]{2,})\s*$",
            r"^\s*(board_[A-Za-z][A-Za-z0-9_.-]{2,})\s*$",
        ]
        for pattern in patterns:
            for match in re.finditer(pattern, markdown, flags=re.IGNORECASE | re.MULTILINE):
                value = match.group(1).strip()
                if value.casefold() not in STOPWORDS:
                    candidates.add(value)
        return candidates

    @staticmethod
    def _build_semantic_map(tools: set[str]) -> dict[str, str]:
        by_casefold = {tool.casefold(): tool for tool in tools}
        mapping: dict[str, str] = {}
        for internal_name, aliases in SEMANTIC_TOOL_ALIASES.items():
            for alias in aliases:
                if alias.casefold() in by_casefold:
                    mapping[internal_name] = by_casefold[alias.casefold()]
                    break
        return mapping

    @staticmethod
    def _load_env_tool_map(raw_map: str, documented_tools: set[str]) -> dict[str, str]:
        if not raw_map.strip():
            return {}
        try:
            parsed = json.loads(raw_map)
        except json.JSONDecodeError:
            logger.error("MCP_TOOL_MAP_JSON is not valid JSON")
            return {}
        if not isinstance(parsed, dict):
            logger.error("MCP_TOOL_MAP_JSON must be a JSON object")
            return {}

        allowed = {tool.casefold(): tool for tool in documented_tools}
        mapping: dict[str, str] = {}
        for internal_name, real_name in parsed.items():
            if internal_name not in SEMANTIC_TOOL_ALIASES or not isinstance(real_name, str):
                continue
            if documented_tools and real_name.casefold() not in allowed:
                logger.error("Configured MCP tool '%s' is not present in board_pmo.md", real_name)
                continue
            mapping[internal_name] = allowed.get(real_name.casefold(), real_name)
        return mapping

    def real_tool_name(self, internal_name: str) -> str:
        tool_name = self.semantic_map.get(internal_name)
        if not tool_name:
            raise MCPToolUnavailableError(
                f"MCP tool for '{internal_name}' is not documented or mapped from {self.source_path}"
            )
        return tool_name


class MCPBoardClient:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.registry = BoardToolRegistry.from_settings(settings)

    @property
    def mcp_loaded(self) -> bool:
        return self.registry.loaded and bool(self.registry.semantic_map)

    async def call_semantic_tool(
        self,
        internal_name: str,
        arguments: dict[str, Any],
        *,
        read_only: bool,
    ) -> Any:
        real_tool_name = self.registry.real_tool_name(internal_name)
        retries = max(0, self.settings.mcp_read_retries) if read_only else 0

        last_error: Exception | None = None
        for attempt in range(retries + 1):
            try:
                return await asyncio.wait_for(
                    self._call_tool(real_tool_name, arguments),
                    timeout=self.settings.mcp_timeout_seconds,
                )
            except Exception as exc:
                last_error = exc
                if not read_only or attempt >= retries:
                    break
                await asyncio.sleep(0.2 * (attempt + 1))

        raise RuntimeError(f"MCP tool call failed for '{real_tool_name}'") from last_error

    async def _call_tool(self, tool_name: str, arguments: dict[str, Any]) -> Any:
        transport = self.settings.mcp_board_transport
        if transport in {"http", "streamable_http"}:
            return await self._call_streamable_http(tool_name, arguments)
        if transport == "sse":
            return await self._call_sse(tool_name, arguments)
        if transport == "stdio":
            return await self._call_stdio(tool_name, arguments)
        raise ValueError(f"Unsupported MCP transport: {transport}")

    async def _call_streamable_http(self, tool_name: str, arguments: dict[str, Any]) -> Any:
        if not self.settings.mcp_board_url:
            raise ValueError("MCP_BOARD_URL is required for HTTP MCP transport")
        from mcp import ClientSession

        try:
            from mcp.client.streamable_http import streamablehttp_client
        except ImportError:
            from mcp.client.streamable_http import streamable_http_client as streamablehttp_client

        async with streamablehttp_client(self.settings.mcp_board_url) as streams:
            read_stream, write_stream, *_ = streams
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                result = await session.call_tool(tool_name, arguments)
                return self._normalize_result(result)

    async def _call_sse(self, tool_name: str, arguments: dict[str, Any]) -> Any:
        if not self.settings.mcp_board_url:
            raise ValueError("MCP_BOARD_URL is required for SSE MCP transport")
        from mcp import ClientSession
        from mcp.client.sse import sse_client

        async with sse_client(self.settings.mcp_board_url) as streams:
            read_stream, write_stream = streams
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                result = await session.call_tool(tool_name, arguments)
                return self._normalize_result(result)

    async def _call_stdio(self, tool_name: str, arguments: dict[str, Any]) -> Any:
        if not self.settings.mcp_board_url:
            raise ValueError("MCP_BOARD_URL must contain the stdio command")
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        command_parts = shlex.split(self.settings.mcp_board_url)
        if not command_parts:
            raise ValueError("MCP_BOARD_URL stdio command is empty")
        params = StdioServerParameters(command=command_parts[0], args=command_parts[1:])
        async with stdio_client(params) as streams:
            read_stream, write_stream = streams
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                result = await session.call_tool(tool_name, arguments)
                return self._normalize_result(result)

    @staticmethod
    def _normalize_result(result: Any) -> Any:
        if hasattr(result, "structured_content") and getattr(result, "structured_content") is not None:
            return getattr(result, "structured_content")
        if hasattr(result, "structuredContent") and getattr(result, "structuredContent") is not None:
            return getattr(result, "structuredContent")

        if hasattr(result, "model_dump"):
            dumped = result.model_dump(mode="json")
        elif hasattr(result, "dict"):
            dumped = result.dict()
        else:
            return result

        is_error = bool(dumped.get("isError") or dumped.get("is_error"))
        content = dumped.get("content")
        if isinstance(content, list):
            normalized = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    text = item.get("text", "")
                    try:
                        normalized.append(json.loads(text))
                    except json.JSONDecodeError:
                        normalized.append(text)
                else:
                    normalized.append(item)
            if len(normalized) == 1:
                single = normalized[0]
                if is_error or (isinstance(single, str) and single.startswith("MCP error")):
                    raise RuntimeError(str(single))
                return single
            if is_error:
                raise RuntimeError(json.dumps(normalized, ensure_ascii=False))
            return normalized
        if is_error:
            raise RuntimeError(json.dumps(dumped, ensure_ascii=False))
        return dumped
