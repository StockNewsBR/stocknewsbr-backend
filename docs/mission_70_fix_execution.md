# Mission 70 — Fix Execution Log

> ## CONTINUATION (Mission 70b) — ROOT CAUSE OF THE SCREENSHOTS: BACKEND WAS DOWN
>
> The `/site` screenshots ("Sem cotação confirmada", "Dados temporariamente indisponíveis",
> empty cards everywhere) were captured while **the backend on `127.0.0.1:8000` was not running**.
> The frontend defaults to `NEXT_PUBLIC_API_BASE=http://127.0.0.1:8000` (`apps/web/lib/api.ts:24`);
> with no backend, every card falls back to its "unavailable" state. This is a **transport (class A)**
> failure, not a contract/cache bug.
>
> **Proof — after starting the canonical backend (`venv/bin/python -m uvicorn main:app --port 8000`),
> the real PETR4 payloads (`/tmp/m70b-payloads/`) are:**
>
> | Field | JSON path | Live value | Screenshot said |
> |---|---|---|---|
> | Quote | `quote` | price **42.21**, change **−0.74**, volume **28,690,300** (source market_cache) | "Sem cotação confirmada" |
> | Volume/avg | `market_metrics.volume_vs_daily_average` | status **READY**, ratio **0.938** | "Média diária indisponível" |
> | Institutional flow | `market_metrics.operational_view.technical_context.institutional_flow` | status **READY**, value **65.0**, label **"Comprador"** | "Sem leitura" |
> | Master score | `insight.master_score_display` | **3.9** (status BLOCKED → "Não Operar") | "Score não calculado" |
> | Strategic panel | `insight.strategic_panel` | **present**, recommended_action AGUARDAR | "Snapshot incompleto" |
> | News | `news.items` | **6 items** with URLs (fresh cache, age 24s) | "Sem notícia específica" |
> | AI tools | `/public/market/ai-tools?symbol=PETR4` | status **READY**, **displayable_count 9** | "abas IA sem resultados" |
> | `/site` | — | **HTTP 200** | — |
>
> Frontend consumption verified live: `resolveFlowCard` reads `best.score` (65) and the
> `technical.institutional_flow` path is READY (renders "Comprador 65.0"); `newsRows`
> (`workspace-shell.tsx:9631`) is built from `activeNews.items` with **no historical filter**, so
> the 6 items render. None of these are contract bugs — they were empty only because :8000 was down.
>
> ### Issues that GENUINELY persist with the backend live (backend-independent)
> 1. **Sentiment** — `market_metrics.sentiment.value = None`, `status=INSUFFICIENT_DATA`. Real feature gap
>    (per-asset news-sentiment aggregation never implemented). Typed honestly today (mission Option C).
> 2. **Liquidity** — `market_metrics.liquidity.status=INSUFFICIENT`, low/high null: weekend single-point
>    collapse (`upper==lower`). Category **B** — expected to recover with a live intraday range (Monday).
> 3. **News weekend labeling** — 6 valid Friday items are flagged `status=historical` (all `is_stale` on
>    Saturday); they still render, but the *state banner* reads "histórico". Cosmetic/labeling.
> 4. **Volume label** — reads "Volume atual / média diária" even when the value is last-session (not live).
>    Cosmetic/correctness.
> 5. **P0.3 freshness** (already fixed this mission) improves the weekend **global-snapshot** AI path; the
>    per-symbol PETR4 path uses on-demand analysis and was already READY.
>
> ### Operational takeaway
> The single most impactful action was **starting the backend**. The mission's "everything is broken"
> premise was a dev-environment issue (API process not running), not a broken data chain. Both servers
> are left running: frontend pid 3785 (:3000), backend pid in `/tmp/stocknewsbr-api.pid` (:8000).
>
> ---


**Date/time:** 2026-07-25 (Saturday), ~afternoon BRT — **B3 closed (weekend)**.
**Repo:** `/home/dcima/stocknewsbr-backend` (canonical WSL clone).
**Branch:** `fix/audit-remediation-2026-07`  ⚠️ *(not the `feat/github-workflow-ai-tools` named in the mission brief — see §0).*
**HEAD at start == HEAD at end:** `a51c0847f2aa6169388ceb4b34a316600010742c` (no commit was made — see §7).
**Push:** not performed (per mission rules).

