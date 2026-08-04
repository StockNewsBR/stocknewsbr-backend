# 35R.3A — Production Operations Decision + Runbooks

**Data:** 2026-07-11
**Branch:** `feat/github-workflow-ai-tools`
**Baseline:** `5ee6301d5046191a428ba02ec5200438be92a3cc`
**Status:** `DOCUMENTED_NOT_OPERATIONALLY_VERIFIED`
**Go-live:** não autorizado por este documento
**Missão 35 reprise:** não iniciada

## 1. Objetivo e limites

Este documento registra a decisão de banco de produção recomendada pelo owner e cria os runbooks mínimos exigidos para uma futura reprise da Missão 35. Ele não comprova capacidade, deploy, backup, restore, rollback, observabilidade ou operação em produção.

Nenhum procedimento abaixo autoriza automaticamente uma mudança externa. Toda ação mutável exige change record, owner humano, janela aprovada, evidência anterior e critério explícito de abortar.

Invariantes desta etapa:

- o sistema permanece `PAPER_ONLY`;
- nenhum runbook pode burlar o Decision Envelope;
- snapshot stale, preço inválido, volume inválido ou `decision_ready=false` continuam bloqueando promoção e alertas;
- nenhum incidente autoriza inventar preço, volume, score, notícia ou confiança;
- nenhum segredo deve aparecer em comando, log, ticket ou screenshot;
- a produção nunca pode degradar silenciosamente de PostgreSQL para SQLite;
- este documento não altera Score Mestre, pesos, thresholds ou regras BUY/SELL/SHORT/COVER/WATCH/HOLD/NO_TRADE.

## 2. Evidência observada

### Observado no repositório

- `app/database.py`, `app/config.py` e `app/core/settings.py` usam `sqlite:///./stocknews.db` quando `DATABASE_URL` não está definido.
- O runtime aceita banco externo por `DATABASE_URL` e configura pool para dialetos não SQLite.
- `scripts/migrations/0001_add_provider_event_id_unique.py` possui preflight read-only e aplicação explícita para PostgreSQL/SQLite.
- Não existem políticas RLS, configuração pgAudit, roles PostgreSQL ou `SET LOCAL` de contexto por usuário versionados.
- `render.yaml` descreve API, engine worker e bot Telegram, mas Render está inativo e a capacidade não foi verificada.
- Existem `/ping`, `/system/status`, `/system/health`, `/system/readiness`, `/system/metrics` e `/system/observability/dashboard`.
- Existem kill switches `READ_ONLY_MODE`, `DISABLE_PUSH_ALERTS`, `DISABLE_TELEGRAM_ALERTS`, `DISABLE_AI_DECISIONS`, `DISABLE_PROVIDER_<NAME>` e `DISABLE_SYMBOL_<SYMBOL>`.
- Não foi localizado fluxo versionado de solicitação de dados do usuário ou exclusão de conta.

### Inferido a partir da evidência

- SQLite continua adequado para local/dev/test e testes determinísticos, mas não prova isolamento multiusuário por RLS, auditoria pgAudit, least privilege por roles, concorrência multiprocesso ou recuperação institucional.
- Os endpoints atuais ajudam na triagem, mas não substituem tracing distribuído; `OPENTELEMETRY_NOT_IMPLEMENTED` permanece aberto.
- Os runbooks abaixo reduzem o blocker documental `OPERATIONS_NOT_READY`, porém só exercícios reais podem fechar os blockers operacionais.

## 3. Decisão de banco de produção

### Opções consideradas

| Opção | Uso | Vantagem | Limitação para a Missão 35 |
| --- | --- | --- | --- |
| A — PostgreSQL obrigatório | Produção/go-live | RLS, pgAudit, roles, backups e concorrência institucional | Exige provider, configuração, migração, testes e operação ainda não comprovados |
| B — SQLite temporário | Local/dev/test | Simplicidade e compatibilidade atual | Não atende os controles de produção exigidos sem alterar formalmente a especificação |

### Decisão registrada

