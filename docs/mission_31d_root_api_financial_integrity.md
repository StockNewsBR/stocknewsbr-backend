# Missao 31D - Root App, API e Integridade Financeira

Status: `EM VALIDACAO`

## Escopo

- Base oficial: `5a7379d7`.
- Branch: `feat/github-workflow-ai-tools`.
- Objetivo: fechar hardening de root app, API e integridade financeira sem alterar Score Mestre, Ranking, Signal Engine, Decision Envelope ou regras BUY/SELL/SHORT/COVER.

## Alteracoes aplicadas

- Stripe webhook agora falha fechado quando `STRIPE_WEBHOOK_SECRET` esta ausente ou vazio.
- Stripe webhook rejeita chamada sem `stripe-signature`, assinatura invalida, evento sem `id` e evento sem `type`.
- Stripe webhook valida `mode`, `payment_status`/`paid`, `status`, `customer`, `subscription`, produto/preco permitido, `livemode` e ownership antes de ativar Premium.
- Stripe webhook rejeita apropriacao de `stripe_customer_id` ou `stripe_subscription_id` ja vinculados a outro usuario e faz rollback antes de gravar auditoria.
- Removido fallback de parse direto de JSON nao assinado no webhook Stripe.
- Replay sequencial e concorrente no mesmo processo passa por trava de webhook e checagem de evento ja processado antes de qualquer efeito financeiro.
- Auditoria Stripe grava somente payload sanitizado com `provider`, `event_id` e `event_type`, sem email, telefone, cartao, metadata bruta, headers ou assinatura.
- `/auth/subscription/sync` nao ativa Premium a partir de `active=true` enviado pelo cliente quando nao ha verificador real de provedor; retorna `subscription_provider_verification_unavailable`.
- `/auth/subscription/sync` preserva downgrade/revogacao segura e grava payload de auditoria por allowlist, sem `purchase_token`.
- `INTERNAL_API_TOKEN` passa a tratar placeholders triviais como nao configurados, preservando o fail-closed 503.
- `X-Internal-Token` nao ASCII passa a ser rejeitado com 403, sem 500, mantendo `compare_digest` em bytes para tokens ASCII validos.
- `.env.example` deixa de sugerir placeholder trivial de token interno.
- Paper Trading passa a preservar timestamps ISO aware, Zulu e naive como epoch UTC em `source_snapshot_timestamp`, mantendo fallback conservador para timestamp invalido.

## Classificacao dos achados

- Stripe webhook fail-open sem secret/assinatura: `CONFIRMED` e corrigido nesta missao.
- Stripe replay/idempotencia sem guarda local: `CONFIRMED` e corrigido nesta missao para repeticao sequencial e concorrencia no mesmo processo.
- Stripe logs com `payload_excerpt` bruto: `CONFIRMED` e corrigido nesta missao.
- Stripe ativava Premium sem validar estado financeiro/ownership: `CONFIRMED` e corrigido nesta missao.
- `subscription_sync` ativava Premium baseado somente em payload cliente: `CONFIRMED` e bloqueado fail-closed ate integracao real de provedor.
- `subscription_sync` podia persistir `purchase_token` no `payload_excerpt`: `CONFIRMED` e corrigido com payload allowlist.
- `log_subscription_event` tinha risco de deslocamento posicional por `provider_event_id`: `CONFIRMED` e corrigido preservando assinatura posicional.
- `X-Internal-Token` nao ASCII podia produzir 500 em `compare_digest`: `CONFIRMED` e corrigido para rejeicao 403.
- `INTERNAL_API_TOKEN` ausente/vazio: `RESOLVED_BEFORE_MISSION`; ja retornava 503 fail-closed.
- `INTERNAL_API_TOKEN` placeholder trivial: `CONFIRMED` e corrigido nesta missao.
- Score Mestre 0..100 bruto / 0..10 publico: `RESOLVED_BEFORE_MISSION`; coberto por teste de regressao 31D.
- Paper Trading com timestamp ISO nao numerico caindo para `now`: `CONFIRMED` e corrigido nesta missao.

## Contratos preservados

- Nenhum peso, formula, threshold ou regra do Score Mestre foi alterado.
- Nenhuma regra BUY, SELL, SHORT, COVER, WATCH, HOLD ou NO_TRADE foi alterada.
- Ranking, Signal Engine, Worker, Decision Envelope e Canonical Symbol Registry nao foram modificados.
- Snapshot/API/frontend/Telegram/Push mantem contrato operacional existente.

## Evidencias

