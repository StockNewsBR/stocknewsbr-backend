import os
import re
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from sqlalchemy import create_engine, inspect as sqlalchemy_inspect, text

os.environ.setdefault("SECRET_KEY", "mission36-unit-test-secret-key-20260711")

from app.core import settings as runtime_settings
from app import config as app_config
from app import database
from app import database_schema


class _CatalogResult:
    def __init__(self, rows):
        self.rows = rows

    def mappings(self):
        return iter(self.rows)


class _CatalogConnection:
    def __init__(self, engine):
        self.engine = engine

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, statement):
        rendered = str(statement).lower()
        if "from pg_class" in rendered:
            rows = [
                {
                    "table_name": table_name,
                    "rls_enabled": table_name != self.engine.disabled_rls_table,
                    "rls_forced": table_name != self.engine.unforced_rls_table,
                }
                for table_name in database_schema.REQUIRED_PRODUCTION_RLS_POLICIES
                if table_name != self.engine.missing_rls_table
            ]
            return _CatalogResult(rows)
        if "from pg_policies" in rendered:
            rows = []
            for table_name, policies in database_schema.REQUIRED_PRODUCTION_RLS_POLICIES.items():
                for policy_name, expected in policies.items():
                    if policy_name == self.engine.missing_policy:
                        continue
                    role, cmd, require_using, require_check, expression_kind = expected
                    expression = (
                        "true"
                        if expression_kind == "true"
                        else (
                            f"({expression_kind} = NULLIF("
                            "current_setting('app.current_user_id'::text, true), "
                            "''::text)::integer)"
                        )
                    )
                    row = {
                        "table_name": table_name,
                        "policyname": policy_name,
                        "cmd": cmd,
                        "roles": [role],
                        "qual": expression if require_using else None,
                        "with_check": expression if require_check else None,
                    }
                    if policy_name == self.engine.overridden_policy:
                        row.update(self.engine.policy_override)
                    rows.append(row)
            return _CatalogResult(rows)
        raise AssertionError(f"unexpected catalog query: {rendered}")


class _NoDdlEngine:
    def __init__(
        self,
        *,
        missing_rls_table=None,
        disabled_rls_table=None,
        unforced_rls_table=None,
        missing_policy=None,
        overridden_policy=None,
        policy_override=None,
    ):
        self.missing_rls_table = missing_rls_table
        self.disabled_rls_table = disabled_rls_table
        self.unforced_rls_table = unforced_rls_table
        self.missing_policy = missing_policy
        self.overridden_policy = overridden_policy
        self.policy_override = dict(policy_override or {})

    def begin(self):
        raise AssertionError("schema validation must not open a DDL transaction")

    def connect(self):
        return _CatalogConnection(self)


class _SchemaInspector:
    def __init__(
        self,
        *,
        missing_table=None,
        missing_column=None,
        missing_index=None,
        index_columns_override=None,
        missing_primary_key=None,
        missing_unique_constraint=None,
        missing_foreign_key=None,
    ):
        self.missing_table = missing_table
        self.columns = {
            table_name: set(required_columns)
            for table_name, required_columns in database_schema.REQUIRED_PRODUCTION_COLUMNS.items()
        }
        self.indexes = {
            table_name: dict(required_indexes)
            for table_name, required_indexes in database_schema.REQUIRED_PRODUCTION_INDEXES.items()
        }
        self.primary_keys = dict(database_schema.REQUIRED_PRODUCTION_PRIMARY_KEYS)
        self.unique_constraints = {
            table_name: dict(required_constraints)
            for table_name, required_constraints in
            database_schema.REQUIRED_PRODUCTION_UNIQUE_CONSTRAINTS.items()
        }
        self.foreign_keys = {
            table_name: set(required_foreign_keys)
            for table_name, required_foreign_keys in
            database_schema.REQUIRED_PRODUCTION_FOREIGN_KEYS.items()
        }
        if missing_column:
            table_name, column_name = missing_column
            self.columns[table_name].discard(column_name)
        if missing_index:
            table_name, index_name = missing_index
            self.indexes[table_name].pop(index_name, None)
        if index_columns_override:
            table_name, index_name, column_names = index_columns_override
            self.indexes[table_name][index_name] = tuple(column_names)
        if missing_primary_key:
            self.primary_keys[missing_primary_key] = ()
        if missing_unique_constraint:
            table_name, constraint_name = missing_unique_constraint
            self.unique_constraints[table_name].pop(constraint_name)
        if missing_foreign_key:
            table_name, foreign_key = missing_foreign_key
            self.foreign_keys[table_name].discard(foreign_key)

    def has_table(self, table_name):
        return table_name != self.missing_table and table_name in self.columns

    def get_columns(self, table_name):
        return [{"name": name} for name in self.columns[table_name]]

    def get_indexes(self, table_name):
        unique_indexes = database_schema.REQUIRED_PRODUCTION_UNIQUE_INDEXES.get(
            table_name,
            set(),
        )
        return [
            {
                "name": name,
                "column_names": list(column_names),
                "unique": name in unique_indexes,
            }
            for name, column_names in self.indexes.get(table_name, {}).items()
        ]

    def get_pk_constraint(self, table_name):
        return {"constrained_columns": list(self.primary_keys[table_name])}

    def get_unique_constraints(self, table_name):
        return [
            {"name": name, "column_names": list(columns)}
            for name, columns in self.unique_constraints.get(table_name, {}).items()
        ]

    def get_foreign_keys(self, table_name):
        return [
            {
                "constrained_columns": list(constrained_columns),
                "referred_table": referred_table,
                "referred_columns": list(referred_columns),
            }
            for constrained_columns, referred_table, referred_columns
            in self.foreign_keys.get(table_name, set())
        ]


class _FakeSession:
    def __init__(self, dialect="postgresql", active_transaction=True, reject_execute=False):
        self.bind = SimpleNamespace(dialect=SimpleNamespace(name=dialect))
        self.active_transaction = active_transaction
        self.reject_execute = reject_execute
        self.info = {}
        self.executions = []
        self.closed = False

    def get_bind(self):
        return self.bind

    def in_transaction(self):
        return self.active_transaction

    def execute(self, statement, parameters=None):
        if self.reject_execute:
            raise AssertionError("session.execute must not be called")
        self.executions.append((statement, parameters))

    def close(self):
        self.closed = True


class _FakeConnection:
    def __init__(self, dialect="postgresql"):
        self.dialect = SimpleNamespace(name=dialect)
        self.executions = []

    def execute(self, statement, parameters=None):
        self.executions.append((statement, parameters))


class DatabaseConfigurationTests(unittest.TestCase):
    def test_production_rejects_missing_database_url(self):
        with self.assertRaisesRegex(RuntimeError, "^DATABASE_URL_REQUIRED_FOR_PRODUCTION$"):
            runtime_settings.validate_database_configuration(
                environment="production",
                database_url="",
            )

    def test_production_rejects_sqlite_and_non_postgresql_dialects(self):
        cases = (
            "sqlite:///production.db",
            "mysql://user:secret@db.internal/stocknewsbr",
        )
        for database_url in cases:
            with self.subTest(database_url=database_url):
                with self.assertRaisesRegex(RuntimeError, "^POSTGRESQL_REQUIRED_FOR_PRODUCTION$"):
                    runtime_settings.validate_database_configuration(
                        environment="prod",
                        database_url=database_url,
                    )

    def test_production_rejects_malformed_database_url(self):
        with self.assertRaisesRegex(RuntimeError, "^DATABASE_URL_INVALID_FOR_PRODUCTION$"):
            runtime_settings.validate_database_configuration(
                environment="production",
                database_url="postgresql://unit:secret@db.internal:not-a-port/database",
            )

    def test_production_rejects_async_or_incomplete_database_urls(self):
        with self.assertRaisesRegex(
            RuntimeError,
            "^SYNC_POSTGRESQL_DRIVER_REQUIRED_FOR_PRODUCTION$",
        ):
            runtime_settings.validate_database_configuration(
                environment="production",
                database_url=(
                    "postgresql+asyncpg://stocknews:strong-secret@"
                    "db.internal/stocknewsbr"
                ),
            )

        for database_url in (
            "postgresql://stocknews:strong-secret@/stocknewsbr",
            "postgresql://stocknews@db.internal/stocknewsbr",
            "postgresql://:strong-secret@db.internal/stocknewsbr",
            "postgresql://stocknews:strong-secret@db.internal/",
        ):
            with self.subTest(database_url=database_url):
                with self.assertRaisesRegex(
                    RuntimeError,
                    "^DATABASE_URL_INCOMPLETE_FOR_PRODUCTION$",
                ):
                    runtime_settings.validate_database_configuration(
                        environment="production",
                        database_url=database_url,
                    )

    def test_production_rejects_placeholders_by_complete_component(self):
        cases = (
            "postgresql://user:strong-secret@db.internal/stocknewsbr",
            "postgresql://stocknews:password@db.internal/stocknewsbr",
            "postgresql://stocknews:strong-secret@host/stocknewsbr",
            "postgresql://stocknews:strong-secret@db.internal/database",
            "postgresql://${DB_USER}:strong-secret@db.internal/stocknewsbr",
            "postgresql://stocknews:<password>@db.internal/stocknewsbr",
        )
        for database_url in cases:
            with self.subTest(database_url=database_url):
                with self.assertRaisesRegex(
                    RuntimeError,
                    "^DATABASE_URL_PLACEHOLDER_FORBIDDEN_IN_PRODUCTION$",
                ):
                    runtime_settings.validate_database_configuration(
                        environment="production",
                        database_url=database_url,
                    )

    def test_legitimate_component_substrings_are_not_placeholders(self):
        database_url = (
            "postgresql://marketuser:securepasswordvalue@"
            "database-host.internal/hostdatabase"
        )
        self.assertEqual(
            runtime_settings.validate_database_configuration(
                environment="production",
                database_url=database_url,
            ),
            database_url,
        )

    def test_valid_postgresql_urls_are_accepted(self):
        for database_url in (
            "postgresql://stocknews:strong-secret@db.internal/stocknewsbr",
            "postgresql+psycopg2://stocknews:strong-secret@db.internal/stocknewsbr",
        ):
            with self.subTest(database_url=database_url):
                self.assertEqual(
                    runtime_settings.validate_database_configuration(
                        environment="production",
                        database_url=database_url,
                    ),
                    database_url,
                )

    def test_local_dev_and_test_accept_sqlite_and_preserve_fallback(self):
        sqlite_url = "sqlite:///:memory:"
        for environment in ("development", "dev", "local", "test", "testing"):
            with self.subTest(environment=environment):
                self.assertEqual(
                    runtime_settings.validate_database_configuration(
                        environment=environment,
                        database_url=sqlite_url,
                    ),
                    sqlite_url,
                )
                self.assertEqual(
                    runtime_settings.validate_database_configuration(
                        environment=environment,
                        database_url="",
                    ),
                    runtime_settings.DEFAULT_DATABASE_URL,
                )

    def test_database_errors_do_not_expose_dsn_or_credentials(self):
        database_url = "postgresql://private-user:password@private-host/private-database"
        with self.assertRaises(RuntimeError) as context:
            runtime_settings.validate_database_configuration(
                environment="production",
                database_url=database_url,
            )
        rendered = str(context.exception)
        for sensitive_value in (
            database_url,
            "private-user",
            "password",
            "private-host",
            "private-database",
        ):
            self.assertNotIn(sensitive_value, rendered)

    def test_all_database_exports_share_the_canonical_value(self):
        self.assertEqual(app_config.DATABASE_URL, runtime_settings.DATABASE_URL)
        self.assertEqual(database.DATABASE_URL, runtime_settings.DATABASE_URL)
        self.assertEqual(runtime_settings.settings.DATABASE_URL, runtime_settings.DATABASE_URL)

    def test_background_worker_default_uses_canonical_production_aliases(self):
        import main

        for environment, expected in (
            ("prod", True),
            ("production", True),
            ("development", False),
            ("dev", False),
            ("local", False),
            ("test", False),
        ):
            with self.subTest(environment=environment):
                with patch.dict(os.environ, {"ENV": environment}):
                    self.assertIs(main._default_start_background_workers(), expected)


