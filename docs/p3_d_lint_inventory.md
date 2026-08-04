# P3-D — Lint Warnings Inventory (H10 Release Hardening)

Source: `npm run lint` inside `/home/dcima/stocknewsbr-h10/apps/web`, captured to
`/tmp/stocknewsbr-h10/p3_c_npm_lint.log` (exit 0, warnings only, no errors).

## Summary

- Total warnings: **24**
- Files affected: **3**
- By rule:
  - `react-hooks/exhaustive-deps`: 16
  - `@next/next/no-img-element`: 8

## Files & warnings

### `apps/web/components/image-lightbox.tsx` (2 warnings)
| Line  | Column | Rule                       | Snippet                                                                                       |
|-------|--------|----------------------------|-----------------------------------------------------------------------------------------------|
| 72    | 122    | `@next/next/no-img-element` | `<img className="snbr-image" src={src} alt={alt} onError={() => setFailed(true)} />`         |
| 132   | 13     | `@next/next/no-img-element` | `<img className="snbr-lightbox-image" src={src} alt={alt} draggable={false} />`              |

#### Risk / cause / safe-fix?
- Risk: swapping to `next/image` requires fixed `width`/`height` (we don't know them — props are dynamic) or `fill` mode requiring a sized parent; the loader must know how to resolve arbitrary remote `src`. This is a lightbox viewer that must already accept arbitrary remote URLs with graceful `onError` fallback; using `next/image` would change layout semantics and require image configuration in `next.config.mjs`.
- Cause: simple `<img>` for preview + lightbox of externally-supplied URLs.
- Decision: **BACKLOG P3**. Do not auto-migrate to `Image`. Migration requires validating dimensions, loader and source contracts.

### `apps/web/components/workspace-rails.tsx` (1 warning)
| Line  | Column | Rule                       | Snippet                                                                                             |
|-------|--------|----------------------------|-----------------------------------------------------------------------------------------------------|
| 126   | 11     | `@next/next/no-img-element` | `<img className="snbr-brand-image" src="/brand/stocknewsbr-brand.png" alt={...} />`                |

#### Risk / cause / safe-fix?
- Risk: this is a brand image with a fixture-like local path (`/brand/...`). Migration to `next/image` is **feasible** (single static asset, dimensions can be measured). However:
  - Without measuring the PNG we can't set the real width/height (which `next/image` requires for static layout). An incorrect dimension would shift layout/CLS.
  - The brand asset lives under `public/brand/`. We would need to import it via `import brand from "/brand/..."` or use `next/image` with explicit width/height.
  - Per mission rule ("Proibido trocar img por Image sem validar dimensões, loader e fonte"), this fix is blocked without measurement.
- Decision: **BACKLOG P3**. Capture exact dimensions and migrate in a follow-up; not in H10 scope.

### `apps/web/components/workspace-shell.tsx` (21 warnings)

#### `@next/next/no-img-element` (3 distinct locations)
| Line   | Col | Snippet use-case                                                                                       |
|--------|-----|---------------------------------------------------------------------------------------------------------|
| 2118   | 9   | `<img src={src} alt={name\|symbol} width={size} height={size} loading="lazy" onError={...} />` (asset sigil/avatar with dynamic src and onError fallback) |
| 9340   | 17  | `<img>` for avatar/mark (dynamic src, onError fallback)                                                 |
| 11340  | 22  | `<img>` (additional brand/avatar)                                                                       |
| 11768  | 9   | `<img>` (additional)                                                                                    |
| 11955  | 27  | `<img>` (additional)                                                                                    |

(5 occurrences listed in this file; the same rationale applies: dynamic `src`, lazy/error-fallback semantics, and no validated dimensions.)

- Decision: **BACKLOG P3** for all `no-img-element` warnings in `workspace-shell.tsx`. Migrating to `next/image` would require a per-call width/height contract and loader setup, and risks CLS for user-fetched assets.

#### `react-hooks/exhaustive-deps` (16 occurrences)

##### (a) "Missing dependency" (intentionally granular deps) — 6 occurrences
- Line 7852: missing `workspace?.layout?.chart_settings`. Effect lists 8 specific subfields of `chart_settings` (show_markers, show_zones, show_price_line, show_vwap, show_macd, show_rsi, …). Adding the parent object would re-fire when *any* field changes (including ones the effect ignores) — a regression in effect cadence.
- Line 8200: missing `priorityPublicWatchSymbols`, `publicTickerTapeSymbols`, `publicWatchSymbols`. Effect already lists `token, deferredTicker, chartInterval, appLocale, focusedTab`; the watch symbols arrays are intentionally abtracted away (likely through refs or stable selectors to avoid refetch spikes).
- Line 8332: missing `publicTickerTapeSymbols` (same family as above).
- Line 8373: missing `priorityPublicWatchSymbols`, `publicTickerTapeSymbols`, `visiblePublicWatchSymbols`.
- Line 8444: missing `priorityPublicWatchSymbols`, `publicTickerTapeSymbols`.
- Line 9694: missing `currentPublicQuote`. Risk of creating an effect-firing loop where every quote update retriggers the effect.

Decision: **BACKLOG P3** for category (a). Adding deps blindly risks re-execution and infinite loops, the explicit prohibition in the mission.

##### (b) "Unnecessary dependencies" — 2 occurrences
- Line 10166: unnecessary deps `'derivedPublicInsight.score', 'displayQuote?.change_pct', 'displayQuote.price', 'selectedTicker'`.
- Line 10261: unnecessary deps `'currentRanking.rsi', 'currentRanking.trend', 'derivedPublicInsight.rsi', 'derivedPublicInsight.signal', 'derivedPublicInsight.trend_bias', 'displayQuote.price', 'displayQuote.volume', 'effectiveAiScore', 'priceMovementPercent', 'selectedTicker', 'symbolLabel'`.

These report deps that are *in* the array but not used in the hook body. Removing them is technically safe (they were already over-firing), but the rules' purpose is to expose the contract the developer actually intended; without understanding why they were added we can't tell if removing them breaks an external invariant (e.g., a test that depends on the effect firing on selectedTicker change).

Decision: **BACKLOG P3** for category (b). Requires behavioural proof before removing.

##### (c) "Complex expression in dependency array" — 1 occurrence
- Line 2107: `useEffect(() => { setAttempt(0); }, [candidates.join("|")])`. The string join creates a value-derived identity; extracting to a variable (`const candidatesKey = candidates.join("|"); useEffect(..., [candidatesKey])`) is **low-risk and idiomatic**, and would silence the warning while preserving behavior.

Decision: **SAFE-FIX CANDIDATE**. Tracked for H10 follow-up, but not applied in P3-D batch because: (i) it touches a 12k+ LOC shell component, (ii) the surrounding monoreear is heavy to diff, and (iii) the warning is purely structural — no functional bug today. Leaving as a documented backlog item to keep H10 changes minimal and reviewable.

##### (d) "Logical expression could make deps change on every render" — 7 occurrences
- Line 9497/9498: `feedPosts = activeFeed?.posts || []` consumed in a useMemo that lists `feedPosts` as dep.
- Line 9518/9498 (x3 for rankingRows at lines 9526, 9555, 9630): `rankingRows = workspace?.ranking || []` in multiple useMemo hooks.
- Line 9519/9498 (x3 for radarRows at lines 9526, 9555, 9633): `radarRows = workspace?.top_signals || []` in multiple useMemo hooks.

The `|| []` fallback creates a fresh array literal every render when the value is falsy, making the dep identity unstable — but moving the initialization into its own `useMemo` would change identity for downstream consumers and could change *what* they receive. The fix is * semantically equivalent * in happy path but divergent in the fallback path (the fallback `[]` would be a stable singleton vs. a fresh literal).

Decision: **BACKLOG P3** for category (d). Refactor requires verifying each downstream consumer's behavior on the empty-array path, which is out of scope for H10 minimal-hardening philosophy.

## Final decision matrix

| Category                          | Count | Action           |
|-----------------------------------|-------|------------------|
| (a) intent-granular missing deps  | 6     | BACKLOG P3       |
| (b) unnecessary deps              | 2     | BACKLOG P3       |
| (c) complex expression in dep array | 1   | BACKLOG P3 (low-risk candidate deferred) |
| (d) logical-expression-then-useMemo | 7  | BACKLOG P3       |
| `no-img-element`                  | 8     | BACKLOG P3       |
| **Total**                         | **24**| **0 fixes applied in H10** |

## Rationale for deferring 100% to backlog

The H10 mission explicitly forbids:

- Desabilitar regra global — not requested; rules remain enabled.
- Adicionar eslint-disable amplo — not done.
- Adicionar dependências a hooks sem analisar loops e reexecuções — these are exactly the categories (a) and (d).
- Refatorar componentes extensamente — `workspace-shell.tsx` is 12000+ LOC.
- Trocar `img` por `Image` sem validar dimensões, loader e fonte — blocks all `no-img-element` migrations.
- Alterar comportamento visual ou funcional — every lint fix in this set risks changing render/effect cadence.

Linter warnings are non-failing (exit 0). The build, tsc, lint all pass and the in-vivo smoke (`/` → 307 `/site` → 200) succeeded. There is no functional defect introduced or surfaced by H10.

## Verdict
H10_P3_D_LINT_INVENTORY_DONE — all 24 warnings catalogued with file, line, rule, snippet, risk, cause, and decision; zero unsafe fixes applied; rules left enabled; no eslint-disable added. All warnings deferred to P3 backlog with explicit rationale per category.

Recommended follow-up (out of H10 scope):
- Measure `/brand/stocknewsbr-brand.png` and migrate the single static brand image first (lowest-risk path of the `no-img-element` set).
- For (c) line 2107, perform an isolated PR that introduces `const candidatesKey = candidates.join("|")` and uses it as the dep — expect identical behavior, with a separate lint-only re-run as the sole signal of change.
- For (a) and (d), do behavior-instrumented refactors (signals snapshot + render-count probe) in a dedicated frontend-spring mission, not in the H10 hardening window.