This log follows the audit in [`mission_70_data_chain_audit.md`](./mission_70_data_chain_audit.md) (read-only investigation phase). This file is the **fix phase**.

---

## 0. Initial Git state and safety findings (READ FIRST)

The working tree was **already dirty before this mission started**, and the nature of that dirt directly constrains what can be safely changed and committed under mission rules 9, 10, 22, 25.

```
$ git branch --show-current
fix/audit-remediation-2026-07
$ git rev-parse HEAD
a51c0847f2aa6169388ceb4b34a316600010742c
$ git status --short   (36 modified, 1 deleted, 2 untracked)
```

Three distinct classes of preexisting change were identified and are **not mine to touch/commit**:

1. **Repo-wide CRLF→LF line-ending normalization** across ~30 backend `.py` files.
   Evidence: HEAD versions are CRLF (e.g. `scheduler.py` = 120 CRLF lines); working tree is LF (0 CRLF).
   `git diff --stat` shows balanced +N/−N per file; `git diff --ignore-all-space` collapses most to 0–7 real lines.
   Example real edit buried in the churn: `scheduler.py` `logger.error(f"...{e}")` → `logger.error("...%s", e)`.

2. **Large unrelated in-progress feature** in the frontend:
   - `apps/web/components/workspace-shell.tsx` — **+389 real lines** (verified via `--ignore-all-space`).
   - `apps/web/app/globals.css` — **+386 real lines**.
   These add a new **“Stock Flow” community panel** (live chat, sentiment polls, editorial editing, live items) — a feature unrelated to the Mission-70 data chain. This is exactly the kind of preexisting user work rules 9/10/25 protect.

3. **Untracked files that predate this session** (timestamps 2026-07-24/25, before this run):
   - `docs/mission_70_data_chain_audit.md` (the audit — kept, referenced).
   - `app/ai/conclusion_generator.py` (not mine — left untouched).

### Consequence for commits (rule 22)
Because the mission’s target files for the **frontend** fixes (score null-vs-zero, flow “Sem leitura”, snapshot-incomplete) all live inside `workspace-shell.tsx`, which carries 389 lines of unrelated in-progress user work, **those files cannot be edited-and-committed without sweeping in the user’s unfinished feature.** Several backend targets (`routes_public_market_live.py`, `public_news_service.py`) are also dirty with churn + small preexisting edits.

**Therefore: no commit was made.** Only work that could be isolated in a **clean** file was implemented. Everything else is delivered as analysis + ready-to-apply guidance below. Exact commit commands are in §7.

---

## 1. What was implemented and proven this session

### ✅ P0.3 — Freshness: daily/session bars no longer judged by the 900s intraday TTL — **Confidence A, proven today**

**File (clean, safely committable):** `app/services/public_ai_tools_service.py`
**Tests (new):** `tests/test_mission_70_ai_tools_freshness.py`

**Root cause (confirmed A):** `_row_is_stale()` applied a flat `_MAX_AS_OF_AGE_SECONDS` (900s, `AI_AS_OF_MAX_AGE_SECONDS`) gate to every row’s `as_of`, regardless of the row’s data granularity. AI-tools rows are stamped with the **daily-bar close** timestamp (engine `market_snapshot_engine.py:517` `as_of = market_data_updated_at / last_bar_at`). On a weekend, Friday’s 20:05Z close is ~17h old → `> 900s` → every tool row moved to `historical_tools` → endpoint `status=HISTORICAL, displayable_count=0` → all five IA tabs show “historical/empty”. The same mismatch would also drop any daily-timeframe row during a live intraday session. Snapshot-level `stale=False` (worker regenerates continuously), so this was purely the per-row age check.