class RuntimeSchemaGuardTests(unittest.TestCase):
    def test_runtime_ddl_is_forbidden_in_production_before_engine_access(self):
        with patch.dict(os.environ, {"ENV": "production"}):
            with self.assertRaisesRegex(RuntimeError, "^RUNTIME_DDL_FORBIDDEN_IN_PRODUCTION$"):
                database_schema.ensure_runtime_schema(_NoDdlEngine())

    def test_runtime_ddl_remains_available_in_test_and_local_sqlite(self):
        for environment in ("test", "local"):
            with self.subTest(environment=environment):
                engine = create_engine("sqlite:///:memory:")
                try:
                    with engine.begin() as connection:
                        connection.execute(text("CREATE TABLE users (id INTEGER PRIMARY KEY)"))
                    with patch.dict(os.environ, {"ENV": environment}):
                        database_schema.ensure_runtime_schema(engine)
                    columns = {
                        column["name"]
                        for column in sqlalchemy_inspect(engine).get_columns("users")
                    }
                    self.assertIn("updated_at", columns)
                finally:
                    engine.dispose()

    def test_production_schema_validation_is_read_only(self):
        inspector = _SchemaInspector()
        with patch("app.database_schema.inspect", return_value=inspector):
            result = database_schema.validate_production_schema(_NoDdlEngine())
        self.assertEqual(
            result,
            {
                "tables": len(database_schema.REQUIRED_PRODUCTION_COLUMNS),
                "indexes": sum(
                    len(indexes)
                    for indexes in database_schema.REQUIRED_PRODUCTION_INDEXES.values()
                ),
                "primary_keys": len(database_schema.REQUIRED_PRODUCTION_PRIMARY_KEYS),
                "unique_constraints": sum(
                    len(constraints)
                    for constraints in
                    database_schema.REQUIRED_PRODUCTION_UNIQUE_CONSTRAINTS.values()
                ),
                "foreign_keys": sum(
                    len(foreign_keys)
                    for foreign_keys in
                    database_schema.REQUIRED_PRODUCTION_FOREIGN_KEYS.values()
                ),
                "rls_policies": sum(
                    len(policies)
                    for policies in database_schema.REQUIRED_PRODUCTION_RLS_POLICIES.values()
                ),
            },
        )

    def test_production_schema_validation_fails_closed_on_missing_objects(self):
        cases = (
            _SchemaInspector(missing_table="users"),
            _SchemaInspector(missing_column=("users", "email")),
            _SchemaInspector(
                missing_index=("auth_audit_events", "ix_auth_audit_event_ip_created")
            ),
            _SchemaInspector(missing_primary_key="media_assets"),
            _SchemaInspector(
                missing_unique_constraint=(
                    "promo_redemptions",
                    "uq_promo_redemption_user_code",
                )
            ),
            _SchemaInspector(
                missing_foreign_key=(
                    "media_assets",
                    (("owner_user_id",), "users", ("id",)),
                )
            ),
        )
        for inspector in cases:
            with self.subTest(inspector=inspector):
                with patch("app.database_schema.inspect", return_value=inspector):
                    with self.assertRaisesRegex(RuntimeError, "^PRODUCTION_SCHEMA_NOT_READY$"):
                        database_schema.validate_production_schema(_NoDdlEngine())

    def test_production_schema_validation_rejects_wrong_common_index_columns(self):
        inspector = _SchemaInspector(
            index_columns_override=(
                "media_assets",
                "ix_media_assets_owner_user_id",
                ("status",),
            )
        )
        with patch("app.database_schema.inspect", return_value=inspector):
            with self.assertRaisesRegex(RuntimeError, "^PRODUCTION_SCHEMA_NOT_READY$"):
                database_schema.validate_production_schema(_NoDdlEngine())

    def test_production_schema_validation_rejects_wrong_unique_index_columns(self):
        inspector = _SchemaInspector(
            index_columns_override=("users", "ix_users_email", ("telegram_id",))
        )
        email_index = next(
            index
            for index in inspector.get_indexes("users")
            if index["name"] == "ix_users_email"
        )
        self.assertTrue(email_index["unique"])
        with patch("app.database_schema.inspect", return_value=inspector):
            with self.assertRaisesRegex(RuntimeError, "^PRODUCTION_SCHEMA_NOT_READY$"):
                database_schema.validate_production_schema(_NoDdlEngine())

    def test_production_schema_validation_rejects_reordered_composite_index(self):
        inspector = _SchemaInspector(
            index_columns_override=(
                "auth_audit_events",
                "ix_auth_audit_event_ip_created",
                ("created_at", "ip_hash", "event"),
            )
        )
        with patch("app.database_schema.inspect", return_value=inspector):
            with self.assertRaisesRegex(RuntimeError, "^PRODUCTION_SCHEMA_NOT_READY$"):
                database_schema.validate_production_schema(_NoDdlEngine())

    def test_production_schema_validation_fails_closed_on_rls_drift(self):
        engines = (
            _NoDdlEngine(missing_rls_table="media_assets"),
            _NoDdlEngine(disabled_rls_table="media_assets"),
            _NoDdlEngine(unforced_rls_table="promo_redemptions"),
            _NoDdlEngine(missing_policy="media_assets_app_select"),
            _NoDdlEngine(
                overridden_policy="media_assets_app_update",
                policy_override={"cmd": "SELECT"},
            ),
            _NoDdlEngine(
                overridden_policy="promo_redemptions_app_insert",
                policy_override={"with_check": None},
            ),
            _NoDdlEngine(
                overridden_policy="media_assets_app_select",
                policy_override={
                    "qual": (
                        "true OR owner_user_id = NULLIF("
                        "current_setting('app.current_user_id', true), '')::integer"
                    )
                },
            ),
        )
        inspector = _SchemaInspector()
        for engine in engines:
            with self.subTest(engine=engine):
                with patch("app.database_schema.inspect", return_value=inspector):
                    with self.assertRaisesRegex(
                        RuntimeError,
                        "^PRODUCTION_SCHEMA_NOT_READY$",
                    ):
                        database_schema.validate_production_schema(engine)

    def test_main_uses_read_only_schema_validation_in_production(self):
        import main

        with (
            patch("main.is_production_environment", return_value=True),
            patch("main.validate_production_schema") as validate_schema,
            patch.object(main.Base.metadata, "create_all") as create_all,
            patch("main.ensure_runtime_schema") as ensure_schema,
        ):
            main._create_tables_if_needed()
        validate_schema.assert_called_once_with(main.engine)
        create_all.assert_not_called()
        ensure_schema.assert_not_called()

    def test_main_preserves_runtime_schema_bootstrap_outside_production(self):
        import main

        with (
            patch("main.is_production_environment", return_value=False),
            patch("main.validate_production_schema") as validate_schema,
            patch.object(main.Base.metadata, "create_all") as create_all,
            patch("main.ensure_runtime_schema") as ensure_schema,
        ):
            main._create_tables_if_needed()
        validate_schema.assert_not_called()
        create_all.assert_called_once_with(bind=main.engine)
        ensure_schema.assert_called_once_with(main.engine)

    def test_social_table_bootstrap_is_read_only_in_production(self):
        from app.social import db as social_db

        original_initialized = social_db._initialized
        try:
            social_db._initialized = False
            with (
                patch("app.social.db.is_production_environment", return_value=True),
                patch("app.social.db.validate_required_tables") as validate_tables,
                patch.object(social_db.Base.metadata, "create_all") as create_all,
            ):
                social_db.ensure_social_tables()
            validate_tables.assert_called_once_with(
                social_db.engine,
                social_db.SOCIAL_REQUIRED_TABLES,
            )
            create_all.assert_not_called()
            self.assertTrue(social_db._initialized)
        finally:
            social_db._initialized = original_initialized

    def test_ai_worker_validates_without_patching_schema_in_production(self):
        from app.system import ai_worker

        with (
            patch("app.system.ai_worker.is_production_environment", return_value=True),
            patch("app.system.ai_worker.validate_production_schema") as validate_schema,
            patch("app.system.ai_worker.ensure_runtime_schema") as ensure_schema,
        ):
            ai_worker._ensure_worker_schema()
        validate_schema.assert_called_once_with(ai_worker.engine)
        ensure_schema.assert_not_called()


class RlsContextTests(unittest.TestCase):
    def test_sqlite_helper_is_an_explicit_noop(self):
        session = _FakeSession(
            dialect="sqlite",
            active_transaction=False,
            reject_execute=True,
        )
        database.apply_rls_context(
            session,
            current_user_id=0,
            current_role="not-a-role",
            request_id="unsafe request id",
        )
        self.assertEqual(session.info, {})
        self.assertEqual(session.executions, [])

    def test_postgresql_helper_requires_an_active_transaction(self):
        session = _FakeSession(active_transaction=False)
        with self.assertRaisesRegex(RuntimeError, "^RLS_CONTEXT_REQUIRES_ACTIVE_TRANSACTION$"):
            database.apply_rls_context(session, current_user_id=1)
        self.assertEqual(session.info, {})
        self.assertEqual(session.executions, [])

    def test_postgresql_helper_validates_context_values(self):
        invalid_cases = (
            {"current_user_id": 0},
            {"current_user_id": True},
            {"current_user_id": 1, "current_actor_id": -1},
            {"current_user_id": 1, "current_role": "owner"},
            {"current_user_id": 1, "request_id": "x" * 129},
            {"current_user_id": 1, "request_id": "unsafe request"},
        )
        for values in invalid_cases:
            with self.subTest(values=values):
                session = _FakeSession()
                with self.assertRaises(ValueError):
                    database.apply_rls_context(session, **values)
                self.assertEqual(session.info, {})
                self.assertEqual(session.executions, [])

    def test_postgresql_helper_uses_bound_transaction_local_set_config(self):
        session = _FakeSession()
        database.apply_rls_context(
            session,
            current_user_id=17,
            current_actor_id=23,
            current_role="worker",
            request_id="request-36.1",
        )
        expected = {
            "current_user_id": "17",
            "current_actor_id": "23",
            "current_role": "worker",
            "request_id": "request-36.1",
        }
        self.assertEqual(session.info[database.RLS_CONTEXT_INFO_KEY], expected)
        self.assertEqual(session.executions, [(database.RLS_CONTEXT_STATEMENT, expected)])

        sql = str(database.RLS_CONTEXT_STATEMENT)
        self.assertEqual(
            set(database.RLS_CONTEXT_STATEMENT._bindparams),
            set(expected),
        )
        self.assertEqual(sql.lower().count("set_config("), 4)
        self.assertEqual(sql.lower().count(", true)"), 4)
        self.assertNotIn("SET ", sql.upper())
        self.assertNotIn("request-36.1", sql)

    def test_after_begin_listener_reapplies_through_connection(self):
        context = {
            "current_user_id": "17",
            "current_actor_id": "17",
            "current_role": "user",
            "request_id": "req-17",
        }
        session = _FakeSession(reject_execute=True)
        session.info[database.RLS_CONTEXT_INFO_KEY] = context
        connection = _FakeConnection()

        database._reapply_rls_context_after_begin(session, object(), connection)

        self.assertEqual(
            connection.executions,
            [(database.RLS_CONTEXT_STATEMENT, context)],
        )
        self.assertTrue(
            getattr(database.Session, database._RLS_LISTENER_MARKER, False)
        )

    def test_listener_without_context_or_on_sqlite_creates_no_value(self):
        session = _FakeSession(reject_execute=True)
        postgresql_connection = _FakeConnection()
        database._reapply_rls_context_after_begin(
            session,
            object(),
            postgresql_connection,
        )
        self.assertEqual(postgresql_connection.executions, [])

        session.info[database.RLS_CONTEXT_INFO_KEY] = {"current_user_id": "17"}
        sqlite_connection = _FakeConnection(dialect="sqlite")
        database._reapply_rls_context_after_begin(session, object(), sqlite_connection)
        self.assertEqual(sqlite_connection.executions, [])

    def test_clear_rls_context_only_removes_session_info(self):
        session = _FakeSession(reject_execute=True)
        session.info.update(
            {
                database.RLS_CONTEXT_INFO_KEY: {"current_user_id": "17"},
                "unrelated": "preserved",
            }
        )
        database.clear_rls_context(session)
        self.assertEqual(session.info, {"unrelated": "preserved"})
        self.assertEqual(session.executions, [])

    def test_get_db_finally_clears_context_before_closing_session(self):
        session = _FakeSession()
        dependency = None
        with patch("app.database.SessionLocal", return_value=session):
            dependency = database.get_db()
            self.assertIs(next(dependency), session)
            session.info[database.RLS_CONTEXT_INFO_KEY] = {"current_user_id": "17"}
            dependency.close()

        self.assertNotIn(database.RLS_CONTEXT_INFO_KEY, session.info)
        self.assertTrue(session.closed)


# =====================================================================
# GATE 3.2 — static, semantic analysis of the versioned SQL artifacts
# =====================================================================

_SQL_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "scripts",
    "sql",
)
ROLES_RLS_SQL_PATH = os.path.join(_SQL_DIR, "mission_36_postgresql_roles_rls.sql")
VERIFY_SQL_PATH = os.path.join(_SQL_DIR, "mission_36_verify.sql")
PGAUDIT_VERIFY_SQL_PATH = os.path.join(_SQL_DIR, "mission_36_pgaudit_verify.sql")

STOCKNEWSBR_ROLES = (
    "stocknewsbr_owner",
    "stocknewsbr_app",
    "stocknewsbr_worker",
    "stocknewsbr_readonly",
    "stocknewsbr_backup",
    "stocknewsbr_migration",
)
APP_FACING_ROLES = (
    "stocknewsbr_app",
    "stocknewsbr_worker",
    "stocknewsbr_readonly",
    "stocknewsbr_backup",
)
RLS_CONTEXT_EXPRESSION = (
    "nullif(current_setting('app.current_user_id', true), '')::integer"
)


def _read_text(path):
    with open(path, "r", encoding="utf-8") as handle:
        return handle.read()


def _strip_sql_comments(sql):
    # Drop `--` line comments so that negative assertions (no GRANT ALL,
    # no BYPASSRLS, no credentials) can never be satisfied or defeated by
    # words that only appear in the documentation comments.
    cleaned = []
    for line in sql.splitlines():
        marker = line.find("--")
        if marker != -1:
            line = line[:marker]
        cleaned.append(line)
    return "\n".join(cleaned)


def _split_statements(sql):
    statements = []
    current = []
    in_dollar = False
    index = 0
    length = len(sql)
    while index < length:
        if sql[index : index + 2] == "$$":
            in_dollar = not in_dollar
            current.append("$$")
            index += 2
            continue
        char = sql[index]
        if char == ";" and not in_dollar:
            statements.append("".join(current).strip())
            current = []
        else:
            current.append(char)
        index += 1
    tail = "".join(current).strip()
    if tail:
        statements.append(tail)
    return [statement for statement in statements if statement]


def _collapse(text):
    return " ".join(text.split())


_POLICY_RE = re.compile(
    r"CREATE\s+POLICY\s+(?P<name>\w+)\s+ON\s+(?:public\.)?(?P<table>\w+)\s+"
    r"FOR\s+(?P<cmd>\w+)\s+TO\s+(?P<role>\w+)\s+(?P<body>.*)",
    re.IGNORECASE | re.DOTALL,
)


