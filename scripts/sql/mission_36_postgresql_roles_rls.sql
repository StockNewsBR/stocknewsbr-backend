-- =====================================================================
-- MISSION 36 — GATE 3.2
-- PostgreSQL roles, memberships, ownership, grants and RLS policies
-- =====================================================================
--
-- SCOPE (Gate 3.2):
--   * Six least-privilege roles.
--   * Controlled membership (migration -> owner, SET ROLE only).
--   * Ownership of the in-scope objects assigned to the owner role.
--   * PUBLIC privileges revoked; explicit grants only.
--   * Row Level Security on media_assets and promo_redemptions.
--   * Application policies scoped to the transaction-local RLS context.
--   * Read-only backup policies (no BYPASSRLS).
--
-- This artifact is the versioned roles/RLS bootstrap used by the completed
-- local pgAudit and backup/restore gates. pgAudit server configuration and
-- disposable-cluster orchestration intentionally remain outside this SQL.
--
-- SECURITY INVARIANTS:
--   * No role is SUPERUSER, CREATEDB, CREATEROLE or BYPASSRLS.
--   * The application role is never an owner and never bypasses RLS.
--   * No password, DSN, host or credential is stored in this file.
--     LOGIN roles are provisioned with a password OUT OF BAND.
--
-- This script is idempotent / re-appliable: role creation is guarded,
-- attributes are enforced with ALTER ROLE, and every policy is dropped
-- if present before being recreated.
-- =====================================================================


-- =====================================================================
-- 1. ROLES (idempotent creation, attributes enforced explicitly)
-- =====================================================================

-- Single top-level transaction: if any statement below fails, the whole
-- roles/ownership/grants/policies bootstrap rolls back (no partial state,
-- no table left with RLS enabled but no policy). The BEGIN inside the DO
-- block further down is PL/pgSQL, not transaction control.
BEGIN;


DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'stocknewsbr_owner') THEN
        CREATE ROLE stocknewsbr_owner;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'stocknewsbr_app') THEN
        CREATE ROLE stocknewsbr_app;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'stocknewsbr_worker') THEN
        CREATE ROLE stocknewsbr_worker;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'stocknewsbr_readonly') THEN
        CREATE ROLE stocknewsbr_readonly;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'stocknewsbr_backup') THEN
        CREATE ROLE stocknewsbr_backup;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'stocknewsbr_migration') THEN
        CREATE ROLE stocknewsbr_migration;
    END IF;
END
$$;

-- Canonical attribute lines. Every role is NOSUPERUSER / NOCREATEDB /
-- NOCREATEROLE / NOBYPASSRLS. LOGIN roles receive their password OUT OF BAND.
ALTER ROLE stocknewsbr_owner     WITH NOLOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
ALTER ROLE stocknewsbr_app       WITH LOGIN   INHERIT   NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
ALTER ROLE stocknewsbr_worker    WITH LOGIN   INHERIT   NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
ALTER ROLE stocknewsbr_readonly  WITH NOLOGIN INHERIT   NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
ALTER ROLE stocknewsbr_backup    WITH LOGIN   INHERIT   NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
ALTER ROLE stocknewsbr_migration WITH NOLOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;


-- =====================================================================
-- 2. MEMBERSHIPS
-- Only the migration role may assume the owner, and only through an
-- explicit SET ROLE (migration is NOINHERIT, so ownership privileges
-- are never inherited implicitly). No application-facing role is ever a
-- member of owner or migration.
-- =====================================================================

-- Remove every pre-existing membership involving a StockNewsBR role. This
-- closes stale ADMIN OPTION and external-role inheritance paths before the
-- single authorized edge is recreated with default ADMIN FALSE semantics.
DO $$
DECLARE
    membership record;
BEGIN
    FOR membership IN
        SELECT parent.rolname AS parent_name, child.rolname AS child_name
        FROM pg_auth_members AS link
        JOIN pg_roles AS parent ON parent.oid = link.roleid
        JOIN pg_roles AS child ON child.oid = link.member
        WHERE parent.rolname LIKE 'stocknewsbr\_%'
           OR child.rolname LIKE 'stocknewsbr\_%'
    LOOP
        EXECUTE format(
            'REVOKE %I FROM %I',
            membership.parent_name,
            membership.child_name
        );
    END LOOP;
END
$$;

GRANT stocknewsbr_owner TO stocknewsbr_migration
    WITH ADMIN FALSE, INHERIT FALSE, SET TRUE;


-- =====================================================================
-- 3. OWNERSHIP OF THE CONTROLLED OBJECTS
-- The owner role owns the in-scope tables and their identity sequences.
-- The application role is never an owner.
-- =====================================================================

