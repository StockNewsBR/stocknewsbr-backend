# Mission 31B.1 — Official accounts, official bot, anti-impersonation — FINAL

## Estado inicial
- **Repositório canônico:** `/mnt/c/Users/dcima/stocknewsbr-backend` (= GitHub `origin`).
- **Branch:** `feat/github-workflow-ai-tools`.
- **Base commit:** `c26bfd06` — `feat(31B): harden secure login and session auth` (31B completa: código + 66 testes).
- **Working tree no Gate 0:** clean.
- **Pré-requisito 31B:** PASS no CodeRabbit; 31B presente e verde localmente (66 testes).

> Nota de reconciliação: a 31B completa vivia no commit `c26bfd06` do repo Windows e foi
> pushada ao GitHub durante a sessão (o tip avançou `60cabbc2` → `c26bfd06`). O checkout WSL
> `/home/dcima/stocknewsbr-backend` estava desatualizado; o repo canônico de trabalho é o Windows.

## Arquivos alterados (7 M, +77 linhas) e não rastreados (3)
Modificados:
- `app/models.py` (+7) — colunas de identidade
- `app/database_schema.py` (+17) — migration idempotente (SCHEMA_PATCHES)
- `app/schemas.py` (+5) — flags de badge em `UserAccessResponse`
- `app/services/access_service.py` (+5) — serialização das flags
- `app/services/auth_audit_service.py` (+5) — eventos de auditoria
- `app/auth.py` (+33) — anti-impersonação em `register` e `PATCH /profile`
- `apps/web/lib/types.ts` (+5) — contrato de badge no front

Novos (untracked):
- `app/social/identity_guard.py` — motor de normalização/anti-impersonação/links oficiais
- `app/services/official_identity_service.py` — identidades oficiais, seed, guard do bot
- `tests/test_mission_31b1_official_accounts.py` — 23 testes / 50 subtests

## Resumo das alterações
- **Taxonomia de identidade (forge-proof):** novas colunas `official`, `role` (enum user/official/bot/system/moderator/admin), `is_bot`, `official_identity_locked`. `is_verified` reutilizado (sem duplicar). Migration mínima e idempotente via `SCHEMA_PATCHES` (ALTER ADD COLUMN com DEFAULT; testado em DB novo e antigo).
- **Anti-impersonação:** `identity_guard.normalize_identity` colapsa caixa, espaços, `_ - .`, acentos (NFKD), caracteres invisíveis (categorias C/Z), homoglyphs Cyrillic/Greek/full-width e leet. Reservados de marca (`stocknewsbr/stocknews/snbr`) e de papel (`admin/suporte/bot/oficial/verified/...`). `register` e `PATCH /profile` bloqueiam identidades reservadas para usuários comuns (403/400 + auditoria).
- **Payload hardening:** `UserProfileUpdateRequest` já é `extra="forbid"` → `official/verified/role/is_bot/is_admin/scopes/permissions/badges` rejeitados com 422. `UserRegister` descarta campos desconhecidos → sem escalada por registro. Verificado por grep: nenhum código seta `official/role/is_bot` a partir de payload de usuário.
- **Conta e bot oficiais:** `official_identity_service.ensure_official_identities` (idempotente) cria "StockNewsBR Oficial" (`official=true, verified=true, role=official, is_bot=false`) e "StockNewsBR Bot" (`role=bot, is_bot=true, official=true`).
- **Least privilege do bot:** `assert_bot_content_allowed` bloqueia BUY/SELL/SHORT/COVER, alerta operacional (antes da Missão 32) e conteúdo sem fonte auditável.
- **Badge:** exposto apenas a partir das flags de backend (`official/verified/role/is_bot`) em `serialize_user_access`; nunca inferido de nome/emoji.
- **Links oficiais:** `is_official_link` valida por hostname real (parse), com allowlist `stocknewsbr.com`/`www.stocknewsbr.com`; bloqueia substring/subdomínio/`@`-trick.
- **Auditoria:** eventos `impersonation_blocked`, `official_identity_provisioned`, `official_content_published`, `bot_content_blocked` no trilho `AuthAuditEvent` existente.

