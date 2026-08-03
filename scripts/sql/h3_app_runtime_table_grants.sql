-- =====================================================================
-- H3 — RUNTIME GRANTS FOR TABLES OUTSIDE THE MISSION 36 RLS SCOPE
-- =====================================================================
--
-- WHY THIS FILE EXISTS:
--   Mission 36 (scripts/sql/mission_36_postgresql_roles_rls.sql) deliberately
--   scoped Row Level Security to media_assets and promo_redemptions only. It
--   never granted stocknewsbr_app/stocknewsbr_worker any privileges on the
--   application's other operational tables (users, user_sessions,
--   login_challenges, auth_audit_events, referrals, referral_stats,
--   telegram_link_tokens, subscription_audit_logs, social_*). Those tables
--   have no RLS policies at all -- isolation for them is enforced at the
--   application layer (explicit WHERE user_id = ... in queries), matching
--   the existing architecture, not by Postgres RLS.
--
--   Without this file, the FastAPI application cannot authenticate a single
--   request when DATABASE_URL points at the stocknewsbr_app role: even
--   reading the users/user_sessions tables during login fails with
--   "permission denied for table users". This was discovered while wiring
--   Gate/FASE 11 (real runtime integration) against the isolated H3
--   PostgreSQL cluster, and is the minimal, explicitly-justified addition
--   needed to run the app for real -- not a new RLS surface.
--
-- SCOPE:
--   Grants ordinary (non-RLS) least-needed DML to stocknewsbr_app and
--   stocknewsbr_worker on the tables the runtime and worker actually touch.
--   No policy is added here. No BYPASSRLS. No superuser. Idempotent:
--   GRANT is naturally re-appliable (PostgreSQL GRANT is not additive-error
--   on repeat) and sequence grants likewise.
-- =====================================================================

BEGIN;

GRANT SELECT, INSERT, UPDATE ON public.users TO stocknewsbr_app, stocknewsbr_worker;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.user_sessions TO stocknewsbr_app, stocknewsbr_worker;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.login_challenges TO stocknewsbr_app, stocknewsbr_worker;
GRANT SELECT, INSERT ON public.auth_audit_events TO stocknewsbr_app, stocknewsbr_worker;
GRANT SELECT, INSERT, UPDATE ON public.referrals TO stocknewsbr_app, stocknewsbr_worker;
GRANT SELECT, INSERT, UPDATE ON public.referral_stats TO stocknewsbr_app, stocknewsbr_worker;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.telegram_link_tokens TO stocknewsbr_app, stocknewsbr_worker;
GRANT SELECT, INSERT ON public.subscription_audit_logs TO stocknewsbr_app, stocknewsbr_worker;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.social_posts TO stocknewsbr_app, stocknewsbr_worker;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.social_comments TO stocknewsbr_app, stocknewsbr_worker;
GRANT SELECT, INSERT, DELETE ON public.social_likes TO stocknewsbr_app, stocknewsbr_worker;
GRANT SELECT, INSERT, DELETE ON public.social_reposts TO stocknewsbr_app, stocknewsbr_worker;
GRANT SELECT, INSERT, DELETE ON public.social_follows TO stocknewsbr_app, stocknewsbr_worker;
GRANT SELECT, INSERT, UPDATE ON public.social_sentiment_votes TO stocknewsbr_app, stocknewsbr_worker;

GRANT USAGE, SELECT ON SEQUENCE public.users_id_seq TO stocknewsbr_app, stocknewsbr_worker;
GRANT USAGE, SELECT ON SEQUENCE public.user_sessions_id_seq TO stocknewsbr_app, stocknewsbr_worker;
GRANT USAGE, SELECT ON SEQUENCE public.login_challenges_id_seq TO stocknewsbr_app, stocknewsbr_worker;
GRANT USAGE, SELECT ON SEQUENCE public.auth_audit_events_id_seq TO stocknewsbr_app, stocknewsbr_worker;
GRANT USAGE, SELECT ON SEQUENCE public.referrals_id_seq TO stocknewsbr_app, stocknewsbr_worker;
GRANT USAGE, SELECT ON SEQUENCE public.telegram_link_tokens_id_seq TO stocknewsbr_app, stocknewsbr_worker;
GRANT USAGE, SELECT ON SEQUENCE public.subscription_audit_logs_id_seq TO stocknewsbr_app, stocknewsbr_worker;
GRANT USAGE, SELECT ON SEQUENCE public.social_posts_id_seq TO stocknewsbr_app, stocknewsbr_worker;
GRANT USAGE, SELECT ON SEQUENCE public.social_comments_id_seq TO stocknewsbr_app, stocknewsbr_worker;
GRANT USAGE, SELECT ON SEQUENCE public.social_likes_id_seq TO stocknewsbr_app, stocknewsbr_worker;
GRANT USAGE, SELECT ON SEQUENCE public.social_reposts_id_seq TO stocknewsbr_app, stocknewsbr_worker;
GRANT USAGE, SELECT ON SEQUENCE public.social_follows_id_seq TO stocknewsbr_app, stocknewsbr_worker;
GRANT USAGE, SELECT ON SEQUENCE public.social_sentiment_votes_id_seq TO stocknewsbr_app, stocknewsbr_worker;

COMMIT;

-- End of H3 runtime grants (non-RLS operational tables).
