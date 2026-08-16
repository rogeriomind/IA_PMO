from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import JSON, DateTime, Integer, String, Text, UniqueConstraint, create_engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from app.config import Settings
from app.observability.langfuse import sanitize_payload
from app.schemas import PendingActionStatus


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class PendingActionModel(Base):
    __tablename__ = "pending_actions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    conversation_id: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    tenant_id: Mapped[str | None] = mapped_column(String(255), index=True)
    thread_id: Mapped[str | None] = mapped_column(String(255), index=True)
    user_id: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    request_id: Mapped[str | None] = mapped_column(String(255), index=True)
    correlation_id: Mapped[str | None] = mapped_column(String(255), index=True)
    action_type: Mapped[str] = mapped_column(String(80), nullable=False)
    tool_name: Mapped[str | None] = mapped_column(String(120), index=True)
    operations: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON)
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    preview: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    action_payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    result: Mapped[Any | None] = mapped_column(JSON)
    error: Mapped[str | None] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class IdempotencyRecordModel(Base):
    __tablename__ = "agent_idempotency_records"

    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    request_id: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    tool_name: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    arguments_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    result: Mapped[Any | None] = mapped_column(JSON)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ToolExecutionAuditModel(Base):
    __tablename__ = "agent_tool_execution_audit"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    request_id: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    thread_id: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    tenant_id: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    user_id: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    intent: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    tool_name: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    tool_type: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    latency_ms: Mapped[int] = mapped_column(nullable=False)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    transport: Mapped[str | None] = mapped_column(String(40))
    arguments: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    result: Mapped[Any | None] = mapped_column(JSON)
    error_code: Mapped[str | None] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AgentThreadModel(Base):
    __tablename__ = "agent_threads"
    __table_args__ = (UniqueConstraint("tenant_id", "thread_id", name="uq_agent_threads_tenant_thread"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    thread_id: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    tenant_id: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    channel: Mapped[str] = mapped_column(String(80), nullable=False)
    user_id: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    user_name: Mapped[str | None] = mapped_column(String(255))
    current_flow: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    current_step: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    state_summary: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    last_event_id: Mapped[str | None] = mapped_column(String(255), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)


class AgentUserIdentityLinkModel(Base):
    __tablename__ = "agent_user_identity_links"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "channel",
            "provider_user_id",
            name="uq_agent_user_identity_link_provider",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    channel: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    provider_user_id: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    board_user_id: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    board_user_name: Mapped[str | None] = mapped_column(String(255))
    board_user_email: Mapped[str | None] = mapped_column(String(255))
    source: Mapped[str] = mapped_column(String(80), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AgentTaskSelectionMapModel(Base):
    __tablename__ = "agent_task_selection_maps"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "thread_id",
            "user_id",
            "context",
            "selection_number",
            name="uq_agent_task_selection_number",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    thread_id: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    tenant_id: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    user_id: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    context: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    selection_number: Mapped[int] = mapped_column(Integer, nullable=False)
    task_id: Mapped[str] = mapped_column(String(255), nullable=False)
    task_title: Mapped[str | None] = mapped_column(String(500))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AgentDraftModel(Base):
    __tablename__ = "agent_drafts"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    thread_id: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    tenant_id: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    user_id: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    draft_type: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False)


class AgentEventModel(Base):
    __tablename__ = "agent_events"
    __table_args__ = (UniqueConstraint("event_id", name="uq_agent_events_event_id"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    event_id: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    request_id: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    thread_id: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    tenant_id: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    user_id: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    message_type: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    flow: Mapped[str | None] = mapped_column(String(80), index=True)
    step: Mapped[str | None] = mapped_column(String(120), index=True)
    input_payload_sanitized: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    output_payload_sanitized: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AgentGraphCheckpointModel(Base):
    __tablename__ = "agent_graph_checkpoints"
    __table_args__ = (UniqueConstraint("tenant_id", "thread_id", name="uq_agent_graph_checkpoint"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    thread_id: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    checkpoint: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


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
        now = utcnow()
        record = PendingActionModel(
            id=str(uuid4()),
            conversation_id=conversation_id,
            tenant_id=action_payload.get("tenant_id"),
            thread_id=conversation_id,
            user_id=user_id,
            request_id=action_payload.get("request_id"),
            correlation_id=action_payload.get("correlation_id"),
            action_type=action_type,
            tool_name=action_type,
            operations=action_payload.get("operations"),
            payload=action_payload.get("tool_input") or action_payload,
            preview=action_payload.get("preview"),
            action_payload=action_payload,
            status=PendingActionStatus.PENDING.value,
            created_at=now,
            updated_at=now,
        )
        with self.SessionLocal() as session:
            session.add(record)
            session.commit()
            session.refresh(record)
            return self._to_dict(record)

    def create_v2_pending_action(
        self,
        *,
        tenant_id: str,
        thread_id: str,
        user_id: str,
        request_id: str,
        correlation_id: str,
        action_type: str,
        tool_name: str,
        operations: list[dict[str, Any]],
        payload: dict[str, Any],
        preview: dict[str, Any],
        expires_at: datetime,
    ) -> dict[str, Any]:
        now = utcnow()
        record = PendingActionModel(
            id=str(uuid4()),
            conversation_id=thread_id,
            tenant_id=tenant_id,
            thread_id=thread_id,
            user_id=user_id,
            request_id=request_id,
            correlation_id=correlation_id,
            action_type=action_type,
            tool_name=tool_name,
            operations=operations,
            payload=payload,
            preview=preview,
            action_payload={
                "tool_input": payload,
                "operations": operations,
                "intent": action_type,
                "tenant_id": tenant_id,
                "thread_id": thread_id,
                "request_id": request_id,
                "correlation_id": correlation_id,
                "preview": preview,
            },
            status="pending",
            created_at=now,
            updated_at=now,
            expires_at=expires_at,
            version=1,
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

    def transition_pending_action(
        self,
        pending_action_id: str,
        *,
        from_status: str,
        to_status: str,
        error: str | None = None,
    ) -> dict[str, Any] | None:
        with self.SessionLocal() as session:
            record = session.get(PendingActionModel, pending_action_id)
            if not record or record.status != from_status:
                return None
            record.status = to_status
            record.updated_at = utcnow()
            record.version += 1
            if to_status in {"executing", "completed", "partial", "failed", "unknown"}:
                record.executed_at = record.executed_at or utcnow()
            if error:
                record.error = error
            session.commit()
            session.refresh(record)
            return self._to_dict(record)

    def mark_confirmed(self, pending_action_id: str) -> dict[str, Any] | None:
        return self._update(
            pending_action_id,
            status=PendingActionStatus.CONFIRMED.value,
            confirmed_at=utcnow(),
            updated_at=utcnow(),
        )

    def mark_cancelled(self, pending_action_id: str) -> dict[str, Any] | None:
        return self._update(pending_action_id, status=PendingActionStatus.CANCELLED.value, updated_at=utcnow())

    def mark_executed(self, pending_action_id: str, result: Any) -> dict[str, Any] | None:
        return self._update(
            pending_action_id,
            status=PendingActionStatus.EXECUTED.value,
            executed_at=utcnow(),
            result=result,
            error=None,
            updated_at=utcnow(),
        )

    def mark_failed(self, pending_action_id: str, error: str, result: Any | None = None) -> dict[str, Any] | None:
        return self._update(
            pending_action_id,
            status=PendingActionStatus.FAILED.value,
            executed_at=utcnow(),
            result=result,
            error=error,
            updated_at=utcnow(),
        )

    def mark_v2_pending_action_result(
        self,
        pending_action_id: str,
        *,
        status: str,
        result: Any | None = None,
        error: str | None = None,
    ) -> dict[str, Any] | None:
        return self._update(
            pending_action_id,
            status=status,
            result=result,
            error=error,
            executed_at=utcnow() if status in {"completed", "partial", "failed", "unknown"} else None,
            updated_at=utcnow(),
        )

    def get_agent_thread(self, *, tenant_id: str, thread_id: str) -> dict[str, Any] | None:
        with self.SessionLocal() as session:
            record = session.scalar(
                select(AgentThreadModel).where(
                    AgentThreadModel.tenant_id == tenant_id,
                    AgentThreadModel.thread_id == thread_id,
                )
            )
            return self._thread_to_dict(record) if record else None

    def upsert_agent_thread(
        self,
        *,
        tenant_id: str,
        thread_id: str,
        channel: str,
        user_id: str,
        user_name: str | None,
        current_flow: str,
        current_step: str,
        state_summary: dict[str, Any],
        last_event_id: str | None,
        expires_at: datetime | None,
    ) -> dict[str, Any]:
        now = utcnow()
        with self.SessionLocal() as session:
            record = session.scalar(
                select(AgentThreadModel).where(
                    AgentThreadModel.tenant_id == tenant_id,
                    AgentThreadModel.thread_id == thread_id,
                )
            )
            if not record:
                record = AgentThreadModel(
                    id=str(uuid4()),
                    tenant_id=tenant_id,
                    thread_id=thread_id,
                    channel=channel,
                    user_id=user_id,
                    user_name=user_name,
                    current_flow=current_flow,
                    current_step=current_step,
                    state_summary=state_summary,
                    last_event_id=last_event_id,
                    created_at=now,
                    updated_at=now,
                    expires_at=expires_at,
                )
                session.add(record)
            else:
                record.channel = channel
                record.user_id = user_id
                record.user_name = user_name
                record.current_flow = current_flow
                record.current_step = current_step
                record.state_summary = state_summary
                record.last_event_id = last_event_id
                record.updated_at = now
                record.expires_at = expires_at
            session.commit()
            session.refresh(record)
            return self._thread_to_dict(record)

    def reset_agent_thread(self, *, tenant_id: str, thread_id: str) -> None:
        with self.SessionLocal() as session:
            record = session.scalar(
                select(AgentThreadModel).where(
                    AgentThreadModel.tenant_id == tenant_id,
                    AgentThreadModel.thread_id == thread_id,
                )
            )
            if record:
                session.delete(record)
            session.query(AgentDraftModel).filter_by(tenant_id=tenant_id, thread_id=thread_id).delete()
            session.query(AgentTaskSelectionMapModel).filter_by(tenant_id=tenant_id, thread_id=thread_id).delete()
            session.commit()

    def get_user_identity_link(
        self,
        *,
        tenant_id: str,
        channel: str,
        provider_user_id: str,
    ) -> dict[str, Any] | None:
        with self.SessionLocal() as session:
            record = session.scalar(
                select(AgentUserIdentityLinkModel).where(
                    AgentUserIdentityLinkModel.tenant_id == tenant_id,
                    AgentUserIdentityLinkModel.channel == channel,
                    AgentUserIdentityLinkModel.provider_user_id == provider_user_id,
                )
            )
            return self._identity_link_to_dict(record) if record else None

    def upsert_user_identity_link(
        self,
        *,
        tenant_id: str,
        channel: str,
        provider_user_id: str,
        board_user_id: str,
        board_user_name: str | None,
        board_user_email: str | None,
        source: str,
    ) -> dict[str, Any]:
        now = utcnow()
        with self.SessionLocal() as session:
            record = session.scalar(
                select(AgentUserIdentityLinkModel).where(
                    AgentUserIdentityLinkModel.tenant_id == tenant_id,
                    AgentUserIdentityLinkModel.channel == channel,
                    AgentUserIdentityLinkModel.provider_user_id == provider_user_id,
                )
            )
            if not record:
                record = AgentUserIdentityLinkModel(
                    id=str(uuid4()),
                    tenant_id=tenant_id,
                    channel=channel,
                    provider_user_id=provider_user_id,
                    board_user_id=board_user_id,
                    board_user_name=board_user_name,
                    board_user_email=board_user_email,
                    source=source,
                    created_at=now,
                    updated_at=now,
                )
                session.add(record)
            else:
                record.board_user_id = board_user_id
                record.board_user_name = board_user_name
                record.board_user_email = board_user_email
                record.source = source
                record.updated_at = now
            session.commit()
            session.refresh(record)
            return self._identity_link_to_dict(record)

    def replace_task_selection_map(
        self,
        *,
        tenant_id: str,
        thread_id: str,
        user_id: str,
        context: str,
        items: list[dict[str, Any]],
        expires_at: datetime,
    ) -> list[dict[str, Any]]:
        with self.SessionLocal() as session:
            session.query(AgentTaskSelectionMapModel).filter_by(
                tenant_id=tenant_id,
                thread_id=thread_id,
                user_id=user_id,
                context=context,
            ).delete()
            records = []
            for item in items:
                record = AgentTaskSelectionMapModel(
                    id=str(uuid4()),
                    tenant_id=tenant_id,
                    thread_id=thread_id,
                    user_id=user_id,
                    context=context,
                    selection_number=int(item["selection_number"]),
                    task_id=str(item["task_id"]),
                    task_title=item.get("task_title"),
                    expires_at=expires_at,
                    created_at=utcnow(),
                )
                records.append(record)
                session.add(record)
            session.commit()
            return [self._selection_to_dict(record) for record in records]

    def resolve_task_selection(
        self,
        *,
        tenant_id: str,
        thread_id: str,
        user_id: str,
        context: str,
        selection_number: int,
    ) -> dict[str, Any] | None:
        now = utcnow()
        with self.SessionLocal() as session:
            record = session.scalar(
                select(AgentTaskSelectionMapModel).where(
                    AgentTaskSelectionMapModel.tenant_id == tenant_id,
                    AgentTaskSelectionMapModel.thread_id == thread_id,
                    AgentTaskSelectionMapModel.user_id == user_id,
                    AgentTaskSelectionMapModel.context == context,
                    AgentTaskSelectionMapModel.selection_number == selection_number,
                )
            )
            if not record or _is_expired_datetime(record.expires_at, now):
                return None
            return self._selection_to_dict(record)

    def resolve_task_selection_with_status(
        self,
        *,
        tenant_id: str,
        thread_id: str,
        user_id: str,
        context: str,
        selection_number: int,
    ) -> dict[str, Any]:
        now = utcnow()
        with self.SessionLocal() as session:
            record = session.scalar(
                select(AgentTaskSelectionMapModel).where(
                    AgentTaskSelectionMapModel.tenant_id == tenant_id,
                    AgentTaskSelectionMapModel.thread_id == thread_id,
                    AgentTaskSelectionMapModel.user_id == user_id,
                    AgentTaskSelectionMapModel.context == context,
                    AgentTaskSelectionMapModel.selection_number == selection_number,
                )
            )
            if record:
                if _is_expired_datetime(record.expires_at, now):
                    return {"status": "expired", "selection": None}
                return {"status": "ok", "selection": self._selection_to_dict(record)}

            latest = session.scalar(
                select(AgentTaskSelectionMapModel)
                .where(
                    AgentTaskSelectionMapModel.tenant_id == tenant_id,
                    AgentTaskSelectionMapModel.thread_id == thread_id,
                    AgentTaskSelectionMapModel.user_id == user_id,
                    AgentTaskSelectionMapModel.context == context,
                )
                .order_by(AgentTaskSelectionMapModel.expires_at.desc())
            )
            if latest and _is_expired_datetime(latest.expires_at, now):
                return {"status": "expired", "selection": None}
            return {"status": "not_found", "selection": None}

    def upsert_draft(
        self,
        *,
        tenant_id: str,
        thread_id: str,
        user_id: str,
        draft_type: str,
        payload: dict[str, Any],
        status: str,
        expires_at: datetime,
    ) -> dict[str, Any]:
        now = utcnow()
        with self.SessionLocal() as session:
            record = session.scalar(
                select(AgentDraftModel).where(
                    AgentDraftModel.tenant_id == tenant_id,
                    AgentDraftModel.thread_id == thread_id,
                    AgentDraftModel.user_id == user_id,
                    AgentDraftModel.draft_type == draft_type,
                    AgentDraftModel.status != "cleared",
                )
            )
            if not record:
                record = AgentDraftModel(
                    id=str(uuid4()),
                    tenant_id=tenant_id,
                    thread_id=thread_id,
                    user_id=user_id,
                    draft_type=draft_type,
                    payload=payload,
                    status=status,
                    created_at=now,
                    updated_at=now,
                    expires_at=expires_at,
                )
                session.add(record)
            else:
                record.payload = payload
                record.status = status
                record.updated_at = now
                record.expires_at = expires_at
            session.commit()
            session.refresh(record)
            return self._draft_to_dict(record)

    def get_active_draft(
        self,
        *,
        tenant_id: str,
        thread_id: str,
        user_id: str,
        draft_type: str,
    ) -> dict[str, Any] | None:
        now = utcnow()
        with self.SessionLocal() as session:
            record = session.scalar(
                select(AgentDraftModel).where(
                    AgentDraftModel.tenant_id == tenant_id,
                    AgentDraftModel.thread_id == thread_id,
                    AgentDraftModel.user_id == user_id,
                    AgentDraftModel.draft_type == draft_type,
                    AgentDraftModel.status != "cleared",
                )
            )
            if not record or _is_expired_datetime(record.expires_at, now):
                return None
            return self._draft_to_dict(record)

    def clear_draft(
        self,
        *,
        tenant_id: str,
        thread_id: str,
        user_id: str,
        draft_type: str,
    ) -> None:
        with self.SessionLocal() as session:
            session.query(AgentDraftModel).filter_by(
                tenant_id=tenant_id,
                thread_id=thread_id,
                user_id=user_id,
                draft_type=draft_type,
            ).update({"status": "cleared", "updated_at": utcnow()})
            session.commit()

    def get_agent_event_by_event_id(self, event_id: str) -> dict[str, Any] | None:
        with self.SessionLocal() as session:
            record = session.scalar(select(AgentEventModel).where(AgentEventModel.event_id == event_id))
            return self._event_to_dict(record) if record else None

    def append_agent_event(
        self,
        *,
        event_id: str,
        request_id: str,
        correlation_id: str,
        thread_id: str,
        tenant_id: str,
        user_id: str,
        message_type: str,
        flow: str | None,
        step: str | None,
        input_payload_sanitized: dict[str, Any],
        output_payload_sanitized: dict[str, Any],
        status: str,
        latency_ms: int,
    ) -> dict[str, Any]:
        record = AgentEventModel(
            id=str(uuid4()),
            event_id=event_id,
            request_id=request_id,
            correlation_id=correlation_id,
            thread_id=thread_id,
            tenant_id=tenant_id,
            user_id=user_id,
            message_type=message_type,
            flow=flow,
            step=step,
            input_payload_sanitized=input_payload_sanitized,
            output_payload_sanitized=output_payload_sanitized,
            status=status,
            latency_ms=latency_ms,
            created_at=utcnow(),
        )
        with self.SessionLocal() as session:
            session.add(record)
            try:
                session.commit()
            except IntegrityError:
                session.rollback()
                existing = session.scalar(select(AgentEventModel).where(AgentEventModel.event_id == event_id))
                return self._event_to_dict(existing) if existing else {}
            session.refresh(record)
            return self._event_to_dict(record)

    def upsert_graph_checkpoint(
        self,
        *,
        tenant_id: str,
        thread_id: str,
        checkpoint: dict[str, Any],
        metadata_json: dict[str, Any],
    ) -> dict[str, Any]:
        now = utcnow()
        with self.SessionLocal() as session:
            record = session.scalar(
                select(AgentGraphCheckpointModel).where(
                    AgentGraphCheckpointModel.tenant_id == tenant_id,
                    AgentGraphCheckpointModel.thread_id == thread_id,
                )
            )
            if not record:
                record = AgentGraphCheckpointModel(
                    id=str(uuid4()),
                    tenant_id=tenant_id,
                    thread_id=thread_id,
                    checkpoint=checkpoint,
                    metadata_json=metadata_json,
                    created_at=now,
                    updated_at=now,
                )
                session.add(record)
            else:
                record.checkpoint = checkpoint
                record.metadata_json = metadata_json
                record.updated_at = now
            session.commit()
            session.refresh(record)
            return {
                "id": record.id,
                "tenant_id": record.tenant_id,
                "thread_id": record.thread_id,
                "checkpoint": record.checkpoint,
                "metadata": record.metadata_json,
            }

    def get_idempotency_record(self, key: str) -> dict[str, Any] | None:
        with self.SessionLocal() as session:
            record = session.get(IdempotencyRecordModel, key)
            return self._idempotency_to_dict(record) if record else None

    def create_idempotency_record(
        self,
        *,
        key: str,
        tenant_id: str,
        request_id: str,
        tool_name: str,
        arguments_hash: str,
    ) -> dict[str, Any]:
        now = utcnow()
        record = IdempotencyRecordModel(
            key=key,
            tenant_id=tenant_id,
            request_id=request_id,
            tool_name=tool_name,
            arguments_hash=arguments_hash,
            status="IN_PROGRESS",
            result=None,
            error=None,
            created_at=now,
            updated_at=now,
        )
        with self.SessionLocal() as session:
            session.add(record)
            session.commit()
            session.refresh(record)
            return self._idempotency_to_dict(record)

    def update_idempotency_record(
        self,
        key: str,
        *,
        status: str,
        result: Any | None = None,
        error: str | None = None,
    ) -> dict[str, Any] | None:
        with self.SessionLocal() as session:
            record = session.get(IdempotencyRecordModel, key)
            if not record:
                return None
            record.status = status
            record.result = result
            record.error = error
            record.updated_at = utcnow()
            session.commit()
            session.refresh(record)
            return self._idempotency_to_dict(record)

    def append_tool_execution_audit(
        self,
        *,
        request_id: str,
        correlation_id: str,
        thread_id: str,
        tenant_id: str,
        user_id: str,
        intent: str,
        tool_name: str,
        tool_type: str,
        status: str,
        latency_ms: int,
        arguments: dict[str, Any],
        result: Any | None = None,
        error_code: str | None = None,
        retry_count: int = 0,
        transport: str | None = None,
    ) -> dict[str, Any]:
        record = ToolExecutionAuditModel(
            id=str(uuid4()),
            request_id=request_id,
            correlation_id=correlation_id,
            thread_id=thread_id,
            tenant_id=tenant_id,
            user_id=user_id,
            intent=intent,
            tool_name=tool_name,
            tool_type=tool_type,
            status=status,
            latency_ms=latency_ms,
            retry_count=retry_count,
            transport=transport,
            arguments=sanitize_payload(arguments),
            result=sanitize_payload(result),
            error_code=error_code,
            created_at=utcnow(),
        )
        with self.SessionLocal() as session:
            session.add(record)
            session.commit()
            session.refresh(record)
            return {
                "id": record.id,
                "request_id": record.request_id,
                "tool_name": record.tool_name,
                "status": record.status,
                "created_at": record.created_at.isoformat(),
            }

    def _update(self, pending_action_id: str, **values: Any) -> dict[str, Any] | None:
        with self.SessionLocal() as session:
            record = session.get(PendingActionModel, pending_action_id)
            if not record:
                return None
            for key, value in values.items():
                setattr(record, key, value)
            record.version = (record.version or 1) + 1
            session.commit()
            session.refresh(record)
            return self._to_dict(record)

    @staticmethod
    def _to_dict(record: PendingActionModel) -> dict[str, Any]:
        return {
            "id": record.id,
            "conversation_id": record.conversation_id,
            "tenant_id": record.tenant_id,
            "thread_id": record.thread_id,
            "user_id": record.user_id,
            "request_id": record.request_id,
            "correlation_id": record.correlation_id,
            "action_type": record.action_type,
            "tool_name": record.tool_name,
            "operations": record.operations,
            "payload": record.payload,
            "preview": record.preview,
            "action_payload": record.action_payload,
            "status": record.status,
            "created_at": record.created_at.isoformat() if record.created_at else None,
            "updated_at": record.updated_at.isoformat() if record.updated_at else None,
            "expires_at": record.expires_at.isoformat() if record.expires_at else None,
            "confirmed_at": record.confirmed_at.isoformat() if record.confirmed_at else None,
            "executed_at": record.executed_at.isoformat() if record.executed_at else None,
            "result": record.result,
            "error": record.error,
            "version": record.version,
        }

    @staticmethod
    def _idempotency_to_dict(record: IdempotencyRecordModel) -> dict[str, Any]:
        return {
            "key": record.key,
            "tenant_id": record.tenant_id,
            "request_id": record.request_id,
            "tool_name": record.tool_name,
            "arguments_hash": record.arguments_hash,
            "status": record.status,
            "result": record.result,
            "error": record.error,
            "created_at": record.created_at.isoformat() if record.created_at else None,
            "updated_at": record.updated_at.isoformat() if record.updated_at else None,
        }

    @staticmethod
    def _thread_to_dict(record: AgentThreadModel) -> dict[str, Any]:
        return {
            "id": record.id,
            "thread_id": record.thread_id,
            "tenant_id": record.tenant_id,
            "channel": record.channel,
            "user_id": record.user_id,
            "user_name": record.user_name,
            "current_flow": record.current_flow,
            "current_step": record.current_step,
            "state_summary": record.state_summary,
            "last_event_id": record.last_event_id,
            "created_at": record.created_at.isoformat() if record.created_at else None,
            "updated_at": record.updated_at.isoformat() if record.updated_at else None,
            "expires_at": record.expires_at.isoformat() if record.expires_at else None,
        }

    @staticmethod
    def _identity_link_to_dict(record: AgentUserIdentityLinkModel) -> dict[str, Any]:
        return {
            "id": record.id,
            "tenant_id": record.tenant_id,
            "channel": record.channel,
            "provider_user_id": record.provider_user_id,
            "board_user_id": record.board_user_id,
            "board_user_name": record.board_user_name,
            "board_user_email": record.board_user_email,
            "source": record.source,
            "created_at": record.created_at.isoformat() if record.created_at else None,
            "updated_at": record.updated_at.isoformat() if record.updated_at else None,
        }

    @staticmethod
    def _selection_to_dict(record: AgentTaskSelectionMapModel) -> dict[str, Any]:
        return {
            "id": record.id,
            "thread_id": record.thread_id,
            "tenant_id": record.tenant_id,
            "user_id": record.user_id,
            "context": record.context,
            "selection_number": record.selection_number,
            "task_id": record.task_id,
            "task_title": record.task_title,
            "expires_at": record.expires_at.isoformat() if record.expires_at else None,
            "created_at": record.created_at.isoformat() if record.created_at else None,
        }

    @staticmethod
    def _draft_to_dict(record: AgentDraftModel) -> dict[str, Any]:
        return {
            "id": record.id,
            "thread_id": record.thread_id,
            "tenant_id": record.tenant_id,
            "user_id": record.user_id,
            "draft_type": record.draft_type,
            "payload": record.payload,
            "status": record.status,
            "created_at": record.created_at.isoformat() if record.created_at else None,
            "updated_at": record.updated_at.isoformat() if record.updated_at else None,
            "expires_at": record.expires_at.isoformat() if record.expires_at else None,
        }

    @staticmethod
    def _event_to_dict(record: AgentEventModel | None) -> dict[str, Any]:
        if record is None:
            return {}
        return {
            "id": record.id,
            "event_id": record.event_id,
            "request_id": record.request_id,
            "correlation_id": record.correlation_id,
            "thread_id": record.thread_id,
            "tenant_id": record.tenant_id,
            "user_id": record.user_id,
            "message_type": record.message_type,
            "flow": record.flow,
            "step": record.step,
            "input_payload_sanitized": record.input_payload_sanitized,
            "output_payload_sanitized": record.output_payload_sanitized,
            "status": record.status,
            "latency_ms": record.latency_ms,
            "created_at": record.created_at.isoformat() if record.created_at else None,
        }


def _is_expired_datetime(expires_at: datetime, now: datetime) -> bool:
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=now.tzinfo)
    return expires_at < now
