"""Mission C20 - keep the production schema contract aligned with the models.

This project has no Alembic. Production runs `validate_production_schema` only
(`ensure_runtime_schema` raises RUNTIME_DDL_FORBIDDEN_IN_PRODUCTION), so the
REQUIRED_PRODUCTION_* dicts *are* the schema contract: whatever they omit is
never checked against a production database.

At the time of writing they mirror the models exactly -- 17/17 tables and
173/173 columns. Nothing pinned that, so a new model column would silently fall
outside production validation.

RLS is PostgreSQL-only (`pg_class`/`pg_policies`), so the clean-install check
below covers the structural contract and not `_validate_production_rls`.
"""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import create_engine, inspect

import app.models  # noqa: F401  (registers the mappers on Base.metadata)
from app.database import Base
from app.database_schema import (
    REQUIRED_PRODUCTION_COLUMNS,
    REQUIRED_PRODUCTION_FOREIGN_KEYS,
    REQUIRED_PRODUCTION_INDEXES,
    REQUIRED_PRODUCTION_PRIMARY_KEYS,
    REQUIRED_PRODUCTION_UNIQUE_CONSTRAINTS,
    _foreign_key_signature,
    ensure_runtime_schema,
)


class MissionC20SchemaContractDriftTests(unittest.TestCase):
    def test_every_model_table_is_validated_in_production(self):
        model_tables = {table.name for table in Base.metadata.sorted_tables}

        self.assertEqual(
            sorted(model_tables - set(REQUIRED_PRODUCTION_COLUMNS)),
            [],
            "model tables outside REQUIRED_PRODUCTION_COLUMNS are never checked in production",
        )

    def test_every_model_column_is_validated_in_production(self):
        gaps = {}

        for table in Base.metadata.sorted_tables:
            required = REQUIRED_PRODUCTION_COLUMNS.get(table.name)

            if required is None:
                continue

            missing = sorted({column.name for column in table.columns} - set(required))

            if missing:
                gaps[table.name] = missing

        self.assertEqual(gaps, {}, "model columns missing from the production schema contract")

    def test_clean_install_satisfies_the_production_contract(self):
        with tempfile.TemporaryDirectory() as tmp:
            engine = create_engine(f"sqlite:///{Path(tmp) / 'clean.db'}", future=True)

            try:
                Base.metadata.create_all(bind=engine)
                ensure_runtime_schema(engine)
                inspector = inspect(engine)

                for table_name, required_columns in REQUIRED_PRODUCTION_COLUMNS.items():
                    self.assertTrue(inspector.has_table(table_name), table_name)
                    available = {column["name"] for column in inspector.get_columns(table_name)}
                    self.assertTrue(set(required_columns).issubset(available), table_name)

                for table_name, required_indexes in REQUIRED_PRODUCTION_INDEXES.items():
                    available = {index["name"] for index in inspector.get_indexes(table_name)}
                    self.assertTrue(set(required_indexes).issubset(available), table_name)

                for table_name, required_pk in REQUIRED_PRODUCTION_PRIMARY_KEYS.items():
                    got = tuple(inspector.get_pk_constraint(table_name).get("constrained_columns") or ())
                    self.assertEqual(got, required_pk, table_name)

                for table_name, required_constraints in REQUIRED_PRODUCTION_UNIQUE_CONSTRAINTS.items():
                    available = {
                        constraint.get("name"): tuple(constraint.get("column_names") or ())
                        for constraint in inspector.get_unique_constraints(table_name)
                    }
                    for name, columns in required_constraints.items():
                        self.assertEqual(available.get(name), columns, f"{table_name}.{name}")

                for table_name, required_foreign_keys in REQUIRED_PRODUCTION_FOREIGN_KEYS.items():
                    available = {
                        _foreign_key_signature(foreign_key)
                        for foreign_key in inspector.get_foreign_keys(table_name)
                    }
                    self.assertTrue(set(required_foreign_keys).issubset(available), table_name)
            finally:
                engine.dispose()

    def test_runtime_ddl_is_refused_in_production(self):
        with tempfile.TemporaryDirectory() as tmp:
            engine = create_engine(f"sqlite:///{Path(tmp) / 'prod.db'}", future=True)

            try:
                with patch("app.database_schema.is_production_environment", return_value=True):
                    with self.assertRaises(RuntimeError) as caught:
                        ensure_runtime_schema(engine)

                self.assertIn("RUNTIME_DDL_FORBIDDEN_IN_PRODUCTION", str(caught.exception))
            finally:
                engine.dispose()


if __name__ == "__main__":
    unittest.main()
