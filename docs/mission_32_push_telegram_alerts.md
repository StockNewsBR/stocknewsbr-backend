# Mission 32 — Push, Telegram e Alertas Institucionais

Branch: `feat/github-workflow-ai-tools`
BASE_COMMIT: `5460de2a2a9bc3d110d528d578251814ab152d83` (commit final da 31G)

## 1. Arquitetura do pipeline

```
worker.py (serviço dedicado, processo único)
  → engine → snapshot (signals)
    → dispatch_signal_pushes(signals)      [app/system/push_dispatcher.py]
        kill switch → eligibilidade (Decision Envelope + Score display) →
        symbol kill switch → cooldown por ticker (estado persistido em JSON) →
        send_push_notification (por usuário, tokens ativos) → auditoria
    → send_bulk_alert(signals)             [app/telegram/telegram_alert_engine.py]
        kill switch → ticker → Decision Envelope → telegram_access
        (configured/linked/allowed) → classificação institucional →
        batch anti-spam → dedup por fingerprint + cooldown por equivalência →
        transporte (sent/failed/unknown) → auditoria + métricas
```

- Push e Telegram são despachados em blocos `try/except` independentes no
  worker: a falha de um canal nunca derruba o outro (32-12).
- O dispatch NUNCA acontece dentro de request HTTP de usuário (32-13); a API
  (uvicorn) apenas registra tokens e expõe status.
- Nenhum provider financeiro alimenta alerta diretamente: os alertas nascem do
  snapshot institucional já auditado.

## 2. Kill switches (32-20)

Implementação por environment variable (`app/system/kill_switches.py`), sem
plataforma externa de feature flags. Leitura dinâmica (rollback imediato ao
remover a variável). Valor padrão de TODOS: **OFF** (pipeline habilitado).

| Switch | Efeito | Default |
|---|---|---|
| `DISABLE_PUSH_ALERTS` | bloqueia dispatch/envio de Push (dispatcher e provider edge) | off |
| `DISABLE_TELEGRAM_ALERTS` | bloqueia alerta Telegram no gate do engine | off |
| `DISABLE_AI_DECISIONS` | switch disponível e exposto em status; consumo pelos componentes financeiros protegidos pertence a missões futuras | off |
| `DISABLE_PROVIDER_<NAME>` (ALPACA/BINANCE/…) | switch disponível e exposto em status; wiring nos providers financeiros é componente protegido (OUT_OF_SCOPE, owner_mission=34/35) | off |
| `DISABLE_SYMBOL_<SYMBOL>` | bloqueia alertas Push e Telegram do símbolo (normalização `A-Z0-9` → `_`, ex.: `BTC-USD` → `DISABLE_SYMBOL_BTC_USD`) | off |
| `READ_ONLY_MODE` | bloqueia qualquer envio externo de alerta (ambos os canais) | off |
| `PAPER_ONLY` | modo imutável do paper trading (constante institucional, não é env toggle) | sempre ativo |

Garantias testadas: fail-safe (erro de avaliação nega envio), bloqueio
auditável (evento em observabilidade/histórico com `kill_switch=...`),
health/status expõe o estado (`/system/status.kill_switches`,
`get_telegram_health().kill_switches`, `get_push_status().push_alerts_disabled`),
nenhum kill switch altera dados históricos (estado de cooldown intocado),
nenhum alerta antigo é reenviado indevidamente ao religar (dedup/cooldown
persistem), rollback imediato.

## 3. Push (32-01, 32-02, 32-18)

- Store: `data/push_tokens.json` por usuário, lock reentrante + escrita atômica.
- **Tokens nunca expostos**: rotas públicas (`/push/tokens`, register,
  unregister) retornam somente `token_masked` (`abcd...wxyz`); o valor bruto
  não sai do serviço. `get_push_token_store()` permanece interno (dispatcher).
- **Vínculo único**: política explícita — re-registro atualiza o vínculo; o
  mesmo token registrado por outro usuário é removido do dono anterior
  (inclusive sob concorrência, coberto por teste com Barrier).
- **Token inválido**: erros permanentes do provider (`UnregisteredError`,
  `SenderIdMismatchError`, `InvalidArgumentError` ou `PushTokenInvalidError`
  no fake) desativam SOMENTE o token afetado (`active=false` +
  `deactivated_reason` sanitizado + timestamp — evidência preservada). Sem
  retry do token inválido; novo registro reativa. Falha transitória não
  desativa nada.
- **Envio**: uma tentativa por token por ciclo; retry entre ciclos é do
  worker. Sem retry infinito, sem bloqueio de request.
- Rotas autenticadas (`require_active_plan`), usuário opera apenas os próprios
  tokens; `/push/test-send` restrito a `require_internal_token`.

## 4. Telegram (32-03, 32-04, 32-15)

