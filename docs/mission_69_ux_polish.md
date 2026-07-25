# Mission 69 — UX Polish / Go Live Readiness

**Status:** OPEN · **Type:** visual stabilization (no new features until closed)
**Premise:** the project has no single large bug — it has many small presentation
problems that together read as "prototype". Close only when all P0/P1 are resolved.

> Method note: every finding below was **proven by tracing the data path** (API → state
> → props → render), not by assuming "cache" or "rebuild". Keep this discipline.

---

## Verified findings that scope the work (evidence, not assumption)

### AI tabs badge ("Fluxo IA 0", "Liquidez IA 0", "Tendência IA 0")
- **NOT** an engine/data gap. `/public/market/bundle` returns `ai_tools status: READY`
  with real rows: `flow:1 (institutional_interest, score 65.0)`, `liquidity:1`, `trend:1`.
- The badge (`apps/web/components/workspace-shell.tsx` `aiToolFindingCounts` ~L9559)
  counts only **actionable "deal findings"** (`isAiDealFinding` filter ~L9576). A partial
  signal on an AGUARDAR asset is not a "deal" → count 0.
- The "0" is technically correct but reads as broken. **Fix applied:** `showTabCount`
  (~L13402) only renders the chip when `tabCount > 0`.

### LLM conclusion render chain (proven end-to-end)
`setPublicInsight({...bundle.insight})` (~L7815) → `publicInsight = bundle.insight` →
`currentStrategicPanel = publicInsight.strategic_panel` (~L9386) →
`strategicConclusionFromPanel(panel)` reads `panel.llm_conclusion` (~L3800) →
renders "Cenário Atual" (~L10662). The frontend **reads the correct field**. A raw
template only shows when the build is stale OR `llm_conclusion` is null (cold/failed LLM
→ falls back to `strategic_panel_summary`). Backend puts it in
`insight.strategic_panel.llm_conclusion` via `routes_public_market_live.py` (bundle).

### News title hybrid ("Petrobras ações Sinks com mercado Gains")
- Backend serves the **correct English** title. The mangling is a **frontend** word-swap:
  `translateEnglishNewsHeadlineToPt` (`workspace-shell.tsx` ~L1593). **Fix applied** (~L1694):
  only publish the swapped title when no English survives (`stillEnglish` guard); otherwise
  return the publisher's original English — never a half-translated hybrid.

### Volume gauge needle
- `renderMeterCard` maps a 0–100 value to the arc. Volume was passed `ratio * 100`, so
  0.95× → 95 → needle near the green end while the label said "na média". **Fix applied:**
  `ratio * 50` so 1.0× = center. (`workspace-shell.tsx` volume `renderMeterCard` call.)

### Sentiment meter "†"
- The needle drew straight up (vertical line + center dot ≈ "†") when value was null.
  **Fix applied** (~L10954): render the needle only when `normalized != null`.

---

## Backlog

### P0 — immediate impact
- [x] **AI tabs:** never show "0" for mere absence of signals — hide the badge (done); on
      open, the panel should say "Sem sinais acionáveis" clearly.
- [x] **News:** eliminate hybrid EN/PT titles (frontend guard applied).
- [ ] **Conclusion:** user must always see either the LLM conclusion or an explicit loading
      state ("Gerando análise…") — **never a raw template**. (Today it falls back to
      `strategic_panel_summary` while the LLM is cold; make that an explicit loading state.)
- [x] **Volume:** needle position must match the displayed text (gauge mapping fixed;
      audit the other gauges too).

### P1
- [ ] **Sentiment:** distinguish clearly between **Calculando / Indisponível / Sem dados /
      Disponível** — today everything collapses to "—".
- [x] **Voting:** explicit message when there is no active poll (done — Option B).
- [ ] **Labels:** remove all PT/EN mixing across the interface (audit beyond news).

### P2 — general review
- [ ] loading states, placeholders, colors, spacing, copy, empty states.

---

## Notes
- Frontend fixes above are in source with `tsc` clean, but pixel-final must be confirmed
  against a fresh `apps/web` build — code proof ≠ rendered proof.
- Open items (conclusion loading state, sentiment 4-state, label audit) are the next work.

---

## RESOLVED (2026-07-25): systemic AI-tabs root cause — ".SA" key mismatch

**Proven via runtime instrumentation (3 checkpoints).** The global `/public/market/ai-tools`
catalog produced 0 rows because the institutional contract validation saw every signal row
WITHOUT `strategic_panel`. Root cause: at snapshot merge time, `normalized` rows carry the B3
suffix (`BBAS3.SA`) while strategic panels are keyed clean (`BBAS3`), and `_ticker()` did not
strip `.SA`, so `apply_strategic_panels_by_ticker` never matched.

- Evidence: apply call #1 (master_score_rows, clean) attached 5/5; call #2 (normalized, `.SA`)
  attached 0/5. Same panels. Keys were `BBAS3` vs `BBAS3.SA`.
- Fix: canonicalize the `.SA` suffix in `app/ai/strategic_panel.py::_ticker`. Regression test:
  `tests/test_ticker_canonicalization.py`.
- Result: contract_coverage 0%->100%, institutional_consistency 0->100, go_live_ready False->True.
- Architectural follow-up (Mission 30): `_ticker` should delegate to
  `app.services.symbol_registry.canonical_symbol` (the official normalizer) once ai.* import
  layering allows; the local strip is the scoped unblock.

**Remaining "empty tabs" is NOT this bug**: `_row_is_stale` marks findings older than
`_MAX_AS_OF_AGE_SECONDS` (900s = 15 min) as HISTORICAL and drops them from the displayable
catalog. When B3 is closed the freshest data is the prior close (~hours old) -> all HISTORICAL ->
0 rows. Correct behavior. Validate the tabs populate DURING market hours now that the contract
is fixed.
