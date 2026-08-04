-- =====================================================================
-- MISSION 36 — GATE 3.2
-- Read-only verification of roles, grants and RLS policies.
-- =====================================================================
--
-- This script MUST NOT modify the database. It only issues SELECT
-- statements against the system catalogs and privilege functions. Each
-- check returns a stable label plus a boolean `passed` column so the
-- output can be asserted mechanically.
--
-- Run with, e.g.:
--   psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f scripts/sql/mission_36_verify.sql
-- =====================================================================


-- 1. All six roles exist.
SELECT 'roles_exist' AS check,
       count(*) = 6
   AND coalesce(
           bool_and(
               rolname = ANY (ARRAY[
                   'stocknewsbr_owner',
                   'stocknewsbr_app',
                   'stocknewsbr_worker',
                   'stocknewsbr_readonly',
                   'stocknewsbr_backup',
                   'stocknewsbr_migration'
               ]::name[])
           ),
           false
       ) AS passed
FROM pg_roles
WHERE rolname LIKE 'stocknewsbr\_%';

-- 2. No stocknewsbr role is SUPERUSER.
SELECT 'no_superuser' AS check,
       count(*) = 6
   AND coalesce(bool_and(NOT rolsuper), false) AS passed
FROM pg_roles
WHERE rolname LIKE 'stocknewsbr\_%';

-- 3. No stocknewsbr role can BYPASSRLS.
SELECT 'no_bypassrls' AS check,
       count(*) = 6
   AND coalesce(bool_and(NOT rolbypassrls), false) AS passed
FROM pg_roles
WHERE rolname LIKE 'stocknewsbr\_%';

-- 4. No stocknewsbr role has CREATEDB, CREATEROLE or REPLICATION.
SELECT 'no_createdb_no_createrole_no_replication' AS check,
       count(*) = 6
   AND coalesce(
           bool_and(NOT rolcreatedb AND NOT rolcreaterole AND NOT rolreplication),
           false
       ) AS passed
FROM pg_roles
WHERE rolname LIKE 'stocknewsbr\_%';

-- 5. LOGIN / NOLOGIN attributes per role model.
SELECT 'login_attributes' AS check,
       count(*) = 6
   AND coalesce(bool_and(
           CASE rolname
               WHEN 'stocknewsbr_owner'     THEN NOT rolcanlogin
               WHEN 'stocknewsbr_app'       THEN rolcanlogin
               WHEN 'stocknewsbr_worker'    THEN rolcanlogin
               WHEN 'stocknewsbr_readonly'  THEN NOT rolcanlogin
               WHEN 'stocknewsbr_backup'    THEN rolcanlogin
               WHEN 'stocknewsbr_migration' THEN NOT rolcanlogin
               ELSE false
           END
       ), false) AS passed
FROM pg_roles
WHERE rolname LIKE 'stocknewsbr\_%';

-- 6. INHERIT / NOINHERIT attributes per role model.
SELECT 'inherit_attributes' AS check,
       count(*) = 6
   AND coalesce(bool_and(
           CASE rolname
               WHEN 'stocknewsbr_owner'     THEN NOT rolinherit
               WHEN 'stocknewsbr_migration' THEN NOT rolinherit
               ELSE rolinherit
           END
       ), false) AS passed
FROM pg_roles
WHERE rolname LIKE 'stocknewsbr\_%';

-- 7. The complete membership graph involving StockNewsBR roles contains
-- exactly migration -> owner, with SET allowed and ADMIN OPTION denied.
SELECT 'membership_owner_only_migration' AS check,
       count(*) = 1
   AND coalesce(
           bool_and(
               parent.rolname = 'stocknewsbr_owner'
               AND child.rolname = 'stocknewsbr_migration'
               AND NOT membership.admin_option
               AND NOT membership.inherit_option
               AND membership.set_option
           ),
           false
       ) AS passed
FROM pg_auth_members AS membership
JOIN pg_roles AS parent ON parent.oid = membership.roleid
JOIN pg_roles AS child ON child.oid = membership.member
WHERE parent.rolname LIKE 'stocknewsbr\_%'
   OR child.rolname LIKE 'stocknewsbr\_%';

-- 8. No app-facing role is a member of owner or migration.
SELECT 'no_appfacing_membership' AS check,
       NOT EXISTS (
           SELECT 1
           FROM pg_auth_members m
           JOIN pg_roles parent ON parent.oid = m.roleid
           JOIN pg_roles child  ON child.oid = m.member
           WHERE parent.rolname IN ('stocknewsbr_owner', 'stocknewsbr_migration')
             AND child.rolname IN (
                 'stocknewsbr_app',
                 'stocknewsbr_worker',
                 'stocknewsbr_readonly',
                 'stocknewsbr_backup'
             )
       ) AS passed;