Semântica dos estados:
- **configured**: `TELEGRAM_TOKEN` + `TELEGRAM_CHAT_ID` presentes (transporte
  falha fechado se ausentes);
- **linked**: usuário vinculado via link-code seguro (rotas `/internal/telegram/*`,
  internal-token);
- **allowed**: `has_channel_access(user, "telegram")` — plano/permissão central;
- **enabled/preference**: o canal institucional é broadcast (chat único); não
  existe preferência por usuário no contrato atual (ver §6);
- Contrato de envio do engine: ticker válido AND kill switch livre AND
  Decision Envelope READY AND `telegram_access.allowed is True` (dados
  ausentes = bloqueio, nunca fail-open) AND classificação institucional.

Correções desta missão:
- **Markdown removido do transporte** (texto plano): conteúdo dinâmico sem
  escape podia gerar HTTP 400 (entity parse) — perda silenciosa de alerta —
  além de injeção de Markdown. Template não usa marcação; caracteres
  especiais agora são seguros por construção.
- **Bot token nunca em log**: exceções de rede (requests) embutem a URL com o
  token; `_scrub_secret` mascara token e chat id em todo log de erro.
- **Timeout ambíguo = UNKNOWN**: `ReadTimeout` após o POST vira status
  `unknown` — a reserva do fingerprint é mantida (sem re-envio automático que
  duplicaria) e o evento é auditado (nunca DELIVERED, nunca silencioso).
  Falha clara (`failed`) libera a reserva para retry legítimo.
- **Retry/backoff**: `urllib3 Retry(total=3, backoff_factor=0.5,
  backoff_jitter=0.3, forcelist=[429,500,502,503,504], POST)`. HTTP 400/401
  fora do forcelist (erro permanente, sem retry). Jitter aplicado quando
  urllib3>=2 (guardado para compat).

## 5. Dedup key e idempotência (32-09, 32-10)

- Fingerprint Telegram = identidade real do alerta: ticker canônico, direção,
  final_decision, priority, conviction, operational, audit, summary — nunca
  apenas texto/timestamp/ticker isolado.
- Cooldown por chave de equivalência (ticker|direção|decisão|nível) evita
  variações do mesmo alerta em janela curta.
- Reserva do fingerprint dentro do lock (31F) garante dedup determinístico em
  concorrência (provado com Barrier, sem sleep).
- Push: dedup por ticker + janela de cooldown persistida em JSON
  (`push_dispatch_state.json`); reinício do worker não reenvia alertas dentro
  da janela. Falha de envio não grava cooldown (o alerta não é perdido — o
  ciclo seguinte re-tenta).
- Idempotência persistente por `notification_id`/constraint exigiria banco ou
  storage novo → **BUSINESS_DECISION_REQUIRED** (Tier 2 não autorizado nesta
  missão; não implementado automaticamente).

## 6. Preferências e quiet hours (32-05, 32-06)

Modelo de consentimento atual:
- Push: opt-in = registrar token (autenticado); opt-out = unregister.
- Telegram: opt-in = vincular conta via link seguro + plano com acesso ao
  canal; opt-out = desvincular/perder acesso.
- Não existe hoje infraestrutura de preferência por usuário/tipo/severidade
  nem timezone de usuário persistido. Implementar exigiria schema/migration →
  **BUSINESS_DECISION_REQUIRED** (registrado; nenhuma migration criada).
- Quiet hours por usuário: sem timezone de usuário e sem política explícita →
  **BUSINESS_DECISION_REQUIRED**; nenhum fallback silencioso para timezone do
  servidor foi introduzido. Rate limiting institucional existente
  (cooldown/batch anti-spam) permanece testado.

## 7. Multiprocess risk (32-19) — classificação formal

- Topologia versionada (`render.yaml`): API `uvicorn main:app` **sem
  `--workers`** (1 processo por instância); dispatch de alertas ocorre
  exclusivamente no serviço `worker` (`python worker.py`, processo único);
  bot em serviço próprio (não envia alertas de sinal).
- Conclusão: o dedup em memória do Telegram e o estado JSON do Push são
  coerentes na topologia atual (single-writer por artefato).
- Risco formal: escala horizontal do worker (ou mover dispatch para a API com
  múltiplas instâncias) quebraria a garantia — lock local não é dedup global.
  Correção exigiria Redis/banco/constraint/fila → **BUSINESS_DECISION_REQUIRED**
  (nenhuma infraestrutura introduzida automaticamente).
  Classificação: CONFIRMED como limitação documentada; mitigação futura
  owner_mission=34.

## 8. Observabilidade e auditoria (32-14)

