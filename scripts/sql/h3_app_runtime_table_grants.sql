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
--
-- PER-TABLE JUSTIFICATION (verified against actual ORM/query usage, not
-- granted speculatively -- every verb below is exercised by a real code
-- path, and no verb is granted that is not):
--   users                   -- SELECT: auth lookup by id/email on every
--                              request (app/security.py). INSERT: account
--                              registration (app/auth.py register()).
--                              UPDATE: refresh_user_access()/official
--                              identity sync mutate plan/access/timestamp
--                              columns in place. No DELETE: users are never
--                              hard-deleted, only deactivated (is_active).
--   user_sessions           -- SELECT/INSERT for session issuance and
--                              lookup (app/security.py resolve_token_user).
--                              UPDATE for revoke/last_seen_at
--                              (auth_session_service.revoke_session /
--                              revoke_all_sessions). No DELETE anywhere in
--                              the codebase -- sessions are soft-revoked
--                              (revoked_at/revoked_reason), never removed.
--   login_challenges        -- SELECT/INSERT to issue and look up OTP
--                              challenges. UPDATE only (SQLAlchemy Core
--                              `update(LoginChallenge)...values(...)` for
--                              consumed_at/invalidated_at/attempt_count in
--                              auth_session_service.py). No DELETE call
--                              exists for this model.
--   auth_audit_events       -- SELECT/INSERT only: append-only audit trail
--                              (auth_audit_service.py). Never updated or
--                              deleted by the application, matching Mission
--                              36's own treatment of audit-shaped tables.
--   referrals               -- SELECT/INSERT/UPDATE: referral creation and
--                              validation state transitions
--                              (services/referrals.py apply_referral_
--                              validation/_sync_referrer_stats mutate rows
--                              in place). No delete() call exists.
--   referral_stats          -- SELECT/INSERT/UPDATE: per-user aggregate
--                              counters created and incremented in place
--                              (services/referrals.py _ensure_stats/
--                              _apply_reward_months). No delete() call
--                              exists; primary key is user_id (no surrogate
--                              identity sequence to grant).
--   telegram_link_tokens    -- SELECT/INSERT to issue a link code
--                              (auth_session_service.py). UPDATE only, to
--                              set consumed_at when a code is used or
--                              superseded. No DELETE call exists.
--   subscription_audit_logs -- SELECT/INSERT only: append-only billing
--                              event trail, same audit-table pattern as
--                              auth_audit_events. Never mutated or deleted.
--   social_posts            -- SELECT/INSERT/UPDATE/DELETE: authors edit
--                              and hard-delete their own posts
--                              (app/social/posts.py delete_post() calls
--                              db.delete(post) plus cascading cleanup of
--                              child rows below).
--   social_comments         -- SELECT/INSERT/UPDATE/DELETE: comment
--                              CRUD, including the bulk
--                              `.filter(post_id=...).delete()` cascade run
--                              when the parent post is deleted.
--   social_likes            -- SELECT/INSERT/DELETE: like/unlike toggle
--                              (app/social/likes.py unlike_post() calls
--                              db.delete(row)). No UPDATE: a like has no
--                              mutable field, only exists or not.
--   social_reposts          -- SELECT/INSERT/DELETE: repost/un-repost
--                              toggle (app/social/reposts.py
--                              delete_repost() calls db.delete(row)).
--   social_follows          -- SELECT/INSERT/DELETE: follow/unfollow
--                              toggle (app/social/followers.py unfollow()
--                              calls db.delete(row)).
--   social_sentiment_votes  -- SELECT/INSERT/UPDATE: one vote per
--                              (ticker, user) is upserted in place
--                              (app/social/sentiment_poll.py vote() sets
--                              row.sentiment = sentiment when a prior vote
--                              exists). No DELETE call exists.
--
-- RLS APPLICABILITY: none of the 14 tables below carry a Postgres RLS
-- policy. This is an existing architectural choice inherited from Mission
-- 36 (which scoped RLS to media_assets/promo_redemptions only), not a new
-- decision made here -- H3's mandate was to prove that existing design on
-- real PostgreSQL, not to redesign the isolation model for every table
-- that happens to carry a user_id. Isolation for these 14 tables is
-- enforced at the application layer: every read/write path above is
-- always scoped by an explicit user_id/session_id/post_id predicate tied
-- to the authenticated caller (never a client-supplied tenant id). This is
-- weaker defense-in-depth than RLS and is flagged here explicitly as a
-- residual gap worth a dedicated follow-up hardening pass, not something
-- silently left unmentioned.
-- =====================================================================

BEGIN;

GRANT SELECT, INSERT, UPDATE ON public.users TO stocknewsbr_app, stocknewsbr_worker;
GRANT SELECT, INSERT, UPDATE ON public.user_sessions TO stocknewsbr_app, stocknewsbr_worker;
GRANT SELECT, INSERT, UPDATE ON public.login_challenges TO stocknewsbr_app, stocknewsbr_worker;
GRANT SELECT, INSERT ON public.auth_audit_events TO stocknewsbr_app, stocknewsbr_worker;
GRANT SELECT, INSERT, UPDATE ON public.referrals TO stocknewsbr_app, stocknewsbr_worker;
GRANT SELECT, INSERT, UPDATE ON public.referral_stats TO stocknewsbr_app, stocknewsbr_worker;
GRANT SELECT, INSERT, UPDATE ON public.telegram_link_tokens TO stocknewsbr_app, stocknewsbr_worker;
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