**Fix:** freshness is now **granularity-aware**:
- **Intraday** rows (explicit minute/hour tokens: `5M/15M/30M/1H/…`) keep the 900s TTL — unchanged.
- **Daily/session** rows (`1D/1W/…`, month-range tokens like `1M/3M`, or missing timeframe) are fresh **while they still represent the most recent completed B3 session**, computed weekend-aware from the existing `America/Sao_Paulo` + 17:55 close convention (mirrors `price_event_engine.py` `B3_CLOSE`). No holiday calendar is hardcoded (a holiday degrades a daily row to HISTORICAL — safe, data still returned in `historical_tools`).
- Explicit `data_quality==STALE` / `stale` / `is_stale` flags still win.
- New **additive** per-row contract metadata: `freshness_basis` (`intraday_ttl`|`daily_session`), `freshness_reason`, `data_timeframe`, `source_as_of`, `evaluated_at`.

The ambiguous `"1M"` token (a month-range in this product, not one minute) is deliberately treated as **daily-scale** — erring toward the daily window avoids false-staling, which the mission prioritizes.

**Before → after (mechanism):**
| when | timeframe | as_of | before | after |
|---|---|---|---|---|
| Saturday | 1D | Fri 20:05Z | HISTORICAL (age 17h > 900s) | **READY** (latest completed session) |
| Saturday | 15M | Fri 20:05Z | HISTORICAL | HISTORICAL (intraday TTL expired) — unchanged |
| Mon pre-open | 1D | Fri 20:05Z | HISTORICAL | **READY** (Fri still latest session) |
| Mon post-close | 1D | Fri 20:05Z | HISTORICAL | HISTORICAL (superseded by Monday session) |

**Tests (deterministic, frozen clock — pass today, a Saturday):**
```
tests/test_mission_70_ai_tools_freshness.py  (10 tests):
  daily bar fresh on weekend / Monday pre-open;  daily bar superseded after newer session closes;
  intraday fresh within TTL / stale beyond TTL;  ambiguous "1M" treated as daily;
  explicit stale flag wins;  missing as_of not falsely staled;
  full payload weekend daily rows -> READY (+metadata);  weekend intraday rows -> HISTORICAL.
```
```
$ venv/bin/python -m pytest tests/test_mission_70_ai_tools_freshness.py tests/test_mission_68_public_ai_tools.py -q
27 passed, 10 subtests passed
```
Regression: the 4 failures seen in `test_public_market_routes / test_single_snapshot_source / test_mission_24c` are **pre-existing** — verified by running them against the untouched HEAD version of the file; my change adds **zero** new failures.

**Persists intraday? (category B):** the *fix mechanism* is A and proven now; confirming the IA tabs stay READY through a live Monday session (daily row not superseded until Monday close) is a market-open observation — see §5.

---

## 2. Contract map (per card) — current status after this session

| Card | Backend source | Endpoint | JSON path | Frontend selector | Root cause | Fix status | Conf |
|---|---|---|---|---|---|---|---|
| IA tabs freshness | `public_ai_tools_service._row_is_stale` | `/public/market/ai-tools` | `tools.*[].freshness_status`, `status` | tab gate on `status/READY` | 900s TTL on daily bars | **FIXED (this session)** | A |
| Sentiment | `routes_public_market_live._market_metrics_contract` (`value=None`) | bundle | `market_metrics.sentiment.value` | ws:~10516 `status==="READY"` | per-asset sentiment never implemented; already returns typed null+INSUFFICIENT | Not changed — see §3 | A |
| Fluxo institucional | `_ai_metric_component(...,"flow")` → 68/65 READY | bundle | `institutional_flow.value` | ws:4355 `resolveFlowCard` empty `rows` → “Sem leitura” | frontend reads a rows-collection that arrives empty while `institutional_flow` is populated | Patch drafted — off-limits file — §3 | A/B |
| Volume | provider quote → `volume_vs_daily_average` | bundle | `market_metrics.volume_vs_daily_average` | ws:10535 | empty backend quote (illiquid/uncached) | §3 (market-dep) | A/B |
| Liquidez 5m | `routes:481` geometry gate; `ai_liquidity_map:19` band | bundle | `liquidity.*` | — | `upper==lower` ⇒ `low<high` false (weekend single point) | §3 (market-dep) | A/B |
| Snapshot incompleto | ws:4219 `incomplete=!hasCoreData` / ws:10733 `price&&volume>0` | bundle | — | frontend | empty quote invalidates whole snapshot incl. valid history/score | Patch drafted — off-limits file — §3 | A |
| Notícias | `public_news_service.build_public_news_payload(allow_fetch=False)` | `/public/market/live` news + `/workspace` | `news.items` | — | endpoint cache-only; warmup gap leaves empty cache | Not changed — arch conflict — §3 | A/B |