`POSTGRES_REQUIRED_FOR_GO_LIVE`

PostgreSQL real é obrigatório para qualquer futuro candidato de go-live. SQLite permanece permitido somente para local, desenvolvimento, testes e simulações explicitamente não produtivas.

A Opção B só poderá voltar a ser considerada se o owner alterar formalmente a especificação da Missão 35 e aceitar, por escrito, a ausência de RLS, pgAudit e roles PostgreSQL. Este documento não faz essa alteração.

### Controles obrigatórios antes de aprovar PostgreSQL

1. Provider e plano de PostgreSQL selecionados, com capacidade e região documentadas.
2. `DATABASE_URL` injetado por secret manager, sem fallback SQLite em produção.
3. Role de runtime sem `SUPERUSER`, ownership de tabelas ou `BYPASSRLS`.
4. Role de migração separada, temporária e auditada.
5. Inventário das tabelas por usuário/tenant e políticas RLS com `USING` e `WITH CHECK`.
6. `FORCE ROW LEVEL SECURITY` onde o modelo de ameaça exigir proteção contra owner paths.
7. Contexto de usuário aplicado com `SET LOCAL` dentro de cada transação, sem vazamento no pool.
8. pgAudit habilitado e validado, com retenção, acesso e mascaramento definidos.
9. Testes usuário A versus usuário B, incluindo create/read/update/delete e background workers.
10. Pool, timeouts, locks, transações longas e comportamento multiprocesso validados no banco candidato.
11. Backup automático comprovado e restore exercitado em banco isolado.
12. Rollback de aplicação e migração ensaiados.

Até essas evidências existirem, usar:

- `DB_PRODUCTION_DECISION_RECORDED`
- `POSTGRES_PRODUCTION_NOT_PROVISIONED`
- `RLS_NOT_IMPLEMENTED_OR_NOT_PROVEN`
- `PGAUDIT_NOT_IMPLEMENTED_OR_NOT_PROVEN`
- `POSTGRES_ROLES_NOT_IMPLEMENTED_OR_NOT_PROVEN`

## 4. Modelo operacional mínimo

### Papéis humanos pendentes

| Papel | Responsabilidade | Status |
| --- | --- | --- |
| Product owner | risco final e autorização de release | `PENDING` |
| Incident commander | coordenação, timeline e comunicação | `PENDING_OWNER` |
| Database owner | PostgreSQL, backup, restore, RLS e migrações | `PENDING_OWNER` |
| Security owner | incidente, segredos, pgAudit e evidência | `PENDING_OWNER` |
| Application owner | API, worker, cache, WebSocket e rollback | `PENDING_OWNER` |
| Communications owner | Push, Telegram e comunicação ao usuário | `PENDING_OWNER` |
| Privacy/legal owner | solicitações de dados e exclusão de conta | `PENDING_OWNER` |
| Billing owner | Stripe, conciliação e entitlement | `PENDING_OWNER` |

### Endpoints de diagnóstico existentes

Todos devem ser usados somente no ambiente autorizado e sem expor respostas sensíveis em canais públicos.

- `/ping`: processo HTTP responde.
- `/system/health`: saúde agregada de snapshot, IA e polls.
- `/system/readiness`: prontidão de API, storage, push, snapshot e workers.
- `/system/status`: métricas operacionais e kill switches.
- `/system/metrics`: métricas Prometheus atuais.
- `/system/observability/dashboard`: visão agregada existente.

### Severidade operacional

| Nível | Exemplo | Ação inicial |
| --- | --- | --- |
| SEV-1 | vazamento, tomada de conta, corrupção de banco, alerta operacional indevido | conter imediatamente, preservar evidência e acionar owners |
| SEV-2 | banco/API/worker indisponível, perda ampla de alertas, Stripe inconsistente | bloquear efeitos externos e restaurar serviço controladamente |
| SEV-3 | degradação parcial, cache stale, WebSocket ou um canal de alerta indisponível | degradar explicitamente, monitorar e abrir incidente |

