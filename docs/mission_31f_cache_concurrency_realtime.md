# Mission 31F - Cache, Concurrency And Realtime

Status: TOOL_BLOCKED by external review tooling; local implementation and tests are validated.

Branch: `feat/github-workflow-ai-tools`

BASE_COMMIT: `23d27889144bf342ee5775c0ca74a1f968e8f397`

HEAD: `23d27889144bf342ee5775c0ca74a1f968e8f397`

Remote HEAD: `origin/feat/github-workflow-ai-tools = 23d27889144bf342ee5775c0ca74a1f968e8f397`

## Execution Model

- Web runtime: `uvicorn main:app --host 0.0.0.0 --port $PORT` in `render.yaml`; no explicit multi-worker count or `WEB_CONCURRENCY` is configured in repo.
- Local API: `uvicorn main:app --reload`.
- Background worker: separate `worker.py` process.
- Threads: engine/thread-pool paths use local `threading`/executor workers.
- Async tasks: FastAPI WebSocket handlers and broadcast paths.
- Shared database: `DATABASE_URL`, defaulting to SQLite with WAL/busy timeout and supporting external DB configuration.
- Shared files: snapshot, signal, outcome, paper-trading, poll, moderation, ticker-room and social JSON stores under `runtime/` or `data/`.

## Lock Matrix

| Area | File | State | Lock policy | I/O policy | Multi-process policy |
| --- | --- | --- | --- | --- | --- |
| Snapshot cache | `app/cache/snapshot_cache.py` | payload, timestamp, last-good | local `RLock` for publish/read snapshots; disk writes serialized separately | disk write uses a cloned payload and empty-clear cannot race a pending write | consistent read plus atomic replace |
| Signal outcome | `app/cache/signal_outcome_cache.py` | outcome state and mtime | local `RLock` for in-memory state | atomic JSON write outside state mutation | double-stat consistent read plus atomic replace |
| Signal cache | `app/cache/signal_cache_layer.py` | signals and timestamp | local `RLock`; deep-copy boundary | write uses a stable cloned snapshot | consistent read plus atomic replace |
| Market data cache | `app/cache/market_data_cache.py` | provider frame, covered tickers, TTL | local `RLock` for metadata plus refresh lock for miss serialization | provider call happens once per miss generation | cache key records actual provider coverage, not requested coverage |
| Paper trading | `app/cache/paper_trading_cache.py` | simulated state and diagnostics | local `RLock` | atomic write outside state mutation | consistent read plus atomic replace |
| Warm pool | `app/data/warm_data_pool.py` | pool, timestamp, empty-log throttle | local `RLock` with check-lock-recheck | provider refresh outside lock | defensive copy on read/write |
| Market WebSocket | `app/system/websocket_manager.py` | active sockets, pending accepts | local `RLock` for capacity reservation | accept/send happen outside lock; rejected/timeout accepts close cleanly | per-process capacity; no cross-process claim |
| Room WebSocket | `app/system/room_websocket_manager.py` | room sockets, pending accepts | local `RLock` per-room and aggregate reservation | accept/send happen outside lock; rejected/timeout accepts close cleanly | per-process room capacity; no cross-process claim |
| Telegram alerts | `app/telegram/telegram_alert_engine.py` | fingerprint, cooldown, history | local `RLock`; separate send-rate lock | network send outside dedupe lock; access fails closed without validated evidence | in-process dedupe only; no cross-worker claim |
| Social SQL | `app/social/likes.py`, `followers.py`, `sentiment_poll.py` | likes/follows/votes | DB transaction and unique constraints | DB commit is the atomic unit | shared DB is the multi-worker guard |
| Moderation JSON | `app/social/moderation.py` | reports, queues, guardian audit | local `RLock` plus file lock for mutation | atomic replace; repeated report by same user/post is idempotent | interprocess file lock for read-modify-write |
| Social JSON store | `app/social/store.py` | legacy social JSON state | local `RLock` plus file lock | atomic replace | interprocess file lock for mutation |
| Poll JSON | `app/services/poll_service.py` | weekly poll votes | local `RLock`; vote path adds file lock | atomic replace | interprocess file lock for vote read-modify-write |
| Ticker room | `app/services/ticker_room_service.py` | room messages | local `RLock` plus file lock | atomic replace | audit rollback if moderation audit fails |

Global lock order:

1. local module lock;
2. file lock when used;
3. local disk read/write;
4. DB or observability call only after releasing unrelated store locks where practical.

No flow intentionally acquires two independent module locks and then performs network I/O.

## Concurrency Matrix

| Scenario | Coverage |
| --- | --- |
| Nested snapshot mutation | `tests/test_mission_31f_cache_concurrency_realtime.py` verifies copy-on-write and copy-on-read. |
| Signal cache mutation | Focused test verifies returned rows cannot mutate internal state and `age/clear` stays coherent. |
| Snapshot/signal clear during pending write | Focused tests verify stale disk payload is not reloaded after a clear or failed clear. |
| Market partial provider response | Focused test verifies missing symbols are not marked cached and trigger a new provider attempt. |
| Market duplicate miss | Focused test verifies concurrent miss requests share one provider refresh and preserve requested response shape. |
| WebSocket capacity | Focused async test verifies last-slot reservation, code `1013`, idempotent disconnect and dead-client cleanup. |
| Room WebSocket capacity | Focused async test verifies per-room limit and idempotent disconnect. |
| Telegram duplicate send and access | Focused tests verify two equal alerts produce one send, linked/no-access is blocked, and missing validation fails closed. |
| Poll lost update | Focused thread test verifies 100 concurrent votes produce 100 total votes. |
| Moderation duplicate report | Focused test verifies repeated reports by one user do not inflate auto-hide counts. |
| Ticker Room audit failure | Focused test verifies message rollback when audit recording fails. |

