# Mission 31B — Login Seguro, Email Code, Sessão Única, OTP, Rate Limit, Logout, Social Protection e Alteração Verificada de E-mail

**Executor:** Claude Code (implementação e validação local; NÃO substitui os gates formais CodeRabbit/Codex Security)
**Branch:** `feat/github-workflow-ai-tools`
**BASE_COMMIT (início da 31B, Gate 0 PASS):** `417405143b2166d282fc0c6f4a449cc4411d04e0`
**Status final:** `TOOL_BLOCKED` — implementação + testes locais + auditorias Playwright PASS; gates formais (CodeRabbit CLI, Codex Security scan/diff-scan) não executados neste executor.

> ⚠️ **Anomalia de estado de repositório:** durante a execução da 31B um processo externo
> (outra sessão/automação) executou `git add/commit/push` no mesmo repositório, avançando o
> HEAD de `41740514` para `60cabbc2` e capturando parte dos arquivos 31B em commits que **não
> foram feitos por Claude Code**. Todos os 18 arquivos da 31B permanecem íntegros na working
> tree (verificado). Nenhum `git add/commit/push/reset` foi executado por Claude Code. O usuário
> deve reconciliar a fronteira de commits antes de qualquer push adicional.

---

## 1. Branch
`feat/github-workflow-ai-tools`

## 2. BASE_COMMIT
`417405143b2166d282fc0c6f4a449cc4411d04e0` (31F fechada e sincronizada no Gate 0).

## 3. Arquitetura anterior
- Login **e-mail+senha** (`/auth/login`, `/auth/login-json`); OTP por e-mail apenas como 2FA para planos pagos.
- JWT HS256 (`python-jose`), claims `sub/sid/channel/iat/exp`, 1440 min. `sid` **opcional** para planos não-estritos (token legado sem `sid` aceito indefinidamente para `free`/`trial`).
- Token devolvido no **JSON** e enviado via `Authorization: Bearer`. Sem cookie.
- `single_per_channel` só para planos pagos; free = sessões ilimitadas.
- E-mail: SMTP; fallback "log" **logava o código OTP em texto puro**.
- Sem rate limit de auth (só `attempt_count<=5` por challenge). Sem limite por e-mail/IP, sem cooldown.
- Auditoria: apenas `SubscriptionAuditLog` (billing). Zero eventos de auth.
- Alteração de e-mail **direta** via `PATCH /auth/profile` (sem verificação, sem auditoria, sem revogação de sessão). Correção da descoberta: a 31D **não** havia bloqueado isso.

## 4. Arquitetura final
- **Login web sem senha por código de e-mail**: `POST /auth/request-code` → `POST /auth/login/verify-otp` sobre o `LoginChallenge` existente (existing-only). Endpoints legados de senha mantidos para o canal app; login premium por senha mantém a etapa OTP.
- JWT HS256 com **allowlist de algoritmo** (`alg=none` e não-HS256 rejeitados). `sid` **obrigatório em todo token aceito**, validado server-side em toda requisição para todos os planos.
- **Web:** token só em **cookie httpOnly** (`SameSite=Lax`, `Secure` em produção, `Path=/`, `__Host-` em produção); JSON web não repete o token. **App:** token bearer no JSON (compatibilidade).
- **Uma sessão ativa por usuário (todos os canais)**: novo login revoga atomicamente todas as sessões anteriores com `revoked_reason=session_replaced_by_new_login`.

## 5. Decisão existing-only / JIT
**existing-only** confirmado pelo código: `request_login_code` só cria challenge para usuário existente e ativo; conta inexistente recebe resposta genérica + token isca, sem criar conta. `/auth/register` (senha) permanece o único ponto de criação, agora com consentimentos explícitos.

## 6. Endpoints
| Fluxo | Endpoint |
|---|---|
| request code | `POST /auth/request-code` |
| verify code (login) | `POST /auth/login/verify-otp` |
| sessão atual | `GET /auth/me`, `GET /auth/access` |
| logout | `POST /auth/logout` |
| logout global | `POST /auth/logout-all` |
| request email change | `POST /auth/email-change/request` |
| verify email change | `POST /auth/email-change/verify` |
| perfil (sem e-mail) | `PATCH /auth/profile` (allowlist `extra=forbid`) |

## 7. Models
- `LoginChallenge` estendido: `purpose (LOGIN|EMAIL_CHANGE)`, `target_email`, `max_attempts`, `delivery_status (PENDING|SENT|FAILED|INVALIDATED)`, `delivery_attempted_at`, `invalidated_at`, `request_ip_hash`, `correlation_id`. O código fica só como digest HMAC no campo existente `code_hash`.
- `UserSession` estendido: `expires_at`, `created_ip_hash`, `user_agent`, `correlation_id`.
- `AuthAuditEvent` (novo): trilha de segurança sem segredos.

