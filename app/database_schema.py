from sqlalchemy import inspect, text

from app.core.settings import is_production_environment


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
                expires_at DATETIME,
                last_seen_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                revoked_at DATETIME,
                revoked_reason VARCHAR,
                created_ip_hash VARCHAR,
                user_agent VARCHAR,
                correlation_id VARCHAR,
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
                expires_at TIMESTAMP,
                last_seen_at TIMESTAMP NOT NULL DEFAULT NOW(),
                revoked_at TIMESTAMP,
                revoked_reason VARCHAR,
                created_ip_hash VARCHAR,
                user_agent VARCHAR,
                correlation_id VARCHAR
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
                purpose VARCHAR NOT NULL DEFAULT 'LOGIN',
                target_email VARCHAR,
                channel VARCHAR NOT NULL DEFAULT 'web',
                device_id VARCHAR,
                device_label VARCHAR,
                attempt_count INTEGER NOT NULL DEFAULT 0,
                max_attempts INTEGER NOT NULL DEFAULT 5,
                delivery_status VARCHAR NOT NULL DEFAULT 'PENDING',
                delivery_attempted_at DATETIME,
                expires_at DATETIME NOT NULL,
                consumed_at DATETIME,
                invalidated_at DATETIME,
                request_ip_hash VARCHAR,
                correlation_id VARCHAR,
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
                purpose VARCHAR NOT NULL DEFAULT 'LOGIN',
                target_email VARCHAR,
                channel VARCHAR NOT NULL DEFAULT 'web',
                device_id VARCHAR,
                device_label VARCHAR,
                attempt_count INTEGER NOT NULL DEFAULT 0,
                max_attempts INTEGER NOT NULL DEFAULT 5,
                delivery_status VARCHAR NOT NULL DEFAULT 'PENDING',
                delivery_attempted_at TIMESTAMP,
                expires_at TIMESTAMP NOT NULL,
                consumed_at TIMESTAMP,
                invalidated_at TIMESTAMP,
                request_ip_hash VARCHAR,
                correlation_id VARCHAR,
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
    "auth_audit_events": {
        "sqlite": """
            CREATE TABLE auth_audit_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event VARCHAR NOT NULL,
                user_id INTEGER,
                email_masked VARCHAR,
                email_hash VARCHAR,
                ip_hash VARCHAR,
                user_agent VARCHAR,
                sid_ref VARCHAR,
                reason VARCHAR,
                status VARCHAR,
                correlation_id VARCHAR,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
        """,
        "default": """
            CREATE TABLE auth_audit_events (
                id SERIAL PRIMARY KEY,
                event VARCHAR NOT NULL,
                user_id INTEGER REFERENCES users(id),
                email_masked VARCHAR,
                email_hash VARCHAR,
                ip_hash VARCHAR,
                user_agent VARCHAR,
                sid_ref VARCHAR,
                reason VARCHAR,
                status VARCHAR,
                correlation_id VARCHAR,
                created_at TIMESTAMP NOT NULL DEFAULT NOW()
            )
        """,
    },
}