## Matriz de requisitos (20 testes obrigatórios)
| # | Requisito | Cobertura |
|---|---|---|
| 1 | Usuário comum não cria username reservado | ✅ `test_01` |
| 2 | Não altera display_name para identidade oficial | ✅ `test_02` + `PATCH /profile` guard |
| 3 | Normalização (caixa/espaço/acento/pontuação) | ✅ `test_03` |
| 4 | Payload official=true não torna oficial | ✅ `test_04...07` (422) |
| 5 | Payload verified=true não verifica | ✅ `test_04...07` |
| 6 | role=admin/official/bot rejeitado | ✅ `test_04...07` |
| 7 | is_bot=true não cria bot | ✅ `test_04...07` |
| 8 | Conta oficial real official=true+verified=true | ✅ `test_08` |
| 9 | Bot oficial real role=bot+is_bot=true | ✅ `test_09` |
| 10 | Badge depende da flag backend, não do nome | ✅ `test_10` |
| 11 | Emoji verificado não cria badge | ✅ `test_11` |
| 12 | Homoglyph/invisível não burla reserva | ✅ `test_12` |
| 13 | Bot não gera BUY/SELL/SHORT/COVER | ✅ `test_13` |
| 14 | Bot não publica notícia sem fonte | ✅ `test_14` |
| 15 | Bot não dispara alerta antes da M32 | ✅ `test_15` |
| 16 | Links oficiais validados por hostname | ✅ `test_16` |
| 17 | Substring/subdomínio enganoso bloqueado | ✅ `test_17` |
| 18 | Auditoria registra ações oficiais/bot | ✅ `test_18` |
| 19 | Endpoints irmãos sem bypass | ✅ `test_19` + self-review grep |
| 20 | Contratos anteriores da 31B válidos | ✅ `test_20` + regressão 66 testes |

## Testes executados e resultados
- **Final hardening (pós-rescan Claude):** `tests/test_mission_31b1_official_accounts.py` → **32 passed, 65 subtests, 0 fail** (29 anteriores + `EmailChangeGuardTests` + `SeedWiringSmokeTests`×2).
- **Security fix P1/P2/P3 (pos-Codex Security):** mesmo suite → **29 passed, 63 subtests, 0 fail**.
- **Regressão auth/session/guardian/moderation/31B.1:** `tests -k "31b1 or auth or session or guardian or moderation"` → **112 passed** (as 3 falhas + 35 erros de coleção = `pandas` ausente no venv subset, testes de engine de mercado/`session_end` de pregão, ortogonais a 31B.1; no venv full = exit 0).
- **31B.1 focado:** `tests/test_mission_31b1_official_accounts.py` → **23 passed, 50 subtests, 0 fail**.
- **Regressão (Gate 4):** `test_mission_31b_auth_login_session` (66) + `test_auth_session_service` + `test_mission_31b0` + `test_social_guardian` + `test_moderation_service` + 31B.1 → **123 passed, 126 subtests, 0 fail**.
- **Migration ALTER-path:** DB de produção simulado (sem colunas) → `ensure_runtime_schema` aplica idempotente; defaults `official=0, role='user', is_bot=0` em linhas antigas. OK.
- **Web (Gate 4 web):** `tsc` → exit 0; `lint` → exit 0 (warnings pré-existentes em `workspace-shell.tsx`); `next build` → **"✓ Compiled successfully in 42s"** (exit 0).
- **Mobile:** `npm --prefix apps/mobile run typecheck` (`tsc --noEmit`) → exit 0 (contrato aditivo não quebra).
- **Auditoria E2E (backend vivo):** `node apps/web/scripts/mission-31b1-official-accounts-audit.mjs` contra uvicorn de teste (:8010, sqlite isolado) → **15/15 PASS**: register bloqueia reservados/homoglyph (400), payload `official`/`role=admin` rejeitado (422), display_name impersonador bloqueado (400), `GET /me` expõe flags e badge de usuário comum = false. Relatório: `runtime/mission_31b1_official_accounts_report.json`. Script degrada para SKIPPED se o backend não estiver de pé.
- **Ambiente de teste:** venv Python 3.14 com subset de deps (sqlalchemy/fastapi/pydantic/passlib/jose/uvicorn/pytest). `ENV=test` + `OTP_PEPPER` de teste. (O backend real do usuário em :8000 não foi tocado.)

## Evidências
- **Anti-impersonação:** `test_01/02/03/11/12` (reservados, display_name oficial, normalização, emoji, homoglyph/invisível).
- **Payload hardening:** `test_04...07` (422 em `UserProfileUpdateRequest`), `test_19` (register descarta), grep de mass-assignment vazio.
- **Bot oficial:** `test_09/13/14/15` (identidade + least privilege).
- **Conta oficial:** `test_08/10/10b` (flags backend + badge).
- **Web:** tsc/lint verdes; `UserAccess` recebeu `official/verified/role/is_bot`.
- **Mobile:** não afetado (nenhum arquivo mobile alterado; contrato apenas adiciona campos opcionais — backward-compatible).