## 5. Runbook — Deploy

**Status atual:** `BLOCKED — RENDER_NOT_ACTIVE_NOW / CAPACITY_NOT_FULLY_VERIFIED`

**Pré-condições:** commit candidato imutável; tree limpa; testes e scans exigidos; ambiente candidato; PostgreSQL aprovado; backup e restore válidos; rollback ensaiado; owners e sign-offs registrados.

**Procedimento futuro:**

1. Abrir change record com SHA, escopo, responsáveis, janela, riscos e critério de abortar.
2. Ativar `READ_ONLY_MODE` e os switches de canais quando o plano de mudança exigir contenção de alertas.
3. Confirmar migrações em preflight read-only antes de qualquer DDL.
4. Publicar somente pelo mecanismo aprovado da plataforma, sem edição manual de código no serviço.
5. Verificar API, engine worker e bot Telegram definidos em `render.yaml`.
6. Executar smoke em `/ping`, `/system/health`, `/system/readiness` e `/system/status`.
7. Confirmar snapshot não stale, workers ativos e ausência de promoção bloqueada.
8. Liberar canais gradualmente somente após aprovação humana.

**Abortar se:** health/readiness não estabilizar; schema divergir; snapshot estiver stale; banco degradar; surgirem erros de auth, billing ou decisões incoerentes.

**Evidência:** SHA, timestamps, logs sem segredos, respostas sanitizadas, sign-offs e resultado de rollback readiness.

## 6. Runbook — Rollback

**Status atual:** `ROLLBACK_NOT_VERIFIED`

1. Identificar o último SHA comprovadamente saudável e a compatibilidade dele com o schema atual.
2. Ativar contenção de alertas antes da troca quando houver risco de duplicação ou sinal stale.
3. Reimplantar o SHA anterior pelo mecanismo aprovado; nunca usar reset destrutivo no repo operacional.
4. Não reverter banco automaticamente. Primeiro validar se a aplicação anterior aceita o schema corrente.
5. Se houver rollback de migração, usar plano específico, backup confirmado e owner de banco.
6. Revalidar `/ping`, health, readiness, auth, snapshot, Stripe, Push e Telegram.
7. Registrar causa, duração, perda de serviço, integridade dos dados e follow-up.

**Critério de sucesso:** versão anterior saudável, dados íntegros, filas/canais sem duplicação e decisão central preservada.

## 7. Runbook — Migration

**Status atual:** `POSTGRES_MIGRATION_NOT_VERIFIED`

1. Injetar `DATABASE_URL` pelo secret manager; nunca registrar seu valor.
2. Executar primeiro o preflight read-only disponível:

   `python scripts/migrations/0001_add_provider_event_id_unique.py`

3. Revisar locks, transações longas, duplicidades, ownership, tamanho e estratégia de índice.
4. Exigir backup válido e restore drill antes de DDL.
5. Aplicação exige aprovação explícita e `--apply --index-strategy normal|concurrent`.
6. Validar schema, índices, RLS, roles, pgAudit e compatibilidade da aplicação após a mudança.
7. Manter rollback de aplicação separado do rollback de dados.

**Proibido:** executar migration em produção sem preflight, backup, janela, owner e critério de abortar.

## 8. Runbook — Backup

**Status atual:** `BACKUP_RESTORE_NOT_VERIFIED`

1. Definir RPO, RTO, retenção, região, criptografia, owner e política de acesso.
2. Habilitar snapshots gerenciados do provider PostgreSQL.
3. Manter export lógico periódico em formato PostgreSQL apropriado, sem credenciais no comando ou arquivo.
4. Gerar checksum, registrar tamanho, versão do PostgreSQL e timestamp.
5. Armazenar cópia em domínio de falha separado, criptografado e com acesso mínimo.
6. Alertar para falha, atraso ou variação anormal de tamanho.
7. Considerar backup válido somente depois de um restore testado.

**Evidência mínima:** identificador do backup, checksum, retenção, owner e último restore bem-sucedido.

