from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import JSON, DateTime, String, Text, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from app.config import Settings
from app.schemas import PendingActionStatus


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class PendingActionModel(Base):
    __tablename__ = "pending_actions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    conversation_id: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    user_id: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    action_type: Mapped[str] = mapped_column(String(80), nullable=False)
    action_payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    result: Mapped[Any | None] = mapped_column(JSON)
    error: Mapped[str | None] = mapped_column(Text)


class PendingActionRepository:
    def __init__(self, settings: Settings):
        self.settings = settings
        connect_args = {}
        if settings.resolved_database_url.startswith("sqlite"):
            connect_args["check_same_thread"] = False
        self.engine = create_engine(
            settings.resolved_database_url,
            pool_pre_ping=True,
            connect_args=connect_args,
        )
        self.SessionLocal = sessionmaker(bind=self.engine, expire_on_commit=False)

    def init_db(self) -> None:
        Base.metadata.create_all(self.engine)

    def create_pending_action(
        self,
        *,
        conversation_id: str,
        user_id: str,
        action_type: str,
        action_payload: dict[str, Any],
    ) -> dict[str, Any]:
        record = PendingActionModel(
            id=str(uuid4()),
            conversation_id=conversation_id,
            user_id=user_id,
            action_type=action_type,
            action_payload=action_payload,
            status=PendingActionStatus.PENDING.value,
            created_at=utcnow(),
        )
        with self.SessionLocal() as session:
            session.add(record)
            session.commit()
            session.refresh(record)
            return self._to_dict(record)

    def get_pending_action(self, pending_action_id: str) -> dict[str, Any] | None:
        with self.SessionLocal() as session:
            record = session.get(PendingActionModel, pending_action_id)
            return self._to_dict(record) if record else None

    def mark_confirmed(self, pending_action_id: str) -> dict[str, Any] | None:
        return self._update(pending_action_id, status=PendingActionStatus.CONFIRMED.value, confirmed_at=utcnow())

    def mark_cancelled(self, pending_action_id: str) -> dict[str, Any] | None:
        return self._update(pending_action_id, status=PendingActionStatus.CANCELLED.value)

    def mark_executed(self, pending_action_id: str, result: Any) -> dict[str, Any] | None:
        return self._update(
            pending_action_id,
            status=PendingActionStatus.EXECUTED.value,
            executed_at=utcnow(),
            result=result,
            error=None,
        )

    def mark_failed(self, pending_action_id: str, error: str, result: Any | None = None) -> dict[str, Any] | None:
        return self._update(
            pending_action_id,
            status=PendingActionStatus.FAILED.value,
            executed_at=utcnow(),
            result=result,
            error=error,
        )

    def _update(self, pending_action_id: str, **values: Any) -> dict[str, Any] | None:
        with self.SessionLocal() as session:
            record = session.get(PendingActionModel, pending_action_id)
            if not record:
                return None
            for key, value in values.items():
                setattr(record, key, value)
            session.commit()
            session.refresh(record)
            return self._to_dict(record)

    @staticmethod
    def _to_dict(record: PendingActionModel) -> dict[str, Any]:
        return {
            "id": record.id,
            "conversation_id": record.conversation_id,
            "user_id": record.user_id,
            "action_type": record.action_type,
            "action_payload": record.action_payload,
            "status": record.status,
            "created_at": record.created_at.isoformat() if record.created_at else None,
            "confirmed_at": record.confirmed_at.isoformat() if record.confirmed_at else None,
            "executed_at": record.executed_at.isoformat() if record.executed_at else None,
            "result": record.result,
            "error": record.error,
        }

