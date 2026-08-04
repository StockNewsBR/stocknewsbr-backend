# Mission 31E - Market, Symbols & Data Integrity

Status: READY_FOR_HUMAN_RISK_DECISION

## Gate 0

- Branch required: `feat/github-workflow-ai-tools`
- Base commit required: `8af196165c96b86d72060bb315af2a2f43b0426e`
- Initial working tree: clean
- Initial local HEAD: `8af196165c96b86d72060bb315af2a2f43b0426e`
- Initial remote HEAD: `8af196165c96b86d72060bb315af2a2f43b0426e`

## Risk Action Record

Mission: 31E
Tier: 2
Action: tighten market symbol identity, crypto ambiguity, BDR proxy rejection, and public batch result semantics.
Component: market data loader, canonical symbol registry, public market routes, quote contract, public market cache reader, web/mobile symbol registries.
Files:
- `app/market/market_data_loader.py`
- `app/services/symbol_registry.py`
- `app/services/symbol_sanitizer.py`
- `app/services/quote_service.py`
- `app/services/public_market_data_service.py`
- `app/api/routes_public_market.py`
- `app/api/routes_public_market_live.py`
- `app/web/routes_search.py`
- `app/watchlists/watchlist_default.py`
- `apps/web/lib/symbol-registry.ts`
- `apps/mobile/lib/symbolRegistry.ts`
- `tests/test_market_data_loader.py`
- `tests/test_public_market_routes.py`
- `tests/test_mission_31e_market_symbols_data_integrity.py`
- `tests/test_mission_30_canonical_symbol_registry.py`
Reason: prevent silent asset identity changes, especially BDR underlying-price leakage and crypto base symbols without quote.
Impact: public quotes now preserve invalid/ambiguous requested items explicitly; BDR foreign-underlying proxy payloads are rejected as negotiated BDR prices; direct BDR payloads retain B3/BRL identity metadata.
Authorization: Mission 31E - nominally authorized.
Rollback: revert the files above to the base commit.
Tests posteriores: focused Mission 31E pytest, related market/symbol pytest, full backend pytest, web lint/tsc/build, mobile typecheck/export, Playwright direct smoke, CodeRabbit review.

## Symbol Matrix

| requested_symbol | canonical_symbol | provider_symbol | asset_type | market | currency | status |
| --- | --- | --- | --- | --- | --- | --- |
| PETR4 | PETR4 | PETR4.SA | B3 | B3 | BRL | direct |
| AAPL | AAPL | AAPL | USA | USA | USD | direct |
| AAPL34 | AAPL34 | AAPL34.SA | BDR | B3 | BRL | direct BDR only |
| MSFT34 | MSFT34 | MSFT34.SA | BDR | B3 | BRL | direct BDR only |
| WINM26 | WINM26 | ^BVSP | B3_FUTURE | B3 | BRL | reference_proxy, not exact contract |
| BTCUSDT | BTCUSD | BTC-USD | CRYPTO | CRYPTO | USD | explicit pair |
| BTC | none | none | CRYPTO | none | none | AMBIGUOUS_SYMBOL |
| BNY | BNY | BNY | USA | USA | USD | direct/searchable |

## Findings

- 31E-01 BDR fallback: confirmed as protected in current diff. Foreign underlying proxy payloads are context-only and rejected by loader, public cache reader, and public live route identity matching.
- 31E-02 asset identity: resolved in current diff by adding requested/canonical/display/provider/asset_type/market/currency/fallback metadata to market loader payloads.
- 31E-03 canonical registry: resolved in current diff for crypto base ambiguity. Bare `BTC`, `ETH`, `SOL` no longer canonicalize silently to USD pairs.
- 31E-04 universal search: resolved in current diff for crypto ambiguity. Search can still find explicit listed pairs, but typed bare crypto is not converted by the canonical registry.
- 31E-05 B3 futures: resolved before mission for reference proxies; current diff preserves explicit `reference_proxy` and non-exact contract semantics.
- 31E-06 crypto/Binance: deterministic contract only; no Binance adapter changed.
- 31E-07 Alpaca: not applicable; no Alpaca adapter changed.
- 31E-08 freshness/stale: covered by focused stale-cache regression.
- 31E-09 single versus batch: public batch now preserves invalid, ambiguous, and duplicate requested items explicitly.
- 31E-10 errors/fallbacks: public quote errors no longer collapse to silent omission for invalid or ambiguous symbols.