SCHEMA_PATCHES = {
    "users": {
        # Mission 31B.1: forge-proof official identity taxonomy.
        "official": {
            "sqlite": "ALTER TABLE users ADD COLUMN official BOOLEAN DEFAULT 0 NOT NULL",
            "default": "ALTER TABLE users ADD COLUMN official BOOLEAN DEFAULT FALSE NOT NULL",
        },
        "role": {
            "sqlite": "ALTER TABLE users ADD COLUMN role VARCHAR DEFAULT 'user' NOT NULL",
            "default": "ALTER TABLE users ADD COLUMN role VARCHAR DEFAULT 'user' NOT NULL",
        },
        "is_bot": {
            "sqlite": "ALTER TABLE users ADD COLUMN is_bot BOOLEAN DEFAULT 0 NOT NULL",
            "default": "ALTER TABLE users ADD COLUMN is_bot BOOLEAN DEFAULT FALSE NOT NULL",
        },
        "official_identity_locked": {
            "sqlite": "ALTER TABLE users ADD COLUMN official_identity_locked BOOLEAN DEFAULT 0 NOT NULL",
            "default": "ALTER TABLE users ADD COLUMN official_identity_locked BOOLEAN DEFAULT FALSE NOT NULL",
        },
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
        "updated_at": {
            "sqlite": "ALTER TABLE users ADD COLUMN updated_at DATETIME",
            "default": "ALTER TABLE users ADD COLUMN updated_at TIMESTAMP",
        },
    },
    "referrals": {
        "reward_processed": {
            "sqlite": "ALTER TABLE referrals ADD COLUMN reward_processed BOOLEAN DEFAULT 0",
            "default": "ALTER TABLE referrals ADD COLUMN reward_processed BOOLEAN DEFAULT FALSE",
        },
    },
    "login_challenges": {
        "purpose": {
            "sqlite": "ALTER TABLE login_challenges ADD COLUMN purpose VARCHAR NOT NULL DEFAULT 'LOGIN'",
            "default": "ALTER TABLE login_challenges ADD COLUMN purpose VARCHAR NOT NULL DEFAULT 'LOGIN'",
        },
        "target_email": {
            "sqlite": "ALTER TABLE login_challenges ADD COLUMN target_email VARCHAR",
            "default": "ALTER TABLE login_challenges ADD COLUMN target_email VARCHAR",
        },
        "max_attempts": {
            "sqlite": "ALTER TABLE login_challenges ADD COLUMN max_attempts INTEGER NOT NULL DEFAULT 5",
            "default": "ALTER TABLE login_challenges ADD COLUMN max_attempts INTEGER NOT NULL DEFAULT 5",
        },
        "delivery_status": {
            "sqlite": "ALTER TABLE login_challenges ADD COLUMN delivery_status VARCHAR NOT NULL DEFAULT 'INVALIDATED'",
            "default": "ALTER TABLE login_challenges ADD COLUMN delivery_status VARCHAR NOT NULL DEFAULT 'INVALIDATED'",
        },
        "delivery_attempted_at": {
            "sqlite": "ALTER TABLE login_challenges ADD COLUMN delivery_attempted_at DATETIME",
            "default": "ALTER TABLE login_challenges ADD COLUMN delivery_attempted_at TIMESTAMP",
        },
        "invalidated_at": {
            "sqlite": "ALTER TABLE login_challenges ADD COLUMN invalidated_at DATETIME",
            "default": "ALTER TABLE login_challenges ADD COLUMN invalidated_at TIMESTAMP",
        },
        "request_ip_hash": {
            "sqlite": "ALTER TABLE login_challenges ADD COLUMN request_ip_hash VARCHAR",
            "default": "ALTER TABLE login_challenges ADD COLUMN request_ip_hash VARCHAR",
        },
        "correlation_id": {
            "sqlite": "ALTER TABLE login_challenges ADD COLUMN correlation_id VARCHAR",
            "default": "ALTER TABLE login_challenges ADD COLUMN correlation_id VARCHAR",
        },
    },
    "user_sessions": {
        "expires_at": {
            "sqlite": "ALTER TABLE user_sessions ADD COLUMN expires_at DATETIME",
            "default": "ALTER TABLE user_sessions ADD COLUMN expires_at TIMESTAMP",
        },
        "created_ip_hash": {
            "sqlite": "ALTER TABLE user_sessions ADD COLUMN created_ip_hash VARCHAR",
            "default": "ALTER TABLE user_sessions ADD COLUMN created_ip_hash VARCHAR",
        },
        "user_agent": {
            "sqlite": "ALTER TABLE user_sessions ADD COLUMN user_agent VARCHAR",
            "default": "ALTER TABLE user_sessions ADD COLUMN user_agent VARCHAR",
        },
        "correlation_id": {
            "sqlite": "ALTER TABLE user_sessions ADD COLUMN correlation_id VARCHAR",
            "default": "ALTER TABLE user_sessions ADD COLUMN correlation_id VARCHAR",
        },
    },
    "promo_codes": {
        "free_months": {
            "sqlite": "ALTER TABLE promo_codes ADD COLUMN free_months INTEGER",
            "default": "ALTER TABLE promo_codes ADD COLUMN free_months INTEGER",
        },
    },
}


