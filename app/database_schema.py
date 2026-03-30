from sqlalchemy import inspect, text


TABLE_PATCHES = {
    "promo_redemptions": {
        "sqlite": """
            CREATE TABLE promo_redemptions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                promo_code_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                redeemed_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                CONSTRAINT uq_promo_redemption_user_code UNIQUE (promo_code_id, user_id),
                FOREIGN KEY(promo_code_id) REFERENCES promo_codes(id),
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
        """,
        "default": """
            CREATE TABLE promo_redemptions (
                id SERIAL PRIMARY KEY,
                promo_code_id INTEGER NOT NULL REFERENCES promo_codes(id),
                user_id INTEGER NOT NULL REFERENCES users(id),
                redeemed_at TIMESTAMP NOT NULL DEFAULT NOW(),
                CONSTRAINT uq_promo_redemption_user_code UNIQUE (promo_code_id, user_id)
            )
        """,
    },
    "media_assets": {
        "sqlite": """
            CREATE TABLE media_assets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                owner_user_id INTEGER NOT NULL,
                provider VARCHAR NOT NULL DEFAULT 'local',
                folder VARCHAR NOT NULL DEFAULT 'posts',
                filename VARCHAR NOT NULL,
                storage_key VARCHAR,
                content_type VARCHAR,
                size_bytes INTEGER,
                public_url VARCHAR,
                status VARCHAR NOT NULL DEFAULT 'uploaded',
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(owner_user_id) REFERENCES users(id)
            )
        """,
        "default": """
            CREATE TABLE media_assets (
                id SERIAL PRIMARY KEY,
                owner_user_id INTEGER NOT NULL REFERENCES users(id),
                provider VARCHAR NOT NULL DEFAULT 'local',
                folder VARCHAR NOT NULL DEFAULT 'posts',
                filename VARCHAR NOT NULL,
                storage_key VARCHAR,
                content_type VARCHAR,
                size_bytes INTEGER,
                public_url VARCHAR,
                status VARCHAR NOT NULL DEFAULT 'uploaded',
                created_at TIMESTAMP NOT NULL DEFAULT NOW()
            )
        """,
    },
    "user_sessions": {
        "sqlite": """
            CREATE TABLE user_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                session_id VARCHAR NOT NULL UNIQUE,
                channel VARCHAR NOT NULL DEFAULT 'web',
                device_id VARCHAR,
                device_label VARCHAR,
                issued_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                last_seen_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                revoked_at DATETIME,
                revoked_reason VARCHAR,
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
        """,
        "default": """
            CREATE TABLE user_sessions (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id),
                session_id VARCHAR NOT NULL UNIQUE,
                channel VARCHAR NOT NULL DEFAULT 'web',
                device_id VARCHAR,
                device_label VARCHAR,
                issued_at TIMESTAMP NOT NULL DEFAULT NOW(),
                last_seen_at TIMESTAMP NOT NULL DEFAULT NOW(),
                revoked_at TIMESTAMP,
                revoked_reason VARCHAR
            )
        """,
    },
    "login_challenges": {
        "sqlite": """
            CREATE TABLE login_challenges (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                email VARCHAR NOT NULL,
                login_token VARCHAR NOT NULL UNIQUE,
                code_hash VARCHAR NOT NULL,
                channel VARCHAR NOT NULL DEFAULT 'web',
                device_id VARCHAR,
                device_label VARCHAR,
                attempt_count INTEGER NOT NULL DEFAULT 0,
                expires_at DATETIME NOT NULL,
                consumed_at DATETIME,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
        """,
        "default": """
            CREATE TABLE login_challenges (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id),
                email VARCHAR NOT NULL,
                login_token VARCHAR NOT NULL UNIQUE,
                code_hash VARCHAR NOT NULL,
                channel VARCHAR NOT NULL DEFAULT 'web',
                device_id VARCHAR,
                device_label VARCHAR,
                attempt_count INTEGER NOT NULL DEFAULT 0,
                expires_at TIMESTAMP NOT NULL,
                consumed_at TIMESTAMP,
                created_at TIMESTAMP NOT NULL DEFAULT NOW()
            )
        """,
    },
    "telegram_link_tokens": {
        "sqlite": """
            CREATE TABLE telegram_link_tokens (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                link_code VARCHAR NOT NULL UNIQUE,
                origin_channel VARCHAR NOT NULL DEFAULT 'app',
                expires_at DATETIME NOT NULL,
                consumed_at DATETIME,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
        """,
        "default": """
            CREATE TABLE telegram_link_tokens (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id),
                link_code VARCHAR NOT NULL UNIQUE,
                origin_channel VARCHAR NOT NULL DEFAULT 'app',
                expires_at TIMESTAMP NOT NULL,
                consumed_at TIMESTAMP,
                created_at TIMESTAMP NOT NULL DEFAULT NOW()
            )
        """,
    },
}


