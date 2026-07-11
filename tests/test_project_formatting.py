from app.agent.domains.projects.nodes import _format_blockers, _format_status


def test_format_blockers_renders_human_readable_summary():
    result = {
        "count": 1,
        "tasks": [
            {
                "id": "fe5a711a-3cd9-4f59-9115-906c2b915bdb",
                "title": "Encontro de dados com CRM",
                "status": "BLOCKED",
                "priority": "HIGH",
                "assignee": {"name": "Matheus"},
                "dueDate": "2026-06-25T12:00:00.000Z",
                "blockedReason": "Dependencia externa",
                "tags": [
                    {"name": "Comunicacao"},
                    {"name": "Dados"},
                ],
            }
        ],
    }

    message = _format_blockers(result)

    assert "🚨 *Bloqueios do projeto*" in message
    assert "Foi identificado *1 bloqueio*" in message
    assert "🔴 *Encontro de dados com CRM*" in message
    assert "📌 *Status:* Bloqueada" in message
    assert "⚡ *Prioridade:* Alta" in message
    assert "👤 *Responsável:* Matheus" in message
    assert "📅 *Prazo:* 25/06/2026" in message
    assert "⚠️ Vencido" in message
    assert "⛔ *Motivo:* Dependencia externa" in message
    assert "🏷️ *Tags:* Comunicacao, Dados" in message


def test_format_status_includes_formatted_blockers_instead_of_raw_dict():
    result = {
        "totalTasks": 7,
        "activeTasks": 6,
        "completedTasks": 1,
        "completionRate": 14.29,
        "blockers": {
            "count": 1,
            "tasks": [
                {
                    "title": "Encontro de dados com CRM",
                    "status": "BLOCKED",
                    "priority": "HIGH",
                    "assignee": {"name": "Matheus"},
                    "dueDate": "2026-06-25T12:00:00.000Z",
                    "blockedReason": "Dependencia externa",
                    "tags": [{"name": "Comunicacao"}, {"name": "Dados"}],
                }
            ],
        },
    }

    message = _format_status(result)

    assert "📊 *Status do projeto*" in message
    assert "📌 *Total de tarefas:* 7" in message
    assert "🚨 *Bloqueios:* 1" in message
    assert "🔴 *Encontro de dados com CRM*" in message
    assert "{'count':" not in message