# ensure_runtime_schema applies INDEX_PATCHES inside engine.begin(); keep
# PostgreSQL CONCURRENTLY and other non-transactional index DDL in migrations.
INDEX_PATCHES = {
    "auth_audit_events": {
        "ix_auth_audit_event_email_created": {
            "sqlite": "CREATE INDEX ix_auth_audit_event_email_created ON auth_audit_events (event, email_hash, created_at)",
            "default": "CREATE INDEX ix_auth_audit_event_email_created ON auth_audit_events (event, email_hash, created_at)",
        },
        "ix_auth_audit_event_ip_created": {
            "sqlite": "CREATE INDEX ix_auth_audit_event_ip_created ON auth_audit_events (event, ip_hash, created_at)",
            "default": "CREATE INDEX ix_auth_audit_event_ip_created ON auth_audit_events (event, ip_hash, created_at)",
        },
    },
    "subscription_audit_logs": {
        "uq_subscription_audit_provider_event": {
            "sqlite": "CREATE UNIQUE INDEX IF NOT EXISTS uq_subscription_audit_provider_event ON subscription_audit_logs (provider, provider_event_id) WHERE provider_event_id IS NOT NULL",
            "default": "CREATE UNIQUE INDEX IF NOT EXISTS uq_subscription_audit_provider_event ON subscription_audit_logs (provider, provider_event_id) WHERE provider_event_id IS NOT NULL",
        },
    },
}


REQUIRED_PRODUCTION_COLUMNS = {
    "users": {
        "id", "email", "password_hash", "display_name", "phone", "avatar_url",
        "is_active", "is_verified", "official", "role", "is_bot",
        "official_identity_locked", "plan", "plan_status", "trial_expires_at",
        "plan_expires_at", "access_app", "access_web", "access_telegram",
        "telegram_id", "telegram_username", "subscription_provider",
        "subscription_origin", "subscription_product_id",
        "external_subscription_id", "google_play_purchase_token",
        "stripe_customer_id", "stripe_subscription_id", "legal_notice_version",
        "accepted_terms_at", "accepted_privacy_at", "accepted_risk_notice_at",
        "referral_code", "created_at", "updated_at", "last_access_at",
    },
    "referrals": {
        "id", "referrer_id", "referred_user_id", "status", "created_at",
        "validated_at", "reward_processed",
    },
    "referral_stats": {
        "user_id", "total_validated", "total_active", "benefit_level",
        "reward_balance_months",
    },
    "promo_codes": {
        "id", "code", "free_year", "free_months", "max_uses", "current_uses",
        "starts_at", "expires_at", "created_at",
    },
    "promo_redemptions": {"id", "promo_code_id", "user_id", "redeemed_at"},
    "media_assets": {
        "id", "owner_user_id", "provider", "folder", "filename", "storage_key",
        "content_type", "size_bytes", "public_url", "status", "created_at",
    },
    "user_sessions": {
        "id", "user_id", "session_id", "channel", "device_id", "device_label",
        "issued_at", "expires_at", "last_seen_at", "revoked_at",
        "revoked_reason", "created_ip_hash", "user_agent", "correlation_id",
    },
    "login_challenges": {
        "id", "user_id", "email", "login_token", "code_hash", "purpose",
        "target_email", "channel", "device_id", "device_label", "attempt_count",
        "max_attempts", "delivery_status", "delivery_attempted_at", "expires_at",
        "consumed_at", "invalidated_at", "request_ip_hash", "correlation_id",
        "created_at",
    },
    "auth_audit_events": {
        "id", "event", "user_id", "email_masked", "email_hash", "ip_hash",
        "user_agent", "sid_ref", "reason", "status", "correlation_id", "created_at",
    },
    "telegram_link_tokens": {
        "id", "user_id", "link_code", "origin_channel", "expires_at",
        "consumed_at", "created_at",
    },
    "subscription_audit_logs": {
        "id", "user_id", "provider", "provider_event_id", "event_type",
        "product_id", "origin", "external_subscription_id", "status",
        "payload_excerpt", "created_at",
    },
    "social_posts": {
        "id", "user_id", "ticker", "text", "image_url", "sentiment",
        "display_name", "email", "avatar_url", "created_at",
    },
    "social_comments": {
        "id", "post_id", "user_id", "text", "image_url", "display_name",
        "email", "avatar_url", "created_at",
    },
    "social_likes": {"id", "post_id", "user_id", "created_at"},
    "social_reposts": {"id", "post_id", "user_id", "quote_text", "created_at"},
    "social_follows": {"id", "user_id", "target_user_id", "created_at"},
    "social_sentiment_votes": {"id", "ticker", "user_id", "sentiment", "created_at"},
}

