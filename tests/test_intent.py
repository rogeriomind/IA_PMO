import pytest

from app.config import Settings
from app.schemas import Intent
from app.services.intent_service import IntentService


@pytest.fixture()
def service():
    settings = Settings(deepseek_model="", langfuse_enabled=False)
    return IntentService(settings)


@pytest.mark.asyncio
async def test_status_board_intent(service):
    result = await service.classify("qual o status do projeto onboarding?")
    assert result.intent == Intent.STATUS_BOARD


@pytest.mark.asyncio
async def test_task_create_intent(service):
    result = await service.classify("cria uma tarefa para revisar o deploy")
    assert result.intent == Intent.TASK_CREATE


@pytest.mark.asyncio
async def test_task_move_intent(service):
    result = await service.classify("muda a tarefa X para em andamento")
    assert result.intent == Intent.TASK_MOVE