def _parse_policies(statements):
    policies = []
    for statement in statements:
        normalized = _collapse(statement)
        if not normalized.upper().startswith("CREATE POLICY"):
            continue
        match = _POLICY_RE.match(normalized)
        assert match, f"unparseable policy: {normalized!r}"
        body = match.group("body")
        policies.append(
            {
                "name": match.group("name").lower(),
                "table": match.group("table").lower(),
                "cmd": match.group("cmd").upper(),
                "role": match.group("role").lower(),
                "has_using": bool(re.search(r"\bUSING\b", body, re.IGNORECASE)),
                "has_check": bool(re.search(r"WITH\s+CHECK", body, re.IGNORECASE)),
                "body": body,
            }
        )
    return policies


def _membership_grants(statements):
    grants = set()
    pattern = re.compile(
        r"^GRANT\s+(stocknewsbr_\w+)\s+TO\s+(stocknewsbr_\w+)"
        r"(?:\s+WITH\s+.*)?$",
        re.IGNORECASE,
    )
    for statement in statements:
        match = pattern.match(_collapse(statement))
        if match:
            grants.add((match.group(1).lower(), match.group(2).lower()))
    return grants


class Mission36RolesRlsSqlTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = _read_text(ROLES_RLS_SQL_PATH)
        cls.sql = _strip_sql_comments(cls.raw)
        cls.collapsed = _collapse(cls.sql.upper())
        cls.statements = _split_statements(cls.sql)
        cls.policies = _parse_policies(cls.statements)

    def _role_attributes(self):
        attributes = {}
        for match in re.finditer(
            r"ALTER\s+ROLE\s+(stocknewsbr_\w+)\s+WITH\s+([^;]*)",
            self.sql,
            re.IGNORECASE,
        ):
            attributes[match.group(1).lower()] = set(match.group(2).upper().split())
        return attributes

    def test_all_six_roles_hardened(self):
        attributes = self._role_attributes()
        self.assertEqual(set(attributes), set(STOCKNEWSBR_ROLES))
        for role, tokens in attributes.items():
            for required in (
                "NOSUPERUSER",
                "NOCREATEDB",
                "NOCREATEROLE",
                "NOREPLICATION",
                "NOBYPASSRLS",
            ):
                self.assertIn(required, tokens, f"{role} missing {required}")

    def test_login_and_inherit_model(self):
        attributes = self._role_attributes()
        expected = {
            "stocknewsbr_owner": ("NOLOGIN", "NOINHERIT"),
            "stocknewsbr_app": ("LOGIN", "INHERIT"),
            "stocknewsbr_worker": ("LOGIN", "INHERIT"),
            "stocknewsbr_readonly": ("NOLOGIN", "INHERIT"),
            "stocknewsbr_backup": ("LOGIN", "INHERIT"),
            "stocknewsbr_migration": ("NOLOGIN", "NOINHERIT"),
        }
        for role, (login, inherit) in expected.items():
            self.assertIn(login, attributes[role])
            self.assertIn(inherit, attributes[role])

    def test_membership_is_migration_to_owner_only(self):
        self.assertEqual(
            _membership_grants(self.statements),
            {("stocknewsbr_owner", "stocknewsbr_migration")},
        )
        self.assertIn(
            "GRANT STOCKNEWSBR_OWNER TO STOCKNEWSBR_MIGRATION "
            "WITH ADMIN FALSE, INHERIT FALSE, SET TRUE",
            self.collapsed,
        )

    def test_no_appfacing_membership(self):
        for parent in ("stocknewsbr_owner", "stocknewsbr_migration"):
            for child in APP_FACING_ROLES:
                pattern = re.compile(rf"GRANT\s+{parent}\s+TO\s+{child}\b", re.IGNORECASE)
                self.assertIsNone(
                    pattern.search(self.sql),
                    f"{child} must not be a member of {parent}",
                )

    def test_application_roles_are_never_owner(self):
        for role in APP_FACING_ROLES:
            pattern = re.compile(rf"OWNER\s+TO\s+{role}\b", re.IGNORECASE)
            self.assertIsNone(pattern.search(self.sql), f"{role} must not own objects")

    def test_owner_owns_controlled_objects(self):
        for table in ("media_assets", "promo_redemptions", "promo_codes"):
            pattern = re.compile(
                rf"ALTER\s+TABLE\s+public\.{table}\s+OWNER\s+TO\s+stocknewsbr_owner",
                re.IGNORECASE,
            )
            self.assertIsNotNone(pattern.search(self.sql))

    def test_public_privileges_revoked(self):
        self.assertIn("REVOKE ALL ON SCHEMA PUBLIC FROM PUBLIC", self.collapsed)

    def test_owner_granted_schema_usage_without_create(self):
        # Gate 3.2B: the owner needs USAGE (foreign-key referential-integrity
        # checks run with the referenced table owner's privileges) but must
        # never receive CREATE or ALL on the schema.
        self.assertIn("GRANT USAGE ON SCHEMA PUBLIC TO STOCKNEWSBR_OWNER", self.collapsed)
        self.assertNotIn("GRANT CREATE ON SCHEMA PUBLIC TO STOCKNEWSBR_OWNER", self.collapsed)
        self.assertNotIn("GRANT ALL ON SCHEMA PUBLIC TO STOCKNEWSBR_OWNER", self.collapsed)
        self.assertNotIn("GRANT ALL PRIVILEGES ON SCHEMA PUBLIC TO STOCKNEWSBR_OWNER", self.collapsed)

    def test_migration_role_has_no_direct_schema_grant(self):
        # The migration role reaches objects via SET ROLE stocknewsbr_owner
        # (it is NOINHERIT and a member of owner), so no direct schema grant is
        # added to it.
        self.assertNotIn("ON SCHEMA PUBLIC TO STOCKNEWSBR_MIGRATION", self.collapsed)

    def test_rls_enabled_and_forced(self):
        for table in ("MEDIA_ASSETS", "PROMO_REDEMPTIONS"):
            self.assertIn(
                f"ALTER TABLE PUBLIC.{table} ENABLE ROW LEVEL SECURITY", self.collapsed
            )
            self.assertIn(
                f"ALTER TABLE PUBLIC.{table} FORCE ROW LEVEL SECURITY", self.collapsed
            )

    def test_media_assets_app_policies(self):
        app = {
            policy["cmd"]: policy
            for policy in self.policies
            if policy["table"] == "media_assets" and policy["role"] == "stocknewsbr_app"
        }
        self.assertEqual(set(app), {"SELECT", "INSERT", "UPDATE", "DELETE"})
        self.assertTrue(app["SELECT"]["has_using"])
        self.assertTrue(app["INSERT"]["has_check"])
        self.assertTrue(app["UPDATE"]["has_using"] and app["UPDATE"]["has_check"])
        self.assertTrue(app["DELETE"]["has_using"])

    def test_promo_redemptions_app_policies_are_select_insert_only(self):
        app = {
            policy["cmd"]: policy
            for policy in self.policies
            if policy["table"] == "promo_redemptions"
            and policy["role"] == "stocknewsbr_app"
        }
        self.assertEqual(set(app), {"SELECT", "INSERT"})
        self.assertTrue(app["SELECT"]["has_using"])
        self.assertTrue(app["INSERT"]["has_check"])

    def test_app_has_no_update_delete_on_promo_redemptions(self):
        self.assertNotIn("UPDATE ON PUBLIC.PROMO_REDEMPTIONS", self.collapsed)
        self.assertNotIn("DELETE ON PUBLIC.PROMO_REDEMPTIONS", self.collapsed)
        for policy in self.policies:
            if policy["table"] == "promo_redemptions" and policy["role"] == "stocknewsbr_app":
                self.assertNotIn(policy["cmd"], {"UPDATE", "DELETE"})

    def test_app_policies_deny_absent_context(self):
        app_policies = [
            policy
            for policy in self.policies
            if policy["role"] == "stocknewsbr_app"
            and policy["table"] in ("media_assets", "promo_redemptions")
        ]
        self.assertTrue(app_policies)
        for policy in app_policies:
            self.assertIn(RLS_CONTEXT_EXPRESSION, policy["body"].lower())

    def test_backup_policies_are_select_true_only(self):
        backup = [p for p in self.policies if p["role"] == "stocknewsbr_backup"]
        self.assertEqual(
            {p["table"] for p in backup}, {"media_assets", "promo_redemptions"}
        )
        for policy in backup:
            self.assertEqual(policy["cmd"], "SELECT")
            self.assertIn("using (true)", policy["body"].lower())

    def test_application_table_grants(self):
        self.assertIn(
            "GRANT SELECT, INSERT, UPDATE, DELETE ON PUBLIC.MEDIA_ASSETS TO STOCKNEWSBR_APP",
            self.collapsed,
        )
        self.assertIn(
            "GRANT SELECT, INSERT ON PUBLIC.PROMO_REDEMPTIONS TO STOCKNEWSBR_APP",
            self.collapsed,
        )
        self.assertIn(
            "GRANT SELECT ON PUBLIC.PROMO_CODES TO STOCKNEWSBR_APP",
            self.collapsed,
        )
        self.assertIn(
            "GRANT UPDATE (CURRENT_USES) ON PUBLIC.PROMO_CODES TO STOCKNEWSBR_APP",
            self.collapsed,
        )
        self.assertNotIn(
            "GRANT SELECT, UPDATE ON PUBLIC.PROMO_CODES TO STOCKNEWSBR_APP",
            self.collapsed,
        )

    def test_application_sequence_grants(self):
        self.assertIn(
            "GRANT USAGE, SELECT ON SEQUENCE PUBLIC.MEDIA_ASSETS_ID_SEQ TO STOCKNEWSBR_APP",
            self.collapsed,
        )
        self.assertIn(
            "GRANT USAGE, SELECT ON SEQUENCE PUBLIC.PROMO_REDEMPTIONS_ID_SEQ TO STOCKNEWSBR_APP",
            self.collapsed,
        )
        self.assertNotIn("PROMO_CODES_ID_SEQ TO STOCKNEWSBR_APP", self.collapsed)

    def test_backup_grants_are_select_only(self):
        self.assertIn(
            "GRANT SELECT ON PUBLIC.MEDIA_ASSETS TO STOCKNEWSBR_BACKUP", self.collapsed
        )
        self.assertIn(
            "GRANT SELECT ON PUBLIC.PROMO_REDEMPTIONS TO STOCKNEWSBR_BACKUP",
            self.collapsed,
        )
        for command in ("INSERT", "UPDATE", "DELETE", "TRUNCATE"):
            self.assertNotIn(
                f"{command} ON PUBLIC.MEDIA_ASSETS TO STOCKNEWSBR_BACKUP", self.collapsed
            )
            self.assertNotIn(
                    f"{command} ON PUBLIC.PROMO_REDEMPTIONS TO STOCKNEWSBR_BACKUP",
                    self.collapsed,
                )
        self.assertIn(
            "GRANT SELECT ON ALL TABLES IN SCHEMA PUBLIC TO STOCKNEWSBR_BACKUP",
            self.collapsed,
        )
        self.assertIn(
            "GRANT SELECT ON ALL SEQUENCES IN SCHEMA PUBLIC TO STOCKNEWSBR_BACKUP",
            self.collapsed,
        )
        self.assertIn(
            "REVOKE TEMPORARY ON DATABASE %I FROM PUBLIC, STOCKNEWSBR_BACKUP",
            self.collapsed,
        )
        self.assertIn("REVOKE ALL PRIVILEGES (%S) ON TABLE PUBLIC.%I", self.collapsed)

    def test_no_broad_or_bypass_grants(self):
        self.assertNotIn("GRANT ALL", self.collapsed)
        for role in ("STOCKNEWSBR_APP", "STOCKNEWSBR_WORKER", "STOCKNEWSBR_READONLY"):
            self.assertNotIn(f"ON ALL TABLES IN SCHEMA PUBLIC TO {role}", self.collapsed)
            self.assertNotIn(f"ON ALL SEQUENCES IN SCHEMA PUBLIC TO {role}", self.collapsed)
        # Every BYPASSRLS token is the negated form NOBYPASSRLS.
        self.assertEqual(
            self.collapsed.count("BYPASSRLS"), self.collapsed.count("NOBYPASSRLS")
        )
        # Every SUPERUSER token is the negated form NOSUPERUSER.
        self.assertEqual(
            self.collapsed.count("SUPERUSER"), self.collapsed.count("NOSUPERUSER")
        )

    def test_no_credentials_in_sql(self):
        self.assertNotIn("PASSWORD", self.collapsed)
        self.assertNotIn("IDENTIFIED BY", self.collapsed)
        self.assertNotIn("://", self.sql)

    def test_script_is_wrapped_in_single_transaction(self):
        uppers = [statement.upper() for statement in self.statements]
        self.assertEqual(uppers[0], "BEGIN", "script must open with a top-level BEGIN;")
        self.assertEqual(uppers[-1], "COMMIT", "script must close with COMMIT;")
        # Exactly one top-level transaction; no intermediate COMMIT/autocommit.
        self.assertEqual(uppers.count("BEGIN"), 1)
        self.assertEqual(uppers.count("COMMIT"), 1)
        # The BEGIN inside the DO block is PL/pgSQL, not a standalone
        # statement, so it is never counted as a transaction control BEGIN.
        do_statements = [statement for statement in uppers if statement.startswith("DO")]
        self.assertTrue(do_statements)
        self.assertTrue(any("BEGIN" in statement for statement in do_statements))

    def test_default_privileges_revoke_public_for_all_object_classes(self):
        for expected in (
            "ALTER DEFAULT PRIVILEGES FOR ROLE STOCKNEWSBR_OWNER IN SCHEMA PUBLIC "
            "REVOKE ALL ON TABLES FROM PUBLIC",
            "ALTER DEFAULT PRIVILEGES FOR ROLE STOCKNEWSBR_OWNER IN SCHEMA PUBLIC "
            "REVOKE ALL ON SEQUENCES FROM PUBLIC",
            "ALTER DEFAULT PRIVILEGES FOR ROLE STOCKNEWSBR_OWNER "
            "REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC",
            "ALTER DEFAULT PRIVILEGES FOR ROLE STOCKNEWSBR_OWNER "
            "REVOKE USAGE ON TYPES FROM PUBLIC",
        ):
            self.assertIn(expected, self.collapsed)

    def test_owner_admin_policies_exist(self):
        owner = {
            policy["table"]: policy
            for policy in self.policies
            if policy["role"] == "stocknewsbr_owner"
        }
        self.assertEqual(set(owner), {"media_assets", "promo_redemptions"})
        for policy in owner.values():
            self.assertEqual(policy["cmd"], "ALL")
            self.assertTrue(policy["has_using"])
            self.assertTrue(policy["has_check"])
            self.assertIn("using (true)", policy["body"].lower())
            self.assertIn("with check (true)", policy["body"].lower())

    def test_admin_true_policies_are_owner_only(self):
        # Any FOR ALL / USING(true) / WITH CHECK(true) policy must target the
        # owner role only — never an application-facing role.
        for policy in self.policies:
            body = policy["body"].lower()
            is_admin = (
                policy["cmd"] == "ALL"
                and "using (true)" in body
                and "with check (true)" in body
            )
            if is_admin:
                self.assertEqual(policy["role"], "stocknewsbr_owner")
        for policy in self.policies:
            if policy["role"] in APP_FACING_ROLES:
                self.assertNotEqual(policy["cmd"], "ALL")

    def test_force_rls_preserved_alongside_owner_policy(self):
        # The owner policy must coexist with FORCE RLS, not replace it.
        for table in ("MEDIA_ASSETS", "PROMO_REDEMPTIONS"):
            self.assertIn(
                f"ALTER TABLE PUBLIC.{table} FORCE ROW LEVEL SECURITY", self.collapsed
            )
        owner_attributes = self._role_attributes()["stocknewsbr_owner"]
        self.assertIn("NOBYPASSRLS", owner_attributes)