- Revisao independente Tier 1: implementacao plausivel; cobertura reforcada em `tests/test_31d_atomicity_referrals.py`.
- Testes focados Tier 1: `tests.test_31d_atomicity_referrals` executado com 12 testes, PASS.
- Testes Stripe webhook focados: `tests.test_stripe_webhook` executado com 27 testes, PASS.
- Testes referral service focados: `tests.test_referral_service` executado com 3 testes, PASS.
- Testes root/API/integridade financeira focados: `tests.test_mission_31d_root_api_financial_integrity` executado com 14 testes, PASS.
- Testes Tier 2 migration/script: `tests.test_mission_31d_tier2_migration` executado com 22 testes, PASS.
- Total focado deste checkpoint: 78 testes, PASS.
- Backend completo: `python -m unittest discover tests` executado com 591 testes, PASS.
- Web TSC/build/audit: pendente.
- Mobile validacoes/audit: pendente.
- Playwright CLI: pendente.
- Playwright Interactive: pendente.
- CodeRabbit: pendente.
- Codex Security diff scan: pendente.

## Riscos e pendencias

- A idempotencia Stripe depende de deduplicacao persistente para cobrir multiprocesso, multiplas instancias, restart e concorrencia real.
- PostgreSQL multiprocesso segue `PENDENTE/BLOCKED`; RLock protege somente o processo atual e a prova cross-process exige PostgreSQL real/staging.
- Integracao real com Google Play/App Store/servico interno de verificacao ainda e necessaria para reabilitar ativacao via `/auth/subscription/sync`.
- Politica de comprimento minimo para `INTERNAL_API_TOKEN` nao foi inventada nesta missao; apenas placeholders triviais passam a falhar fechado.

## Plano formal Tier 2 - IMPLEMENTACAO CONTROLADA

Status: `IMPLEMENTACAO AUTORIZADA, EXECUCAO NAO AUTORIZADA`.

O plano Tier 2 foi aprovado para implementacao controlada no repositorio. Nenhuma migration foi executada em qualquer banco nesta etapa. Nenhum DDL foi executado contra producao, Render ou banco externo.

### Objetivo

Garantir idempotencia persistente do webhook Stripe por `(provider, provider_event_id)` para evitar efeito financeiro duplicado em ambientes com multiplos workers, multiplas instancias, restart de servidor ou reentrega concorrente do mesmo evento.

### Principios obrigatorios

- `ensure_runtime_schema` nao deve ser responsavel por criar `provider_event_id` nem o objeto de unicidade desta mudanca.
- O usuario runtime da aplicacao nao deve depender de permissoes DDL para iniciar.
- A migration deve ser executada por usuario/rotina operacional separada, antes do deploy que exigir a coluna/indice em producao.
- Nao deve existir redundancia entre `UniqueConstraint` tradicional e indice manual sem justificativa formal.
- PostgreSQL multiprocesso permanece `PENDENTE/BLOCKED` ate validacao com banco PostgreSQL real, duas conexoes independentes, duas Sessions e dois workers/processos concorrentes.

### Mecanismo de migration identificado

- Alembic nao existe no repositorio.
- Nao ha mecanismo formal versionado de migration.
- O projeto usava `ensure_runtime_schema` como patch runtime/startup.
- Para esta mudanca, foi criado script operacional versionado standalone:
  - `scripts/migrations/0001_add_provider_event_id_unique.py`
- O script recebe `DATABASE_URL` exclusivamente por variavel de ambiente.
- O script nao imprime nem registra o valor de `DATABASE_URL`; registra apenas o dialeto.
- Sem `--apply`, executa somente diagnostico/preflight.
- Com `--apply`, executa DDL apenas apos preflight aprovado e estrategia explicita de indice quando o indice precisar ser criado.

### Estado implementado no repositorio

- `app/models.py` mantem `SubscriptionAuditLog.provider_event_id` como coluna nullable.
- `app/models.py` nao mantem `UniqueConstraint("provider", "provider_event_id")`.
- `app/database_schema.py` nao contem mais patch runtime para adicionar `provider_event_id`.
- `app/database_schema.py` nao contem mais patch runtime para criar `uq_subscription_audit_provider_event`.
- `ensure_runtime_schema`, lifespan, startup e import de modulo nao executam `ALTER TABLE`, `CREATE INDEX` ou `CREATE UNIQUE INDEX` desta mudanca.
- `Base.metadata.create_all` pode refletir o modelo em ambientes locais/dev, mas nao substitui migration operacional em producao.

### Objeto canonico escolhido

Objeto canonico em PostgreSQL:

