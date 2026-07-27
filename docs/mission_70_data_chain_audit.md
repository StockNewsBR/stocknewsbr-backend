# Mission 70 — Data Chain Reverse-Engineering (READ-ONLY)

**Runtime anchor:** 2026-07-25 **Saturday** ~13:30 UTC / 10:30 BRT — **B3 closed (weekend)**.
Freshest market data everywhere = **Friday 2026-07-24 20:05 UTC (17:05 BRT daily close)**.
No code was modified. Method: 3 read-only agents + direct curls + Python execution against the live backend.

## Confidence legend
- **A — CONFIRMED**: proven by code inspection AND execution (payload/API/curl agree).
- **B — VERY STRONG**: consistent evidence, one proof still missing (usually market-open reproduction).
- **C — HYPOTHESIS**: a single indication, still open.
- **D — DISCARDED**: hypothesis investigated and refuted (documented so we don't retry it).

Language rule: no absolutes ("breaks every session", "is the root") for anything below A. Below A → "evidence strongly indicates…".

---

## 1. Data chain

```
Provider (yfinance)           news via provider_symbol()->".SA"/"-USD"; quotes for warmed names
   │
quote_cache / chart_cache     holds warmed names; illiquid B3 => empty quote
   │
Snapshot Engine               universe = 10 symbols; strategic_panels contract 100% (post .SA fix)
 (market_snapshot_engine.py)  stamps rows freshness_status=READY, as_of = daily-bar close ts
   │
AI specialists                ai_liquidity_map (band geometry), ai_market_pulse (global sentiment)
   │
Public AI Tools service       RE-JUDGES row as_of vs 15-min gate (public_ai_tools_service.py)
   │
API (routes_public_market_live.py + news_service.py)
   │  bundle: market_metrics.sentiment.value = None (literal); liquidity geometry gate
   │  ai-tools: HISTORICAL when displayable=0
   │  news endpoint: cache-only reader (allow_fetch=False) + schedules warmup
   │
Frontend (workspace-shell.tsx)  cards gate on status==="READY"; flow "Sem leitura" on empty rows
   │
Workspace cards
```

---

## 2. Per-card findings (with category + persists-intraday)

### SENTIMENT — **A (CONFIRMED)**
- Born: nowhere per-asset. `routes_public_market_live.py:781` `_market_metrics_contract` sets `"value": None` (literal). Reason string `:762` `no_fresh_sentiment_source`.
- Value before→after: no producer → `value=null, status=INSUFFICIENT_DATA` (curl CSNA3/CSAN3/PETR4 all null).
- Frontend: `workspace-shell.tsx:10516` shows a score only when `status==="READY"`; renders "—"/"indisponível". No frontend bug.
- Provider check: only a market-wide `market_pulse.sentiment` exists (ai_market_pulse.py); null on the per-symbol path. **Per-asset sentiment was never implemented.**
- Persists intraday? **YES** — hardcoded None, independent of market state.

### FLUXO INSTITUCIONAL — **A (CONFIRMED, split backend/frontend)**
- Backend: `_ai_metric_component(...,"flow")` → `institutional_flow` READY, value **68.0/65.0 "Comprador"** (curl CSNA3/PETR4). Backend has the data.
- Frontend: literal "Sem leitura" only in `workspace-shell.tsx:4355` `resolveFlowCard` when its `rows` array is empty (and `:4473`). So the card reads a row source that arrives empty while `institutional_flow` is populated.
- Persists intraday? **B** — confirmed the fallback fires on empty rows; whether the empty is transient (ai_tools PENDING before load) or a permanent wrong-collection wiring needs a live reload to disambiguate.

### VOLUME / MÉDIA DIÁRIA — **A (CONFIRMED, asset-specific)**
- Born: provider quote → `market_metrics.volume_vs_daily_average` (`routes:743`).
- Values (curl): CSNA3 `current=7.96M, avg=12.29M, ratio=0.648, status=READY`; CSAN3 `ratio=0.574, READY`; **BTCUSD `null/null/null, INSUFFICIENT, reason=daily_average_unavailable`** (quote itself `status=empty`).
- Frontend: `workspace-shell.tsx:10535` passes ratio when `status==="READY"`, else null → "Média diária indisponível" + gauge "—". Mirrors API faithfully.
- Persists intraday? **B** — "indisponível" tracks an EMPTY BACKEND QUOTE (BTCUSD/CSNA3 not warmed). Whether an illiquid B3 name gets a live quote during a session (or stays uncached) needs market-open confirmation.

### LIQUIDEZ 5m — **A (mechanism) / B (cause)**
- Mechanism (A): `routes:481` `if component_status != "READY" or not geometry_ready`; `geometry_ready` (`:478`) requires `valid_range` (`:477` `low<high`). Live rows: `upper_liquidity==lower_liquidity` (CSNA3 5.36==5.36, PETR4 42.21==42.21) → `valid_range=false` → INSUFFICIENT, reason `missing_liquidity_geometry`. Band math source: `ai_liquidity_map.py:19-22` (±25% band collapses when `high≈low`). Same root feeds levels `INSUFFICIENT_SEPARATION`.
- Cause (B): high≈low is consistent with a single Friday-close point (weekend). Evidence strongly indicates a live intraday range would restore `low<high`; **needs market-open confirmation** that it recovers.
- Persists intraday? **B — likely NO** (weekend artifact), pending market-open.

### ABAS IA (Fluxo/Liquidez/Tendência/Momento/Dinheiro Inteligente) — **A (mechanism now) / B (intraday)**
- Now (A, executed): `/public/market/ai-tools` → `status=HISTORICAL, displayable_count=0`; every tool has 10 rows, all moved to `historical_tools`. Drop point `public_ai_tools_service.py:283` `if stale or _row_is_stale(row)`; the firing condition is `_row_is_stale:132` `(now-as_of) > _MAX_AS_OF_AGE_SECONDS (=900, :96)`. Sample row `as_of=2026-07-24T20:05Z` (~17h) ≫ 900s → HISTORICAL. Snapshot-level `stale=False`, so it is purely the per-row age check.
- Intraday claim (B): the engine stamps `as_of` from the **daily-bar** timestamp (`market_snapshot_engine.py ~505-520`), and the public service re-judges it against a **15-min** window. Evidence strongly indicates this mismatch would also drop rows during a live session, but this is an INFERENCE from the timestamp source — **not observed intraday** (Saturday). Must reproduce with market open before calling it a root cause.
- Persists intraday? **AINDA NÃO COMPROVADO** (strong inference: yes).

### PAINEL "SNAPSHOT INCOMPLETO" (CSNA3) — **A (CONFIRMED)**
- CSNA3 is NOT in the 10-symbol global snapshot; on-demand hydration attaches the panel (72 keys, `recommended_action=AGUARDAR`) — the `.SA` fix held.
- Driver `workspace-shell.tsx:4219` `incomplete = !hasCoreData || score == null`; `hasStrategicCoreData` (`:10733`) requires `price!=null && volume>0`. CSNA3 quote is empty (`price=None, source="empty"`) → `!hasCoreData` → "Snapshot Incompleto". Secondary: `master_score_display=0.0 + master_score_display_invalid` (`score_display.py:134` returns 0.0/invalid on None) while `insight.master_score=3.9` is valid — the display block doesn't receive the valid score → "Sem score confirmado".
- Persists intraday? **B** — depends on whether CSNA3 gets a live quote (same illiquid-quote question).

### NOTÍCIAS — **A (mechanism) — two prior hypotheses DISCARDED (D)**
- **D1 (DISCARDED):** ".SA is stripped before the provider query." Refuted: `news_service.py:1701` uses `provider_symbol(normalized)` which returns **`CSNA3`→`CSNA3.SA`** (executed). `_news_ticker_candidates` (`:1695`) yields `['CSNA3','CSNA3.SA']`.
- **D2 (DISCARDED):** "the build/filter drops all items." Refuted: executed `build_symbol_news_with_report("CSNA3", 10 raw)` → **6 items**, `discard_reasons={}`. First title "National Steel Q1 Earnings Miss…" = CSN, relevant.
- **A (CONFIRMED real mechanism):** the fetch loop (`:2200-2206`) tries `CSNA3` (0), then `CSNA3.SA` (10), builds 6. So `get_symbol_news` produces **6** when it runs. But the public endpoint is **cache-only** (`allow_fetch=False`) and the CSNA3 cache is empty → returns `count=0, EMPTY`.
- Open (B): why is the cache empty — warmup not scheduled/completed for CSNA3, or Saturday coverage. Needs confirming the warmup path populates the cache on a live session.
- Persists intraday? **AINDA NÃO COMPROVADO** — pipeline works; endpoint depends on warmup/cache population.

---

## 3. Confidence summary

### Confirmed by code inspection + execution (A)
- Sentiment per-asset = `value=None` literal, never implemented (routes:781).
- Flow backend delivers 68/65; frontend "Sem leitura" comes from `resolveFlowCard` on empty rows (ws:4355).
- Volume READY with a live quote, INSUFFICIENT only when the backend quote is empty (ws:10535).
- Liquidity INSUFFICIENT via `low<high` false because `upper==lower` (routes:481, ai_liquidity_map:19).
- IA tabs are HISTORICAL now because row `as_of` (daily-bar, 20:05) fails the 900s gate (public_ai_tools_service:283/132).
- "Snapshot Incompleto" (CSNA3) driven by empty quote → `!hasCoreData` (ws:4219/10733) + score not propagated (score_display:134).
- News: fetch+build produce 6 items for CSNA3 via CSNA3.SA; endpoint returns 0 because it's cache-only.

### Hypotheses requiring market-open reproduction (B)
- IA tabs failing INTRADAY (daily-bar as_of vs 15-min gate) — mechanism confirmed now, intraday not observed.
- Liquidity `high≈low` being purely a weekend single-point artifact (expect recovery Monday).
- Illiquid names (CSNA3-class) getting a live quote intraday vs staying uncached (affects Volume + Snapshot Incompleto).
- News cache/warmup populating during a live session.
- Flow "Sem leitura" being transient (PENDING) vs a permanent wrong-collection wiring.

### Discarded (D)
- News caused by `.SA` stripping — the app queries the provider WITH `.SA`.
- News caused by the build/relevance filter — it returns 6 valid items.

---

## 4. What the evidence points to (fix phase, not yet started)
Two items are confirmed at the mechanism level and independent of market state, so they are the strongest fix candidates:
- **Sentiment (A):** per-asset value is a hardcoded None — a feature, not a bug fix.
- **News endpoint (A mechanism / B trigger):** the pipeline yields 6 items; the endpoint serves an empty cache — evidence strongly indicates a warmup/cache-population gap, to confirm on a live session.

The highest-user-impact item (IA tabs) is A-now / B-intraday: confirm with market open before committing a fix. No code will change until this report is approved.