REQUIRED_PRODUCTION_PRIMARY_KEYS = {
    table_name: ("user_id",) if table_name == "referral_stats" else ("id",)
    for table_name in REQUIRED_PRODUCTION_COLUMNS
}

REQUIRED_PRODUCTION_UNIQUE_CONSTRAINTS = {
    "promo_redemptions": {
        "uq_promo_redemption_user_code": ("promo_code_id", "user_id"),
    },
    "social_likes": {"uq_social_like_post_user": ("post_id", "user_id")},
    "social_reposts": {"uq_social_repost_post_user": ("post_id", "user_id")},
    "social_follows": {
        "uq_social_follow_user_target": ("user_id", "target_user_id"),
    },
    "social_sentiment_votes": {
        "uq_social_sentiment_vote_ticker_user": ("ticker", "user_id"),
    },
}

REQUIRED_PRODUCTION_FOREIGN_KEYS = {
    "referrals": {
        (("referrer_id",), "users", ("id",)),
        (("referred_user_id",), "users", ("id",)),
    },
    "referral_stats": {(("user_id",), "users", ("id",))},
    "promo_redemptions": {
        (("promo_code_id",), "promo_codes", ("id",)),
        (("user_id",), "users", ("id",)),
    },
    "media_assets": {(("owner_user_id",), "users", ("id",))},
    "user_sessions": {(("user_id",), "users", ("id",))},
    "login_challenges": {(("user_id",), "users", ("id",))},
    "auth_audit_events": {(("user_id",), "users", ("id",))},
    "telegram_link_tokens": {(("user_id",), "users", ("id",))},
    "subscription_audit_logs": {(("user_id",), "users", ("id",))},
    "social_posts": {(("user_id",), "users", ("id",))},
    "social_comments": {
        (("post_id",), "social_posts", ("id",)),
        (("user_id",), "users", ("id",)),
    },
    "social_likes": {
        (("post_id",), "social_posts", ("id",)),
        (("user_id",), "users", ("id",)),
    },
    "social_reposts": {
        (("post_id",), "social_posts", ("id",)),
        (("user_id",), "users", ("id",)),
    },
    "social_follows": {
        (("user_id",), "users", ("id",)),
        (("target_user_id",), "users", ("id",)),
    },
    "social_sentiment_votes": {(("user_id",), "users", ("id",))},
}