## 9. Runbook — Restore

**Status atual:** `RESTORE_NOT_VERIFIED`

1. Nunca testar restore diretamente sobre produção.
2. Criar banco isolado e vazio no mesmo major de PostgreSQL.
3. Restaurar o backup com credenciais temporárias e role sem acesso ao ambiente produtivo.
4. Validar schema, índices, constraints, RLS, roles, pgAudit e contagens por tabela.
5. Executar testes de integridade de auth, billing, social, alertas e snapshots sem enviar mensagens externas.
6. Medir tempo total e comparar com RTO; medir perda de dados contra RPO.
7. Destruir o ambiente de ensaio segundo política aprovada e preservar apenas evidência sanitizada.

**Critério de sucesso:** restauração reproduzível, íntegra, dentro de RPO/RTO e aprovada pelo database owner.

## 10. Runbook — Secret rotation

**Status atual:** `SECRET_ROTATION_NOT_VERIFIED`

Escopo mínimo: `SECRET_KEY`, `OTP_PEPPER`, `INTERNAL_API_TOKEN`, credenciais PostgreSQL, Stripe, Telegram, Firebase/Push, storage e providers.

1. Identificar exposição, consumidores, prazo e impacto da rotação.
2. Criar novo segredo no secret manager; nunca no repo ou ticket.
3. Definir período de sobreposição somente quando o protocolo suportar dois valores.
4. Rotacionar consumidores em ordem controlada e verificar logs mascarados.
5. Revogar o segredo antigo e confirmar que ele não autentica mais.
6. Para `SECRET_KEY`, planejar invalidação de JWT/sessões.
7. Para `OTP_PEPPER`, invalidar challenges pendentes e comunicar o impacto.
8. Para Stripe/Telegram/Push, executar smoke fake/sandbox antes de qualquer envio real.

**Escalar como SEV-1** se houver indício de vazamento ou uso não autorizado.

## 11. Runbook — Provider outage

**Status atual:** `PROVIDER_FAILOVER_NOT_VERIFIED`

1. Identificar provider, símbolos afetados, última atualização válida e impacto no snapshot.
2. Ativar o switch `DISABLE_PROVIDER_<NAME>` quando o consumidor correspondente estiver comprovadamente integrado ao switch.
3. Se a integração do switch não estiver comprovada, usar `READ_ONLY_MODE` e bloquear decisões/alertas externamente.
4. Usar somente último snapshot válido quando a regra permitir; marcar stale/degraded explicitamente.
5. Não promover ranking, Push ou Telegram sem Decision Envelope pronto.
6. Recuperar ingestão e normalização antes dos consumidores.
7. Remover contenção somente após timestamps, preço, volume e identidade canônica voltarem ao normal.

## 12. Runbook — Database outage

**Status atual:** `DATABASE_OUTAGE_DRILL_NOT_VERIFIED`

1. Declarar incidente e ativar contenção de efeitos externos.
2. Confirmar indisponibilidade, saturação do pool, locks, storage ou failover do provider.
3. Nunca apontar produção para `sqlite:///./stocknews.db` como fallback.
4. Preservar logs e métricas; não executar DDL ou repair improvisado.
5. Acionar failover gerenciado somente pelo database owner.
6. Após recuperação, validar schema, RLS, pgAudit, consistência de sessões, Stripe e filas de alertas.
7. Reprocessar eventos somente com idempotência comprovada.

## 13. Runbook — Cache outage

**Status atual:** `CACHE_RECOVERY_NOT_DRILLED`

1. Identificar camada afetada: snapshot, signal, market quote/chart, news ou last-good.
2. Bloquear promoção se o snapshot estiver stale, vazio ou inconsistente.
3. Não preencher cache manualmente com dados inventados.
4. Recuperar pelo fluxo provider → ingestão → normalização → cache/snapshot.
5. Validar símbolo canônico, timestamp, preço, volume e Decision Envelope.
6. Liberar ranking/API/Workspace/Telegram/Push somente após consistência comprovada.