## Provider Calls

- Alpaca: not applicable, adapter not changed.
- Binance: not applicable, adapter not changed.
- yfinance: no new production provider call added. Deterministic tests use fixtures/mocks.

## Codex Security

Default status: NOT_APPLICABLE.

Justification: the diff is scoped to market data identity, symbol normalization, public quote status, tests, and docs. It does not alter authentication, secrets, tokens, security settings, trust boundaries, private provider endpoints, or sensitive logging.

## AI Tooling

- GitHub: branch `feat/github-workflow-ai-tools` confirmed on remote; remote branch is identical to base commit `8af196165c96b86d72060bb315af2a2f43b0426e`.
- CodeRabbit: authenticated review iterations completed after the 31E.1 fixes for legacy identity overwrite, strict cache identity, BDR/reference-proxy filtering, sanitized public error payloads, corrected web/mobile BDR allowlists, and quote diagnostics fallback. Final post-edit review must remain the closeout gate.
- Codex Security: NOT_APPLICABLE by mission rule because no auth, secrets, trust-boundary, token, header, sensitive logging, or private provider surface changed.
- Playwright Interactive: browser/API smoke passed with system Google Chrome. Evidence artifacts: `playwright-report.json`, scenario screenshots, and `trace.zip` from the final 31E.1 Playwright run.
- Playwright legacy scripts: `test:mission30e` and `smoke:etapa7` still fail on pre-existing/legacy frontend assertions unrelated to the 31E contract. `test:mission30e` reproduces stale-news marker failures on the base commit; `smoke:etapa7` reproduces `USA deve traduzir painel de IA` on the base commit.

## Validation

- `venv\Scripts\python.exe -m py_compile app/market/market_data_loader.py app/services/symbol_registry.py app/services/symbol_sanitizer.py app/services/quote_service.py app/services/public_market_data_service.py app/api/routes_public_market.py app/api/routes_public_market_live.py app/web/routes_search.py app/watchlists/watchlist_default.py` passed.
- `venv\Scripts\python.exe -m pytest tests/test_mission_31e_market_symbols_data_integrity.py -q` passed: 28 passed, 37 subtests passed.
- `venv\Scripts\python.exe -m pytest tests/test_market_data_loader.py tests/test_market_data_cache.py tests/test_public_market_routes.py tests/test_mission_30_canonical_symbol_registry.py tests/test_market_universe_cleanup.py tests/test_single_snapshot_source.py tests/test_mission_31e_market_symbols_data_integrity.py -q` passed: 100 passed, 59 subtests passed.
- `venv\Scripts\python.exe -m pytest -q` passed: 619 passed, 1 warning, 190 subtests passed.
- `npm --prefix apps/web run lint`, `npm --prefix apps/web run tsc`, and `npm --prefix apps/web run build` passed.
- `npm --prefix apps/mobile run typecheck` and `npm --prefix apps/mobile run export:android` passed.
- `git diff --exit-code -- apps/web/package.json apps/web/package-lock.json apps/mobile/package.json apps/mobile/package-lock.json` passed; no dependency or lockfile changes.

## Out Of Scope

- 31F: locks, RLock, races, TOCTOU, atomicity, realtime, multiprocess cache semantics.
- 31G: ranking, radar, Score Mestre, AI/news editorial ranking, trade decisions.
- 34: broad performance, load testing, Redis, 500+ ticker benchmark.

## Residual Risk

- Existing frontend search can surface explicit crypto pairs when users type a base ticker; this is acceptable because selection resolves to an explicit quoted pair, not a silent backend quote conversion.
- Reference proxies for B3 futures remain informational only and are not exact contracts.