-- 9. The in-scope tables are owned by the owner role.
SELECT 'ownership_owner' AS check,
       count(*) = 3
   AND coalesce(bool_and(tableowner = 'stocknewsbr_owner'), false) AS passed
FROM pg_tables
WHERE schemaname = 'public'
  AND tablename IN ('media_assets', 'promo_redemptions', 'promo_codes');

-- 10. The application role has no CREATE on the public schema.
SELECT 'app_no_schema_create' AS check,
       NOT has_schema_privilege('stocknewsbr_app', 'public', 'CREATE') AS passed;

-- 11. Application table grants are exactly as expected.
SELECT 'app_media_grants' AS check,
       has_table_privilege('stocknewsbr_app', 'public.media_assets', 'SELECT')
   AND has_table_privilege('stocknewsbr_app', 'public.media_assets', 'INSERT')
   AND has_table_privilege('stocknewsbr_app', 'public.media_assets', 'UPDATE')
   AND has_table_privilege('stocknewsbr_app', 'public.media_assets', 'DELETE') AS passed;

SELECT 'app_promo_redemptions_grants' AS check,
       has_table_privilege('stocknewsbr_app', 'public.promo_redemptions', 'SELECT')
   AND has_table_privilege('stocknewsbr_app', 'public.promo_redemptions', 'INSERT') AS passed;

-- 12. The application role has NO update/delete on promo_redemptions.
SELECT 'app_no_update_delete_promo_redemptions' AS check,
       NOT has_table_privilege('stocknewsbr_app', 'public.promo_redemptions', 'UPDATE')
   AND NOT has_table_privilege('stocknewsbr_app', 'public.promo_redemptions', 'DELETE') AS passed;

SELECT 'app_promo_codes_grants' AS check,
       has_table_privilege('stocknewsbr_app', 'public.promo_codes', 'SELECT')
   AND NOT has_table_privilege('stocknewsbr_app', 'public.promo_codes', 'UPDATE')
   AND has_column_privilege(
       'stocknewsbr_app', 'public.promo_codes', 'current_uses', 'UPDATE'
   )
   AND NOT EXISTS (
       SELECT 1
       FROM information_schema.columns AS column_definition
       WHERE column_definition.table_schema = 'public'
         AND column_definition.table_name = 'promo_codes'
         AND column_definition.column_name <> 'current_uses'
         AND has_column_privilege(
             'stocknewsbr_app',
             'public.promo_codes',
             column_definition.column_name,
             'UPDATE'
         )
   )
   AND NOT has_table_privilege('stocknewsbr_app', 'public.promo_codes', 'INSERT')
   AND NOT has_table_privilege('stocknewsbr_app', 'public.promo_codes', 'DELETE') AS passed;

-- 13. Sequence grants for the application role.
SELECT 'app_sequence_grants' AS check,
       has_sequence_privilege('stocknewsbr_app', 'public.media_assets_id_seq', 'USAGE')
   AND has_sequence_privilege('stocknewsbr_app', 'public.promo_redemptions_id_seq', 'USAGE')
   AND NOT has_sequence_privilege('stocknewsbr_app', 'public.promo_codes_id_seq', 'USAGE') AS passed;

-- 14. Backup role has SELECT only (no write) on the in-scope tables.
SELECT 'backup_select_only' AS check,
       has_table_privilege('stocknewsbr_backup', 'public.media_assets', 'SELECT')
   AND has_table_privilege('stocknewsbr_backup', 'public.promo_redemptions', 'SELECT')
   AND NOT has_table_privilege('stocknewsbr_backup', 'public.media_assets', 'INSERT')
   AND NOT has_table_privilege('stocknewsbr_backup', 'public.media_assets', 'UPDATE')
   AND NOT has_table_privilege('stocknewsbr_backup', 'public.media_assets', 'DELETE')
   AND NOT has_table_privilege('stocknewsbr_backup', 'public.promo_redemptions', 'INSERT')
   AND NOT has_table_privilege('stocknewsbr_backup', 'public.promo_redemptions', 'UPDATE')
   AND NOT has_table_privilege('stocknewsbr_backup', 'public.promo_redemptions', 'DELETE')
   AND NOT has_schema_privilege('stocknewsbr_backup', 'public', 'CREATE')
   AND NOT has_database_privilege(
       'stocknewsbr_backup', current_database(), 'TEMPORARY'
   ) AS passed;