ALTER TABLE public.media_assets       OWNER TO stocknewsbr_owner;
ALTER TABLE public.promo_redemptions  OWNER TO stocknewsbr_owner;
ALTER TABLE public.promo_codes        OWNER TO stocknewsbr_owner;

ALTER SEQUENCE public.media_assets_id_seq      OWNER TO stocknewsbr_owner;
ALTER SEQUENCE public.promo_redemptions_id_seq OWNER TO stocknewsbr_owner;
ALTER SEQUENCE public.promo_codes_id_seq       OWNER TO stocknewsbr_owner;


-- =====================================================================
-- 4. SCHEMA PRIVILEGES — revoke PUBLIC, grant only USAGE
-- No application-facing role receives CREATE on the schema.
-- =====================================================================

REVOKE ALL ON SCHEMA public FROM PUBLIC;
REVOKE ALL ON SCHEMA public FROM stocknewsbr_owner;
REVOKE ALL ON SCHEMA public FROM stocknewsbr_app;
REVOKE ALL ON SCHEMA public FROM stocknewsbr_worker;
REVOKE ALL ON SCHEMA public FROM stocknewsbr_readonly;
REVOKE ALL ON SCHEMA public FROM stocknewsbr_backup;
REVOKE ALL ON SCHEMA public FROM stocknewsbr_migration;

-- The owner must retain USAGE on the schema: it owns the controlled tables and
-- PostgreSQL runs foreign-key referential-integrity checks with the privileges
-- of the referenced table's owner. Without this GRANT an application-role INSERT
-- into promo_redemptions (FK -> promo_codes, owned by stocknewsbr_owner) fails
-- with "permission denied for schema public". USAGE only — never CREATE. The
-- migration role reaches these objects via SET ROLE stocknewsbr_owner and so
-- needs no separate schema grant.
GRANT USAGE ON SCHEMA public TO stocknewsbr_owner;

GRANT USAGE ON SCHEMA public TO stocknewsbr_app;
GRANT USAGE ON SCHEMA public TO stocknewsbr_worker;
GRANT USAGE ON SCHEMA public TO stocknewsbr_readonly;
GRANT USAGE ON SCHEMA public TO stocknewsbr_backup;

-- TEMPORARY is granted to PUBLIC by default at database level. A direct
-- REVOKE from the backup role would not override that inherited PUBLIC grant,
-- so remove the ambient grant from this database. No StockNewsBR runtime role
-- currently requires temporary-table DDL; any future need must be explicit.
DO $$
BEGIN
    EXECUTE format(
        'REVOKE TEMPORARY ON DATABASE %I FROM PUBLIC, stocknewsbr_backup',
        current_database()
    );
END
$$;

REVOKE ALL ON public.media_assets      FROM PUBLIC;
REVOKE ALL ON public.promo_redemptions FROM PUBLIC;
REVOKE ALL ON public.promo_codes       FROM PUBLIC;

REVOKE ALL ON public.media_assets      FROM stocknewsbr_app, stocknewsbr_worker, stocknewsbr_readonly, stocknewsbr_backup, stocknewsbr_migration;
REVOKE ALL ON public.promo_redemptions FROM stocknewsbr_app, stocknewsbr_worker, stocknewsbr_readonly, stocknewsbr_backup, stocknewsbr_migration;
REVOKE ALL ON public.promo_codes       FROM stocknewsbr_app, stocknewsbr_worker, stocknewsbr_readonly, stocknewsbr_backup, stocknewsbr_migration;

-- Table-level REVOKE does not remove grants made directly on columns. Strip
-- every column ACL for the controlled tables before rebuilding the exact
-- column-level contract below (currently only promo_codes.current_uses).
DO $$
DECLARE
    controlled_table record;
BEGIN
    FOR controlled_table IN
        SELECT column_definition.table_name,
               string_agg(
                   format('%I', column_definition.column_name),
                   ', '
                   ORDER BY column_definition.ordinal_position
               ) AS column_list
        FROM information_schema.columns AS column_definition
        WHERE column_definition.table_schema = 'public'
          AND column_definition.table_name IN (
              'media_assets', 'promo_redemptions', 'promo_codes'
          )
        GROUP BY column_definition.table_name
    LOOP
        EXECUTE format(
            'REVOKE ALL PRIVILEGES (%s) ON TABLE public.%I '
            'FROM stocknewsbr_app, stocknewsbr_worker, stocknewsbr_readonly, '
            'stocknewsbr_backup, stocknewsbr_migration',
            controlled_table.column_list,
            controlled_table.table_name
        );
    END LOOP;