SCHEMA_PATCHES = {
    "users": {
        "display_name": {
            "sqlite": "ALTER TABLE users ADD COLUMN display_name VARCHAR",
            "default": "ALTER TABLE users ADD COLUMN display_name VARCHAR",
        },
        "phone": {
            "sqlite": "ALTER TABLE users ADD COLUMN phone VARCHAR",
            "default": "ALTER TABLE users ADD COLUMN phone VARCHAR",
        },
        "avatar_url": {
            "sqlite": "ALTER TABLE users ADD COLUMN avatar_url VARCHAR",
            "default": "ALTER TABLE users ADD COLUMN avatar_url VARCHAR",
        },
        "access_app": {
            "sqlite": "ALTER TABLE users ADD COLUMN access_app BOOLEAN DEFAULT 1",
            "default": "ALTER TABLE users ADD COLUMN access_app BOOLEAN DEFAULT TRUE",
        },
        "access_web": {
            "sqlite": "ALTER TABLE users ADD COLUMN access_web BOOLEAN DEFAULT 1",
            "default": "ALTER TABLE users ADD COLUMN access_web BOOLEAN DEFAULT TRUE",
        },
        "access_telegram": {
            "sqlite": "ALTER TABLE users ADD COLUMN access_telegram BOOLEAN DEFAULT 1",
            "default": "ALTER TABLE users ADD COLUMN access_telegram BOOLEAN DEFAULT TRUE",
        },
        "telegram_id": {
            "sqlite": "ALTER TABLE users ADD COLUMN telegram_id VARCHAR",
            "default": "ALTER TABLE users ADD COLUMN telegram_id VARCHAR",
        },
        "telegram_username": {
            "sqlite": "ALTER TABLE users ADD COLUMN telegram_username VARCHAR",
            "default": "ALTER TABLE users ADD COLUMN telegram_username VARCHAR",
        },
        "subscription_provider": {
            "sqlite": "ALTER TABLE users ADD COLUMN subscription_provider VARCHAR",
            "default": "ALTER TABLE users ADD COLUMN subscription_provider VARCHAR",
        },
        "subscription_origin": {
            "sqlite": "ALTER TABLE users ADD COLUMN subscription_origin VARCHAR",
            "default": "ALTER TABLE users ADD COLUMN subscription_origin VARCHAR",
        },
        "subscription_product_id": {
            "sqlite": "ALTER TABLE users ADD COLUMN subscription_product_id VARCHAR",
            "default": "ALTER TABLE users ADD COLUMN subscription_product_id VARCHAR",
        },
        "external_subscription_id": {
            "sqlite": "ALTER TABLE users ADD COLUMN external_subscription_id VARCHAR",
            "default": "ALTER TABLE users ADD COLUMN external_subscription_id VARCHAR",
        },
        "google_play_purchase_token": {
            "sqlite": "ALTER TABLE users ADD COLUMN google_play_purchase_token VARCHAR",
            "default": "ALTER TABLE users ADD COLUMN google_play_purchase_token VARCHAR",
        },
        "legal_notice_version": {
            "sqlite": "ALTER TABLE users ADD COLUMN legal_notice_version VARCHAR DEFAULT '2026-03'",
            "default": "ALTER TABLE users ADD COLUMN legal_notice_version VARCHAR DEFAULT '2026-03'",
        },
        "accepted_terms_at": {
            "sqlite": "ALTER TABLE users ADD COLUMN accepted_terms_at DATETIME",
            "default": "ALTER TABLE users ADD COLUMN accepted_terms_at TIMESTAMP",
        },
        "accepted_privacy_at": {
            "sqlite": "ALTER TABLE users ADD COLUMN accepted_privacy_at DATETIME",
            "default": "ALTER TABLE users ADD COLUMN accepted_privacy_at TIMESTAMP",
        },
        "accepted_risk_notice_at": {
            "sqlite": "ALTER TABLE users ADD COLUMN accepted_risk_notice_at DATETIME",
            "default": "ALTER TABLE users ADD COLUMN accepted_risk_notice_at TIMESTAMP",
        },
        "last_access_at": {
            "sqlite": "ALTER TABLE users ADD COLUMN last_access_at DATETIME",
            "default": "ALTER TABLE users ADD COLUMN last_access_at TIMESTAMP",
        },
    },
    "referrals": {
        "reward_processed": {
            "sqlite": "ALTER TABLE referrals ADD COLUMN reward_processed BOOLEAN DEFAULT 0",
            "default": "ALTER TABLE referrals ADD COLUMN reward_processed BOOLEAN DEFAULT FALSE",
        },
    },
    "promo_codes": {
        "free_months": {
            "sqlite": "ALTER TABLE promo_codes ADD COLUMN free_months INTEGER",
            "default": "ALTER TABLE promo_codes ADD COLUMN free_months INTEGER",
        },
    },
}


def ensure_runtime_schema(engine):
    inspector = inspect(engine)
    driver = engine.url.drivername
    dialect_key = "sqlite" if driver.startswith("sqlite") else "default"

    with engine.begin() as conn:
        for table_name, ddl_map in TABLE_PATCHES.items():
            if inspector.has_table(table_name):
                continue

            ddl = ddl_map.get(dialect_key) or ddl_map["default"]
            conn.execute(text(ddl))

        for table_name, columns in SCHEMA_PATCHES.items():
            if not inspector.has_table(table_name):
                continue

            current_columns = {
                column["name"]
                for column in inspect(engine).get_columns(table_name)
            }

            for column_name, ddl_map in columns.items():
                if column_name in current_columns:
                    continue

                ddl = ddl_map.get(dialect_key) or ddl_map["default"]
                conn.execute(text(ddl))