REQUIRED_PRODUCTION_INDEXES = {
    "users": {
        "ix_users_email": ("email",),
        "ix_users_referral_code": ("referral_code",),
        "ix_users_telegram_id": ("telegram_id",),
    },
    "referrals": {
        "ix_referrals_referrer_id": ("referrer_id",),
        "ix_referrals_referred_user_id": ("referred_user_id",),
    },
    "promo_codes": {"ix_promo_codes_code": ("code",)},
    "promo_redemptions": {
        "ix_promo_redemptions_promo_code_id": ("promo_code_id",),
        "ix_promo_redemptions_user_id": ("user_id",),
    },
    "media_assets": {
        "ix_media_assets_owner_user_id": ("owner_user_id",),
    },
    "user_sessions": {
        "ix_user_sessions_session_id": ("session_id",),
        "ix_user_sessions_user_id": ("user_id",),
    },
    "login_challenges": {
        "ix_login_challenges_login_token": ("login_token",),
        "ix_login_challenges_user_id": ("user_id",),
        "ix_login_challenges_expires_at": ("expires_at",),
    },
    "auth_audit_events": {
        "ix_auth_audit_event_email_created": ("event", "email_hash", "created_at"),
        "ix_auth_audit_event_ip_created": ("event", "ip_hash", "created_at"),
        "ix_auth_audit_events_user_id": ("user_id",),
    },
    "telegram_link_tokens": {
        "ix_telegram_link_tokens_link_code": ("link_code",),
        "ix_telegram_link_tokens_user_id": ("user_id",),
    },
    "subscription_audit_logs": {
        "ix_subscription_audit_logs_user_id": ("user_id",),
        "uq_subscription_audit_provider_event": ("provider", "provider_event_id"),
    },
}

REQUIRED_PRODUCTION_UNIQUE_INDEXES = {
    "users": {"ix_users_email", "ix_users_referral_code", "ix_users_telegram_id"},
    "referrals": {"ix_referrals_referred_user_id"},
    "promo_codes": {"ix_promo_codes_code"},
    "user_sessions": {"ix_user_sessions_session_id"},
    "login_challenges": {"ix_login_challenges_login_token"},
    "telegram_link_tokens": {"ix_telegram_link_tokens_link_code"},
    "subscription_audit_logs": {"uq_subscription_audit_provider_event"},
}

REQUIRED_PRODUCTION_RLS_POLICIES = {
    "media_assets": {
        "media_assets_app_select": ("stocknewsbr_app", "SELECT", True, False, "owner_user_id"),
        "media_assets_app_insert": ("stocknewsbr_app", "INSERT", False, True, "owner_user_id"),
        "media_assets_app_update": ("stocknewsbr_app", "UPDATE", True, True, "owner_user_id"),
        "media_assets_app_delete": ("stocknewsbr_app", "DELETE", True, False, "owner_user_id"),
        "media_assets_owner_admin": ("stocknewsbr_owner", "ALL", True, True, "true"),
        "media_assets_backup_read": ("stocknewsbr_backup", "SELECT", True, False, "true"),
    },
    "promo_redemptions": {
        "promo_redemptions_app_select": ("stocknewsbr_app", "SELECT", True, False, "user_id"),
        "promo_redemptions_app_insert": ("stocknewsbr_app", "INSERT", False, True, "user_id"),
        "promo_redemptions_owner_admin": ("stocknewsbr_owner", "ALL", True, True, "true"),
        "promo_redemptions_backup_read": ("stocknewsbr_backup", "SELECT", True, False, "true"),
    },
}


def validate_required_tables(engine, required_tables) -> dict[str, int]:
    inspector = inspect(engine)
    names = tuple(dict.fromkeys(str(name) for name in required_tables))
    if any(not inspector.has_table(table_name) for table_name in names):
        raise RuntimeError("PRODUCTION_SCHEMA_NOT_READY")
    return {"tables": len(names)}


def _foreign_key_signature(foreign_key) -> tuple[tuple[str, ...], str, tuple[str, ...]]:
    return (
        tuple(foreign_key.get("constrained_columns") or ()),
        str(foreign_key.get("referred_table") or ""),
        tuple(foreign_key.get("referred_columns") or ()),
    )


def _normalized_policy_expression(value) -> str:
    rendered = str(value or "").lower().replace("::text", "")
    return "".join(
        char
        for char in rendered
        if char not in "() \t\r\n"
    )