---

## 3. Items NOT changed this session, with reason and recommended fix

These are real and mostly confirmed at mechanism level, but each is blocked by one of: (a) an off-limits/dirty file that cannot be committed cleanly, (b) a documented conflict with `AGENTS.md`, or (c) a category-B market-open dependency. Recommended, minimal fixes are recorded so a follow-up on a clean tree can apply them.

### P0.1 — News cache-first + lazy fetch — **blocked by AGENTS.md + dirty file**
- Confirmed (A): `build_public_news_payload(..., allow_fetch=False)` at `routes_public_market_live.py:1458` and `routes_workspace.py:75` returns cache-only; `get_symbol_news` (in the **clean** `news_service.py`, TTL-guarded) yields 6 valid items for `CSNA3` via `CSNA3.SA`, but the public cache is empty on the weekend → `count=0`.
- **Conflict:** `AGENTS.md` — *“Nunca chamar provedores externos de mercado diretamente dentro de endpoints HTTP.”* The mission’s “lazy fetch in the request path” contradicts this rule. Also `public_news_service.py` is dirty (+7 preexisting lines), so an edit-and-commit would sweep them.
- **Recommended (respects both):** keep the endpoint cache-first, but on a **cache miss** trigger an immediate, singleflight- and timeout-bounded warmup for the requested symbol via the existing warmup machinery (already partially wired: `_request_news_warmup_safe` + `schedule_warmup=True`), and either (a) briefly await it under a hard timeout then re-read cache, or (b) shorten negative-cache TTL so the scheduled warmup fills within one refresh. Preserve `.SA` candidates, dedupe, relevance/temporal filters, locale, limit. Add typed metadata (`status`, `reason`, `cache.hit/stale`, `as_of`). Needs a clean tree + product decision on the AGENTS.md rule before implementing.

### P0.2 — Sentiment hardcoded `None` — **already typed-insufficient; Option-B is a feature in a dirty file**
- `routes_public_market_live._market_metrics_contract` sets `sentiment.value=None, status=INSUFFICIENT_DATA, reason=no_fresh_sentiment_source`. This already satisfies mission **Option C** (typed absence, not zero/neutral). Building **Option B** (deterministic per-article aggregation of the symbol’s news sentiment) is a genuine new feature and lives in a **dirty** file. Recommend implementing on a clean tree as a small isolated aggregator with `sample_size`, `confidence`, `as_of` from the newest article used, min-article threshold, and null when evidence is insufficient. **Do not** use market-wide `market_pulse.sentiment` as per-asset.

### P0.4 / P0.5 / P0.8 — Score null-vs-zero, Flow “Sem leitura”, Snapshot-incomplete — **off-limits frontend file**
All three live in `apps/web/components/workspace-shell.tsx`, which holds **389 lines of unrelated in-progress “Stock Flow” work**. Editing-and-committing would violate rules 9/10/25. Recommended minimal patches (to apply on a clean tree):
- **P0.4:** replace numeric truthiness (`value ?? 0`, `Number(x) || 0`, `if (score)`) with explicit `score !== null && score !== undefined && Number.isFinite(score)`; render `0.0` only when `status==="READY"`, else PENDING/INSUFFICIENT (“Sem leitura”)/STALE distinctly. Backend `score_display.normalize_master_score_display` (clean) returns `(0.0,"…_invalid")` on `None` while `insight.master_score` is valid — pass the valid score into the display block instead of the 0.0/invalid pair.
- **P0.5:** point `resolveFlowCard` at the populated `institutional_flow` field (value 68/65) rather than a rows-collection that arrives empty; treat real `0` as a value, PENDING/STALE as distinct from “Sem leitura”.
- **P0.8:** make `hasStrategicCoreData` not require live `price && volume>0` to consider the snapshot complete when valid historical/session data exists; downgrade to a `HISTORICAL_COMPLETE`/`DEGRADED` state instead of “Snapshot Incompleto”.