END
$$;

REVOKE ALL ON SEQUENCE public.media_assets_id_seq      FROM stocknewsbr_app, stocknewsbr_worker, stocknewsbr_readonly, stocknewsbr_backup, stocknewsbr_migration;
REVOKE ALL ON SEQUENCE public.promo_redemptions_id_seq FROM stocknewsbr_app, stocknewsbr_worker, stocknewsbr_readonly, stocknewsbr_backup, stocknewsbr_migration;
REVOKE ALL ON SEQUENCE public.promo_codes_id_seq       FROM stocknewsbr_app, stocknewsbr_worker, stocknewsbr_readonly, stocknewsbr_backup, stocknewsbr_migration;


-- =====================================================================
-- 5. EXPLICIT TABLE GRANTS (least privilege, no GRANT ALL)
-- =====================================================================

-- media_assets: full owner-scoped DML for the application (rows are
-- still constrained by RLS below).
GRANT SELECT, INSERT, UPDATE, DELETE ON public.media_assets TO stocknewsbr_app;

-- promo_redemptions: the application may only read and create its own
-- redemptions. UPDATE and DELETE are intentionally withheld.
GRANT SELECT, INSERT ON public.promo_redemptions TO stocknewsbr_app;

-- promo_codes: the application reads codes and may update ONLY current_uses
-- during a redemption. Administrative columns remain immutable to the app.
GRANT SELECT ON public.promo_codes TO stocknewsbr_app;
GRANT UPDATE (current_uses) ON public.promo_codes TO stocknewsbr_app;


-- =====================================================================
-- 6. EXPLICIT SEQUENCE GRANTS
-- Only the identity sequences the application actually inserts into.
-- promo_codes_id_seq is NOT granted to the application (no INSERT).
-- =====================================================================

GRANT USAGE, SELECT ON SEQUENCE public.media_assets_id_seq      TO stocknewsbr_app;
GRANT USAGE, SELECT ON SEQUENCE public.promo_redemptions_id_seq TO stocknewsbr_app;


-- =====================================================================
-- 7. BACKUP GRANTS (read only)
-- The backup role reads every CURRENT table and sequence so pg_dump can produce
-- a complete logical backup. RLS still applies: the two controlled tables use
-- explicit USING (true) backup policies below, and pg_dump must opt in to row
-- security. No default SELECT is granted for future objects, so every schema
-- expansion must consciously update this migration and its restore proof.
-- It has no INSERT / UPDATE / DELETE / TRUNCATE / DDL, and no BYPASSRLS.
-- Row visibility is provided by the dedicated backup policies (section 9).
-- =====================================================================

GRANT SELECT ON public.media_assets      TO stocknewsbr_backup;
GRANT SELECT ON public.promo_redemptions TO stocknewsbr_backup;

GRANT SELECT ON SEQUENCE public.media_assets_id_seq      TO stocknewsbr_backup;
GRANT SELECT ON SEQUENCE public.promo_redemptions_id_seq TO stocknewsbr_backup;

GRANT SELECT ON ALL TABLES IN SCHEMA public TO stocknewsbr_backup;
GRANT SELECT ON ALL SEQUENCES IN SCHEMA public TO stocknewsbr_backup;


-- =====================================================================
-- 8. ROW LEVEL SECURITY — media_assets
-- Owner-scoped access for the application role. FORCE guarantees the
-- table owner is also subject to the policies. Absent RLS context makes
-- current_setting() return '' -> NULLIF -> NULL, which denies every row.
-- =====================================================================

ALTER TABLE public.media_assets ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.media_assets FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS media_assets_app_select ON public.media_assets;
CREATE POLICY media_assets_app_select
    ON public.media_assets
    FOR SELECT
    TO stocknewsbr_app
    USING (
        owner_user_id = NULLIF(current_setting('app.current_user_id', true), '')::integer
    );

DROP POLICY IF EXISTS media_assets_app_insert ON public.media_assets;
CREATE POLICY media_assets_app_insert
    ON public.media_assets
    FOR INSERT
    TO stocknewsbr_app
    WITH CHECK (
        owner_user_id = NULLIF(current_setting('app.current_user_id', true), '')::integer
    );

DROP POLICY IF EXISTS media_assets_app_update ON public.media_assets;
CREATE POLICY media_assets_app_update
    ON public.media_assets
    FOR UPDATE
    TO stocknewsbr_app
    USING (
        owner_user_id = NULLIF(current_setting('app.current_user_id', true), '')::integer
    )
    WITH CHECK (
        owner_user_id = NULLIF(current_setting('app.current_user_id', true), '')::integer
    );