def _validate_production_rls(engine) -> int:
    relation_sql = text(
        """
        SELECT c.relname AS table_name,
               c.relrowsecurity AS rls_enabled,
               c.relforcerowsecurity AS rls_forced
        FROM pg_class AS c
        WHERE c.relnamespace = 'public'::regnamespace
          AND c.relkind IN ('r', 'p')
          AND c.relname IN ('media_assets', 'promo_redemptions')
        """
    )
    policy_sql = text(
        """
        SELECT tablename AS table_name, policyname, cmd, roles, qual, with_check
        FROM pg_policies
        WHERE schemaname = 'public'
          AND tablename IN ('media_assets', 'promo_redemptions')
        """
    )

    try:
        with engine.connect() as connection:
            relations = {
                row["table_name"]: dict(row)
                for row in connection.execute(relation_sql).mappings()
            }
            policies = [
                dict(row)
                for row in connection.execute(policy_sql).mappings()
            ]
    except Exception:
        raise RuntimeError("PRODUCTION_SCHEMA_NOT_READY") from None

    if set(relations) != set(REQUIRED_PRODUCTION_RLS_POLICIES):
        raise RuntimeError("PRODUCTION_SCHEMA_NOT_READY")
    if any(
        not relation["rls_enabled"] or not relation["rls_forced"]
        for relation in relations.values()
    ):
        raise RuntimeError("PRODUCTION_SCHEMA_NOT_READY")

    policies_by_table = {}
    for policy in policies:
        policies_by_table.setdefault(policy["table_name"], {})[policy["policyname"]] = policy

    for table_name, expected_policies in REQUIRED_PRODUCTION_RLS_POLICIES.items():
        actual_policies = policies_by_table.get(table_name, {})
        if set(actual_policies) != set(expected_policies):
            raise RuntimeError("PRODUCTION_SCHEMA_NOT_READY")

        for policy_name, expected in expected_policies.items():
            expected_role, expected_cmd, require_using, require_check, expression_kind = expected
            actual = actual_policies[policy_name]
            if tuple(actual.get("roles") or ()) != (expected_role,):
                raise RuntimeError("PRODUCTION_SCHEMA_NOT_READY")
            if actual.get("cmd") != expected_cmd:
                raise RuntimeError("PRODUCTION_SCHEMA_NOT_READY")

            qual = actual.get("qual")
            with_check = actual.get("with_check")
            if (qual is not None) != require_using:
                raise RuntimeError("PRODUCTION_SCHEMA_NOT_READY")
            if (with_check is not None) != require_check:
                raise RuntimeError("PRODUCTION_SCHEMA_NOT_READY")

            expressions = [value for value in (qual, with_check) if value is not None]
            expected_expression = _normalized_policy_expression(
                "true"
                if expression_kind == "true"
                else (
                    f"{expression_kind}=nullif("
                    "current_setting('app.current_user_id',true),'')::integer"
                )
            )
            if any(
                _normalized_policy_expression(value) != expected_expression
                for value in expressions
            ):
                raise RuntimeError("PRODUCTION_SCHEMA_NOT_READY")

    return sum(len(policies) for policies in REQUIRED_PRODUCTION_RLS_POLICIES.values())