-- 15. RLS is enabled and forced on both in-scope tables.
SELECT 'rls_enabled_and_forced' AS check,
       count(*) = 2
   AND coalesce(bool_and(relrowsecurity AND relforcerowsecurity), false) AS passed
FROM pg_class
WHERE relnamespace = 'public'::regnamespace
  AND relkind IN ('r', 'p')
  AND relname IN ('media_assets', 'promo_redemptions');

-- 16. media_assets has exactly the four expected application policies.
SELECT 'media_app_policy_commands' AS check,
       coalesce((
           SELECT array_agg(DISTINCT cmd ORDER BY cmd)
           FROM pg_policies
           WHERE schemaname = 'public'
             AND tablename = 'media_assets'
             AND 'stocknewsbr_app' = ANY (roles)
       ), ARRAY[]::text[]) = ARRAY['DELETE', 'INSERT', 'SELECT', 'UPDATE']::text[] AS passed;

-- 17. The media UPDATE policy has both USING and WITH CHECK.
SELECT 'media_update_using_and_check' AS check,
       bool_or(cmd = 'UPDATE' AND qual IS NOT NULL AND with_check IS NOT NULL) AS passed
FROM pg_policies
WHERE schemaname = 'public'
  AND tablename = 'media_assets'
  AND 'stocknewsbr_app' = ANY (roles);

-- 18. promo_redemptions app policies are exactly SELECT and INSERT.
SELECT 'promo_app_policy_commands' AS check,
       coalesce((
           SELECT array_agg(DISTINCT cmd ORDER BY cmd)
           FROM pg_policies
           WHERE schemaname = 'public'
             AND tablename = 'promo_redemptions'
             AND 'stocknewsbr_app' = ANY (roles)
       ), ARRAY[]::text[]) = ARRAY['INSERT', 'SELECT']::text[] AS passed;

-- 19. Backup policies are exactly the two read-all SELECT policies, and the
-- controlled tables contain exactly ten policies in total (no permissive
-- policy can be added without failing this check).
SELECT 'backup_policies_select_true' AS check,
       count(*) = 2
   AND coalesce(
           bool_and(
               cmd = 'SELECT'
               AND roles = ARRAY['stocknewsbr_backup']::name[]
               AND with_check IS NULL
               AND btrim(coalesce(qual, '')) = 'true'
               AND (tablename, policyname) IN (
                   ('media_assets', 'media_assets_backup_read'),
                   ('promo_redemptions', 'promo_redemptions_backup_read')
               )
           ),
           false
       )
   AND (
       SELECT count(*) = 10
       FROM pg_policies AS all_controlled_policies
       WHERE all_controlled_policies.schemaname = 'public'
         AND all_controlled_policies.tablename IN (
             'media_assets', 'promo_redemptions'
         )
   ) AS passed
FROM pg_policies
WHERE schemaname = 'public'
  AND tablename IN ('media_assets', 'promo_redemptions')
  AND 'stocknewsbr_backup' = ANY (roles);

