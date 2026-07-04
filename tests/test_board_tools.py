import pytest

from app.mcp.board_tools import BoardTools, normalize_priority, normalize_status
from app.mcp.client import MCPBoardClient


class FakeClient:
    def __init__(self):
        self.calls = []

    async def call_semantic_tool(self, internal_name, arguments, *, read_only):
        self.calls.append((internal_name, arguments, read_only))
        return arguments


def test_normalize_priority_to_board_enum():
    assert normalize_priority("baixa") == "LOW"
    assert normalize_priority("média") == "MEDIUM"
    assert normalize_priority("alta") == "HIGH"
    assert normalize_priority("urgente") == "CRITICAL"


def test_normalize_status_to_board_enum():
    assert normalize_status("em andamento") == "IN_PROGRESS"
    assert normalize_status("bloqueado") == "BLOCKED"


@pytest.mark.asyncio
async def test_create_task_normalizes_priority_before_mcp_call():
    fake_client = FakeClient()
    board_tools = BoardTools(fake_client)

    result = await board_tools.create_task({"title": "Teste", "priority": "baixa"})

    assert result["priority"] == "LOW"
    assert fake_client.calls[0][0] == "create_task"


def test_mcp_error_result_raises_runtime_error():
    class Result:
        def model_dump(self, mode="json"):
            return {
                "isError": True,
                "content": [{"type": "text", "text": "MCP error -32602: invalid"}],
            }

    with pytest.raises(RuntimeError, match="MCP error"):
        MCPBoardClient._normalize_result(Result())
