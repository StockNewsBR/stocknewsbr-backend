import importlib.util
import io
import os
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError


SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "migrations"
    / "0001_add_provider_event_id_unique.py"
)
SPEC = importlib.util.spec_from_file_location("mission31d_tier2_migration", SCRIPT_PATH)
tier2_migration = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = tier2_migration
SPEC.loader.exec_module(tier2_migration)


class Mission31DTier2MigrationTests(unittest.TestCase):
    def _state(self, **overrides):
        state = tier2_migration.PreflightState(dialect="sqlite", table_exists=True)
        for key, value in overrides.items():
            setattr(state, key, value)
        return state

    def test_missing_database_url_fails_closed(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(
                tier2_migration.main([]),
                tier2_migration.EXIT_PREFLIGHT_FAILED,
            )

    def test_database_url_is_not_printed_or_logged(self):
        secret_url = "postgresql://user:secret-password@example.test/db"
        fake_engine = SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))

        stdout = io.StringIO()
        stderr = io.StringIO()
        with patch.dict(os.environ, {"DATABASE_URL": secret_url}, clear=True), patch.object(
            tier2_migration, "create_engine", return_value=fake_engine
        ), patch.object(tier2_migration, "run", return_value=tier2_migration.EXIT_OK), redirect_stdout(
            stdout
        ), redirect_stderr(stderr):
            exit_code = tier2_migration.main([])

        self.assertEqual(exit_code, tier2_migration.EXIT_OK)
        combined_output = stdout.getvalue() + stderr.getvalue()
        self.assertNotIn(secret_url, combined_output)
        self.assertNotIn("secret-password", combined_output)
        self.assertNotIn(
            "secret-password",
            tier2_migration._redact("connection failed for secret-password", secret_url),
        )

    def test_preflight_mode_does_not_execute_apply(self):
        state = self._state(column_exists=False, canonical_index_exists=False)
        fake_engine = SimpleNamespace(dialect=SimpleNamespace(name="sqlite"))

        with patch.object(tier2_migration, "run_preflight", return_value=state), patch.object(
            tier2_migration, "apply_migration"
        ) as apply_migration:
            exit_code = tier2_migration.run(fake_engine, apply=False, index_strategy=None)

        self.assertEqual(exit_code, tier2_migration.EXIT_OK)
        apply_migration.assert_not_called()

    def test_apply_requires_explicit_index_strategy_when_index_is_needed(self):
        state = self._state(column_exists=True, canonical_index_exists=False)
        fake_engine = SimpleNamespace(dialect=SimpleNamespace(name="sqlite"))

        with self.assertRaises(tier2_migration.MigrationBlocked):
            tier2_migration.apply_migration(fake_engine, state, index_strategy=None)

        with self.assertRaises(tier2_migration.MigrationBlocked):
            tier2_migration.apply_migration(fake_engine, state, index_strategy="concurrent")

    def test_existing_database_without_column_has_safe_plan(self):
        state = self._state(column_exists=False, canonical_index_exists=False)

        self.assertEqual(
            tier2_migration.planned_actions(state),
            [
                "add_nullable_provider_event_id_column",
                "create_canonical_partial_unique_index",
            ],
        )

    def test_existing_database_with_column_without_index_has_safe_plan(self):
        state = self._state(
            column_exists=True,
            column_nullable=True,
            canonical_index_exists=False,
        )

        self.assertEqual(
            tier2_migration.planned_actions(state),
            ["create_canonical_partial_unique_index"],
        )

    def test_postgresql_table_and_index_references_are_schema_qualified(self):
        self.assertEqual(
            tier2_migration._table_ref("postgresql"),
            "public.subscription_audit_logs",
        )
        self.assertEqual(
            tier2_migration._index_ref("postgresql"),
            "uq_subscription_audit_provider_event",
        )
        self.assertEqual(
            tier2_migration._table_ref("sqlite"),
            "subscription_audit_logs",
        )

    def test_sqlite_apply_migration_creates_column_and_canonical_index(self):
        engine = create_engine("sqlite:///:memory:", future=True)
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    CREATE TABLE subscription_audit_logs (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        provider VARCHAR NOT NULL,
                        event_type VARCHAR NOT NULL
                    )
                    """
                )
            )

        state = tier2_migration.run_preflight(engine)
        tier2_migration.apply_migration(engine, state, index_strategy="normal")
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO subscription_audit_logs(provider, provider_event_id, event_type)
                    VALUES ('stripe', 'evt_unique_31d', 'checkout.session.completed')
                    """
                )
            )
            conn.execute(
                text(
                    """
                    INSERT INTO subscription_audit_logs(provider, provider_event_id, event_type)
                    VALUES ('google_play', 'evt_unique_31d', 'subscription.sync')
                    """
                )
            )
        with self.assertRaises(IntegrityError):
            with engine.begin() as conn:
                conn.execute(
                    text(
                        """
                        INSERT INTO subscription_audit_logs(provider, provider_event_id, event_type)
                        VALUES ('stripe', 'evt_unique_31d', 'checkout.session.completed')
                        """
                    )
                )
        post_state = tier2_migration.run_preflight(engine)

        self.assertTrue(post_state.applied)
        self.assertFalse(post_state.unsafe_reasons)

    def test_add_column_step_is_idempotent_against_stale_preflight(self):
        engine = create_engine("sqlite:///:memory:", future=True)
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    CREATE TABLE subscription_audit_logs (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        provider VARCHAR NOT NULL,
                        provider_event_id VARCHAR,
                        event_type VARCHAR NOT NULL
                    )
                    """
                )
            )

        tier2_migration._add_column(engine)
        with engine.connect() as conn:
            columns = [
                column["name"]
                for column in conn.exec_driver_sql("PRAGMA table_info(subscription_audit_logs)")
                .mappings()
                .all()
            ]

        self.assertEqual(columns.count("provider_event_id"), 1)

    def test_preflight_blocks_when_provider_base_column_is_missing(self):
        engine = create_engine("sqlite:///:memory:", future=True)
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    CREATE TABLE subscription_audit_logs (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        event_type VARCHAR NOT NULL
                    )
                    """
                )
            )

        state = tier2_migration.run_preflight(engine)

        self.assertIn(
            "subscription_audit_logs base schema is missing required columns: provider",
            state.unsafe_reasons,
        )

    def test_preflight_blocks_nullable_or_null_provider_before_unique_index(self):
        engine = create_engine("sqlite:///:memory:", future=True)
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    CREATE TABLE subscription_audit_logs (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        provider VARCHAR,
                        provider_event_id VARCHAR,
                        event_type VARCHAR NOT NULL
                    )
                    """
                )
            )
            conn.execute(
                text(
                    """
                    INSERT INTO subscription_audit_logs(provider, provider_event_id, event_type)
                    VALUES (NULL, 'evt_null_provider_31d', 'checkout.session.completed')
                    """
                )
            )

        state = tier2_migration.run_preflight(engine)

        self.assertIn(
            "provider column must be NOT NULL before relying on provider_event_id unique index",
            state.unsafe_reasons,
        )
        self.assertIn(
            "subscription_audit_logs contains rows with NULL provider; normalize them before applying uniqueness",
            state.unsafe_reasons,
        )

    def test_preflight_blocks_historical_stripe_rows_without_provider_event_id(self):
        engine_without_column = create_engine("sqlite:///:memory:", future=True)
        with engine_without_column.begin() as conn:
            conn.execute(
                text(
                    """
                    CREATE TABLE subscription_audit_logs (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        provider VARCHAR NOT NULL,
                        event_type VARCHAR NOT NULL
                    )
                    """
                )
            )
            conn.execute(
                text(
                    """
                    INSERT INTO subscription_audit_logs(provider, event_type)
                    VALUES ('stripe', 'checkout.session.completed')
                    """
                )
            )

        missing_column_state = tier2_migration.run_preflight(engine_without_column)
        self.assertIn(
            "historical Stripe audit rows without provider_event_id require reconciliation before uniqueness",
            missing_column_state.unsafe_reasons,
        )
        self.assertEqual(tier2_migration.run(engine_without_column, apply=True, index_strategy=None), 2)
        blocked_state = tier2_migration.run_preflight(engine_without_column)
        self.assertFalse(blocked_state.column_exists)

        engine_with_column = create_engine("sqlite:///:memory:", future=True)
        with engine_with_column.begin() as conn:
            conn.execute(
                text(
                    """
                    CREATE TABLE subscription_audit_logs (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        provider VARCHAR NOT NULL,
                        provider_event_id VARCHAR,
                        event_type VARCHAR NOT NULL
                    )
                    """
                )
            )
            conn.execute(
                text(
                    """
                    INSERT INTO subscription_audit_logs(provider, provider_event_id, event_type)
                    VALUES ('stripe', NULL, 'invoice.payment_succeeded')
                    """
                )
            )

        null_event_id_state = tier2_migration.run_preflight(engine_with_column)
        self.assertIn(
            "historical Stripe audit rows without provider_event_id require reconciliation before uniqueness",
            null_event_id_state.unsafe_reasons,
        )

    def test_applied_database_has_no_actions(self):
        state = self._state(
            column_exists=True,
            column_nullable=True,
            column_type="VARCHAR",
            canonical_index_exists=True,
            canonical_index_valid=True,
            canonical_index_columns=["provider", "provider_event_id"],
        )

        self.assertTrue(state.applied)
        self.assertEqual(tier2_migration.planned_actions(state), [])

    def test_duplicate_provider_event_pairs_block_preflight(self):
        state = self._state(
            column_exists=True,
            column_nullable=True,
            duplicate_provider_event_pairs=[
                {"provider": "stripe", "provider_event_id": "evt_dup", "duplicates": 2}
            ],
        )

        tier2_migration._validate_preflight_state(state)

        self.assertIn(
            "duplicate (provider, provider_event_id) pairs detected",
            state.unsafe_reasons,
        )

    def test_invalid_index_blocks_preflight(self):
        state = self._state(
            column_exists=True,
            column_nullable=True,
            invalid_indexes=["uq_subscription_audit_provider_event"],
        )

        tier2_migration._validate_preflight_state(state)

        self.assertIn(
            "invalid index detected; drop/reconcile invalid index before applying migration",
            state.unsafe_reasons,
        )

    def test_incompatible_existing_column_type_blocks_preflight(self):
        state = self._state(column_exists=True, column_nullable=True, column_type="INTEGER")

        tier2_migration._validate_preflight_state(state)

        self.assertIn("provider_event_id exists with incompatible type", state.unsafe_reasons)

    def test_concurrent_index_allows_benign_postgresql_locks_only(self):
        state = self._state(
            dialect="postgresql",
            column_exists=True,
            canonical_index_exists=False,
            active_locks=[{"mode": "AccessShareLock", "granted": True}],
        )
        actions = tier2_migration.planned_actions(state)

        self.assertEqual(
            tier2_migration._conflicting_active_locks(state, actions, "concurrent"),
            [],
        )

        state.active_locks = [{"mode": "AccessExclusiveLock", "granted": True}]
        self.assertEqual(
            tier2_migration._conflicting_active_locks(state, actions, "concurrent"),
            state.active_locks,
        )

    def test_add_column_blocks_on_any_granted_postgresql_lock(self):
        state = self._state(
            dialect="postgresql",
            column_exists=False,
            canonical_index_exists=False,
            active_locks=[{"mode": "AccessShareLock", "granted": True}],
        )

        self.assertEqual(
            tier2_migration._conflicting_active_locks(
                state,
                tier2_migration.planned_actions(state),
                "concurrent",
            ),
            state.active_locks,
        )

    def test_postgresql_ddl_timeout_guards_are_applied_in_correct_scope(self):
        class FakeConnection:
            def __init__(self):
                self.dialect = SimpleNamespace(name="postgresql")
                self.statements = []

            def execute(self, statement):
                self.statements.append(str(statement))

        transactional_conn = FakeConnection()
        tier2_migration._apply_postgresql_timeout_guards(transactional_conn, local=True)
        self.assertEqual(
            transactional_conn.statements,
            [
                "SET LOCAL lock_timeout TO '5s'",
                "SET LOCAL statement_timeout TO '60s'",
            ],
        )

        autocommit_conn = FakeConnection()
        tier2_migration._apply_postgresql_timeout_guards(autocommit_conn, local=False)
        self.assertEqual(
            autocommit_conn.statements,
            [
                "SET lock_timeout TO '5s'",
                "SET statement_timeout TO '60s'",
            ],
        )

        concurrent_conn = FakeConnection()
        tier2_migration._apply_postgresql_timeout_guards(
            concurrent_conn,
            local=False,
            statement_timeout=tier2_migration.CONCURRENT_INDEX_STATEMENT_TIMEOUT,
        )
        self.assertEqual(
            concurrent_conn.statements,
            [
                "SET lock_timeout TO '5s'",
                "SET statement_timeout TO '15min'",
            ],
        )

    def test_non_postgresql_ddl_timeout_guards_are_noop(self):
        class FakeConnection:
            dialect = SimpleNamespace(name="sqlite")

            def execute(self, statement):
                raise AssertionError(f"unexpected statement: {statement}")

        tier2_migration._apply_postgresql_timeout_guards(FakeConnection(), local=True)

    def test_sqlite_preflight_validates_existing_partial_index_without_apply(self):
        engine = create_engine("sqlite:///:memory:", future=True)
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    CREATE TABLE subscription_audit_logs (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        provider VARCHAR NOT NULL,
                        provider_event_id VARCHAR,
                        event_type VARCHAR NOT NULL
                    )
                    """
                )
            )
            conn.execute(
                text(
                    """
                    CREATE UNIQUE INDEX uq_subscription_audit_provider_event
                    ON subscription_audit_logs(provider, provider_event_id)
                    WHERE provider_event_id IS NOT NULL
                    """
                )
            )

        state = tier2_migration.run_preflight(engine)

        self.assertTrue(state.applied)
        self.assertFalse(state.unsafe_reasons)

    def test_sqlite_preflight_rejects_non_unique_partial_index(self):
        engine = create_engine("sqlite:///:memory:", future=True)
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    CREATE TABLE subscription_audit_logs (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        provider VARCHAR NOT NULL,
                        provider_event_id VARCHAR,
                        event_type VARCHAR NOT NULL
                    )
                    """
                )
            )
            conn.execute(
                text(
                    """
                    CREATE INDEX uq_subscription_audit_provider_event
                    ON subscription_audit_logs(provider, provider_event_id)
                    WHERE provider_event_id IS NOT NULL
                    """
                )
            )

        state = tier2_migration.run_preflight(engine)

        self.assertFalse(state.applied)
        self.assertIn(
            "canonical index exists but does not match the required partial unique index",
            state.unsafe_reasons,
        )


if __name__ == "__main__":
    unittest.main()
