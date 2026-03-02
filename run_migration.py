from sqlalchemy import create_engine, text
import os

DATABASE_URL = "postgresql://stocknewsbr_user:13d8i3RDEKKsx9emYiCcxTbE8L4MB9Pg@dpg-d6icd79r0fns73b7v8a0-a.oregon-postgres.render.com/stocknewsbr_a1bs"

engine = create_engine(DATABASE_URL)

with engine.connect() as conn:
    conn.execute(text("""
        ALTER TABLE users
        ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT TRUE;
    """))

    conn.execute(text("""
        ALTER TABLE users
        ADD COLUMN IF NOT EXISTS plan_status VARCHAR DEFAULT 'active';
    """))

    conn.execute(text("""
        ALTER TABLE users
        ADD COLUMN IF NOT EXISTS plan_expires_at TIMESTAMP NULL;
    """))

    conn.execute(text("""
        ALTER TABLE users
        ADD COLUMN IF NOT EXISTS stripe_customer_id VARCHAR NULL;
    """))

    conn.execute(text("""
        ALTER TABLE users
        ADD COLUMN IF NOT EXISTS stripe_subscription_id VARCHAR NULL;
    """))

    conn.commit()

print("✅ Migration executed successfully")