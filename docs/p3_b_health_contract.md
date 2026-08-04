# P3-B — Health Check Contract (H10 Release Hardening)

Mission: H10 release hardening (post-tag) — Phase 4 P3-B.
Working tree: `/home/dcima/stocknewsbr-h10` on branch `chore/h10-release-hardening`.

## TAG_SEAL_ALREADY_VALID
- annotated tag object: `d449c99705bb48ca9cff8761fa4eea801c1eadce`
- peeled target `^{}`: `d01033912262d57ac27c3bb5a59d9615091d3c74`
- branch HEAD: `d01033912262d57ac27c3bb5a59d9615091d3c74`

## Inventory scan scope
References to `/health`, `/system/health`, `/system/readiness`, `/system-health` were searched across:
backend (`*.py`), frontend (`ts/tsx/js`), CI (`.github/`), Docker/scripts, deploy manifests, docs, tests.

## Findings

### Deploy platform contract (render.yaml)
`render.yaml` declares:
```
services:
  - type: web
    healthCheckPath: /ping
```
**The deploy platform depends exclusively on `/ping` as the liveness probe.** No infra depends on `/health` or `/system/health`.

### Backend surface discovered

| Path              | Module                                                  | Function          | Auth                                           | Purpose                                                      |
|-------------------|---------------------------------------------------------|-------------------|------------------------------------------------|--------------------------------------------------------------|
| `/ping`           | `main.py:477` (`@app.get`)                              | `ping`            | none (public)                                  | Liveness. Honest about routers bootstrap, no internal data.  |
| `/system/health`  | `app/api/routes_system.py:332` (prefix `/system`)      | `system_health`   | `X-Internal-Token` (`require_internal_token`)  | Aggregate operational health (snapshot, ai-worker, polls).    |
| `/system/status`  | `app/api/routes_system.py:96`                           | `system_status`   | `X-Internal-Token`                             | Internal status surface.                                     |
| `/system/readiness` | `app/api/routes_system.py:175`                        | `system_readiness`| `X-Internal-Token`                             | Readiness probes (storage/cdn/push/snapshot/paper trading). |

### Legacy stub removed (P3-A side effect)
`app/api/api_market_routes.py` previously exposed `GET /system-health` returning a placeholder
`{"status":"running","signals":N}` under `require_channel_access("app")`. It produced a duplicate
FastAPI operation id (`system_health_system_health_get`) and had no consumers in the repo.
Removed in P3-A. No consumer regression is possible (`grep system-health` over the repo, after
the fix, returns 0 hits).

## Decision: CASO 2 with `/ping` already satisfying the public liveness contract

Infra already depends on `/ping` (public, static-ish, no DB, no workers, no snapshots,
no credentials). The endpoint returns:
```json
{
  "ping": "pong",
  "status": "ok" | "degraded",
  "routers_expected": <int>,
  "routers_missing": [<module path>, ...]
}
```
- No new endpoint needed.
- `/system/health` and `/system/readiness` remain protected by `X-Internal-Token`.
- The legacy `/system-health` stub was removed in P3-A; no consumer regression.

## HTTP semantics (locked)

| Surface              | Without token                | With token                                       |
|----------------------|------------------------------|--------------------------------------------------|
| `/ping`              | 200 (public)                 | n/a (token ignored)                              |
| `/system/health`     | token unconfigured → 503 `internal_token_not_configured`<br>header missing → 403 `internal_access_required`<br>header invalid → 403 `internal_access_required` | 200 with aggregate health payload |
| `/system/readiness`  | same gated semantics above   | 200 with readiness payload                       |

## Secret-leak guard
The contract tests assert that response bodies of `/ping`, `/system/health` and `/system/readiness`
never contain `secret`, `password`, `credential` tokens, nor echo the `VALID_INTERNAL_TOKEN`
configured for the test. This is enforced by `tests/test_health_contract.py`.

## Tests
File: `tests/test_health_contract.py` — 8 cases:
1. `test_ping_is_public_liveness_without_auth`
2. `test_system_health_without_configured_token_returns_503`
3. `test_system_health_without_supplied_header_returns_403`
4. `test_system_health_with_invalid_header_returns_403`
5. `test_system_health_with_valid_token_returns_200_without_secrets`
6. `test_system_readiness_without_supplied_header_returns_403`
7. `test_system_readiness_with_valid_token_returns_200_without_secrets`
8. `test_health_contract_endpoint_paths_are_stable`

All passed. `ruff check` clean. `py_compile` clean.

## Verdict
H10_P3_B_HEALTH_CONTRACT_LOCKED — no new endpoint created; `/ping` already serves public
liveness, `/system/{health,readiness,status}` remain protected by `X-Internal-Token`, and
the legacy stub `/system-health` removed by P3-A is excluded from the OpenAPI.