Small-load validation:

- 100 cache/social operations: covered by focused unit tests for cache mutation and 100 poll votes.
- 2 duplicate Telegram alerts: covered by concurrent thread test.
- WebSocket 10/50 live client load: script reports backend manager coverage; full browser fan-out remains a later scale certification item.

## Deadlock Analysis

Coffman conditions:

- Mutual exclusion exists for local in-memory state and file-backed JSON stores.
- Hold-and-wait is minimized by avoiding WebSocket accept/send and Telegram network send under state locks.
- No-preemption is inherent to Python/file locks, so critical sections are kept bounded.
- Circular wait is not introduced by the changed flows; global order avoids acquiring WebSocket or Telegram locks after unrelated store locks.

Shared/exclusive locks:

- RW locks were not introduced. The existing workload is write-sensitive and short critical sections with defensive snapshots are simpler and safer.
- Local locks are documented as process-local only. Multi-worker state relies on DB uniqueness or file locks where the current store is JSON-backed.

## Retry And Capacity

- WebSocket capacity is configurable via `WEBSOCKET_MAX_CONNECTIONS`, `ROOM_WEBSOCKET_MAX_CONNECTIONS`, and `WEBSOCKET_MAX_CONNECTIONS_PER_ROOM`.
- WebSocket rejection uses code `1013` with explicit reason.
- Capacity is currently process-local. The documented Render start command launches a single `uvicorn` process unless deploy configuration adds more workers outside this repo.
- No product requirement for a distributed global WebSocket quota is encoded in the current repo. If future deploys add multiple web processes and require a global quota, a shared approved limiter is required before claiming a global cap.
- Telegram dedupe reserves the fingerprint before send, keeps send outside the dedupe lock, and retains failed reservations briefly to avoid immediate duplicate retries on ambiguous failures.
- Market provider cooldown remains bounded and rate-limited.

## Deferred Items

- `DEFERRED_TO_34_PROVIDER_BENCHMARK`: broad browser/WebSocket scale certification, real multi-worker load, provider streaming migration, and production-like 50+ browser clients.
- `DEFERRED_TO_32`: definitive Alert Event / Alert Delivery / Notification Center architecture.
- `DEFERRED_TO_31G`: unrelated news/email/workspace/backtest refactors.

## Validation

Focused backend:

```text
venv\Scripts\python.exe -m unittest tests.test_mission_31f_cache_concurrency_realtime
22 tests OK
```

Regression slice:

```text
venv\Scripts\python.exe -m unittest tests.test_market_data_cache tests.test_telegram_institutional tests.test_poll_service tests.test_ticker_room_service tests.test_moderation_service tests.test_social_guardian tests.test_mission_31f_cache_concurrency_realtime
59 tests OK
```

Backend completo:

```text
venv\Scripts\python.exe -m unittest discover -s tests
648 tests OK
```

Compile:

```text
venv\Scripts\python.exe -m py_compile <31F touched python files>
OK
```

Frontend:

```text
npm --prefix apps/web run tsc
OK

npm --prefix apps/web run build
OK, with pre-existing Next/React warnings in workspace components
```

Playwright/script artifact:

```text
node apps/web/scripts/mission-31f-realtime-concurrency-audit.mjs
runtime/mission_31f_realtime_concurrency_report.json
failureCount=0
```

## Security And Review Tool State

- Codex Security diff workspace was opened as `2e5b05c9-f953-4c3a-ad7b-6bde91e4c4a2`; `await_codex_security_scan_start` timed out before a launched scan id was provided. No Codebase Deep Scan or Changes/Diff Scan result is available, so the gate remains `TOOL_BLOCKED`.
- CodeRabbit complete run `runtime/mission31f-coderabbit-postfix2.log` found 2 Major and 1 Minor. The Major findings were validated and fixed: Telegram access now fails closed without validated evidence, and duplicate moderation reports no longer inflate report counts. The Minor documentation count was also corrected here.
- Final CodeRabbit rerun `runtime/mission31f-coderabbit-postfix3.log` started against `23d27889144bf342ee5775c0ca74a1f968e8f397` but stalled in `summarizing` for more than 30 minutes and was terminated to avoid leaving an orphan review process. Because a post-fix complete review result was not produced, this gate remains `TOOL_BLOCKED`.
- Local security-sensitive behavior was validated by tests, but the mission cannot be declared `PASS` without the external scan outputs.

## Trading Impact

No BUY/SELL/SHORT/COVER behavior changed. No Score Mestre weights, thresholds, Ranking rule, Decision Envelope rule, provider mapping, Canonical Symbol Registry rule or financial trigger was changed. Telegram delivery authorization was hardened to block unvalidated access; this affects alert delivery eligibility, not trade decision generation.