## 14. Runbook — WebSocket outage

**Status atual:** `WEBSOCKET_OUTAGE_DRILL_NOT_VERIFIED`

1. Verificar conexões e erros em `/system/status`, `/system/metrics` e observabilidade.
2. Confirmar se a falha é accept, capacidade, broadcast, rede ou cliente morto.
3. Preservar API HTTP e snapshot como fonte; WebSocket não pode criar decisão paralela.
4. Reiniciar o serviço somente com autorização e depois de avaliar impacto nas conexões.
5. Validar reconexão, deduplicação, ordenação e ausência de vazamento entre usuários/salas.
6. Manter estado degradado explícito até clientes reconectarem de forma estável.

## 15. Runbook — Push outage

**Status atual:** `PUSH_OUTAGE_DRILL_NOT_VERIFIED`

1. Ativar `DISABLE_PUSH_ALERTS=1` ou `READ_ONLY_MODE=1` para conter tentativas.
2. Verificar `/push/status`, `/system/status` e métricas de dispatch.
3. Confirmar provider, credenciais, tokens inválidos, timeout e cooldown.
4. Não reenviar timeout ambíguo sem verificar deduplicação/idempotência.
5. Recuperar com envio sandbox/interno autorizado.
6. Remover o switch somente após saúde e métricas estáveis.

## 16. Runbook — Telegram outage

**Status atual:** `TELEGRAM_OUTAGE_DRILL_NOT_VERIFIED`

1. Ativar `DISABLE_TELEGRAM_ALERTS=1` ou `READ_ONLY_MODE=1`.
2. Verificar saúde Telegram em `/system/status` e métricas agregadas.
3. Confirmar token/chat configurados sem expor valores.
4. Tratar timeout após POST como ambíguo; não duplicar envio sem evidência.
5. Validar acesso do usuário e Decision Envelope antes de teste controlado.
6. Remover contenção gradualmente e monitorar deduplicação/cooldown.

## 17. Runbook — Stripe outage

**Status atual:** `STRIPE_OUTAGE_DRILL_NOT_VERIFIED`

1. Não ativar Premium com payload do cliente ou ajuste manual sem trilha autorizada.
2. Preservar eventos e respostas do webhook sem segredos ou payload sensível.
3. Confirmar assinatura, id do evento, ownership, status e idempotência.
4. Em indisponibilidade, manter entitlement conservador e registrar conciliação pendente.
5. Reprocessar eventos somente pela fonte Stripe e com deduplicação persistente comprovada.
6. Validar usuário, customer, subscription, audit log e ausência de dupla ativação.

## 18. Runbook — Security incident

**Status atual:** `SECURITY_INCIDENT_DRILL_NOT_VERIFIED`

1. Declarar SEV-1, nomear incident commander e iniciar timeline UTC.
2. Ativar `READ_ONLY_MODE` e canais de contenção aplicáveis.
3. Preservar logs, pgAudit, hashes, snapshots e evidência; não apagar ou “limpar” antes da coleta.
4. Revogar sessões/tokens e rotacionar segredos conforme o vetor confirmado.
5. Isolar componente afetado sem promover fallback inseguro.
6. Avaliar escopo de usuários/dados e acionar privacy/legal.
7. Corrigir em missão separada, com reprodução, testes e revisão independente.
8. Só encerrar após validação técnica, comunicação e post-incident review.

## 19. Runbook — User data request

**Status atual:** `USER_DATA_REQUEST_WORKFLOW_NOT_IMPLEMENTED`

1. Receber solicitação em canal oficial e gerar identificador auditável.
2. Verificar identidade sem solicitar segredo, senha ou OTP em texto.
3. Definir escopo com privacy/legal: perfil, sessões, billing, social, Push, Telegram e auditoria.
4. Extrair somente dados do solicitante, com dupla revisão contra vazamento cross-user.
5. Redigir segredos, tokens, dados de terceiros e controles internos.
6. Entregar por canal seguro e registrar prazo, owner e confirmação.
7. Não executar processo manual em produção até privacy/legal aprovar consulta, retenção e formato.