```sql
CREATE UNIQUE INDEX uq_subscription_audit_provider_event
ON subscription_audit_logs(provider, provider_event_id)
WHERE provider_event_id IS NOT NULL;
```

Justificativa:

- O evento Stripe so e deduplicavel quando `provider_event_id` existe; registros historicos nao Stripe podem permanecer com `NULL`, mas registros historicos Stripe sem `provider_event_id` bloqueiam a criacao do indice/finalizacao ate reconciliacao operacional.
- PostgreSQL permite multiplos `NULL` em unique constraints, mas o indice parcial expressa melhor o contrato, evita indexar historico sem `provider_event_id` e reduz superficie de lock/manutencao.
- SQLite tambem permite multiplos `NULL` e suporta indices parciais em versoes modernas, mas a garantia operacional Tier 2 e PostgreSQL.
- `UniqueConstraint` tradicional nao representa o predicado `WHERE provider_event_id IS NOT NULL`.
- Reflection deve tratar esse objeto via `get_indexes`; `get_unique_constraints` pode nao retornar o indice parcial como constraint.
- O ORM declara a coluna, mas a unicidade canonica fica no script/migration operacional para evitar objeto redundante no metadata.

### Caminho para banco novo

1. Criar schema base por processo operacional adotado pelo ambiente, nao por startup automatico da API em producao.
2. Garantir que `subscription_audit_logs.provider_event_id` exista como coluna nullable.
3. Executar `scripts/migrations/0001_add_provider_event_id_unique.py` em preflight.
4. Aplicar a migration somente com nova autorizacao humana e `--apply`.
5. Criar o indice unico parcial canonico antes de receber webhooks em producao.
6. Validar coluna, indice, duplicatas e replay Stripe.
7. Testes locais SQLite podem validar contrato basico e idempotencia do script, mas nao provam comportamento PostgreSQL multiprocesso.

### Caminho para banco existente

1. Executar preflight completo.
2. Adicionar a coluna nullable se ausente.
3. Manter historico nao Stripe existente com `provider_event_id = NULL`; historico Stripe sem `provider_event_id` deve ser reconciliado ou aceito em decisao operacional separada antes da unicidade.
4. Validar duplicatas nao nulas antes de criar unicidade.
5. Criar o objeto canonico de unicidade conforme estrategia A ou B, apos escolha operacional explicita.
6. Validar indice.
7. Validar aplicacao e replay Stripe.
8. Habilitar deploy.
9. Monitorar erros.
10. Manter rollback disponivel.

### Deploy parcial detectado pelo script

O script deve detectar estado parcial e bloquear estado inseguro em vez de ignorar silenciosamente:

- tabela ausente sem schema base;
- coluna ausente, com acao planejada de adicionar coluna apenas em `--apply`;
- coluna ausente com historico Stripe existente, bloqueando qualquer DDL ate decisao/reconciliacao operacional;
- coluna existente sem indice, com acao planejada de criar indice apenas em `--apply`;
- indice canonico existente com colunas/predicado incompativeis;
- constraint unica redundante;
- indice PostgreSQL `INVALID`;
- registros historicos Stripe sem `provider_event_id`;
- duplicatas de `provider_event_id`;
- duplicatas de `(provider, provider_event_id)`;
- locks ativos quando houver DDL pendente;
- transacoes longas quando houver DDL pendente;
- permissao insuficiente quando houver DDL pendente;
- dialeto nao suportado.

### Preflight obrigatorio

```sql
SELECT current_database(), current_user, version();

SELECT column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_schema = 'public'
  AND table_name = 'subscription_audit_logs'
  AND column_name = 'provider_event_id';

SELECT indexname, indexdef
FROM pg_indexes
WHERE schemaname = 'public'
  AND tablename = 'subscription_audit_logs';

SELECT conname, contype
FROM pg_constraint
WHERE conrelid = 'public.subscription_audit_logs'::regclass;

SELECT provider, provider_event_id, COUNT(*) AS duplicates
FROM subscription_audit_logs
WHERE provider_event_id IS NOT NULL
GROUP BY provider, provider_event_id
HAVING COUNT(*) > 1;

SELECT COUNT(*) AS stripe_rows_without_provider_event_id
FROM subscription_audit_logs
WHERE provider = 'stripe'
  AND provider_event_id IS NULL;

SELECT COUNT(*) AS rows_total
FROM subscription_audit_logs;

SELECT pg_size_pretty(pg_total_relation_size('public.subscription_audit_logs')) AS table_size;

SELECT pid, mode, granted
FROM pg_locks
WHERE relation = 'public.subscription_audit_logs'::regclass
  AND pid <> pg_backend_pid();

SELECT pg_catalog.pg_get_userbyid(c.relowner) = current_user
       OR pg_has_role(pg_catalog.pg_get_userbyid(c.relowner), 'MEMBER')
       OR (
           SELECT rolsuper
           FROM pg_roles
           WHERE rolname = current_user
       ) AS can_alter_table
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'public'
  AND c.relname = 'subscription_audit_logs';

SELECT indexrelid::regclass AS invalid_index
FROM pg_index
WHERE indrelid = 'public.subscription_audit_logs'::regclass
  AND indisvalid = false;

SELECT pid, state, now() - xact_start AS age
FROM pg_stat_activity
WHERE xact_start IS NOT NULL
  AND pid <> pg_backend_pid()
  AND now() - xact_start > interval '5 minutes';
```