## 8. Migrations
Via `ensure_runtime_schema` (`app/database_schema.py`, aditivo no startup, dialetos sqlite/postgres): nova tabela `auth_audit_events` + `ADD COLUMN` idempotentes em `login_challenges`/`user_sessions` + índices em `auth_audit_events`. Sem Alembic (padrão do projeto). Preserva usuários existentes; colunas apenas aditivas.

## 9. Challenge
`purpose`, expiração 10 min (`LOGIN_CODE_EXPIRY_SECONDS=600`), uso único, `max_attempts=5`, estados de delivery; verificação só aceita `delivery_status=SENT`.

## 10. Digest
`HMAC-SHA256(pepper, "{purpose}:{challenge_id}:{code}")` — `build_login_code_digest`. Comparação com `hmac.compare_digest`. Código gerado por `secrets.randbelow(1_000_000)` (CSPRNG), 6 dígitos com zeros à esquerda.

## 11. Pepper
`OTP_PEPPER` obrigatório. `get_otp_pepper()` **falha fechado em produção** se ausente/placeholder/curto; fora de produção deriva de `SECRET_KEY` (nunca vazio). Sem fallback `or ""`.

## 12. Provider de e-mail
`app/services/email_service.py`: SMTP em produção; override injetável para testes; **mailbox de teste** só fora de produção (`AUTH_EMAIL_TEST_MAILBOX`, bloqueado no startup em produção); modo "log" **não** loga mais o código. Sem rota de debug de OTP.

## 13. Rate limits
Ledger DB-backed (`auth_audit_events`) — multi-worker safe: `LOGIN_CODE_MAX_SENDS_PER_EMAIL=3`/`LOGIN_CODE_SEND_WINDOW_SECONDS=900`, `LOGIN_CODE_MAX_SENDS_PER_IP=10`, `LOGIN_CODE_RESEND_COOLDOWN_SECONDS=60`. E-mail bruto nunca em chave visível (hash HMAC). Contador de tentativa persiste mesmo em erro.

## 14. Atomicidade
`_consume_challenge_core`: incremento de tentativa commitado em transação própria (sobrevive a erro); `UPDATE ... WHERE consumed_at IS NULL` garante um único vencedor; a sessão é criada só após consumir o challenge, na mesma transação. Duas verificações simultâneas → exatamente 1 sucesso, 1 sessão ativa, 1 auditoria de sucesso.

## 15. Sessão / 16. Cookie / 17. JWT-SID / 18. Sessão única
- Sessão opaca `secrets.token_urlsafe(32)`; só digest de sessão referenciado, token bruto nunca persistido.
- Cookie httpOnly/Secure(prod)/SameSite=Lax/Path=/; sem Domain; `__Host-` em produção; `delete_cookie` com atributos compatíveis.
- JWT: allowlist HS256, `alg=none` rejeitado, assinatura válida não basta, `sid` obrigatório, sessão precisa existir/ativa/não-expirada, `sub` == dono.
- **Tokens legados sem SID: revogação imediata** (política explícita — rejeitados para todos os planos; janela natural = expiração de 24h do token).
- Sessão única: novo login revoga todas as anteriores atomicamente.

## 19. Logout / 20. Logout global
- Logout: revoga sessão atual, apaga cookie, idempotente, auditado, refresh não revive.
- Logout global: revoga todas as sessões do usuário, apaga cookie atual, auditado, não afeta outros usuários.

## 21. CSRF / CORS
- CSRF: middleware Origin/Referer allowlist para métodos mutáveis **quando o cookie de sessão está presente** + `SameSite=Lax`. Clientes bearer (app/bot) não afetados. `app/core/csrf.py`.
- CORS: origens exatas, `allow_credentials=True`, wildcard `*` removido do fallback.

## 22. Social / 23. Social Guardian
Contrato preservado: **todas as ações mutáveis exigem auth server-side** (`require_any_channel_access`/`require_active_plan`); ordem autenticar → autorizar → Social Guardian (`can_publish`/`validate_attachment_url`) → persistir → auditar. Guardian segue bloqueando links, e-mails, telefones, WhatsApp/Telegram, apostas/cassinos. Ownership em delete. WS de chat passou a aceitar cookie de sessão além do token de query.

## 24. Mass assignment
`UserProfileUpdateRequest` com `extra="forbid"` e allowlist (`display_name`, `avatar_url`, `phone`). Campos como `role/is_admin/official/verified/is_bot/premium/plan/subscription_status/user_id/session_generation/active_session_id/email` → **422**.

## 25. Consentimentos
`accepted_terms/privacy/risk_notice` agora **sem default** no schema — obrigatórios e explícitos no registro. Login normal não sobrescreve timestamps de consentimento (`accept_legal_documents` é first-acceptance-wins).

## 26. Alteração de e-mail
Fluxo verificado em duas etapas: `request` (autenticado, rate limited, challenge `EMAIL_CHANGE`, código ao **novo** e-mail, resposta genérica) + `verify` (consumo atômico, checagem de owner/purpose/digest, unicidade via `users.email UNIQUE` com tratamento de `IntegrityError`, invalida challenges, revoga demais sessões, notifica e-mail antigo, auditoria). `PATCH /auth/profile` **não** altera e-mail. Duas contas não terminam com o mesmo e-mail; conflito → `email_change_failed` sem estado parcial.