Eventos sanitizados registrados (observability_engine + histórico Telegram +
métricas): alert blocked (envelope/access/kill switch), discarded (nível/batch),
deduplicated, cooldown, sent, error, unknown; Push: dispatch_blocked_by_kill_switch,
signal_blocked_by_symbol_kill_switch, signal_skipped_cooldown, signal_dispatched.
Nunca registrados: device token, bot token, chat id, JWT, Authorization,
payload privado integral. Correlação disponível: ticker/canonical_symbol,
decision fields, alert_level, fingerprint, status, reason.

## 9. Deep links (32-16)

Nenhuma superfície de deep link é construída no backend de notificações:
mensagens Telegram são texto plano sem URLs; o payload de push data contém
apenas campos institucionais do Decision Envelope (sem URL, token ou
credencial). Allowlist de scheme/rota no cliente pertence à Missão 33
(OUT_OF_SCOPE, owner_mission=33).

## 10. OUT_OF_SCOPE

- 33: POST_NOTIFICATIONS, FCM/APNs real, Expo nativo, channels Android,
  deep-link handling nativo, emulator, Keystore/Play Store.
- 34: carga massiva, fila distribuída, Toxiproxy amplo, OpenTelemetry/SLOs,
  dedup global multiprocesso.
- 35: providers reais autorizados, go-live final, backup/failover/runbooks.

## 11. Testes

`tests/test_mission_32_push_telegram_alerts.py` — 81 testes: kill switches
(defaults/truthy/rollback/canal/símbolo/provider/status), token store
(isolamento, mascaramento, rebind, rotação, cap, concorrência com Barrier),
envio push fake (sucesso, inválido→desativação, transitório, kill switch,
fail-closed), dispatcher (kill switch, símbolo, cooldown persistente, falha
sem cooldown, histórico intocado), Telegram gates (kill switches, envelope,
access), dedup/idempotência/cooldown/janela/falha/unknown/concorrência,
transporte (plain text sem parse_mode, truncamento, 400/timeout/conexão,
token nunca em log, retry policy), templates (ações BUY..NO_TRADE, N/A,
escala 0..10, especiais, cripto/B3), autorização de rotas, isolamento de
canais, multiprocess, PAPER_ONLY.

RED/GREEN: cada teste novo codifica comportamento ausente/incorreto no
BASE_COMMIT (ex.: tokens brutos em resposta, parse_mode Markdown, token em
log de exceção, ausência de kill switches, timeout tratado como falha
re-enviável) — RED demonstrado por inspeção do diff sobre o BASE_COMMIT
imutável (reexecutar a suite no commit base é possível via checkout sem
alterações locais); GREEN comprovado pela execução registrada em
`runtime/mission_32/tests/`.

## 12. Evidências finais

- Branch: `feat/github-workflow-ai-tools`.
- BASE_COMMIT / HEAD local / HEAD remoto: `5460de2a2a9bc3d110d528d578251814ab152d83`.
- Gate 0: branch correta, base 31G preservada, sem `git add`, sem commit,
  sem push, sem produção, sem dependência nova, sem migration.
- Focused backend: `.\\venv\\Scripts\\python.exe -m unittest
  tests.test_mission_32_push_telegram_alerts -v` → **81/81 PASS**.
- Full backend: `.\\venv\\Scripts\\python.exe -m unittest discover tests`
  → **852/852 PASS**, 0 skips.
- Mobile typecheck: `npm --prefix apps/mobile run typecheck` → **PASS**.
- Mobile smoke: `npm --prefix apps/mobile run smoke:mobile` → **PASS**.
- Mobile Android export: `npm --prefix apps/mobile run export:android`
  → **PASS**, exportado em `apps/mobile/dist/android`.
- `git diff --check`: **PASS**.
- CodeRabbit: `coderabbit review --agent -t uncommitted --base-commit
  5460de2a2a9bc3d110d528d578251814ab152d83 -c AGENTS.md` → **0 issues**.
- Codex Security: **PASS** — diff scan desbloqueado/finalizado no app
  (`scanId=53fd330c-cc37-4e5d-b80e-5f616bb4d682`), **0 findings**,
  P0/P1/P2/P3 = 0/0/0/0. O 401 anterior (`token_invalidated` /
  `refresh_token_invalidated`) fica apenas como histórico em
  `runtime/mission_32/security/codex_security_diff_scan_TOOL_BLOCKED_401.log`.
- Playwright CLI/Interactive: **NOT_APPLICABLE** — nenhuma superfície Web
  visual alterada nesta missão.
- Push real: **NÃO executado**; Telegram real: **NÃO executado**.
- Tokens/segredos: nenhum token bruto em resposta pública ou log coberto
  pelos testes; logs de erro Telegram mascaram bot token e chat id.
- Cross-user: zero vazamento coberto por testes de rebind/isolamento.
- Alertas perdidos silenciosamente: zero nos caminhos fake testados; timeout
  Telegram vira `unknown` auditável.

Status institucional: **PASS** — Codex Security desbloqueado e sem findings;
todos os gates executáveis passaram.