## 20. Runbook — Account deletion

**Status atual:** `ACCOUNT_DELETION_WORKFLOW_NOT_IMPLEMENTED`

1. Verificar identidade e intenção por fluxo resistente a takeover.
2. Revogar sessões, tokens Push e vínculos Telegram antes da remoção.
3. Cancelar/conciliar billing sem apagar trilha legal ou financeira obrigatória.
4. Classificar dados em delete, anonymize e retain por obrigação legal.
5. Remover dados por usuário com proteção transacional e prova de isolamento.
6. Validar que conta, sessões e dados sociais não voltam após novo login/restart.
7. Registrar evidência sanitizada e confirmação ao usuário.
8. Não executar deleção manual até existir implementação, teste e sign-off privacy/legal.

## 21. Observabilidade e capacidade

Os endpoints atuais fornecem métricas locais, mas não comprovam tracing distribuído, retenção ou alertas externos.

Status mantidos:

- `OPENTELEMETRY_NOT_IMPLEMENTED`
- `RENDER_NOT_ACTIVE_NOW`
- `CAPACITY_NOT_FULLY_VERIFIED`
- `SNAPSHOT_OPERATIONAL_BLOCKED`

Antes da reprise da Missão 35, é obrigatório definir SLOs, alertas, retenção, correlação entre API/worker/bot, dashboards e um teste de capacidade no ambiente candidato. Nenhuma meta numérica foi inventada neste documento; RPO, RTO, SLO e capacidade exigem decisão humana.

## 22. Sign-offs obrigatórios

| Sign-off | Evidência mínima | Status |
| --- | --- | --- |
| Produto | risco aceito e escopo de release | `PENDING` |
| Segurança | RLS, pgAudit, roles, secrets e scans | `PENDING` |
| Banco/infra | capacidade, backup, restore e failover | `PENDING` |
| Backend | testes, migração, snapshot e workers | `PENDING` |
| Web/Mobile | builds e fluxos candidatos | `PENDING` |
| Billing | Stripe sandbox, webhook e conciliação | `PENDING` |
| Privacy/legal | data request, deletion e retenção | `PENDING` |
| Operações | deploy, rollback e incident drill | `PENDING` |

## 23. Critérios para iniciar 35R.4

35R.4 permanece bloqueada até existir evidência de todos os itens abaixo:

- PostgreSQL de produção/candidato provisionado;
- RLS, pgAudit e roles implementados e testados;
- Render ativo ou plataforma candidata formalmente definida;
- capacidade verificada;
- snapshot operacional real válido;
- backup e restore drill aprovados;
- rollback drill aprovado;
- observabilidade e alertas operacionais;
- runbook drills prioritários executados;
- workflows de privacy/account deletion implementados ou formalmente resolvidos;
- sign-offs humanos completos;
- novo `AUDITED_COMMIT` se qualquer arquivo funcional, teste, config ou dependência mudar.

## 24. Estado após 35R.3A

| Blocker | Estado após documentação |
| --- | --- |
| `OPERATIONS_NOT_READY` | `DOCUMENTED_NOT_DRILLED` |
| `DB_PRODUCTION_DECISION_REQUIRED` | `DECISION_RECORDED_POSTGRES_REQUIRED` |
| `RENDER_NOT_ACTIVE_NOW` | aberto |
| `CAPACITY_NOT_FULLY_VERIFIED` | aberto |
| `BACKUP_RESTORE_NOT_VERIFIED` | plano documentado, aberto |
| `ROLLBACK_NOT_VERIFIED` | plano documentado, aberto |
| `SIGNOFFS_PENDING` | aberto |
| `SNAPSHOT_OPERATIONAL_BLOCKED` | aberto |
| `OPENTELEMETRY_NOT_IMPLEMENTED` | aberto |

Este documento reduz lacunas de decisão e operação. Ele não fecha nenhum blocker que dependa de infraestrutura, execução real, implementação ou aceite humano.
