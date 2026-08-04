-- =====================================================================
-- MISSION 36 — GATE 5
-- Read-only verification of the pgAudit configuration.
-- =====================================================================
--
-- SELECT-only. Asserts that pgAudit is loaded, the extension exists, and the
-- audit policy is SELECTIVE (structural + administrative + writes) rather than
-- blanket ('all') or read-heavy ('read'), and that parameter values are NOT
-- logged. Contains no passwords, DSNs or local paths.
--
-- Run with, e.g.:
--   psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f scripts/sql/mission_36_pgaudit_verify.sql
-- =====================================================================


-- 1. pgAudit extension is installed.
SELECT 'pgaudit_extension_installed' AS check,
       count(*) = 1 AS passed
FROM pg_extension WHERE extname = 'pgaudit';

-- 2. pgAudit library is preloaded (session audit logging active).
SELECT 'pgaudit_library_preloaded' AS check,
       'pgaudit' = ANY (
           string_to_array(
               regexp_replace(
                   lower(coalesce(current_setting('shared_preload_libraries', true), '')),
                   '[[:space:]]',
                   '',
                   'g'
               ),
               ','
           )
       ) AS passed;

-- 3. The selective class set is exactly DDL, ROLE and WRITE.
SELECT 'pgaudit_log_has_ddl_role_write' AS check,
       string_to_array(
           regexp_replace(
               lower(coalesce(current_setting('pgaudit.log', true), '')),
               '[[:space:]]',
               '',
               'g'
           ),
           ','
       ) @> ARRAY['ddl', 'role', 'write']::text[]
   AND cardinality(
           string_to_array(
               regexp_replace(
                   lower(coalesce(current_setting('pgaudit.log', true), '')),
                   '[[:space:]]',
                   '',
                   'g'
               ),
               ','
           )
       ) = 3 AS passed;

-- 4. NOT auditing everything ('all' would be indiscriminate).
SELECT 'pgaudit_log_not_all' AS check,
       lower(coalesce(current_setting('pgaudit.log', true), '')) NOT LIKE '%all%' AS passed;

-- 5. READ is NOT globally audited (avoids volume + logging sensitive queries).
SELECT 'pgaudit_log_no_read' AS check,
       lower(coalesce(current_setting('pgaudit.log', true), '')) NOT LIKE '%read%' AS passed;

-- 6. Bound parameter VALUES are never logged.
SELECT 'pgaudit_log_parameter_off' AS check,
       lower(coalesce(current_setting('pgaudit.log_parameter', true), 'on')) = 'off' AS passed;

-- 7. Catalog access is not audited (suppresses noise).
SELECT 'pgaudit_log_catalog_off' AS check,
       lower(coalesce(current_setting('pgaudit.log_catalog', true), 'on')) = 'off' AS passed;

-- 8. Relation-level rows are emitted (per-object granularity).
SELECT 'pgaudit_log_relation_on' AS check,
       lower(coalesce(current_setting('pgaudit.log_relation', true), 'off')) = 'on' AS passed;

-- 9. Each statement is logged once (bounds duplication / volume).
SELECT 'pgaudit_log_statement_once_on' AS check,
       lower(coalesce(current_setting('pgaudit.log_statement_once', true), 'off')) = 'on' AS passed;

-- 10. The application role cannot bypass auditing (no SUPERUSER / BYPASSRLS).
SELECT 'app_role_cannot_bypass_audit' AS check,
       count(*) = 1
   AND coalesce(bool_and(NOT rolsuper AND NOT rolbypassrls), false) AS passed
FROM pg_roles WHERE rolname = 'stocknewsbr_app';

-- End of Mission 36 — Gate 5 pgAudit verification script (read-only).
