import unittest

from sqlalchemy import create_engine, inspect, text

from app.database_schema import ensure_runtime_schema


class RuntimeSchemaTests(unittest.TestCase):
    def test_users_runtime_schema_adds_updated_at_for_existing_sqlite_db(self):
        engine = create_engine("sqlite:///:memory:", future=True)

        try:
            with engine.begin() as conn:
                conn.execute(
                    text(
                        """
                        CREATE TABLE users (
                            id INTEGER PRIMARY KEY,
                            email VARCHAR NOT NULL,
                            password_hash VARCHAR NOT NULL,
                            referral_code VARCHAR NOT NULL,
                            created_at DATETIME
                        )
                        """
                    )
                )

            ensure_runtime_schema(engine)

            columns = {column["name"] for column in inspect(engine).get_columns("users")}
            self.assertIn("updated_at", columns)
        finally:
            engine.dispose()


if __name__ == "__main__":
    unittest.main()