-- 20. Application policies use the exact fail-closed ownership expression.
-- Cosmetic parentheses, whitespace and PostgreSQL's explicit ::text casts
-- are normalized; additional OR/AND terms or a different owner column fail.
SELECT 'app_policies_use_exact_rls_context' AS check,
       count(*) = 6
   AND coalesce(
           bool_and(
               CASE
                   WHEN table_name = 'media_assets'
                    AND policy_name = 'media_assets_app_select' THEN
                       normalized_qual = 'owner_user_id=nullifcurrent_setting''app.current_user_id'',true,''''::integer'
                       AND normalized_check = ''
                   WHEN table_name = 'media_assets'
                    AND policy_name = 'media_assets_app_insert' THEN
                       normalized_qual = ''
                       AND normalized_check = 'owner_user_id=nullifcurrent_setting''app.current_user_id'',true,''''::integer'
                   WHEN table_name = 'media_assets'
                    AND policy_name = 'media_assets_app_update' THEN
                       normalized_qual = 'owner_user_id=nullifcurrent_setting''app.current_user_id'',true,''''::integer'
                       AND normalized_check = 'owner_user_id=nullifcurrent_setting''app.current_user_id'',true,''''::integer'
                   WHEN table_name = 'media_assets'
                    AND policy_name = 'media_assets_app_delete' THEN
                       normalized_qual = 'owner_user_id=nullifcurrent_setting''app.current_user_id'',true,''''::integer'
                       AND normalized_check = ''
                   WHEN table_name = 'promo_redemptions'
                    AND policy_name = 'promo_redemptions_app_select' THEN
                       normalized_qual = 'user_id=nullifcurrent_setting''app.current_user_id'',true,''''::integer'
                       AND normalized_check = ''
                   WHEN table_name = 'promo_redemptions'
                    AND policy_name = 'promo_redemptions_app_insert' THEN
                       normalized_qual = ''
                       AND normalized_check = 'user_id=nullifcurrent_setting''app.current_user_id'',true,''''::integer'
                   ELSE false
               END
           ),
           false
       ) AS passed
FROM (
    SELECT tablename AS table_name,
           policyname AS policy_name,
           regexp_replace(
               lower(coalesce(qual, '')),
               '::text|[()[:space:]]',
               '',
               'g'
           ) AS normalized_qual,
           regexp_replace(
               lower(coalesce(with_check, '')),
               '::text|[()[:space:]]',
               '',
               'g'
           ) AS normalized_check
    FROM pg_policies
    WHERE schemaname = 'public'
      AND tablename IN ('media_assets', 'promo_redemptions')
      AND 'stocknewsbr_app' = ANY (roles)
) app_policy_expressions;

-- 21. Owner administrative policies exist and are correct: exactly two,
-- FOR ALL, granted ONLY to stocknewsbr_owner, with USING (true) and
-- WITH CHECK (true). The expression comparison strips parentheses and
-- whitespace and lowercases, tolerating only cosmetic rendering
-- differences — never a semantically different predicate. Any policy on
-- the wrong table/schema, with the wrong command, a non-owner role
-- (including PUBLIC, app or backup), or a non-true clause is excluded
-- from the count, so a missing or weakened admin policy fails the check.
SELECT 'owner_admin_policies_valid' AS check,
       count(*) = 2 AS passed
FROM pg_policies
WHERE schemaname = 'public'
  AND (tablename, policyname) IN (
      ('media_assets', 'media_assets_owner_admin'),
      ('promo_redemptions', 'promo_redemptions_owner_admin')
  )
  AND cmd = 'ALL'
  AND roles = ARRAY['stocknewsbr_owner']::name[]
  AND btrim(lower(regexp_replace(coalesce(qual, ''), '[()[:space:]]', '', 'g'))) = 'true'
  AND btrim(lower(regexp_replace(coalesce(with_check, ''), '[()[:space:]]', '', 'g'))) = 'true';

-- 22. The owner role must hold USAGE (needed for foreign-key referential-
-- integrity checks that run as the referenced table's owner) but MUST NOT hold
-- CREATE on the public schema. Verified against the live catalog, not the SQL
-- text. A missing USAGE (the Gate 4 defect) or an excessive CREATE fails here.
SELECT 'owner_schema_usage_without_create' AS check,
       has_schema_privilege('stocknewsbr_owner', 'public', 'USAGE') = true
   AND has_schema_privilege('stocknewsbr_owner', 'public', 'CREATE') = false AS passed;

-- 23. The backup identity can read every current table but cannot mutate any.
SELECT 'backup_all_current_tables_read_only' AS check,
       count(*) > 0
   AND coalesce(
           bool_and(
               has_table_privilege('stocknewsbr_backup', format('%I.%I', schemaname, tablename), 'SELECT')
               AND NOT has_table_privilege('stocknewsbr_backup', format('%I.%I', schemaname, tablename), 'INSERT')
               AND NOT has_table_privilege('stocknewsbr_backup', format('%I.%I', schemaname, tablename), 'UPDATE')
               AND NOT has_table_privilege('stocknewsbr_backup', format('%I.%I', schemaname, tablename), 'DELETE')
               AND NOT has_table_privilege('stocknewsbr_backup', format('%I.%I', schemaname, tablename), 'TRUNCATE')
           ),
           false
       ) AS passed
FROM pg_tables
WHERE schemaname = 'public';

-- 24. New owner-created routines and types do not inherit PUBLIC access.
SELECT 'default_privileges_no_public_function_or_type_access' AS check,
       count(*) = 2
   AND coalesce(
           bool_and(
               NOT EXISTS (
                   SELECT 1
                   FROM aclexplode(default_acl.defaclacl) AS acl
                   WHERE acl.grantee = 0
               )
           ),
           false
       ) AS passed
FROM pg_default_acl AS default_acl
JOIN pg_roles AS owner_role ON owner_role.oid = default_acl.defaclrole
WHERE owner_role.rolname = 'stocknewsbr_owner'
  AND default_acl.defaclnamespace = 0
  AND default_acl.defaclobjtype IN ('f', 'T');

-- End of Mission 36 — Gate 3.2 verification script (read-only).