def validate_production_schema(engine) -> dict[str, int]:
    inspector = inspect(engine)

    for table_name, required_columns in REQUIRED_PRODUCTION_COLUMNS.items():
        if not inspector.has_table(table_name):
            raise RuntimeError("PRODUCTION_SCHEMA_NOT_READY")
        available_columns = {
            column["name"]
            for column in inspector.get_columns(table_name)
        }
        if not required_columns.issubset(available_columns):
            raise RuntimeError("PRODUCTION_SCHEMA_NOT_READY")

    for table_name, required_indexes in REQUIRED_PRODUCTION_INDEXES.items():
        available_indexes = {
            index["name"]: index
            for index in inspector.get_indexes(table_name)
        }
        if not set(required_indexes).issubset(available_indexes):
            raise RuntimeError("PRODUCTION_SCHEMA_NOT_READY")
        if any(
            tuple(available_indexes[index_name].get("column_names") or ())
            != tuple(expected_columns)
            for index_name, expected_columns in required_indexes.items()
        ):
            raise RuntimeError("PRODUCTION_SCHEMA_NOT_READY")
        if any(
            not available_indexes[index_name].get("unique", False)
            for index_name in REQUIRED_PRODUCTION_UNIQUE_INDEXES.get(table_name, set())
        ):
            raise RuntimeError("PRODUCTION_SCHEMA_NOT_READY")

    for table_name, required_primary_key in REQUIRED_PRODUCTION_PRIMARY_KEYS.items():
        primary_key = tuple(
            inspector.get_pk_constraint(table_name).get("constrained_columns") or ()
        )
        if primary_key != required_primary_key:
            raise RuntimeError("PRODUCTION_SCHEMA_NOT_READY")

    for table_name, required_constraints in REQUIRED_PRODUCTION_UNIQUE_CONSTRAINTS.items():
        available_constraints = {
            constraint.get("name"): tuple(constraint.get("column_names") or ())
            for constraint in inspector.get_unique_constraints(table_name)
        }
        if any(
            available_constraints.get(constraint_name) != columns
            for constraint_name, columns in required_constraints.items()
        ):
            raise RuntimeError("PRODUCTION_SCHEMA_NOT_READY")

    for table_name, required_foreign_keys in REQUIRED_PRODUCTION_FOREIGN_KEYS.items():
        available_foreign_keys = {
            _foreign_key_signature(foreign_key)
            for foreign_key in inspector.get_foreign_keys(table_name)
        }
        if not required_foreign_keys.issubset(available_foreign_keys):
            raise RuntimeError("PRODUCTION_SCHEMA_NOT_READY")

    policy_count = _validate_production_rls(engine)

    return {
        "tables": len(REQUIRED_PRODUCTION_COLUMNS),
        "indexes": sum(len(indexes) for indexes in REQUIRED_PRODUCTION_INDEXES.values()),
        "primary_keys": len(REQUIRED_PRODUCTION_PRIMARY_KEYS),
        "unique_constraints": sum(
            len(constraints)
            for constraints in REQUIRED_PRODUCTION_UNIQUE_CONSTRAINTS.values()
        ),
        "foreign_keys": sum(
            len(foreign_keys)
            for foreign_keys in REQUIRED_PRODUCTION_FOREIGN_KEYS.values()
        ),
        "rls_policies": policy_count,
    }


def ensure_runtime_schema(engine):
    if is_production_environment():
        raise RuntimeError("RUNTIME_DDL_FORBIDDEN_IN_PRODUCTION")

    inspector = inspect(engine)
    driver = engine.url.drivername
    dialect_key = "sqlite" if driver.startswith("sqlite") else "default"

    with engine.begin() as conn:
        for table_name, ddl_map in TABLE_PATCHES.items():
            if inspector.has_table(table_name):
                continue

            ddl = ddl_map.get(dialect_key) or ddl_map["default"]
            conn.execute(text(ddl))

        inspector = inspect(conn)

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

        for table_name, indexes in INDEX_PATCHES.items():
            if not inspector.has_table(table_name):
                continue

            current_indexes = {
                index["name"]
                for index in inspect(engine).get_indexes(table_name)
            }

            for index_name, ddl_map in indexes.items():
                if index_name in current_indexes:
                    continue

                ddl = ddl_map.get(dialect_key) or ddl_map["default"]
                if "concurrently" in ddl.lower():
                    raise RuntimeError(
                        f"INDEX_PATCHES {table_name}.{index_name} uses CONCURRENTLY; "
                        "apply it through a standalone migration instead of ensure_runtime_schema"
                    )
                conn.execute(text(ddl))
