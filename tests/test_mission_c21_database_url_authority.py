"""Mission C21 - the migration script must normalise DATABASE_URL like the app.

Only two places build an engine: `app/database.py`, from
`app.core.settings.validate_database_configuration()`, and this standalone
migration script, which reads the environment itself and fails closed when the
variable is absent.

The application authority strips the value; the script checked `.strip()` for
emptiness but returned the raw string, so a padded DATABASE_URL made the
migration die on an opaque SQLAlchemy ArgumentError while the application it was
migrating connected to that same database without complaint.

Synthetic URLs only -- no real credentials, no connections.
"""

import importlib.util
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from app.core.settings import validate_database_configuration

SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "migrations"
    / "0001_add_provider_event_id_unique.py"
)
SPEC = importlib.util.spec_from_file_location("mission_c21_tier2_migration", SCRIPT_PATH)
tier2_migration = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = tier2_migration
SPEC.loader.exec_module(tier2_migration)

PADDED = "  postgresql://snbapp:s3cr3t@db.internal.example:5432/stocknews  "


class MissionC21DatabaseUrlAuthorityTests(unittest.TestCase):
    def test_migration_strips_the_url_like_the_application(self):
        with patch.dict(os.environ, {"DATABASE_URL": PADDED}, clear=True):
            from_script = tier2_migration._database_url_from_env()

        with patch.dict(os.environ, {"DATABASE_URL": PADDED, "ENV": "production"}, clear=True):
            from_app = validate_database_configuration()

        self.assertEqual(from_script, PADDED.strip())
        self.assertEqual(
            from_script,
            from_app,
            "the migration and the application must resolve the same database",
        )

    def test_migration_still_fails_closed_without_a_url(self):
        for value in ({}, {"DATABASE_URL": ""}, {"DATABASE_URL": "   "}):
            with self.subTest(value=value):
                with patch.dict(os.environ, value, clear=True):
                    with self.assertRaises(tier2_migration.MigrationBlocked):
                        tier2_migration._database_url_from_env()

    def test_migration_url_is_usable_by_create_engine(self):
        from sqlalchemy.engine import make_url

        with patch.dict(os.environ, {"DATABASE_URL": PADDED}, clear=True):
            resolved = tier2_migration._database_url_from_env()

        parsed = make_url(resolved)
        self.assertEqual(parsed.get_backend_name(), "postgresql")
        self.assertEqual(parsed.database, "stocknews")


if __name__ == "__main__":
    unittest.main()