class Mission36VerifyScriptTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = _read_text(VERIFY_SQL_PATH)
        cls.sql = _strip_sql_comments(cls.raw)
        cls.collapsed = _collapse(cls.sql.upper())
        cls.statements = _split_statements(cls.sql)

    def test_only_select_statements(self):
        self.assertTrue(self.statements)
        for statement in self.statements:
            head = statement.lstrip().split(None, 1)[0].upper()
            self.assertEqual(head, "SELECT", f"non-SELECT statement: {statement[:60]!r}")

    def test_no_mutating_constructs(self):
        for forbidden in (
            "CREATE ROLE",
            "ALTER ROLE",
            "DROP ",
            "TRUNCATE ",
            "DELETE FROM",
            "INSERT INTO",
            "GRANT ",
            "REVOKE ",
        ):
            self.assertNotIn(forbidden, self.collapsed)

    def test_checks_key_invariants(self):
        for needle in (
            "ROLSUPER",
            "ROLBYPASSRLS",
            "ROLREPLICATION",
            "RELFORCEROWSECURITY",
            "PG_POLICIES",
            "HAS_TABLE_PRIVILEGE",
            "HAS_COLUMN_PRIVILEGE",
            "HAS_SEQUENCE_PRIVILEGE",
            "PROMO_REDEMPTIONS",
        ):
            self.assertIn(needle, self.collapsed)

    def test_verify_checks_owner_schema_usage_via_catalog(self):
        # Gate 3.2B: verify.sql must probe the LIVE catalog for the owner's
        # schema privileges (USAGE granted, CREATE absent) — not just parse text.
        self.assertIn("OWNER_SCHEMA_USAGE_WITHOUT_CREATE", self.collapsed)
        self.assertIn(
            "HAS_SCHEMA_PRIVILEGE('STOCKNEWSBR_OWNER', 'PUBLIC', 'USAGE')", self.collapsed
        )
        self.assertIn(
            "HAS_SCHEMA_PRIVILEGE('STOCKNEWSBR_OWNER', 'PUBLIC', 'CREATE')", self.collapsed
        )
        self.assertIn("'CREATE') = FALSE", self.collapsed)

    def test_verify_fails_closed_on_missing_or_unexpected_catalog_rows(self):
        self.assertIn("WHERE ROLNAME LIKE 'STOCKNEWSBR\\_%'", self.collapsed)
        self.assertIn("ELSE FALSE", self.collapsed)
        self.assertIn("COUNT(*) = 3", self.collapsed)
        self.assertIn("COUNT(*) = 2", self.collapsed)
        self.assertGreaterEqual(self.collapsed.count("ARRAY[]::TEXT[]"), 2)
        self.assertGreaterEqual(self.collapsed.count("COALESCE("), 5)
        self.assertIn("BACKUP_ALL_CURRENT_TABLES_READ_ONLY", self.collapsed)
        self.assertIn("APP_POLICIES_USE_EXACT_RLS_CONTEXT", self.collapsed)
        self.assertIn("COUNT(*) = 1", self.collapsed)
        self.assertIn("NOT MEMBERSHIP.ADMIN_OPTION", self.collapsed)
        self.assertIn("DEFAULT_PRIVILEGES_NO_PUBLIC_FUNCTION_OR_TYPE_ACCESS", self.collapsed)
        self.assertIn("DEFACLNAMESPACE = 0", self.collapsed)
        self.assertIn("DEFACLOBJTYPE IN ('F', 'T')", self.collapsed)


class Mission36PgAuditVerifyScriptTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sql = _strip_sql_comments(_read_text(PGAUDIT_VERIFY_SQL_PATH))
        cls.statements = _split_statements(cls.sql)
        cls.collapsed = _collapse(cls.sql.upper())

    def test_script_is_strictly_read_only(self):
        self.assertTrue(self.statements)
        for statement in self.statements:
            self.assertEqual(statement.lstrip().split(None, 1)[0].upper(), "SELECT")

    def test_missing_app_role_returns_false_not_null(self):
        self.assertIn("COUNT(*) = 1", self.collapsed)
        self.assertIn(
            "COALESCE(BOOL_AND(NOT ROLSUPER AND NOT ROLBYPASSRLS), FALSE)",
            self.collapsed,
        )

    def test_preload_and_audit_classes_are_tokenized_not_substring_matched(self):
        self.assertIn("'PGAUDIT' = ANY", self.collapsed)
        self.assertIn("STRING_TO_ARRAY", self.collapsed)
        self.assertIn("CARDINALITY", self.collapsed)
        self.assertNotIn("LIKE '%PGAUDIT%'", self.collapsed)


class Mission36VerifyOwnerPolicyCheckTests(unittest.TestCase):
    """The verify script must positively assert the owner admin policies."""

    @classmethod
    def setUpClass(cls):
        cls.statements = _split_statements(_strip_sql_comments(_read_text(VERIFY_SQL_PATH)))
        owner_checks = [s for s in cls.statements if "owner_admin" in s.lower()]
        assert len(owner_checks) == 1, (
            f"expected exactly one owner-policy check, got {len(owner_checks)}"
        )
        cls.check = _collapse(owner_checks[0])
        cls.lower = cls.check.lower()

    def test_check_is_a_read_only_select(self):
        self.assertEqual(self.check.split(None, 1)[0].upper(), "SELECT")

    def test_covers_both_policies_and_tables(self):
        for token in (
            "media_assets_owner_admin",
            "promo_redemptions_owner_admin",
            "media_assets",
            "promo_redemptions",
        ):
            self.assertIn(token, self.lower)

    def test_requires_owner_role_exclusively(self):
        # Exact role-array equality proves exclusivity; no app/worker/
        # readonly/backup role may appear in the owner-policy check.
        self.assertRegex(self.lower, r"roles\s*=\s*array\['stocknewsbr_owner'\]")
        for forbidden in (
            "stocknewsbr_app",
            "stocknewsbr_worker",
            "stocknewsbr_readonly",
            "stocknewsbr_backup",
        ):
            self.assertNotIn(forbidden, self.lower)

    def test_requires_all_command_and_true_clauses(self):
        self.assertRegex(self.lower, r"cmd\s*=\s*'all'")
        self.assertIn("qual", self.lower)
        self.assertIn("with_check", self.lower)
        # Both USING and WITH CHECK are normalized and compared to 'true'.
        self.assertGreaterEqual(self.lower.count("'true'"), 2)

    def test_expects_exactly_two_valid_policies(self):
        self.assertRegex(self.lower, r"count\(\*\)\s*=\s*2")


