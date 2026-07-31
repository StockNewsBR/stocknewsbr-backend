#!/usr/bin/env python
"""
Mission 31D Tier 2 operational migration.

Adds the nullable subscription_audit_logs.provider_event_id column and the
canonical partial unique index for persistent Stripe event deduplication.

Default mode is read-only preflight. DDL requires --apply and, when index
creation is needed, an explicit --index-strategy.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import unquote, urlsplit

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError


TABLE_NAME = "subscription_audit_logs"
SCHEMA_NAME = "public"
COLUMN_NAME = "provider_event_id"
INDEX_NAME = "uq_subscription_audit_provider_event"
REQUIRED_BASE_COLUMNS = ("provider",)
DDL_LOCK_TIMEOUT = "5s"
DDL_STATEMENT_TIMEOUT = "60s"
CONCURRENT_INDEX_STATEMENT_TIMEOUT = "15min"
CONCURRENT_INDEX_CONFLICTING_LOCKS = frozenset(
    {
        "ShareUpdateExclusiveLock",
        "ShareLock",
        "ShareRowExclusiveLock",
        "ExclusiveLock",
        "AccessExclusiveLock",
    }
)
SUPPORTED_COLUMN_TYPE_MARKERS = ("char", "text", "string")
EXPECTED_INDEX_PREDICATE = f"{COLUMN_NAME} is not null"

EXIT_OK = 0
EXIT_PREFLIGHT_FAILED = 2
EXIT_APPLY_FAILED = 3
EXIT_UNEXPECTED = 4

logger = logging.getLogger("mission31d.tier2_migration")


class MigrationBlocked(RuntimeError):
    """Raised when preflight finds an unsafe or inconsistent state."""

    def __init__(self, message: str, exit_code: int = EXIT_PREFLIGHT_FAILED):
        super().__init__(message)
        self.exit_code = exit_code


@dataclass
class PreflightState:
    dialect: str
    table_exists: bool
    provider_column_nullable: bool | None = False
    null_provider_rows: int = 0
    column_exists: bool = False
    column_nullable: bool | None = None
    column_type: str | None = None
    canonical_index_exists: bool = False
    canonical_index_valid: bool | None = None
    canonical_index_columns: list[str] = field(default_factory=list)
    canonical_index_definition: str | None = None
    redundant_unique_constraints: list[str] = field(default_factory=list)
    invalid_indexes: list[str] = field(default_factory=list)
    duplicate_provider_event_pairs: list[dict[str, Any]] = field(default_factory=list)
    duplicate_provider_event_pair_count: int = 0
    historical_stripe_rows_without_provider_event_id: int = 0
    total_rows: int | None = None
    table_size: str | None = None
    indexes_size: str | None = None
    active_locks: list[dict[str, Any]] = field(default_factory=list)
    long_transactions: list[dict[str, Any]] = field(default_factory=list)
    can_alter_table: bool | None = None
    table_owner: str | None = None
    unsafe_reasons: list[str] = field(default_factory=list)

    @property
    def needs_column(self) -> bool:
        return self.table_exists and not self.column_exists

    @property
    def needs_index(self) -> bool:
        return self.table_exists and self.column_exists and not self.canonical_index_exists

    @property
    def applied(self) -> bool:
        return (
            self.table_exists
            and self.column_exists
            and self.column_nullable is True
            and _provider_event_id_column_type_valid(self.column_type)
            and self.canonical_index_exists
            and self.canonical_index_valid is True
            and self.provider_column_nullable is False
            and self.null_provider_rows == 0
            and not self.redundant_unique_constraints
            and not self.invalid_indexes
            and self.duplicate_provider_event_pair_count == 0
            and not self.duplicate_provider_event_pairs
            and self.historical_stripe_rows_without_provider_event_id == 0
        )


def configure_logging() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Mission 31D Tier 2 provider_event_id migration preflight/apply"
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Execute DDL after a successful preflight. Omitted means read-only preflight.",
    )
    parser.add_argument(
        "--index-strategy",
        choices=("normal", "concurrent"),
        default=None,
        help=(
            "Required with --apply when index creation is needed. Use normal for a "
            "controlled maintenance window, concurrent for hot PostgreSQL tables."
        ),
    )
    return parser.parse_args(argv)


def _redact(message: str, database_url: str | None) -> str:
    redacted = message
    if database_url:
        redacted = redacted.replace(database_url, "<redacted DATABASE_URL>")
        password = urlsplit(database_url).password
        for secret in {password, unquote(password or "")}:
            if secret:
                redacted = redacted.replace(secret, "<redacted DATABASE_PASSWORD>")
    return redacted


def _database_url_from_env() -> str:
    database_url = os.getenv("DATABASE_URL")
    if not database_url or not database_url.strip():
        raise MigrationBlocked("DATABASE_URL is required and must be provided by environment only")
    # Same normalisation the application authority applies
    # (app.core.settings.validate_database_configuration). Without it a padded
    # value reaches create_engine unstripped and dies on an opaque ArgumentError,
    # while the app it is migrating connects to that very database.
    return database_url.strip()


def _rows_to_dicts(rows) -> list[dict[str, Any]]:
    return [dict(row._mapping) for row in rows]


def _scalar(conn, sql: str, **params):
    return conn.execute(text(sql), params).scalar()


def _dialect_key(dialect: str) -> str:
    if dialect.startswith("postgres"):
        return "postgresql"
    if dialect.startswith("sqlite"):
        return "sqlite"
    return dialect


def _schema_for_dialect(dialect: str) -> str | None:
    return SCHEMA_NAME if _dialect_key(dialect) == "postgresql" else None


def _table_ref(dialect: str) -> str:
    return f"{SCHEMA_NAME}.{TABLE_NAME}" if _dialect_key(dialect) == "postgresql" else TABLE_NAME


def _index_ref(dialect: str) -> str:
    return INDEX_NAME


def _postgres_index_definition(conn) -> str | None:
    return conn.execute(
        text(
            """
            SELECT indexdef
            FROM pg_indexes
            WHERE schemaname = 'public'
              AND tablename = :table_name
              AND indexname = :index_name
            """
        ),
        {"table_name": TABLE_NAME, "index_name": INDEX_NAME},
    ).scalar()


def _provider_event_id_column_type_valid(column_type: str | None) -> bool:
    normalized = str(column_type or "").strip().lower()
    return any(marker in normalized for marker in SUPPORTED_COLUMN_TYPE_MARKERS)


def _provider_event_id_column_exists(conn: Any) -> bool:
    schema = _schema_for_dialect(conn.dialect.name)
    columns = inspect(conn).get_columns(TABLE_NAME, schema=schema)
    return any(column["name"] == COLUMN_NAME for column in columns)


def _index_predicate_matches(definition: str | None) -> bool:
    normalized = " ".join(str(definition or "").replace('"', "").lower().split())
    if " where " not in normalized:
        return False
    predicate = normalized.split(" where ", 1)[1].strip().rstrip(";")
    while predicate.startswith("(") and predicate.endswith(")"):
        predicate = predicate[1:-1].strip()
    return predicate == EXPECTED_INDEX_PREDICATE


def _sqlite_index_is_unique_partial(conn) -> bool | None:
    rows = conn.execute(text(f"PRAGMA index_list({TABLE_NAME})")).fetchall()
    for row in rows:
        mapping = row._mapping
        if mapping.get("name") == INDEX_NAME:
            return bool(mapping.get("partial")) and bool(mapping.get("unique"))
    return None


def _canonical_index_valid(state: PreflightState) -> bool | None:
    if not state.canonical_index_exists:
        return None

    expected_columns = ["provider", COLUMN_NAME]
    if state.canonical_index_columns != expected_columns:
        return False

    if state.dialect == "postgresql":
        definition = (state.canonical_index_definition or "").lower()
        return (
            "unique index" in definition
            and _index_predicate_matches(state.canonical_index_definition)
        )

    if state.dialect == "sqlite":
        return state.canonical_index_valid is True and _index_predicate_matches(state.canonical_index_definition)

    return False


def _collect_common_preflight(conn, state: PreflightState) -> None:
    inspector = inspect(conn)
    schema = _schema_for_dialect(state.dialect)
    table_ref = _table_ref(state.dialect)
    state.table_exists = inspector.has_table(TABLE_NAME, schema=schema)
    if not state.table_exists:
        state.unsafe_reasons.append(
            "subscription_audit_logs table is missing; base schema must exist before this migration"
        )
        return

    columns = inspector.get_columns(TABLE_NAME, schema=schema)
    column_names = {str(column["name"]) for column in columns}
    missing_base_columns = [
        column_name for column_name in REQUIRED_BASE_COLUMNS if column_name not in column_names
    ]
    if missing_base_columns:
        state.unsafe_reasons.append(
            "subscription_audit_logs base schema is missing required columns: "
            + ", ".join(missing_base_columns)
        )
        return

    for column in columns:
        if column["name"] == "provider":
            state.provider_column_nullable = bool(column.get("nullable"))
        if column["name"] == COLUMN_NAME:
            state.column_exists = True
            state.column_nullable = bool(column.get("nullable"))
            state.column_type = str(column.get("type"))

    indexes = inspector.get_indexes(TABLE_NAME, schema=schema)
    for index in indexes:
        if index.get("name") == INDEX_NAME:
            state.canonical_index_exists = True
            state.canonical_index_columns = list(index.get("column_names") or [])
            break

    constraints = inspector.get_unique_constraints(TABLE_NAME, schema=schema)
    for constraint in constraints:
        columns = list(constraint.get("column_names") or [])
        name = constraint.get("name") or "<unnamed>"
        if name == INDEX_NAME or columns == ["provider", COLUMN_NAME]:
            state.redundant_unique_constraints.append(name)

    state.null_provider_rows = int(
        _scalar(conn, f"SELECT COUNT(*) FROM {table_ref} WHERE provider IS NULL") or 0
    )

    if state.column_exists:
        state.historical_stripe_rows_without_provider_event_id = int(
            _scalar(
                conn,
                f"""
                SELECT COUNT(*)
                FROM {table_ref}
                WHERE provider = 'stripe'
                  AND {COLUMN_NAME} IS NULL
                """,
            )
            or 0
        )
        state.duplicate_provider_event_pair_count = int(
            _scalar(
                conn,
                f"""
                SELECT COUNT(*)
                FROM (
                    SELECT provider, {COLUMN_NAME}
                    FROM {table_ref}
                    WHERE {COLUMN_NAME} IS NOT NULL
                    GROUP BY provider, {COLUMN_NAME}
                    HAVING COUNT(*) > 1
                ) duplicate_pairs
                """,
            )
            or 0
        )
        state.duplicate_provider_event_pairs = _rows_to_dicts(
            conn.execute(
                text(
                    f"""
                    SELECT provider, {COLUMN_NAME}, COUNT(*) AS duplicates
                    FROM {table_ref}
                    WHERE {COLUMN_NAME} IS NOT NULL
                    GROUP BY provider, {COLUMN_NAME}
                    HAVING COUNT(*) > 1
                    LIMIT 10
                    """
                )
            )
        )
    else:
        state.historical_stripe_rows_without_provider_event_id = int(
            _scalar(
                conn,
                f"""
                SELECT COUNT(*)
                FROM {table_ref}
                WHERE provider = 'stripe'
                """,
            )
            or 0
        )

    state.total_rows = int(_scalar(conn, f"SELECT COUNT(*) FROM {table_ref}") or 0)


def _collect_postgresql_preflight(conn, state: PreflightState) -> None:
    state.canonical_index_definition = _postgres_index_definition(conn)
    state.canonical_index_valid = _canonical_index_valid(state)

    state.invalid_indexes = [
        str(row._mapping["invalid_index"])
        for row in conn.execute(
            text(
                """
                SELECT indexrelid::regclass AS invalid_index
                FROM pg_index
                WHERE indrelid = 'public.subscription_audit_logs'::regclass
                  AND indisvalid = false
                """
            )
        ).fetchall()
    ]
    state.table_size = _scalar(
        conn,
        "SELECT pg_size_pretty(pg_total_relation_size('public.subscription_audit_logs'))",
    )
    state.indexes_size = _scalar(
        conn,
        "SELECT pg_size_pretty(pg_indexes_size('public.subscription_audit_logs'))",
    )
    state.active_locks = _rows_to_dicts(
        conn.execute(
            text(
                """
                SELECT pid, mode, granted
                FROM pg_locks
                WHERE relation = 'public.subscription_audit_logs'::regclass
                  AND pid <> pg_backend_pid()
                """
            )
        )
    )
    state.long_transactions = _rows_to_dicts(
        conn.execute(
            text(
                """
                SELECT pid, state, now() - xact_start AS age
                FROM pg_stat_activity
                WHERE xact_start IS NOT NULL
                  AND pid <> pg_backend_pid()
                  AND datname = current_database()
                  AND now() - xact_start > interval '5 minutes'
                """
            )
        )
    )
    state.can_alter_table = bool(
        _scalar(
            conn,
            """
            SELECT pg_catalog.pg_get_userbyid(c.relowner) = current_user
                   OR pg_has_role(pg_catalog.pg_get_userbyid(c.relowner), 'MEMBER')
                   OR (
                       SELECT rolsuper
                       FROM pg_roles
                       WHERE rolname = current_user
                   )
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = 'public'
              AND c.relname = 'subscription_audit_logs'
            """,
        )
    )
    state.table_owner = _scalar(
        conn,
        """
        SELECT pg_catalog.pg_get_userbyid(c.relowner)
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'public'
          AND c.relname = 'subscription_audit_logs'
        """,
    )


def _collect_sqlite_preflight(conn, state: PreflightState) -> None:
    if state.canonical_index_exists:
        state.canonical_index_definition = conn.execute(
            text(
                """
                SELECT sql
                FROM sqlite_master
                WHERE type = 'index'
                  AND name = :index_name
                """
            ),
            {"index_name": INDEX_NAME},
        ).scalar()
        state.canonical_index_valid = _sqlite_index_is_unique_partial(conn)
        state.canonical_index_valid = _canonical_index_valid(state)
    state.can_alter_table = True
    state.table_size = "sqlite_not_available"
    state.indexes_size = "sqlite_not_available"


def run_preflight(engine: Engine) -> PreflightState:
    dialect = _dialect_key(engine.dialect.name)
    logger.info("step=preflight_start dialect=%s", dialect)

    with engine.connect() as conn:
        state = PreflightState(dialect=dialect, table_exists=False)
        _collect_common_preflight(conn, state)

        if state.table_exists:
            if dialect == "postgresql":
                _collect_postgresql_preflight(conn, state)
            elif dialect == "sqlite":
                _collect_sqlite_preflight(conn, state)
            else:
                state.unsafe_reasons.append(f"unsupported database dialect: {dialect}")

    _validate_preflight_state(state)
    _log_preflight_state(state)
    return state


def _validate_preflight_state(state: PreflightState) -> None:
    if not state.table_exists:
        return

    ddl_needed = state.needs_column or (
        state.table_exists
        and (state.column_exists or state.needs_column)
        and not state.canonical_index_exists
    )

    if state.column_exists and state.column_nullable is not True:
        state.unsafe_reasons.append("provider_event_id exists but is not nullable")

    if state.column_exists and not _provider_event_id_column_type_valid(state.column_type):
        state.unsafe_reasons.append("provider_event_id exists with incompatible type")

    if state.provider_column_nullable is not False:
        state.unsafe_reasons.append(
            "provider column must be NOT NULL before relying on provider_event_id unique index"
        )

    if state.null_provider_rows:
        state.unsafe_reasons.append(
            "subscription_audit_logs contains rows with NULL provider; normalize them before applying uniqueness"
        )

    if state.canonical_index_exists and state.canonical_index_valid is not True:
        state.unsafe_reasons.append("canonical index exists but does not match the required partial unique index")

    if state.redundant_unique_constraints:
        state.unsafe_reasons.append(
            "redundant UniqueConstraint detected; remove or reconcile before applying canonical partial index"
        )

    if state.invalid_indexes:
        state.unsafe_reasons.append("invalid index detected; drop/reconcile invalid index before applying migration")

    if state.duplicate_provider_event_pair_count or state.duplicate_provider_event_pairs:
        state.unsafe_reasons.append("duplicate (provider, provider_event_id) pairs detected")

    if state.historical_stripe_rows_without_provider_event_id:
        state.unsafe_reasons.append(
            "historical Stripe audit rows without provider_event_id require reconciliation before uniqueness"
        )

    if ddl_needed and state.long_transactions:
        state.unsafe_reasons.append("long transactions detected before DDL")

    if ddl_needed and state.can_alter_table is False:
        state.unsafe_reasons.append("current database user lacks ALTER privilege on subscription_audit_logs")

    if state.canonical_index_exists and not state.column_exists:
        state.unsafe_reasons.append("canonical index exists but provider_event_id column is missing")


def _log_preflight_state(state: PreflightState) -> None:
    logger.info("step=preflight_table_exists value=%s", state.table_exists)
    logger.info("step=preflight_provider_nullable value=%s", state.provider_column_nullable)
    logger.info("step=preflight_null_provider_rows value=%s", state.null_provider_rows)
    logger.info("step=preflight_column_exists value=%s", state.column_exists)
    logger.info("step=preflight_index_exists value=%s", state.canonical_index_exists)
    logger.info("step=preflight_total_rows value=%s", state.total_rows)
    logger.info("step=preflight_table_size value=%s", state.table_size)
    logger.info("step=preflight_indexes_size value=%s", state.indexes_size)
    logger.info("step=preflight_table_owner value=%s", state.table_owner)
    logger.info("step=preflight_can_alter_table value=%s", state.can_alter_table)
    logger.info("step=preflight_active_locks count=%s", len(state.active_locks))
    logger.info("step=preflight_long_transactions count=%s", len(state.long_transactions))
    logger.info("step=preflight_invalid_indexes count=%s", len(state.invalid_indexes))
    logger.info(
        "step=preflight_duplicate_provider_event_pairs count=%s sample=%s",
        state.duplicate_provider_event_pair_count,
        len(state.duplicate_provider_event_pairs),
    )
    logger.info(
        "step=preflight_historical_stripe_without_provider_event_id count=%s",
        state.historical_stripe_rows_without_provider_event_id,
    )
    if state.unsafe_reasons:
        for reason in state.unsafe_reasons:
            logger.error("step=preflight_blocked reason=%s", reason)
    else:
        logger.info("step=preflight_ok")


def planned_actions(state: PreflightState) -> list[str]:
    actions: list[str] = []
    if state.needs_column:
        actions.append("add_nullable_provider_event_id_column")
    if (
        state.table_exists
        and not state.canonical_index_exists
        and not state.historical_stripe_rows_without_provider_event_id
    ):
        actions.append("create_canonical_partial_unique_index")
    return actions


def _assert_safe_for_apply(state: PreflightState, index_strategy: str | None) -> None:
    if state.unsafe_reasons:
        raise MigrationBlocked("preflight failed; DDL is blocked")

    actions = planned_actions(state)
    if not actions:
        return

    if "create_canonical_partial_unique_index" in actions and not index_strategy:
        raise MigrationBlocked(
            "--index-strategy normal|concurrent is required when index creation is needed"
        )

    if index_strategy == "concurrent" and state.dialect != "postgresql":
        raise MigrationBlocked("concurrent index strategy is supported only for PostgreSQL")

    conflicting_locks = _conflicting_active_locks(state, actions, index_strategy)
    if conflicting_locks:
        raise MigrationBlocked("conflicting active locks detected on subscription_audit_logs")


def _conflicting_active_locks(
    state: PreflightState,
    actions: list[str],
    index_strategy: str | None,
) -> list[dict[str, Any]]:
    if not actions or not state.active_locks:
        return []

    granted_locks = [lock for lock in state.active_locks if lock.get("granted") is not False]
    if not granted_locks:
        return []

    if "add_nullable_provider_event_id_column" in actions:
        return granted_locks

    if "create_canonical_partial_unique_index" in actions and index_strategy == "concurrent":
        return [
            lock
            for lock in granted_locks
            if str(lock.get("mode") or "") in CONCURRENT_INDEX_CONFLICTING_LOCKS
        ]

    return granted_locks


def _apply_postgresql_timeout_guards(conn: Any, *, local: bool, statement_timeout: str = DDL_STATEMENT_TIMEOUT) -> None:
    if conn.dialect.name != "postgresql":
        return

    scope = "LOCAL " if local else ""
    logger.info(
        "step=ddl_timeout_guards scope=%s lock_timeout=%s statement_timeout=%s",
        "transaction" if local else "connection",
        DDL_LOCK_TIMEOUT,
        statement_timeout,
    )
    conn.execute(text(f"SET {scope}lock_timeout TO '{DDL_LOCK_TIMEOUT}'"))
    conn.execute(text(f"SET {scope}statement_timeout TO '{statement_timeout}'"))


def _add_column(engine: Engine) -> None:
    logger.info("step=ddl_add_column_start")
    with engine.begin() as conn:
        _apply_postgresql_timeout_guards(conn, local=True)
        if _provider_event_id_column_exists(conn):
            logger.info("step=ddl_add_column_skip reason=already_exists")
            return
        conn.execute(text(f"ALTER TABLE {_table_ref(conn.dialect.name)} ADD COLUMN {COLUMN_NAME} VARCHAR"))
    logger.info("step=ddl_add_column_done")


def _apply_normal_migration(engine: Engine, actions: list[str]) -> None:
    logger.info("step=ddl_normal_transaction_start")
    with engine.begin() as conn:
        _apply_postgresql_timeout_guards(conn, local=True)
        if "add_nullable_provider_event_id_column" in actions:
            logger.info("step=ddl_add_column_start")
            if _provider_event_id_column_exists(conn):
                logger.info("step=ddl_add_column_skip reason=already_exists")
            else:
                conn.execute(text(f"ALTER TABLE {_table_ref(conn.dialect.name)} ADD COLUMN {COLUMN_NAME} VARCHAR"))
                logger.info("step=ddl_add_column_done")
        if "create_canonical_partial_unique_index" in actions:
            logger.info("step=ddl_create_index_normal_start")
            conn.execute(
                text(
                    f"""
                    CREATE UNIQUE INDEX IF NOT EXISTS {_index_ref(conn.dialect.name)}
                    ON {_table_ref(conn.dialect.name)}(provider, {COLUMN_NAME})
                    WHERE {COLUMN_NAME} IS NOT NULL
                    """
                )
            )
            logger.info("step=ddl_create_index_normal_done")
    logger.info("step=ddl_normal_transaction_done")


def _create_index_normal(engine: Engine) -> None:
    logger.info("step=ddl_create_index_normal_start")
    with engine.begin() as conn:
        _apply_postgresql_timeout_guards(conn, local=True)
        conn.execute(
            text(
                f"""
                CREATE UNIQUE INDEX IF NOT EXISTS {_index_ref(conn.dialect.name)}
                ON {_table_ref(conn.dialect.name)}(provider, {COLUMN_NAME})
                WHERE {COLUMN_NAME} IS NOT NULL
                """
            )
        )
    logger.info("step=ddl_create_index_normal_done")


def _create_index_concurrently(engine: Engine) -> None:
    logger.info("step=ddl_create_index_concurrently_start")
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        _apply_postgresql_timeout_guards(
            conn,
            local=False,
            statement_timeout=CONCURRENT_INDEX_STATEMENT_TIMEOUT,
        )
        conn.execute(
            text(
                f"""
                CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS {_index_ref(conn.dialect.name)}
                ON {_table_ref(conn.dialect.name)}(provider, {COLUMN_NAME})
                WHERE {COLUMN_NAME} IS NOT NULL
                """
            )
        )
    logger.info("step=ddl_create_index_concurrently_done")


def apply_migration(engine: Engine, state: PreflightState, index_strategy: str | None) -> None:
    _assert_safe_for_apply(state, index_strategy)
    actions = planned_actions(state)

    if not actions:
        logger.info("step=apply_noop reason=already_applied")
        return

    if index_strategy == "normal":
        _apply_normal_migration(engine, actions)
    else:
        if state.needs_column:
            _add_column(engine)

        if "create_canonical_partial_unique_index" in actions:
            if index_strategy == "concurrent":
                _create_index_concurrently(engine)
            else:
                raise MigrationBlocked("index strategy missing for index creation")

    post_state = run_preflight(engine)
    if post_state.unsafe_reasons or not post_state.applied:
        raise MigrationBlocked("post-apply validation failed", exit_code=EXIT_APPLY_FAILED)
    logger.info("step=post_apply_validation_ok")


def run(engine: Engine, apply: bool, index_strategy: str | None) -> int:
    state = run_preflight(engine)
    actions = planned_actions(state)

    if state.unsafe_reasons:
        return EXIT_PREFLIGHT_FAILED

    if not apply:
        logger.info("step=mode_preflight_only ddl_executed=false")
        logger.info("step=planned_actions actions=%s", ",".join(actions) or "none")
        return EXIT_OK

    logger.info("step=mode_apply ddl_executed=pending")
    apply_migration(engine, state, index_strategy)
    logger.info("step=mode_apply ddl_executed=true")
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    configure_logging()
    args = parse_args(argv)
    database_url: str | None = None

    try:
        database_url = _database_url_from_env()
        engine = create_engine(database_url, future=True)
        logger.info("step=database_detected dialect=%s", _dialect_key(engine.dialect.name))
        return run(engine, apply=args.apply, index_strategy=args.index_strategy)
    except MigrationBlocked as exc:
        logger.error("step=migration_blocked detail=%s", _redact(str(exc), database_url))
        return exc.exit_code
    except SQLAlchemyError as exc:
        logger.error("step=sqlalchemy_error type=%s detail=%s", type(exc).__name__, _redact(str(exc), database_url))
        return EXIT_APPLY_FAILED
    except Exception as exc:
        logger.error("step=unexpected_error type=%s detail=%s", type(exc).__name__, _redact(str(exc), database_url))
        return EXIT_UNEXPECTED


if __name__ == "__main__":
    sys.exit(main())