## 27. Auditoria
`AuthAuditEvent` cobre os eventos exigidos (login_code_requested/sent/verified/invalid/expired/rate_limited, login_success/failed, session_created/revoked/expired/replaced, logout/logout_all, protected_action_blocked, email_change_*). Campos: `user_id`, e-mail mascarado + hash HMAC, ip hash, user-agent resumido, sid_ref (hash truncado), reason, status, correlation_id. **Nunca** grava OTP, digest, token, JWT, cookie, pepper, secret ou e-mail completo. `login_success` só após criação de sessão; `email_changed` só após commit.

## 28. Testes
- **Backend:** `python -m unittest discover tests` → **729 passed, exit 0**. Novo `tests/test_mission_31b_auth_login_session.py` (66 testes): OTP primitives, request/verify, rate limits, concorrência (2 verificações → 1 vencedor; 2 logins → 1 sessão; e-mail duplicado bloqueado por constraint), token/JWT/cookie hardening, mass assignment, consentimentos, alteração de e-mail, auditoria sem segredos, proteção social, cookie Secure fail-closed em produção e guarda de Origin do WebSocket. `test_mission_31b0` atualizado para a política de SID da 31B.
- **Frontend:** `npm run tsc` ✅, `npm run build` ✅.
- **Regressões:** mission30 (101 checks) ✅, mission31a ✅, mission31a2 (failureCount 0, com workers de mercado) ✅.
- **Pós-CodeRabbit (fixes aplicados):** `uploadMedia` com `credentials:"include"`; lock transacional por usuário (`SELECT ... FOR UPDATE`) na troca de sessão única (fecha a corrida em PostgreSQL); fail-closed de `SESSION_COOKIE_SECURE` em produção; validação de Origin em handshake WebSocket autenticado por cookie; scrub do `?token=` da URL via `history.replaceState`; sentinel de cookie fora da URL do WS; timer de reabilitação do cooldown; DDL do `TABLE_PATCHES` alinhado às colunas novas; CORS registrado como middleware mais externo (403 do CSRF carrega headers CORS — verificado via curl).

## 29. Playwright
`apps/web/scripts/mission-31b-auth-session-audit.mjs` → `runtime/mission_31b_auth_session_report.json`, **failureCount=0** (29 flows), 5 screenshots. Cobre os 30 cenários exigidos (visitante bloqueado + prompt, modal, e-mail inválido, solicita código, código incorreto, expiração via fixture de banco, autentica, replay falha, ação social válida, Guardian bloqueia, logout, ação bloqueada pós-logout, aba A perde sessão com mensagem PT-BR, cookie/storage sem token, rascunho preservado, sem auto-post, cooldown pós-reload, loading termina, sem stack/erros técnicos, PT-BR, logout repetido seguro, logout global, mass assignment, alteração de e-mail com código, refresh não ressuscita). Captura de OTP em teste via mailbox injetável (não em produção).

## 30. Screenshots / evidências sanitizadas
`output/playwright/mission31b/*.jpg` (01-login-card, 02-code-step, 03-logged-in, 04-session-replaced, 05-email-change). Relatório sem OTP/cookie/token (varredura confirmou ausência de padrão de JWT).

## 31. CodeRabbit
**EXECUTADO E LIMPO** (CLI 0.6.4, autenticado, `--base-commit 41740514` cobrindo 100% do diff 31B):
- Rodada 1: 14 findings (0 critical, 13 major, 1 minor) — 3 atribuídos ao commit externo `60cabbc2` (guardian), 1 a código pré-existente arrastado por EOL, demais tratados.
- Rodada 2 (pós-fixes): 1 finding minor (ordem do CORS no stack) — corrigido e verificado em runtime.
- **Rodada final: `review_completed`, 0 findings.**

## 32. Codex Security
`PENDING` — `codex-security/security-scan` e `security-diff-scan` oficiais não executados neste executor. Claude Code fez apenas revisão local complementar (**não** é o gate oficial Codex Security).

## 33. Riscos residuais
- CSRF por Origin/Referer depende do envio desses headers pelo browser (padrão em navegadores modernos); reforçado por `SameSite=Lax`.
- Rate-limit ledger em `auth_audit_events`: cresce com o tempo — considerar rotação/retention.
- Notificação ao e-mail antigo é best-effort (`BackgroundTask`); falha de SMTP não bloqueia a troca (por design).
- **Fronteira de commits desalinhada por processo externo** (ver aviso no topo) — precisa de reconciliação humana antes de push.

## 34. Status final
`TOOL_BLOCKED` — implementação, 727 testes backend, TSC, build, regressões e Playwright (failureCount=0) locais **PASS**; PASS formal bloqueado até CodeRabbit + Codex Security oficiais rodarem com zero P0/P1.
