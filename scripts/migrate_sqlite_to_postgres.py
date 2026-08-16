from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any

from sqlalchemy import Engine, Table, create_engine, func, inspect, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError

from app.storage.repository import Base
from app.tenancy.control_plane import TenantBase


class MigrationError(RuntimeError):
    pass


def managed_tables() -> list[Table]:
    return list(TenantBase.metadata.sorted_tables) + list(Base.metadata.sorted_tables)


def migrate(
    *,
    sqlite_url: str,
    target_url: str,
    init_schema: bool = False,
    idempotent: bool = False,
    require_empty: bool = True,
    expected_threads: int | None = None,
    expected_pending_action_id: str | None = None,
) -> dict[str, Any]:
    source_engine = create_engine(sqlite_url, connect_args={"check_same_thread": False})
    target_engine = create_engine(_normalize_database_url(target_url), pool_pre_ping=True)
    try:
        if init_schema:
            TenantBase.metadata.create_all(target_engine)
            Base.metadata.create_all(target_engine)

        tables = _existing_managed_tables(source_engine, target_engine)
        source_counts = count_rows(source_engine, tables)
        target_before = count_rows(target_engine, tables)
        if require_empty and any(target_before.values()) and not idempotent:
            raise MigrationError("Target database is not empty. Use --idempotent only after validating it is the same import.")

        copied: dict[str, int] = {}
        skipped: dict[str, int] = {}
        with source_engine.connect() as source, target_engine.begin() as target:
            for table in tables:
                rows = [dict(row) for row in source.execute(select(table)).mappings().all()]
                copied_count = 0
                skipped_count = 0
                for row in rows:
                    if idempotent and _target_row_exists(target, table, row):
                        skipped_count += 1
                        continue
                    try:
                        target.execute(
                            _insert_statement(
                                table,
                                row,
                                idempotent=idempotent,
                                dialect_name=target.dialect.name,
                            )
                        )
                        copied_count += 1
                    except IntegrityError as exc:
                        raise MigrationError(f"Failed to insert row into {table.name}: {exc}") from exc
                copied[table.name] = copied_count
                skipped[table.name] = skipped_count

        target_after = count_rows(target_engine, tables)
        mismatches = {
            table: {"source": source_counts[table], "target": target_after[table]}
            for table in source_counts
            if source_counts[table] != target_after[table]
        }
        if mismatches:
            raise MigrationError(f"Count mismatch after migration: {json.dumps(mismatches, sort_keys=True)}")

        if expected_threads is not None and target_after.get("agent_threads", 0) < expected_threads:
            raise MigrationError(
                f"Expected at least {expected_threads} agent_threads, found {target_after.get('agent_threads', 0)}"
            )
        if expected_pending_action_id and not pending_action_exists(target_engine, expected_pending_action_id):
            raise MigrationError(f"Pending action not found after migration: {expected_pending_action_id}")

        return {
            "source_counts": source_counts,
            "target_before": target_before,
            "target_after": target_after,
            "copied": copied,
            "skipped": skipped,
        }
    finally:
        source_engine.dispose()
        target_engine.dispose()


def count_rows(engine: Engine, tables: list[Table]) -> dict[str, int]:
    counts: dict[str, int] = {}
    existing = set(inspect(engine).get_table_names())
    with engine.connect() as connection:
        for table in tables:
            if table.name not in existing:
                counts[table.name] = 0
                continue
            counts[table.name] = int(connection.scalar(select(func.count()).select_from(table)) or 0)
    return counts


def pending_action_exists(engine: Engine, pending_action_id: str) -> bool:
    table = Base.metadata.tables["pending_actions"]
    with engine.connect() as connection:
        return connection.scalar(select(table.c.id).where(table.c.id == pending_action_id)) is not None


def sqlite_file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _existing_managed_tables(source_engine: Engine, target_engine: Engine) -> list[Table]:
    source_tables = set(inspect(source_engine).get_table_names())
    target_tables = set(inspect(target_engine).get_table_names())
    tables = [table for table in managed_tables() if table.name in source_tables]
    missing_target = [table.name for table in tables if table.name not in target_tables]
    if missing_target:
        raise MigrationError(f"Target database is missing tables: {', '.join(missing_target)}")
    return tables


def _target_row_exists(connection: Any, table: Table, row: dict[str, Any]) -> bool:
    pk_columns = list(table.primary_key.columns)
    if not pk_columns:
        return False
    conditions = []
    for column in pk_columns:
        if column.name not in row:
            return False
        conditions.append(column == row[column.name])
    return connection.scalar(select(pk_columns[0]).select_from(table).where(*conditions)) is not None


def _insert_statement(table: Table, row: dict[str, Any], *, idempotent: bool, dialect_name: str):
    if idempotent and dialect_name == "postgresql":
        return pg_insert(table).values(row).on_conflict_do_nothing(index_elements=[column.name for column in table.primary_key])
    return table.insert().values(row)


def _normalize_database_url(url: str) -> str:
    if url.startswith("postgres://"):
        return "postgresql+psycopg://" + url.removeprefix("postgres://")
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url.removeprefix("postgresql://")
    return url


def _sqlite_url(path_or_url: str) -> str:
    if path_or_url.startswith("sqlite:"):
        return path_or_url
    return f"sqlite:///{Path(path_or_url).resolve()}"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Migrate PMO Agent state from SQLite to Postgres.")
    parser.add_argument("--sqlite", required=True, help="SQLite file path or SQLAlchemy sqlite URL.")
    parser.add_argument("--target-url", default=os.getenv("DATABASE_URL", ""), help="Postgres SQLAlchemy URL.")
    parser.add_argument("--init-schema", action="store_true", help="Create target tables before importing.")
    parser.add_argument("--idempotent", action="store_true", help="Skip rows whose primary key already exists.")
    parser.add_argument("--allow-non-empty", action="store_true", help="Allow a non-empty target without idempotent mode.")
    parser.add_argument("--expect-min-threads", type=int, default=None)
    parser.add_argument("--expect-pending-action-id", default=None)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not args.target_url:
        raise SystemExit("Set DATABASE_URL or pass --target-url.")

    sqlite_path = args.sqlite
    if not sqlite_path.startswith("sqlite:"):
        print(json.dumps({"sqlite_sha256": sqlite_file_sha256(Path(sqlite_path))}, sort_keys=True))

    result = migrate(
        sqlite_url=_sqlite_url(sqlite_path),
        target_url=args.target_url,
        init_schema=args.init_schema,
        idempotent=args.idempotent,
        require_empty=not args.allow_non_empty,
        expected_threads=args.expect_min_threads,
        expected_pending_action_id=args.expect_pending_action_id,
    )
    print(json.dumps(result, indent=2, sort_keys=True, default=str))


if __name__ == "__main__":
    main()
