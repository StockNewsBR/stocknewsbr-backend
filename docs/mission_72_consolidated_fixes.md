# Mission 72 — Consolidated Fixes (in progress)

**Repo:** `/home/dcima/stocknewsbr-backend` · branch `fix/audit-remediation-2026-07` · HEAD `a51c0847`
**Backups:** `/tmp/stocknewsbr-m72-backup/` (dependencies.py, routes_public_market_live.py before edit)
**No commit / no push.** Working tree already had 36 pre-existing user changes — NOT reverted.

---

## DONE this session

### P0 — Premium gating (server-side entitlement) — IMPLEMENTED, SAFE, TESTED
Real finding (validated): `/public/market/bundle/{symbol}` returns full premium data
(strategic_panel, master_score=3.9, ai_tools) to anonymous curl with HTTP 200 — the
frontend "Pro" lock is cosmetic only.

- **`app/dependencies.py`** — new `resolve_premium_entitlement(token, db) -> bool`: optional,
  never-raising (a bad/absent token → False, not 401). Premium = plan in
  `{trial, premium, enterprise}` (reuses `get_request_token`/`resolve_token_user`/`refresh_user_access`).
- **`app/api/routes_public_market_live.py`** — `_gate_bundle_for_entitlement(payload, is_premium)`
  redacts `insight.{strategic_panel,master_score*,institutional_flow}` and `ai_tools` for non-premium,
  keeps public fields (quote, chart, news). Wired into `public_market_bundle` via
  `Depends(resolve_premium_entitlement)`. Behind env flag **`STOCKNEWS_PREMIUM_GATING` (default OFF)**.
- **`tests/test_premium_gating.py`** — 3 cases PASS: anon-redacted / pro-full / flag-off-noop.
- **Live verified:** backend restarted, flag OFF → bundle anon still HTTP 200 + full data
  (`premium_locked: None`) → app NOT broken. Resolver does not 401 anon.
- **To activate:** set `STOCKNEWS_PREMIUM_GATING=1` AFTER the frontend renders a "Disponível no Pro"
  state for redacted premium fields (otherwise Básico/anon cards go empty).
- ceiling (`ponytail:`): redaction list is explicit; frontend "Disponível no Pro" handling +
  the 12 entitlement tests (Trial/expired/invalid-token/query-force) still owed.

### Lint (Section 8) — FIXED
4 real `react/no-unescaped-entities` errors in `workspace-shell.tsx` (12531, 12607) →
escaped `"` to `&quot;` (Stock Flow editorial quote + chat text). Only entity escaping,
no WIP logic touched. **lint errors 4 → 0**, tsc 0.

---

## Validated against the audits (do NOT re-patch)

- **401 on `/public/market/quote/{symbol}` (M71-008) — report WRONG.** Route EXISTS
  (`routes_public_market.py:106`, `Depends(require_channel_access("web"))`). 401 for an
  unauthenticated curl is EXPECTED. Not "route inexistente", not a broken fallback to fix.
  (Irony: singular quote is protected while the full bundle is wide open → the real gap is P0 gating.)
- **`tool=all` (M71-007) — frontend does NOT use it.** `getPublicAiTools(symbol, tool)` passes
  specific tools (`api.ts:327`); the global fetch has no `tool` param. Low priority; don't patch for a manual curl.
- **News CSNA3 `.SA` and relevance-filter hypotheses — DISCARDED (executed).**
  `provider_symbol("CSNA3")="CSNA3.SA"`; `_fetch_yfinance_news("CSNA3.SA")=10 raw`;
  `build_symbol_news_with_report("CSNA3", raw)=6 items` (`discard_reasons={}`). The pipeline
  PRODUCES 6. The endpoint returns 0 because it is **cache-only (`allow_fetch=False`) and the
  CSNA3 cache is empty** — a warmup/cache-population gap, NOT the filter or `.SA`.
- **Liquidity `upper==lower`** — weekend single-close-point artifact; keep pending live-session proof.

---

## Traces for the remaining items (for Codex/Gemini continuation)

- **On-demand snapshot (CSNA3/HYPE3 no score/panel/flow):** these are outside the 10-symbol
  global snapshot; on-demand hydration builds quote/rsi but not `master_score`/`strategic_panel`.
  Fix generically: run the SAME canonical enrichment chain for on-demand symbols
  (`build_snapshot_payload([seed])` already produces a full panel per seed — proven earlier).
  Do NOT add CSNA3/HYPE3 to a fixed list.
- **institutional_flow null in bundle:** for in-snapshot symbols it's READY (PETR4=65.0). Null is
  for out-of-snapshot symbols → same root as on-demand snapshot. Frontend "Sem leitura" =
  `resolveFlowCard` (`workspace-shell.tsx:4355`) firing on empty rows.
- **Sentiment per-asset:** `value=None` literal (`routes_public_market_live.py:781`). Feature never
  built. Implement deterministic aggregation of the symbol's news sentiment (no LLM per render),
  with sample_size/confidence/source/as_of.
- **PETR4 quote flicker (live bug):** `_resolve_cached_quote` (`routes:934`) HAS a stale fallback;
  the empty result appears only when the warmup writes a price-less payload OVER a READY one, so no
  candidate is usable even as stale. Root is the cache WRITE — add a guard so an empty/PENDING
  refresh never overwrites a usable READY quote (find the write in `market_data_loader.py`).

## Operational note
The "whole screen broken" episodes were the **backend running degraded (no engine workers)**.
`bash /home/dcima/stocknewsbr-artifacts/restart_backend2.sh` restores workers + env + test-mailbox.
Consider a single dev-up script + a public health check (Mission 72 §6 operational items).