DROP POLICY IF EXISTS media_assets_app_delete ON public.media_assets;
CREATE POLICY media_assets_app_delete
    ON public.media_assets
    FOR DELETE
    TO stocknewsbr_app
    USING (
        owner_user_id = NULLIF(current_setting('app.current_user_id', true), '')::integer
    );


-- =====================================================================
-- 9. ROW LEVEL SECURITY — promo_redemptions
-- The application may only read and insert its own redemptions. There is
-- deliberately NO update/delete policy (and no update/delete grant), so
-- corrections are only possible through the controlled migration/owner
-- path in a later gate.
-- =====================================================================

ALTER TABLE public.promo_redemptions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.promo_redemptions FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS promo_redemptions_app_select ON public.promo_redemptions;
CREATE POLICY promo_redemptions_app_select
    ON public.promo_redemptions
    FOR SELECT
    TO stocknewsbr_app
    USING (
        user_id = NULLIF(current_setting('app.current_user_id', true), '')::integer
    );

DROP POLICY IF EXISTS promo_redemptions_app_insert ON public.promo_redemptions;
CREATE POLICY promo_redemptions_app_insert
    ON public.promo_redemptions
    FOR INSERT
    TO stocknewsbr_app
    WITH CHECK (
        user_id = NULLIF(current_setting('app.current_user_id', true), '')::integer
    );


-- =====================================================================
-- 10. OWNER ADMINISTRATIVE POLICIES
-- FORCE ROW LEVEL SECURITY makes the owner obey RLS as well, which would
-- otherwise block the controlled migration/backfill path. These policies
-- restore full DML for the owner role ONLY (assumed exclusively through
-- `SET ROLE stocknewsbr_owner` from the migration role). No application
-- role and no BYPASSRLS is involved; FORCE RLS stays in effect.
-- =====================================================================

DROP POLICY IF EXISTS media_assets_owner_admin ON public.media_assets;
CREATE POLICY media_assets_owner_admin
    ON public.media_assets
    FOR ALL
    TO stocknewsbr_owner
    USING (true)
    WITH CHECK (true);

DROP POLICY IF EXISTS promo_redemptions_owner_admin ON public.promo_redemptions;
CREATE POLICY promo_redemptions_owner_admin
    ON public.promo_redemptions
    FOR ALL
    TO stocknewsbr_owner
    USING (true)
    WITH CHECK (true);


-- =====================================================================
-- 11. BACKUP POLICIES (read only, TO stocknewsbr_backup, USING (true))
-- Dedicated SELECT visibility for logical backups without BYPASSRLS.
-- =====================================================================

DROP POLICY IF EXISTS media_assets_backup_read ON public.media_assets;
CREATE POLICY media_assets_backup_read
    ON public.media_assets
    FOR SELECT
    TO stocknewsbr_backup
    USING (true);

DROP POLICY IF EXISTS promo_redemptions_backup_read ON public.promo_redemptions;
CREATE POLICY promo_redemptions_backup_read
    ON public.promo_redemptions
    FOR SELECT
    TO stocknewsbr_backup
    USING (true);


-- =====================================================================
-- 12. DEFAULT PRIVILEGES
-- New objects owned by the owner role never grant to PUBLIC and never
-- grant DML to the application/worker automatically. Every new table or
-- sequence requires an explicit grant in a migration, and every new RLS
-- table requires an explicit backup policy. Backup default SELECT is
-- intentionally NOT granted, so each new table is a deliberate decision.
-- =====================================================================

ALTER DEFAULT PRIVILEGES FOR ROLE stocknewsbr_owner IN SCHEMA public
    REVOKE ALL ON TABLES FROM PUBLIC;

ALTER DEFAULT PRIVILEGES FOR ROLE stocknewsbr_owner IN SCHEMA public
    REVOKE ALL ON SEQUENCES FROM PUBLIC;

-- PostgreSQL's built-in PUBLIC EXECUTE/USAGE defaults are global. These two
-- revocations must therefore be global as well; a per-schema REVOKE cannot
-- subtract a privilege inherited from the global default ACL.
ALTER DEFAULT PRIVILEGES FOR ROLE stocknewsbr_owner
    REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC;

ALTER DEFAULT PRIVILEGES FOR ROLE stocknewsbr_owner
    REVOKE USAGE ON TYPES FROM PUBLIC;


COMMIT;

-- End of Mission 36 — Gate 3.2 roles/RLS script.