### P0.6 / P0.7 — Volume fallback, Liquidity `high==low` — **dirty file + category B**
Both live in `routes_public_market_live.py` (dirty). Liquidity `upper==lower` is consistent with a weekend single Friday-close point; evidence strongly indicates a live intraday range restores `low<high` (audit §LIQUIDEZ, B). Recommended: guard the geometry against zero-range (no div-by-zero / NaN), fall back through intraday→last-session OHLC, and return typed `INSUFFICIENT reason=zero_range` when no range exists — on a clean tree.

### P2 — Supertrend markers — not started (correctly gated behind P0/P1)
Not investigated for implementation this session (mission orders P2 only after P0/P1 are green). The chart component is `apps/web/components/ticker-chart.tsx` (dirty). Determining widget vs lightweight-charts and building the ATR/Supertrend signal engine is a separate, isolatable commit for a clean tree.

---

## 4. Discarded hypotheses (kept discarded — do not reintroduce)
- **D1:** News did **not** break due to `.SA` being stripped — the provider is queried **with** `.SA` (`provider_symbol("CSNA3") → "CSNA3.SA"`; candidates `['CSNA3','CSNA3.SA']`).
- **D2:** News is **not** zeroed by the relevance filter — `build_symbol_news_with_report("CSNA3", 10 raw) → 6 items`, `discard_reasons={}`.

---

## 5. Pregão (market-open) validation checklist — category B, observe next regular session
- IA tabs stay READY through a live Monday session (daily row fresh until Monday close); intraday tools populate/expire on the 900s TTL as expected.
- Liquidity `low<high` recovers once an intraday range exists (expect INSUFFICIENT→READY).
- Illiquid B3 names (CSNA3-class) receive a live quote intraday (affects Volume + Snapshot-incompleto).
- News warmup/cache populates during a live session for on-demand symbols.
- Flow “Sem leitura” being transient (PENDING) vs a permanent wrong-collection wiring.

---

## 6. Files changed by THIS mission (only)
| File | Type | Reason |
|---|---|---|
| `app/services/public_ai_tools_service.py` | modified (was clean) | P0.3 granularity-aware freshness |
| `tests/test_mission_70_ai_tools_freshness.py` | new | 10 deterministic frozen-clock tests for P0.3 |
| `docs/mission_70_fix_execution.md` | new | this log |

**Untouched preexisting (NOT mine):** the 36 churned/edited files, the deleted `liquidity_sweep.py`, `docs/mission_70_data_chain_audit.md`, `app/ai/conclusion_generator.py`.

---

## 7. Commit commands (present-only — not executed, per rule 22)

No commit was made because the working tree mixes the user’s unrelated changes (CRLF→LF churn + “Stock Flow” feature) with everything else, and `git add` is per-file (rules 10/22/25). The P0.3 change is confined to two files that were **clean** before this mission, so they can be staged explicitly and safely:

```bash
cd /home/dcima/stocknewsbr-backend

# Review exactly what will be staged (P0.3 only):
git diff -- app/services/public_ai_tools_service.py
git status --short -- tests/test_mission_70_ai_tools_freshness.py docs/mission_70_fix_execution.md

# Stage ONLY the mission-70 files (never `git add .`):
git add app/services/public_ai_tools_service.py \
        tests/test_mission_70_ai_tools_freshness.py \
        docs/mission_70_fix_execution.md

# Verify nothing else was staged (must show ONLY the three files above):
git diff --cached --name-only

git commit -m "fix(70): make AI-tools freshness granularity-aware (daily vs intraday)"
# Do NOT push.
```
> ⚠️ Before running, confirm you intend to commit on `fix/audit-remediation-2026-07` (the mission brief named `feat/github-workflow-ai-tools`). If a different branch is required, create it first with `git switch -c <branch>` — do **not** reset/stash the working tree.