## Codex Security / CodeRabbit
- **Codex Security diff scan:** retornou **SECURITY_DIFF_SCAN_FAIL** com 1 P1, 1 P2 e 1 P3.
- **P1 corrigido:** seed oficial/bot agora é fail-closed. Conta pública preexistente com e-mail oficial/bot não é promovida; identidades canônicas já travadas continuam idempotentes; sessões ativas de identidade oficial reconciliada são revogadas e `password_hash` fica login-disabled (`!`).
- **P2 corrigido:** normalização preserva separadores para tokenização segura e bloqueia palavras reservadas sensíveis isoladas, como `Suporte Trader`, `Admin Trader`, `Sistema Trader`, `Bot Trader` e `Oficial Trader`.
- **P3 corrigido:** links oficiais aceitam somente `http`/`https` com hostname real em allowlist; `javascript`, `data`, `file`, `ftp` e scheme ausente são bloqueados.

## Rescan independente (Claude) + final hardening
- **Rescan read-only (Claude):** re-executou os 29 testes, `git diff --check` limpo, e confirmou P1/P2/P3 corrigidos. Confirmação-chave: `official/role/is_bot/official_identity_locked` são escritos **exclusivamente** por `official_identity_service._apply_identity` (o seed) — grep no repo inteiro: zero mass-assignment via payload. Veredito: **0 P0/P1**.
- **Novo achado do rescan → P3-LOW `email-change` (CORRIGIDO):** o `register` reservava e-mails oficiais, mas o endpoint-irmão `POST /email-change/request` ([app/auth.py](app/auth.py)) não. Adicionado o mesmo guard `is_official_service_email(new_email)` → 400 `official_email_reserved` + auditoria `impersonation_blocked`. Teste `EmailChangeGuardTests` prova que usuário comum não migra para `oficial@`/`bot@stocknewsbr.com`. (Já era contido por OTP-para-o-alvo + badge=flags, mas fechado por defense-in-depth.)
- **Wiring do seed no runtime (LIGADO, mínimo e seguro):** `main.py` `lifespan` chama `_seed_official_identities_if_needed()` após o schema — caminho de bootstrap controlado já existente, **sem rota pública, sem Telegram/Push, o bot não publica nada**. Fail-closed: conflito de identidade oficial → log de erro + skip (conta pública **nunca** promovida). Gate por env `SEED_OFFICIAL_IDENTITIES` (default on). Idempotente. Smoke `SeedWiringSmokeTests` (idempotência + fail-closed no conflito).
- **`is_official_link` → N/A nesta missão:** não há superfície runtime hoje que aceite/renderize um "link oficial" (em `schemas.py` só há `avatar_url` de imagem e `deep_link` do Telegram). Conforme decisão, **não foi criada feature nova**; a função permanece disponível e unit-testada para a futura superfície de badge/perfil.
- **Trading/Score/Ranking/Radar/Snapshot/Telegram/Push:** inalterados.

## Riscos residuais / pendências
- **Reexecutar Codex Security `security-diff-scan` (formal)** sobre o diff atual — gate obrigatório.
- Rodar **CodeRabbit real** somente após o Codex formal retornar 0 P0/P1 (exige commit→push→PR; não invocável por Claude/Codex local).
- Commit/push do diff (Claude proibido).
- A UI social de badge (feed/comentários/chat) não existe neste repo web — o contrato de flags já está pronto no `types.ts`; o audit `.mjs` cobre o contrato de API.
- Migration idempotente; nenhuma coluna existente foi alterada.

## Conclusão
Após o SECURITY_DIFF_SCAN_FAIL: P1/P2/P3 corrigidos pelo Codex; rescan independente do Claude confirmou 0 P0/P1 e encontrou + fechou 1 P3-LOW (`email-change`); seed ligado ao bootstrap de forma mínima/fail-closed; `is_official_link` documentado como N/A. **Sem commit e sem push**. `git diff --check` limpo. Testes: 32 focados + 112 regressão relevante (venv subset).

**STATUS: MISSION_31B1_READY_FOR_FORMAL_SECURITY_RESCAN** — não declarar PASS formal até o Codex Security formal retornar 0 P0/P1 e, depois, CodeRabbit real retornar 0 Critical/Major.
