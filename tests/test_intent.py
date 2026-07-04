import pytest
from datetime import datetime
from zoneinfo import ZoneInfo

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


@pytest.mark.asyncio
async def test_change_task_date_to_today_intent_and_entities(service):
    message = "altere a data do Configurar lembrete automatico para hoje"

    result = await service.classify(message)
    entities = await service.extract_entities(message, result.intent)

    assert result.intent == Intent.TASK_UPDATE
    assert entities.task_query == "Configurar lembrete automatico"
    assert entities.fields["due_date"] == datetime.now(ZoneInfo("America/Sao_Paulo")).date().isoformat()