Tambem confirmar:

- quantidade de instancias/workers que podem receber webhooks;
- janela operacional;
- backup/snapshot recente;
- plano de reversao;
- se a tabela e pequena/fria ou grande/quente.

### Estrategia de criacao

Opcao A - tabela pequena ou janela controlada:

- criar coluna nullable em migration transacional quando permitido;
- criar indice normal documentando lock de escrita;
- usar apenas se o preflight confirmar baixo volume e janela segura.

Opcao B - tabela quente ou grande:

- criar coluna nullable em etapa propria;
- criar o indice com `CREATE UNIQUE INDEX CONCURRENTLY`;
- executar fora de transaction block;
- usar conexao/autocommit dedicada;
- detectar e remover indice `INVALID` de tentativa anterior antes de repetir;
- alinhar ORM/migration depois, sem DDL automatico em startup.

`CREATE UNIQUE INDEX CONCURRENTLY` nao deve ser escolhido automaticamente sem evidencia de tamanho, volume ou risco operacional. O script exige estrategia explicita quando a criacao do indice for necessaria.

### Modos do script

Preflight somente leitura:

```powershell
$env:DATABASE_URL="<definido-fora-do-repositorio>"
python scripts/migrations/0001_add_provider_event_id_unique.py
```

Aplicacao com janela controlada:

```powershell
$env:DATABASE_URL="<definido-fora-do-repositorio>"
python scripts/migrations/0001_add_provider_event_id_unique.py --apply --index-strategy normal
```

Aplicacao em tabela quente/grande PostgreSQL:

```powershell
$env:DATABASE_URL="<definido-fora-do-repositorio>"
python scripts/migrations/0001_add_provider_event_id_unique.py --apply --index-strategy concurrent
```

Exit codes:

- `0`: preflight/aplicacao bem-sucedidos ou estado ja aplicado e validado;
- `2`: preflight reprovado, configuracao ausente ou estado inseguro;
- `3`: falha SQLAlchemy/aplicacao ou validacao pos-apply reprovada;
- `4`: erro inesperado.

### Upgrade

1. Preflight aprovado e salvo como evidencia operacional.
2. Decidir estrategia normal ou concurrente conforme tamanho/uso.
3. Aplicar migration com usuario autorizado e nova autorizacao humana.
4. Confirmar coluna, indice canonico valido e ausencia de duplicatas.
5. Deploy da aplicacao sem exigir DDL no startup.
6. Executar replay Stripe focado.
7. Executar teste PostgreSQL multiprocesso antes de declarar Tier 2 concluido.

### Rollback

1. Reverter codigo, se o deploy da aplicacao precisar ser revertido.
2. Para indice concorrente, executar fora de transaction block:

```sql
DROP INDEX CONCURRENTLY IF EXISTS uq_subscription_audit_provider_event;
```

3. Para indice normal, usar `DROP INDEX IF EXISTS` em janela controlada.
4. Manter a coluna nullable em rollback imediato para preservar dados historicos, salvo decisao separada para remocao.
5. Se houver indice `INVALID`, remover explicitamente antes de nova tentativa.
6. A remocao da coluna nao e automatica e exige decisao humana separada.

### Criterio de aprovacao PostgreSQL multiprocesso

Permanece `PENDENTE/BLOCKED` ate existir evidencia com:

- PostgreSQL de teste;
- migration aplicada;
- duas conexoes independentes;
- duas Sessions;
- dois processos/workers;
- mesmo `event_id`;
- exatamente um efeito financeiro;
- exatamente um audit log;
- segundo processamento tratado como duplicate;
- nenhum HTTP 500 indevido no replay duplicado.