class Mission36RlsRouteIntegrationTests(unittest.TestCase):
    """Gate 3.3: prove the RLS context is bound to the authenticated user, on the
    SAME Session as auth, with an active transaction, BEFORE any protected query.

    apply_rls_context is a no-op on SQLite, so these tests never rely on the SQL
    itself: they use a real FastAPI request (so FastAPI's per-callable dependency
    caching genuinely shares one Session between auth and the endpoint) plus
    spies that record Session identity, in_transaction() and call order.
    """

    def _sqlite_app(self, router):
        from fastapi import FastAPI
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from sqlalchemy.pool import StaticPool

        from app.database import Base, clear_rls_context, get_db

        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(engine)
        test_session = sessionmaker(bind=engine, autoflush=False)

        def override_get_db():
            db = test_session()
            try:
                yield db
            finally:
                clear_rls_context(db)
                db.close()

        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[get_db] = override_get_db
        return app

    def _auth_override(self, user_id):
        from fastapi import Depends

        from app.database import get_db
        from app.models import User

        def _dependency(db=Depends(get_db)):
            # Represent the real auth/plan DB access on the SHARED Session so a
            # transaction is naturally active — no artificial query in the route.
            db.query(User).first()
            return SimpleNamespace(id=user_id, is_active=True)

        return _dependency

    def _client(self, app):
        from fastapi.testclient import TestClient

        return TestClient(app, raise_server_exceptions=False)

    # ----- media -----

    def test_media_read_binds_context_before_query_same_session_in_tx(self):
        from app.api import routes_media
        from app.dependencies import require_active_plan

        app = self._sqlite_app(routes_media.router)
        app.dependency_overrides[require_active_plan] = self._auth_override(7)
        events = []

        def spy(db, **kwargs):
            events.append(("rls", id(db), db.in_transaction(), kwargs.get("current_user_id")))

        def record(db, asset_id):
            events.append(("query", id(db)))
            return SimpleNamespace(id=asset_id, owner_user_id=7)

        with (
            patch.object(routes_media, "apply_rls_context", side_effect=spy),
            patch.object(routes_media, "get_media_asset", side_effect=record),
            patch.object(routes_media, "serialize_media_asset", side_effect=lambda a: {"id": a.id}),
        ):
            response = self._client(app).get("/api/media/5")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(events[0][0], "rls")
        self.assertTrue(events[0][2])           # transaction active at apply
        self.assertEqual(events[0][3], 7)       # id comes ONLY from the auth user
        self.assertEqual(events[1][0], "query")
        self.assertEqual(events[0][1], events[1][1])  # same Session instance

    def test_media_upload_binds_context_before_create(self):
        from unittest.mock import AsyncMock

        from app.api import routes_media
        from app.dependencies import require_active_plan

        app = self._sqlite_app(routes_media.router)
        app.dependency_overrides[require_active_plan] = self._auth_override(7)
        events = []
        payload = {
            "provider": "local",
            "folder": "posts",
            "filename": "x.png",
            "content_type": "image/png",
            "size_bytes": 4,
            "url": "/media/posts/x.png",
        }

        def spy(db, **kwargs):
            events.append(("rls", id(db), db.in_transaction()))

        def record(db, **kwargs):
            events.append(("query", id(db)))
            return SimpleNamespace(id=1)

        with (
            patch.object(routes_media, "save_upload", new=AsyncMock(return_value=payload)),
            patch.object(routes_media, "apply_rls_context", side_effect=spy),
            patch.object(routes_media, "create_media_asset", side_effect=record),
            patch.object(routes_media, "serialize_media_asset", side_effect=lambda a: {"id": a.id}),
        ):
            response = self._client(app).post(
                "/api/media/upload", files={"file": ("x.png", b"data", "image/png")}
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(events[0][0], "rls")
        self.assertTrue(events[0][2])
        self.assertEqual(events[1][0], "query")
        self.assertEqual(events[0][1], events[1][1])

    def test_media_presign_binds_context_before_create(self):
        from app.api import routes_media
        from app.dependencies import require_active_plan

        app = self._sqlite_app(routes_media.router)
        app.dependency_overrides[require_active_plan] = self._auth_override(7)
        events = []

        def spy(db, **kwargs):
            events.append(("rls", id(db), db.in_transaction()))

        def record(db, **kwargs):
            events.append(("query", id(db)))
            return SimpleNamespace(id=2)

        with (
            patch.object(
                routes_media,
                "get_signed_upload",
                side_effect=lambda **kw: {"key": "posts/x.png", "provider": "local", "public_url": "/media/posts/x.png"},
            ),
            patch.object(routes_media, "apply_rls_context", side_effect=spy),
            patch.object(routes_media, "create_media_asset", side_effect=record),
            patch.object(routes_media, "serialize_media_asset", side_effect=lambda a: {"id": a.id}),
        ):
            response = self._client(app).post(
                "/api/media/presign", json={"content_type": "image/png", "folder": "posts"}
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(events[0][0], "rls")
        self.assertTrue(events[0][2])
        self.assertEqual(events[1][0], "query")
        self.assertEqual(events[0][1], events[1][1])

    def test_media_context_failure_blocks_protected_query(self):
        from app.api import routes_media
        from app.dependencies import require_active_plan

        app = self._sqlite_app(routes_media.router)
        app.dependency_overrides[require_active_plan] = self._auth_override(7)
        events = []

        def boom(db, **kwargs):
            events.append(("rls", id(db)))
            raise RuntimeError("RLS_CONTEXT_FAIL")

        def record(db, asset_id):
            events.append(("query", id(db)))
            return SimpleNamespace(id=asset_id, owner_user_id=7)

        with (
            patch.object(routes_media, "apply_rls_context", side_effect=boom),
            patch.object(routes_media, "get_media_asset", side_effect=record),
        ):
            response = self._client(app).get("/api/media/5")

        self.assertNotEqual(response.status_code, 200)  # fail closed, not success
        self.assertEqual([event[0] for event in events], ["rls"])  # query never ran

    # ----- promo -----

    def test_promo_router_uses_canonical_get_db(self):
        from app.api import promo_router
        from app import database

        self.assertIs(promo_router.get_db, database.get_db)
        self.assertFalse(hasattr(promo_router, "SessionLocal"))

    def test_promo_redeem_binds_context_before_query_same_session_in_tx(self):
        from app.api import promo_router
        from app.security import get_current_user

        app = self._sqlite_app(promo_router.router)
        app.dependency_overrides[get_current_user] = self._auth_override(9)
        events = []

        def spy(db, **kwargs):
            events.append(("rls", id(db), db.in_transaction(), kwargs.get("current_user_id")))

        def record(db, user_id, code):
            events.append(("query", id(db)))
            return {"status": "success", "code": code}

        with (
            patch.object(promo_router, "apply_rls_context", side_effect=spy),
            patch.object(promo_router, "redeem_promo_code", side_effect=record),
        ):
            response = self._client(app).post("/promo/redeem", params={"code": "ABC"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(events[0][0], "rls")
        self.assertTrue(events[0][2])
        self.assertEqual(events[0][3], 9)
        self.assertEqual(events[1][0], "query")
        self.assertEqual(events[0][1], events[1][1])

    def test_promo_context_failure_blocks_redeem(self):
        from app.api import promo_router
        from app.security import get_current_user

        app = self._sqlite_app(promo_router.router)
        app.dependency_overrides[get_current_user] = self._auth_override(9)
        events = []

        def boom(db, **kwargs):
            events.append(("rls", id(db)))
            raise RuntimeError("RLS_CONTEXT_FAIL")

        def record(db, user_id, code):
            events.append(("query", id(db)))
            return {"status": "success"}

        with (
            patch.object(promo_router, "apply_rls_context", side_effect=boom),
            patch.object(promo_router, "redeem_promo_code", side_effect=record),
        ):
            response = self._client(app).post("/promo/redeem", params={"code": "ABC"})

        self.assertNotEqual(response.status_code, 200)
        self.assertEqual([event[0] for event in events], ["rls"])  # redeem never ran


# =====================================================================
# GATE 4 — permanent, opt-in proof against a REAL local PostgreSQL.
#
# Skipped unless DATABASE_URL_TEST_POSTGRES points at a disposable,
# user-space cluster on 127.0.0.1 that has ALREADY been prepared by the
# Mission 36 SQL artifacts (roles + RLS + FORCE RLS + policies). The test
# is autonomous: it seeds and removes ONLY its own high-range synthetic
# fixtures, uses real psycopg2 / SQLAlchemy connections (never mocks the
# database), and refuses any non-local or 18/main DSN. It never prints the
# DSN or any password.
# =====================================================================

from sqlalchemy.engine import make_url  # noqa: E402

_PG_ENV_VAR = "DATABASE_URL_TEST_POSTGRES"
_PG_SKIP_REASON = "DATABASE_URL_TEST_POSTGRES não configurada"
_PG_DISPOSABLE_DATABASE = "stocknewsbr_m36_gate5"
_PG_DISPOSABLE_PORT = 55432
_PG_SENTINEL_TABLE = "mission36_disposable_cluster_sentinel"
_PG_SENTINEL_PURPOSE = "gate5"
_PG_SENTINEL_MARKER = "stocknewsbr-m36-gate5-disposable-v1"

# Synthetic fixtures owned exclusively by THIS test (cleaned up in tearDownClass).
_PG_UA = 900001
_PG_UB = 900002
_PG_PROMO_ID = 900500
_PG_PROMO_CODE = "M36PERMCODE"


def _validate_local_test_dsn(
    dsn,
    *,
    expected_database=_PG_DISPOSABLE_DATABASE,
    expected_port=_PG_DISPOSABLE_PORT,
    expected_purpose=_PG_SENTINEL_PURPOSE,
    expected_marker=_PG_SENTINEL_MARKER,
):
    """Refuse anything that is not an explicit local disposable cluster.

    Guards against ever pointing the suite at a remote/cloud database or at the
    system 18/main cluster. Only the host/port are inspected in error messages —
    never the password.
    """
    try:
        url = make_url(dsn)
        host = url.host or ""
        port = url.port
    except Exception:
        raise ValueError("UNSAFE_TEST_DSN: malformed PostgreSQL URL") from None
    problems = []
    remote_markers = (
        "render.com", "neon.tech", "supabase", "railway",
        "rds.amazonaws", "amazonaws", "cloud.google", "azure", "gcp",
    )
    if any(marker in host.lower() for marker in remote_markers):
        problems.append("remote/cloud host marker")
    if host == "localhost":
        problems.append("host is 'localhost'; require literal 127.0.0.1")
    if host != "127.0.0.1":
        problems.append("host must be literal 127.0.0.1")
    if url.get_backend_name() != "postgresql":
        problems.append("backend must be PostgreSQL")
    if port is None:
        problems.append("port must be explicit")
    if port == 5432:
        problems.append("port 5432 is the system 18/main cluster")
    if port != expected_port:
        problems.append("port does not match the authorized disposable cluster")
    if url.database != expected_database:
        problems.append("database does not match the authorized disposable database")
    if problems:
        raise ValueError("UNSAFE_TEST_DSN: " + "; ".join(problems))

    import psycopg2

    try:
        with psycopg2.connect(
            host=host,
            port=port,
            dbname=url.database,
            user=url.username,
            password=url.password,
        ) as connection:
            with connection.cursor() as cursor:
                cursor.execute("SHOW data_directory")
                data_directory = str(cursor.fetchone()[0])
                cursor.execute(
                    "SELECT marker FROM public.mission36_disposable_cluster_sentinel "
                    "WHERE purpose = %s",
                    (expected_purpose,),
                )
                row = cursor.fetchone()
    except psycopg2.Error:
        raise ValueError("UNSAFE_TEST_DSN: disposable sentinel unavailable") from None

    if data_directory.startswith("/var/lib/postgresql"):
        raise ValueError("UNSAFE_TEST_DSN: system PostgreSQL data directory")
    if not row or row[0] != expected_marker:
        raise ValueError("UNSAFE_TEST_DSN: disposable sentinel mismatch")
    return url


class Mission36TestDsnGuardTests(unittest.TestCase):
    def _connection(self, *, data_directory="/home/dcima/disposable", marker=_PG_SENTINEL_MARKER):
        cursor = MagicMock()
        cursor.__enter__.return_value = cursor
        cursor.fetchone.side_effect = [(data_directory,), (marker,) if marker is not None else None]
        connection = MagicMock()
        connection.__enter__.return_value = connection
        connection.cursor.return_value = cursor
        return connection

    def test_guard_requires_exact_database_port_and_precreated_sentinel(self):
        dsn = (
            "postgresql+psycopg2://m36-user:m36-secret-value@"
            "127.0.0.1:55432/stocknewsbr_m36_gate5"
        )
        with patch("psycopg2.connect", return_value=self._connection()) as connect:
            url = _validate_local_test_dsn(dsn)
        self.assertEqual(url.database, _PG_DISPOSABLE_DATABASE)
        connect.assert_called_once()

    def test_guard_rejects_other_local_database_before_connecting(self):
        dsn = "postgresql://m36-user:m36-secret-value@127.0.0.1:55432/other_local_db"
        with patch("psycopg2.connect") as connect:
            with self.assertRaisesRegex(ValueError, "^UNSAFE_TEST_DSN"):
                _validate_local_test_dsn(dsn)
        connect.assert_not_called()

    def test_guard_rejects_missing_wrong_or_system_sentinel(self):
        dsn = (
            "postgresql://m36-user:m36-secret-value@"
            "127.0.0.1:55432/stocknewsbr_m36_gate5"
        )
        connections = (
            self._connection(marker=None),
            self._connection(marker="wrong-marker"),
            self._connection(data_directory="/var/lib/postgresql/18/main"),
        )
        for connection in connections:
            with self.subTest(connection=connection):
                with patch("psycopg2.connect", return_value=connection):
                    with self.assertRaisesRegex(ValueError, "^UNSAFE_TEST_DSN") as context:
                        _validate_local_test_dsn(dsn)
                rendered = str(context.exception)
                self.assertNotIn(dsn, rendered)
                self.assertNotIn("m36-user", rendered)
                self.assertNotIn("m36-secret-value", rendered)
                self.assertNotIn("stocknewsbr_m36_gate5", rendered)


@unittest.skipUnless(os.environ.get(_PG_ENV_VAR), _PG_SKIP_REASON)
class Mission36RealPostgresRlsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import secrets

        import psycopg2

        cls.psycopg2 = psycopg2
        cls.url = _validate_local_test_dsn(os.environ[_PG_ENV_VAR])
        cls.host = cls.url.host
        cls.port = cls.url.port
        cls.dbname = cls.url.database
        cls._super_kwargs = dict(
            host=cls.host, port=cls.port, dbname=cls.dbname,
            user=cls.url.username, password=cls.url.password,
        )
        # Disposable password for the app LOGIN role, generated by THIS test so
        # the suite never needs an out-of-band credential file.
        cls.app_pw = secrets.token_hex(24)
        with cls._superconn() as conn:
            conn.autocommit = True
            with conn.cursor() as cur:
                # Never let pgAudit (if loaded) record the plaintext password: the
                # namespaced GUC is a harmless placeholder when pgAudit is absent.
                cur.execute("SET pgaudit.log = 'none'")
                cur.execute("ALTER ROLE stocknewsbr_app WITH PASSWORD %s", (cls.app_pw,))
                for uid, tag in ((_PG_UA, "perma"), (_PG_UB, "permb")):
                    cur.execute(
                        "INSERT INTO users (id,email,password_hash,referral_code,role,"
                        "official,is_bot,official_identity_locked,is_active,created_at) "
                        "VALUES (%s,%s,'x',%s,'user',false,false,false,true,now()) "
                        "ON CONFLICT (id) DO NOTHING",
                        (uid, f"{tag}@m36perm.invalid", f"M36PERMREF{uid}"),
                    )
                cur.execute(
                    "INSERT INTO promo_codes (id,code,current_uses,created_at) "
                    "VALUES (%s,%s,0,now()) ON CONFLICT (id) DO NOTHING",
                    (_PG_PROMO_ID, _PG_PROMO_CODE),
                )

    @classmethod
    def tearDownClass(cls):
        # Remove ONLY this test's synthetic fixtures (superuser bypasses RLS).
        try:
            with cls._superconn() as conn:
                conn.autocommit = True
                with conn.cursor() as cur:
                    cur.execute("DELETE FROM promo_redemptions WHERE user_id IN (%s,%s)", (_PG_UA, _PG_UB))
                    cur.execute("DELETE FROM media_assets WHERE owner_user_id IN (%s,%s)", (_PG_UA, _PG_UB))
                    cur.execute("DELETE FROM promo_codes WHERE id = %s", (_PG_PROMO_ID,))
                    cur.execute("DELETE FROM users WHERE id IN (%s,%s)", (_PG_UA, _PG_UB))
        except Exception:
            pass

    @classmethod
    def _superconn(cls):
        # Catch-and-sanitize: a failed connect must never surface the DSN or
        # password (psycopg2's connect frame would otherwise print both).
        try:
            return cls.psycopg2.connect(**cls._super_kwargs)
        except cls.psycopg2.Error:
            raise RuntimeError(
                "Não foi possível conectar ao PostgreSQL local de teste (superuser; credenciais omitidas)."
            ) from None

    def _appconn(self):
        try:
            conn = self.psycopg2.connect(
                host=self.host, port=self.port, dbname=self.dbname,
                user="stocknewsbr_app", password=self.app_pw,
            )
        except self.psycopg2.Error:
            raise RuntimeError(
                "Não foi possível conectar ao PostgreSQL local de teste (app role; credenciais omitidas)."
            ) from None
        conn.autocommit = False
        return conn

    @staticmethod
    def _set_ctx(cur, uid):
        cur.execute("SELECT set_config('app.current_user_id', %s, true)", (str(uid),))

    # ---- DSN safety (reject remote / localhost / 5432) ----
    def test_dsn_is_local_and_not_production(self):
        self.assertEqual(self.host, "127.0.0.1")
        self.assertIsNotNone(self.port)
        self.assertNotEqual(self.port, 5432)
        for unsafe in (
            "postgresql://u:p@db.render.com:5432/x",
            "postgresql://u:p@localhost:55432/x",
            "postgresql://u:p@127.0.0.1:5432/x",
            "postgresql://u:p@10.0.0.5:55432/x",
        ):
            with self.subTest(unsafe=unsafe):
                with self.assertRaises(ValueError):
                    _validate_local_test_dsn(unsafe)

    # ---- server identity: real PostgreSQL, user-space (not 18/main) ----
    def test_server_is_postgres_userspace_cluster(self):
        with self._superconn() as conn, conn.cursor() as cur:
            cur.execute("SHOW server_version")
            version = cur.fetchone()[0]
            cur.execute("SHOW data_directory")
            data_dir = cur.fetchone()[0]
        self.assertTrue(version)
        self.assertNotEqual(data_dir, "/var/lib/postgresql/18/main")
        self.assertFalse(
            data_dir.startswith("/var/lib/postgresql"),
            "must be a user-space cluster, not a system one",
        )

    # ---- owner schema privileges: USAGE granted, CREATE absent (Gate 3.2B) ----
    def test_owner_has_usage_without_create_on_schema(self):
        with self._superconn() as conn, conn.cursor() as cur:
            cur.execute("SELECT has_schema_privilege('stocknewsbr_owner','public','USAGE')")
            usage = cur.fetchone()[0]
            cur.execute("SELECT has_schema_privilege('stocknewsbr_owner','public','CREATE')")
            create = cur.fetchone()[0]
        self.assertTrue(usage, "owner must hold USAGE (FK RI checks run as referenced owner)")
        self.assertFalse(create, "owner must NOT hold CREATE on public")

    # ---- app role hardened ----
    def test_app_role_is_hardened(self):
        with self._superconn() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT rolsuper, rolbypassrls, rolcreatedb, rolcreaterole, "
                "rolreplication, rolcanlogin "
                "FROM pg_roles WHERE rolname='stocknewsbr_app'"
            )
            (
                rolsuper,
                rolbypassrls,
                rolcreatedb,
                rolcreaterole,
                rolreplication,
                rolcanlogin,
            ) = cur.fetchone()
        self.assertFalse(rolsuper)
        self.assertFalse(rolbypassrls)
        self.assertFalse(rolcreatedb)
        self.assertFalse(rolcreaterole)
        self.assertFalse(rolreplication)
        self.assertTrue(rolcanlogin)

    def test_role_script_removes_replication_admin_and_external_membership_drift(self):
        roles_sql = _read_text(ROLES_RLS_SQL_PATH)
        connection = self._superconn()
        connection.autocommit = True
        try:
            with connection.cursor() as cur:
                cur.execute("DROP ROLE IF EXISTS mission36_membership_probe")
                cur.execute("CREATE ROLE mission36_membership_probe NOLOGIN")
                cur.execute("ALTER ROLE stocknewsbr_app WITH REPLICATION")
                cur.execute(
                    "GRANT UPDATE (free_year) ON public.promo_codes "
                    "TO stocknewsbr_app"
                )
                cur.execute(
                    "GRANT TEMPORARY ON DATABASE stocknewsbr_m36_gate5 "
                    "TO stocknewsbr_backup"
                )
                cur.execute(
                    "GRANT mission36_membership_probe TO stocknewsbr_app "
                    "WITH ADMIN OPTION"
                )
                cur.execute(roles_sql)
                cur.execute(
                    "SELECT rolreplication FROM pg_roles "
                    "WHERE rolname='stocknewsbr_app'"
                )
                self.assertFalse(cur.fetchone()[0])
                cur.execute(
                    "SELECT has_column_privilege("
                    "'stocknewsbr_app','public.promo_codes','free_year','UPDATE'), "
                    "has_database_privilege("
                    "'stocknewsbr_backup',current_database(),'TEMPORARY')"
                )
                self.assertEqual(cur.fetchone(), (False, False))
                cur.execute(
                    "SELECT parent.rolname,child.rolname,membership.admin_option,"
                    "membership.inherit_option,membership.set_option "
                    "FROM pg_auth_members membership "
                    "JOIN pg_roles parent ON parent.oid=membership.roleid "
                    "JOIN pg_roles child ON child.oid=membership.member "
                    "WHERE parent.rolname LIKE 'stocknewsbr\\_%' "
                    "OR child.rolname LIKE 'stocknewsbr\\_%'"
                )
                self.assertEqual(
                    cur.fetchall(),
                    [
                        (
                            "stocknewsbr_owner",
                            "stocknewsbr_migration",
                            False,
                            False,
                            True,
                        )
                    ],
                )
                cur.execute("DROP ROLE mission36_membership_probe")
        finally:
            connection.close()

    def test_app_promo_update_is_limited_to_current_uses(self):
        with self._superconn() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT has_table_privilege("
                "'stocknewsbr_app','public.promo_codes','UPDATE'), "
                "has_column_privilege("
                "'stocknewsbr_app','public.promo_codes','current_uses','UPDATE'), "
                "has_column_privilege("
                "'stocknewsbr_app','public.promo_codes','free_year','UPDATE')"
            )
            self.assertEqual(cur.fetchone(), (False, True, False))

    # ---- RLS enabled AND forced ----
    def test_rls_enabled_and_forced_on_controlled_tables(self):
        with self._superconn() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT relname, relrowsecurity, relforcerowsecurity FROM pg_class "
                "WHERE relnamespace='public'::regnamespace "
                "AND relname IN ('media_assets','promo_redemptions') ORDER BY relname"
            )
            rows = cur.fetchall()
        self.assertEqual(len(rows), 2)
        for _, enabled, forced in rows:
            self.assertTrue(enabled)
            self.assertTrue(forced)

    # ---- policies carry the exact fail-closed USING / WITH CHECK expressions ----
    def test_app_policies_have_exact_using_and_with_check(self):
        with self._superconn() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT tablename,policyname,cmd,roles,qual,with_check "
                "FROM pg_policies WHERE schemaname='public' "
                "AND tablename IN ('media_assets','promo_redemptions') "
                "AND 'stocknewsbr_app' = ANY(roles)"
            )
            actual = {
                (table_name, policy_name): (cmd, tuple(roles), qual, check)
                for table_name, policy_name, cmd, roles, qual, check in cur.fetchall()
            }
        expected_keys = {
            (table_name, policy_name)
            for table_name, policies in database_schema.REQUIRED_PRODUCTION_RLS_POLICIES.items()
            for policy_name, policy in policies.items()
            if policy[0] == "stocknewsbr_app"
        }
        self.assertEqual(set(actual), expected_keys)
        for table_name, policy_name in expected_keys:
            role, expected_cmd, require_using, require_check, expression_kind = (
                database_schema.REQUIRED_PRODUCTION_RLS_POLICIES[table_name][policy_name]
            )
            cmd, roles, qual, check = actual[(table_name, policy_name)]
            expected_expression = database_schema._normalized_policy_expression(
                f"{expression_kind}=nullif("
                "current_setting('app.current_user_id',true),'')::integer"
            )
            self.assertEqual(cmd, expected_cmd)
            self.assertEqual(roles, (role,))
            self.assertEqual(
                database_schema._normalized_policy_expression(qual),
                expected_expression if require_using else "",
            )
            self.assertEqual(
                database_schema._normalized_policy_expression(check),
                expected_expression if require_check else "",
            )

    # ---- media isolation A/B + spoofing + context absence (as the app role) ----
    def test_media_isolation_spoofing_and_context_absence(self):
        for uid, fname in ((_PG_UA, "perm_a.png"), (_PG_UB, "perm_b.png")):
            conn = self._appconn()
            try:
                cur = conn.cursor()
                self._set_ctx(cur, uid)
                cur.execute(
                    "INSERT INTO media_assets (owner_user_id,provider,folder,filename,status,created_at) "
                    "VALUES (%s,'local','posts',%s,'uploaded',now())", (uid, fname))
                conn.commit()
            finally:
                conn.close()

        conn = self._appconn()
        try:
            cur = conn.cursor()
            self._set_ctx(cur, _PG_UA)
            cur.execute("SELECT count(*) FROM media_assets")
            total_a = cur.fetchone()[0]
            cur.execute("SELECT count(*) FROM media_assets WHERE owner_user_id <> %s", (_PG_UA,))
            foreign_a = cur.fetchone()[0]
            self.assertGreaterEqual(total_a, 1)
            self.assertEqual(foreign_a, 0)
            with self.assertRaises(self.psycopg2.Error):
                cur.execute(
                    "INSERT INTO media_assets (owner_user_id,provider,folder,filename,status,created_at) "
                    "VALUES (%s,'local','posts','spoof.png','uploaded',now())", (_PG_UB,))
            conn.rollback()
        finally:
            conn.close()

        conn = self._appconn()
        try:
            cur = conn.cursor()
            self._set_ctx(cur, _PG_UB)
            cur.execute("SELECT count(*) FROM media_assets WHERE owner_user_id = %s", (_PG_UA,))
            self.assertEqual(cur.fetchone()[0], 0)
            conn.rollback()
        finally:
            conn.close()

        conn = self._appconn()
        try:
            cur = conn.cursor()
            cur.execute("SELECT count(*) FROM media_assets")   # no context -> nothing
            self.assertEqual(cur.fetchone()[0], 0)
            with self.assertRaises(self.psycopg2.Error):
                cur.execute(
                    "INSERT INTO media_assets (owner_user_id,provider,folder,filename,status,created_at) "
                    "VALUES (%s,'local','posts','noctx.png','uploaded',now())", (_PG_UA,))
            conn.rollback()
        finally:
            conn.close()

    # ---- promo isolation A/B + spoofing (as the app role) ----
    def test_promo_isolation_as_app_role(self):
        conn = self._appconn()
        try:
            cur = conn.cursor()
            self._set_ctx(cur, _PG_UA)
            cur.execute(
                "INSERT INTO promo_redemptions (promo_code_id,user_id,redeemed_at) "
                "VALUES (%s,%s,now()) RETURNING id", (_PG_PROMO_ID, _PG_UA))
            red_a = cur.fetchone()[0]
            cur.execute("SELECT count(*) FROM promo_redemptions WHERE user_id <> %s", (_PG_UA,))
            self.assertEqual(cur.fetchone()[0], 0)
            conn.commit()
            self.assertIsNotNone(red_a)
        finally:
            conn.close()

        conn = self._appconn()
        try:
            cur = conn.cursor()
            self._set_ctx(cur, _PG_UA)
            with self.assertRaises(self.psycopg2.Error):
                cur.execute(
                    "INSERT INTO promo_redemptions (promo_code_id,user_id,redeemed_at) "
                    "VALUES (%s,%s,now())", (_PG_PROMO_ID, _PG_UB))
            conn.rollback()
        finally:
            conn.close()

        conn = self._appconn()
        try:
            cur = conn.cursor()
            self._set_ctx(cur, _PG_UB)
            cur.execute("SELECT count(*) FROM promo_redemptions WHERE user_id = %s", (_PG_UA,))
            self.assertEqual(cur.fetchone()[0], 0)
            conn.rollback()
        finally:
            conn.close()

    # ---- transaction-local context cleared after commit AND rollback ----
    def test_context_cleared_after_commit_and_rollback(self):
        conn = self._appconn()
        try:
            cur = conn.cursor()
            self._set_ctx(cur, _PG_UA)
            cur.execute("SELECT current_setting('app.current_user_id', true)")
            in_tx = cur.fetchone()[0]
            conn.commit()
            cur.execute("SELECT current_setting('app.current_user_id', true)")
            after_commit = cur.fetchone()[0]
            self.assertEqual(in_tx, str(_PG_UA))
            self.assertIn(after_commit, ("", None))
            self._set_ctx(cur, _PG_UA)
            conn.rollback()
            cur.execute("SELECT current_setting('app.current_user_id', true)")
            after_rollback = cur.fetchone()[0]
            self.assertIn(after_rollback, ("", None))
        finally:
            conn.close()

    # ---- SQLAlchemy pool (size=1): same pid, no residual GUC, info clean, exc path ----
    def test_pool_has_no_rls_context_leak(self):
        from sqlalchemy.exc import SQLAlchemyError
        from sqlalchemy.orm import sessionmaker

        app_url = f"postgresql+psycopg2://stocknewsbr_app:{self.app_pw}@{self.host}:{self.port}/{self.dbname}"
        engine = create_engine(app_url, pool_size=1, max_overflow=0, pool_pre_ping=False)
        SessionL = sessionmaker(bind=engine)
        try:
            # All DB I/O runs inside this guard so a driver-level failure re-raises
            # a sanitized error (the app_url carries the password). AssertionErrors
            # below run outside the guard and surface normally.
            try:
                seed = SessionL()
                seed.execute(text("SELECT 1"))
                database.apply_rls_context(seed, current_user_id=_PG_UA, current_actor_id=_PG_UA, current_role="user")
                seed.execute(text(
                    "INSERT INTO media_assets (owner_user_id,provider,folder,filename,status,created_at) "
                    "VALUES (:u,'local','posts','pool_perm_a.png','uploaded',now())"), {"u": _PG_UA})
                seed.commit()
                database.clear_rls_context(seed)
                seed.close()

                sa = SessionL()
                sa.execute(text("SELECT 1"))
                database.apply_rls_context(sa, current_user_id=_PG_UA, current_actor_id=_PG_UA, current_role="user")
                pid_a = sa.execute(text("SELECT pg_backend_pid()")).scalar()
                ctx_a = sa.execute(text("SELECT current_setting('app.current_user_id', true)")).scalar()
                own_a = sa.execute(text("SELECT count(*) FROM media_assets WHERE owner_user_id = :u"), {"u": _PG_UA}).scalar()
                tot_a = sa.execute(text("SELECT count(*) FROM media_assets")).scalar()
                info_set = database.RLS_CONTEXT_INFO_KEY in sa.info
                sa.commit()
                database.clear_rls_context(sa)
                info_cleared = database.RLS_CONTEXT_INFO_KEY not in sa.info
                sa.close()

                sb = SessionL()
                sb.execute(text("SELECT 1"))
                pid_b = sb.execute(text("SELECT pg_backend_pid()")).scalar()
                residual = sb.execute(text("SELECT current_setting('app.current_user_id', true)")).scalar()
                database.apply_rls_context(sb, current_user_id=_PG_UB, current_actor_id=_PG_UB, current_role="user")
                own_b = sb.execute(text("SELECT count(*) FROM media_assets WHERE owner_user_id = :u"), {"u": _PG_UB}).scalar()
                tot_b = sb.execute(text("SELECT count(*) FROM media_assets")).scalar()
                sb.commit()
                database.clear_rls_context(sb)
                sb.close()

                sc = SessionL()
                sc.execute(text("SELECT 1"))
                database.apply_rls_context(sc, current_user_id=_PG_UA, current_actor_id=_PG_UA, current_role="user")
                try:
                    sc.execute(text("SELECT 1/0"))
                except SQLAlchemyError:
                    sc.rollback()
                database.clear_rls_context(sc)
                sc.close()

                sd = SessionL()
                sd.execute(text("SELECT 1"))
                pid_d = sd.execute(text("SELECT pg_backend_pid()")).scalar()
                residual_d = sd.execute(text("SELECT current_setting('app.current_user_id', true)")).scalar()
                sd.close()
            except SQLAlchemyError:
                raise RuntimeError(
                    "Falha de I/O no pool do PostgreSQL local de teste (credenciais omitidas)."
                ) from None

            self.assertEqual(pid_a, pid_b)                 # same pooled physical connection
            self.assertEqual(ctx_a, str(_PG_UA))
            self.assertIn(residual, ("", None))            # no residual GUC on reuse
            self.assertTrue(info_set and info_cleared)     # Session.info lifecycle
            self.assertGreaterEqual(own_a, 1)
            self.assertEqual(own_a, tot_a)                 # A sees only its own rows
            self.assertEqual(own_b, tot_b)                 # B sees only its own rows (no leak)
            self.assertEqual(pid_d, pid_a)
            self.assertIn(residual_d, ("", None))          # no leak after exception path
        finally:
            engine.dispose()


# =====================================================================
# GATE 5 — permanent, opt-in proof that pgAudit is loaded, SELECTIVE, and never
# leaks parameter values. Skipped unless BOTH a local disposable-cluster DSN and
# the cluster's audit log path are provided. Real psycopg2 / psql — no mocks; the
# probes use unique names and are cleaned up in tearDownClass.
# =====================================================================

_PGAUDIT_LOG_ENV = "MISSION36_PGAUDIT_LOG_PATH"
_PGAUDIT_SKIP_REASON = "DATABASE_URL_TEST_POSTGRES/MISSION36_PGAUDIT_LOG_PATH não configuradas"
_PSQL_BIN = "/usr/lib/postgresql/18/bin/psql"


def _pgaudit_opt_in():
    return bool(os.environ.get(_PG_ENV_VAR) and os.environ.get(_PGAUDIT_LOG_ENV))


@unittest.skipUnless(_pgaudit_opt_in(), _PGAUDIT_SKIP_REASON)
class Mission36PgAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import secrets
        import time

        import psycopg2

        cls.psycopg2 = psycopg2
        cls.url = _validate_local_test_dsn(os.environ[_PG_ENV_VAR])
        cls.host = cls.url.host
        cls.port = cls.url.port
        cls.dbname = cls.url.database
        cls.log_path = os.environ[_PGAUDIT_LOG_ENV]
        cls._super_kwargs = dict(
            host=cls.host, port=cls.port, dbname=cls.dbname,
            user=cls.url.username, password=cls.url.password,
        )
        try:
            from pathlib import Path

            with cls._superconn() as conn, conn.cursor() as cur:
                cur.execute("SHOW data_directory")
                data_directory = Path(cur.fetchone()[0])
                cur.execute("SHOW log_directory")
                configured_log_directory = Path(cur.fetchone()[0])
                cur.execute("SHOW log_filename")
                configured_log_filename = cur.fetchone()[0]
                cur.execute("SHOW logging_collector")
                logging_collector = cur.fetchone()[0].lower()
            if not configured_log_directory.is_absolute():
                configured_log_directory = data_directory / configured_log_directory
            expected_log_path = (
                configured_log_directory / configured_log_filename
            ).resolve()
            supplied_log_path = Path(cls.log_path)
            authorized_log_path = supplied_log_path.resolve(strict=True)
            if (
                logging_collector != "on"
                or authorized_log_path != expected_log_path
                or supplied_log_path.is_symlink()
                or not authorized_log_path.is_file()
            ):
                raise RuntimeError("PGAUDIT_LOG_PATH_NOT_AUTHORIZED")
        except (OSError, RuntimeError):
            raise RuntimeError("PGAUDIT_LOG_PATH_NOT_AUTHORIZED") from None
        cls.uniq = str(int(time.time()))
        cls.tbl_ddl = "gate5_ddl_probe_" + cls.uniq
        cls.tbl_bind = "gate5_bind_probe_" + cls.uniq
        cls.role = "gate5_role_probe_" + cls.uniq
        cls.app_pw = secrets.token_hex(24)
        with cls._superconn() as conn:
            conn.autocommit = True
            with conn.cursor() as cur:
                # Do NOT audit the password-setting statement (plaintext secret).
                cur.execute("SET pgaudit.log = 'none'")
                cur.execute("ALTER ROLE stocknewsbr_app WITH PASSWORD %s", (cls.app_pw,))

    @classmethod
    def tearDownClass(cls):
        try:
            with cls._superconn() as conn:
                conn.autocommit = True
                with conn.cursor() as cur:
                    cur.execute("SET pgaudit.log = 'none'")
                    cur.execute('DROP TABLE IF EXISTS public."%s"' % cls.tbl_ddl)
                    cur.execute('DROP TABLE IF EXISTS public."%s"' % cls.tbl_bind)
                    cur.execute('DROP ROLE IF EXISTS "%s"' % cls.role)
        except Exception:
            pass

    @classmethod
    def _superconn(cls):
        try:
            return cls.psycopg2.connect(**cls._super_kwargs)
        except cls.psycopg2.Error:
            raise RuntimeError(
                "Não foi possível conectar ao PostgreSQL local de teste (pgaudit; credenciais omitidas)."
            ) from None

    def _appconn(self):
        try:
            conn = self.psycopg2.connect(
                host=self.host, port=self.port, dbname=self.dbname,
                user="stocknewsbr_app", password=self.app_pw,
            )
        except self.psycopg2.Error:
            raise RuntimeError(
                "Não foi possível conectar ao PostgreSQL local de teste (app; credenciais omitidas)."
            ) from None
        conn.autocommit = True
        return conn

    def _log_text(self):
        try:
            with open(self.log_path, "r", encoding="utf-8", errors="replace") as handle:
                return handle.read()
        except OSError:
            raise RuntimeError("PGAUDIT_LOG_UNAVAILABLE") from None

    def _audit_lines(self):
        return [line for line in self._log_text().splitlines() if "AUDIT:" in line]

    @staticmethod
    def _audit_class(line):
        # '... LOG:  AUDIT: SESSION,<n>,<n>,<CLASS>,<COMMAND>,<OBJTYPE>,<OBJ>,...'
        marker = line.find("AUDIT:")
        parts = line[marker + len("AUDIT:"):].strip().split(",")
        return parts[3].strip().upper() if len(parts) > 3 else ""

    def _wait_for_audit(self, predicate, timeout=8.0):
        import time

        deadline = time.time() + timeout
        lines = self._audit_lines()
        while time.time() < deadline:
            if predicate(lines):
                return lines
            time.sleep(0.3)
            lines = self._audit_lines()
        return lines

    def _ensure_bind_table(self):
        with self._superconn() as conn:
            conn.autocommit = True
            with conn.cursor() as cur:
                cur.execute(
                    'CREATE TABLE IF NOT EXISTS public."%s" '
                    "(id serial primary key, label text)" % self.tbl_bind
                )

    # ---- pgAudit is loaded and the policy is selective ----
    def test_pgaudit_config_is_selective(self):
        with self._superconn() as conn, conn.cursor() as cur:
            cur.execute("SHOW shared_preload_libraries")
            spl = cur.fetchone()[0]
            cur.execute("SELECT count(*) FROM pg_extension WHERE extname='pgaudit'")
            ext = cur.fetchone()[0]
            cur.execute("SHOW pgaudit.log")
            log = cur.fetchone()[0].lower()
            cur.execute("SHOW pgaudit.log_parameter")
            log_parameter = cur.fetchone()[0].lower()
            cur.execute("SHOW pgaudit.log_catalog")
            log_catalog = cur.fetchone()[0].lower()
            cur.execute("SHOW pgaudit.log_relation")
            log_relation = cur.fetchone()[0].lower()
            cur.execute("SHOW pgaudit.log_statement_once")
            log_statement_once = cur.fetchone()[0].lower()
        self.assertIn("pgaudit", spl)
        self.assertEqual(ext, 1)
        self.assertIn("ddl", log)
        self.assertIn("role", log)
        self.assertIn("write", log)
        self.assertNotIn("all", log)
        self.assertNotIn("read", log)
        self.assertEqual(log_parameter, "off")
        self.assertEqual(log_catalog, "off")
        self.assertEqual(log_relation, "on")
        self.assertEqual(log_statement_once, "on")

    # ---- ROLE, DDL and WRITE statements ARE audited ----
    def test_role_ddl_write_are_audited(self):
        tbl, role = self.tbl_ddl, self.role
        with self._superconn() as conn:
            conn.autocommit = True
            cur = conn.cursor()
            cur.execute('CREATE ROLE "%s" NOLOGIN' % role)          # ROLE
            cur.execute('ALTER ROLE "%s" NOLOGIN' % role)
            cur.execute('GRANT "%s" TO stocknewsbr_app' % role)
            cur.execute('REVOKE "%s" FROM stocknewsbr_app' % role)
            cur.execute('CREATE TABLE public."%s" (id serial primary key, label text, note text)' % tbl)  # DDL
            cur.execute('ALTER TABLE public."%s" ADD COLUMN extra text' % tbl)
            cur.execute('CREATE INDEX "%s_idx" ON public."%s" (label)' % (tbl, tbl))
            cur.execute('DROP INDEX public."%s_idx"' % tbl)
            cur.execute('INSERT INTO public."%s" (label) VALUES (%%s)' % tbl, ("probe-write",))  # WRITE
            cur.execute('UPDATE public."%s" SET note=%%s WHERE label=%%s' % tbl, ("n", "probe-write"))
            cur.execute('DELETE FROM public."%s" WHERE label=%%s' % tbl, ("probe-write",))
            cur.execute('TRUNCATE public."%s"' % tbl)
        lines = self._wait_for_audit(
            lambda ls: any(tbl in line and self._audit_class(line) == "WRITE" for line in ls)
        )
        role_lines = [line for line in lines if self._audit_class(line) == "ROLE" and role in line]
        ddl_lines = [line for line in lines if self._audit_class(line) == "DDL" and tbl in line]
        write_lines = [line for line in lines if self._audit_class(line) == "WRITE" and tbl in line]
        self.assertTrue(role_lines, "no ROLE-class audit lines for the probe role")
        self.assertTrue(ddl_lines, "no DDL-class audit lines for the probe table")
        self.assertTrue(write_lines, "no WRITE-class audit lines for the probe table")

    # ---- common READs are NOT audited (selective policy, bounded volume) ----
    def test_common_reads_are_not_audited(self):
        import time

        with self._superconn() as conn:
            conn.autocommit = True
            cur = conn.cursor()
            cur.execute("SELECT 1")
            cur.execute("SELECT current_timestamp")
            cur.execute("SELECT id FROM users WHERE id = -1")
        time.sleep(0.8)
        read_lines = [line for line in self._audit_lines() if self._audit_class(line) == "READ"]
        self.assertEqual(read_lines, [], "READ class must not be audited under the selective policy")

    # ---- bound (extended-protocol) parameter VALUES never reach the log ----
    def test_bound_parameter_values_are_not_logged(self):
        import subprocess
        import tempfile
        import time

        self._ensure_bind_table()
        sentinel_pw = "SENTINEL_PGAUDIT_PASSWORD_MUST_NOT_APPEAR"
        sentinel_tok = "SENTINEL_PGAUDIT_TOKEN_MUST_NOT_APPEAR"
        # psql \bind uses the extended protocol, so the sentinels are TRUE bound
        # parameters (never inlined into the statement text).
        script = (
            'INSERT INTO public."%s" (label) VALUES ($1)\n\\bind %s\n\\g\n'
            'INSERT INTO public."%s" (label) VALUES ($1)\n\\bind %s\n\\g\n'
            % (self.tbl_bind, sentinel_pw, self.tbl_bind, sentinel_tok)
        )
        env = dict(os.environ)
        env["PGPASSWORD"] = self.url.password or ""
        path = None
        try:
            with tempfile.NamedTemporaryFile("w", suffix=".sql", delete=False) as handle:
                handle.write(script)
                path = handle.name
            subprocess.run(
                [_PSQL_BIN, "-h", self.host, "-p", str(self.port), "-U", self.url.username,
                 "-d", self.dbname, "-v", "ON_ERROR_STOP=1", "-f", path],
                env=env, check=True, capture_output=True, text=True, timeout=30,
            )
        except subprocess.CalledProcessError:
            raise RuntimeError("psql \\bind probe failed (output suppressed)") from None
        finally:
            if path:
                os.unlink(path)
        time.sleep(0.8)
        text_log = self._log_text()
        self.assertNotIn(sentinel_pw, text_log, "bound password value leaked into the audit log")
        self.assertNotIn(sentinel_tok, text_log, "bound token value leaked into the audit log")
        # The bound INSERTs must still have been audited as WRITE (structural only).
        bound_writes = [
            line for line in self._wait_for_audit(
                lambda ls: any(self.tbl_bind in line and self._audit_class(line) == "WRITE" and "$1" in line for line in ls)
            )
            if self.tbl_bind in line and self._audit_class(line) == "WRITE" and "$1" in line
        ]
        self.assertTrue(bound_writes, "the extended-protocol INSERT was not audited as WRITE")

    # ---- the application role cannot disable or remove auditing ----
    def test_app_role_cannot_disable_or_remove_audit(self):
        attempts = {
            "alter_system": "ALTER SYSTEM SET pgaudit.log = 'none'",
            "set_pgaudit_log": "SET pgaudit.log = 'none'",
            "alter_role_pgaudit": "ALTER ROLE stocknewsbr_app SET pgaudit.log = 'none'",
            "drop_extension": "DROP EXTENSION pgaudit",
            "alter_extension": "ALTER EXTENSION pgaudit UPDATE",
            "alter_database_pgaudit": (
                "ALTER DATABASE stocknewsbr_m36_gate5 SET pgaudit.log = 'none'"
            ),
            "alter_database_preload": (
                "ALTER DATABASE stocknewsbr_m36_gate5 "
                "SET shared_preload_libraries = 'pgaudit'"
            ),
        }
        blocked = {}
        for name, sql in attempts.items():
            conn = self._appconn()
            try:
                cur = conn.cursor()
                try:
                    cur.execute(sql)
                    blocked[name] = False
                except self.psycopg2.Error as exc:
                    blocked[name] = exc.pgcode == "42501"
            finally:
                conn.close()

        probe_database = "stocknewsbr_m36_extension_probe_" + self.uniq
        conn = self._superconn()
        try:
            conn.autocommit = True
            with conn.cursor() as cur:
                cur.execute('CREATE DATABASE "%s"' % probe_database)
        finally:
            conn.close()
        try:
            try:
                probe_conn = self.psycopg2.connect(
                    host=self.host,
                    port=self.port,
                    dbname=probe_database,
                    user="stocknewsbr_app",
                    password=self.app_pw,
                )
            except self.psycopg2.Error:
                raise RuntimeError(
                    "Não foi possível conectar ao banco descartável de extensão "
                    "(credenciais omitidas)."
                ) from None
            probe_conn.autocommit = True
            try:
                with probe_conn.cursor() as cur:
                    try:
                        cur.execute("CREATE EXTENSION pgaudit")
                        blocked["create_extension"] = False
                    except self.psycopg2.Error as exc:
                        blocked["create_extension"] = exc.pgcode == "42501"
            finally:
                probe_conn.close()
        finally:
            conn = self._superconn()
            try:
                conn.autocommit = True
                with conn.cursor() as cur:
                    cur.execute('DROP DATABASE IF EXISTS "%s"' % probe_database)
            finally:
                conn.close()
        self.assertTrue(all(blocked.values()), "app role could control audit: %s" % blocked)


_BACKUP_RESTORE_ENV = "MISSION36_BACKUP_RESTORE_DSN"
_BACKUP_PASSWORD_ENV = "MISSION36_BACKUP_ROLE_PASSWORD"
_BACKUP_SKIP_REASON = "MISSION36_BACKUP_RESTORE_DSN não configurada"
_BACKUP_DATABASE = "stocknewsbr_m36_gate6_restore"
_BACKUP_PORT = 55433
_BACKUP_SENTINEL_PURPOSE = "gate6-restore"
_BACKUP_SENTINEL_MARKER = "stocknewsbr-m36-gate6-restore-v1"
_BACKUP_USER_A = 910001
_BACKUP_USER_B = 910002


@unittest.skipUnless(os.environ.get(_BACKUP_RESTORE_ENV), _BACKUP_SKIP_REASON)
class Mission36BackupRestoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import secrets

        import psycopg2
        from sqlalchemy.engine import URL

        cls.psycopg2 = psycopg2
        cls.url = _validate_local_test_dsn(
            os.environ[_BACKUP_RESTORE_ENV],
            expected_database=_BACKUP_DATABASE,
            expected_port=_BACKUP_PORT,
            expected_purpose=_BACKUP_SENTINEL_PURPOSE,
            expected_marker=_BACKUP_SENTINEL_MARKER,
        )
        cls.backup_password = str(os.environ.get(_BACKUP_PASSWORD_ENV) or "")
        if len(cls.backup_password) < 32:
            raise RuntimeError("MISSION36_BACKUP_ROLE_PASSWORD_REQUIRED")
        cls._super_kwargs = {
            "host": cls.url.host,
            "port": cls.url.port,
            "dbname": cls.url.database,
            "user": cls.url.username,
            "password": cls.url.password,
            "connect_timeout": 5,
        }
        cls.app_password = secrets.token_hex(24)
        with cls._superconn() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SET pgaudit.log = 'none'")
                cursor.execute(
                    "ALTER ROLE stocknewsbr_app WITH PASSWORD %s",
                    (cls.app_password,),
                )
        cls.app_url = URL.create(
            "postgresql+psycopg2",
            username="stocknewsbr_app",
            password=cls.app_password,
            host=cls.url.host,
            port=cls.url.port,
            database=cls.url.database,
        )

    @classmethod
    def _superconn(cls):
        try:
            return cls.psycopg2.connect(**cls._super_kwargs)
        except cls.psycopg2.Error:
            raise RuntimeError(
                "Falha de conexão ao restore descartável (credenciais omitidas)."
            ) from None

    def _appconn(self):
        try:
            connection = self.psycopg2.connect(
                host=self.url.host,
                port=self.url.port,
                dbname=self.url.database,
                user="stocknewsbr_app",
                password=self.app_password,
                connect_timeout=5,
            )
        except self.psycopg2.Error:
            raise RuntimeError(
                "Falha de conexão da app role no restore (credenciais omitidas)."
            ) from None
        connection.autocommit = False
        return connection

    def _backupconn(self):
        try:
            connection = self.psycopg2.connect(
                host=self.url.host,
                port=self.url.port,
                dbname=self.url.database,
                user="stocknewsbr_backup",
                password=self.backup_password,
                connect_timeout=5,
            )
        except self.psycopg2.Error:
            raise RuntimeError(
                "Falha de conexão da backup role no restore (credenciais omitidas)."
            ) from None
        connection.autocommit = True
        return connection

    @staticmethod
    def _set_context(cursor, user_id):
        cursor.execute(
            "SELECT set_config('app.current_user_id', %s, true)",
            (str(user_id),),
        )

    def test_restored_rows_are_complete_and_deterministic(self):
        with self._superconn() as connection, connection.cursor() as cursor:
            expected_counts = {
                "users": 2,
                "referrals": 1,
                "referral_stats": 1,
                "promo_codes": 2,
                "promo_redemptions": 2,
                "media_assets": 2,
            }
            for table_name, expected_count in expected_counts.items():
                cursor.execute(f'SELECT count(*) FROM "{table_name}"')
                self.assertEqual(cursor.fetchone()[0], expected_count, table_name)

            cursor.execute(
                "SELECT id, email, referral_code FROM users ORDER BY id"
            )
            self.assertEqual(
                cursor.fetchall(),
                [
                    (_BACKUP_USER_A, "tenant-a@m36.invalid", "M36G6REFA"),
                    (_BACKUP_USER_B, "tenant-b@m36.invalid", "M36G6REFB"),
                ],
            )
            cursor.execute(
                "SELECT id, owner_user_id, filename, storage_key, status "
                "FROM media_assets ORDER BY id"
            )
            self.assertEqual(
                cursor.fetchall(),
                [
                    (910101, _BACKUP_USER_A, "tenant-a.png", "posts/tenant-a.png", "uploaded"),
                    (910102, _BACKUP_USER_B, "tenant-b.png", "posts/tenant-b.png", "uploaded"),
                ],
            )
            cursor.execute(
                "SELECT id, promo_code_id, user_id FROM promo_redemptions ORDER BY id"
            )
            self.assertEqual(
                cursor.fetchall(),
                [(910601, 910500, _BACKUP_USER_A), (910602, 910500, _BACKUP_USER_B)],
            )

    def test_restored_schema_contract_rls_and_policies(self):
        from sqlalchemy import create_engine
        from sqlalchemy.exc import SQLAlchemyError

        engine = create_engine(self.url, pool_pre_ping=True)
        try:
            try:
                result = database_schema.validate_production_schema(engine)
            except SQLAlchemyError:
                raise RuntimeError(
                    "Falha ao validar o schema restaurado (credenciais omitidas)."
                ) from None
        finally:
            engine.dispose()
        self.assertEqual(
            result["rls_policies"],
            sum(
                len(policies)
                for policies in database_schema.REQUIRED_PRODUCTION_RLS_POLICIES.values()
            ),
        )

    def test_roles_owners_and_grants_match_the_model(self):
        expected_roles = {
            "stocknewsbr_owner",
            "stocknewsbr_app",
            "stocknewsbr_worker",
            "stocknewsbr_readonly",
            "stocknewsbr_backup",
            "stocknewsbr_migration",
        }
        with self._superconn() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT rolname FROM pg_roles WHERE rolname LIKE 'stocknewsbr\\_%'"
            )
            self.assertEqual({row[0] for row in cursor.fetchall()}, expected_roles)
            cursor.execute(
                "SELECT rolsuper, rolbypassrls, rolcreatedb, rolcreaterole, "
                "rolreplication, rolcanlogin FROM pg_roles "
                "WHERE rolname='stocknewsbr_backup'"
            )
            self.assertEqual(cursor.fetchone(), (False, False, False, False, False, True))
            cursor.execute(
                "SELECT has_schema_privilege('stocknewsbr_backup','public','CREATE'), "
                "has_database_privilege('stocknewsbr_backup',current_database(),'TEMPORARY')"
            )
            self.assertEqual(cursor.fetchone(), (False, False))
            cursor.execute(
                "SELECT tablename, tableowner FROM pg_tables WHERE schemaname='public' "
                "AND tablename IN ('media_assets','promo_redemptions','promo_codes') "
                "ORDER BY tablename"
            )
            self.assertEqual(
                cursor.fetchall(),
                [
                    ("media_assets", "stocknewsbr_owner"),
                    ("promo_codes", "stocknewsbr_owner"),
                    ("promo_redemptions", "stocknewsbr_owner"),
                ],
            )
            for role in ("stocknewsbr_worker", "stocknewsbr_readonly"):
                cursor.execute(
                    "SELECT has_schema_privilege(%s,'public','USAGE'), "
                    "has_schema_privilege(%s,'public','CREATE'), "
                    "has_table_privilege(%s,'public.media_assets','INSERT')",
                    (role, role, role),
                )
                self.assertEqual(cursor.fetchone(), (True, False, False))

    def test_app_isolation_spoofing_and_transaction_local_context_survive_restore(self):
        connection = self._appconn()
        try:
            cursor = connection.cursor()
            self._set_context(cursor, _BACKUP_USER_A)
            cursor.execute("SELECT owner_user_id FROM media_assets ORDER BY id")
            self.assertEqual(cursor.fetchall(), [(_BACKUP_USER_A,)])
            cursor.execute("SELECT user_id FROM promo_redemptions ORDER BY id")
            self.assertEqual(cursor.fetchall(), [(_BACKUP_USER_A,)])
            connection.commit()
            cursor.execute("SELECT current_setting('app.current_user_id', true)")
            self.assertIn(cursor.fetchone()[0], ("", None))
        finally:
            connection.close()

        connection = self._appconn()
        try:
            cursor = connection.cursor()
            self._set_context(cursor, _BACKUP_USER_B)
            cursor.execute("SELECT owner_user_id FROM media_assets ORDER BY id")
            self.assertEqual(cursor.fetchall(), [(_BACKUP_USER_B,)])
            cursor.execute("SELECT user_id FROM promo_redemptions ORDER BY id")
            self.assertEqual(cursor.fetchall(), [(_BACKUP_USER_B,)])
            with self.assertRaises(self.psycopg2.Error):
                cursor.execute(
                    "INSERT INTO media_assets "
                    "(owner_user_id,provider,folder,filename,status,created_at) "
                    "VALUES (%s,'local','posts','spoof-g6.png','uploaded',now())",
                    (_BACKUP_USER_A,),
                )
            connection.rollback()
            self._set_context(cursor, _BACKUP_USER_B)
            with self.assertRaises(self.psycopg2.Error):
                cursor.execute(
                    "INSERT INTO promo_redemptions "
                    "(promo_code_id,user_id,redeemed_at) VALUES (910501,%s,now())",
                    (_BACKUP_USER_A,),
                )
            connection.rollback()
        finally:
            connection.close()

    def test_backup_role_reads_all_tenants_but_cannot_mutate_or_create(self):
        connection = self._backupconn()
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT owner_user_id FROM media_assets ORDER BY owner_user_id")
                self.assertEqual(cursor.fetchall(), [(_BACKUP_USER_A,), (_BACKUP_USER_B,)])
                cursor.execute("SELECT user_id FROM promo_redemptions ORDER BY user_id")
                self.assertEqual(cursor.fetchall(), [(_BACKUP_USER_A,), (_BACKUP_USER_B,)])
        finally:
            connection.close()

        attempts = (
            "INSERT INTO media_assets (owner_user_id,provider,folder,filename,status,created_at) "
            "VALUES (910001,'local','posts','forbidden.png','uploaded',now())",
            "UPDATE media_assets SET status='forbidden' WHERE id=910101",
            "DELETE FROM media_assets WHERE id=910101",
            "TRUNCATE media_assets",
            "CREATE TABLE gate6_forbidden_ddl (id integer)",
            "CREATE TEMP TABLE gate6_forbidden_temp_ddl (id integer)",
        )
        for statement in attempts:
            connection = self._backupconn()
            try:
                with connection.cursor() as cursor:
                    with self.assertRaises(self.psycopg2.Error) as context:
                        cursor.execute(statement)
                self.assertEqual(context.exception.pgcode, "42501")
            finally:
                connection.close()

    def test_application_pool_connects_without_context_leak(self):
        from sqlalchemy import create_engine, text
        from sqlalchemy.exc import SQLAlchemyError

        engine = create_engine(
            self.app_url,
            pool_size=1,
            max_overflow=0,
            pool_pre_ping=False,
        )
        try:
            try:
                with engine.begin() as connection:
                    connection.execute(
                        text("SELECT set_config('app.current_user_id', :uid, true)"),
                        {"uid": str(_BACKUP_USER_A)},
                    )
                    self.assertEqual(
                        connection.execute(
                            text("SELECT count(*) FROM media_assets")
                        ).scalar(),
                        1,
                    )
                with engine.connect() as connection:
                    residual = connection.execute(
                        text("SELECT current_setting('app.current_user_id', true)")
                    ).scalar()
                    visible_without_context = connection.execute(
                        text("SELECT count(*) FROM media_assets")
                    ).scalar()
                self.assertIn(residual, ("", None))
                self.assertEqual(visible_without_context, 0)
            except SQLAlchemyError:
                raise RuntimeError(
                    "Falha no pool restaurado (credenciais omitidas)."
                ) from None
        finally:
            engine.dispose()


if __name__ == "__main__":
    unittest.main()
