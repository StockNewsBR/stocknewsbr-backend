# Missão 77C — Correção dos achados confirmados pela validação 77B

Data da execução: 2026-07-26/27  
Agente: Codex com Ponytail `lite`  
Repositório: `/home/dcima/stocknewsbr-backend`

## 1. Resumo executivo

A Missão 77C corrigiu o bypass premium confirmado na 77B e alinhou o contrato
consumidor de liquidez com as duas geometrias realmente possíveis:

- zona inteiramente acima/abaixo do preço: `SELL_SIDE`/`BUY_SIDE`;
- envelope válido que envolve o preço: `BOTH_SIDES`, sem inventar direção.

Durante a validação focal também foram reproduzidos e corrigidos:

- `/public/market/ai-tools` expunha o mesmo conteúdo premium fora do bundle;
- notícia fresca sem `impact` virava `READY/Neutro`;
- o painel de IA calculava “atualizado hoje” pelo evento de detecção, não pelo
  timestamp do dado-fonte;
- o teste visual antigo exigia ponteiro neutro para sentimento ausente e escala
  de volume que colocava `1×` no máximo do gauge.

O suposto caso AXIA3 → PETR4 permaneceu refutado e nenhum alias foi alterado.

Veredito: **NO-GO — BLOQUEADORES RESTANTES**. Os testes direcionados, lint,
TypeScript e build estão verdes, mas a suíte pytest completa não conclui por
travamento reproduzível do `TestClient` Starlette/httpx, e a inspeção visual
automatizada não pôde iniciar por dependência nativa ausente.

## 2. Documentos e estado inicial

Documentos lidos integralmente:

- `docs/mission_77b_codex_independent_validation.md`;
- `docs/mission_77a_opus_pre_codex_review.md`;
- `docs/mission_74_nemotron_final_audit.md`;
- `docs/mission_75_laguna_adversarial_audit.md`;
- `docs/mission_76_north_mechanical_verification.md`.

Documento solicitado mas ausente antes da implementação:

- `docs/mission_77_codex_cross_audit_and_remediation.md`.

A ausência foi registrada e não impediu a 77C porque o documento obrigatório de
evidência, a Missão 77B, existia.

Estado Git inicial salvo em
`/tmp/stocknewsbr-m77c-codex/git-initial.txt`:

```text
branch: fix/audit-remediation-2026-07
HEAD: a51c0847f2aa6169388ceb4b34a316600010742c
diff inicial: 49 files changed, 2650 insertions(+), 1602 deletions(-)
```

A working tree já continha dezenas de alterações e arquivos não rastreados.
Nenhum deles foi descartado, restaurado, limpo ou atribuído automaticamente a
esta missão.

## 3. Reprodução antes das correções

### 3.1 Insight premium

Com payload determinístico e gating ativo:

```text
BEFORE_INSIGHT
master_score=8.2
strategic_panel.recommended_action=COMPRAR
institutional_flow.label=Comprador
```

A rota `/public/market/insight/{symbol}` não possuía dependency de entitlement.
O teste novo falhou antes do patch porque
`insight_route.dependant.dependencies` não continha
`resolve_premium_entitlement`.

O runtime antigo confirmou o vazamento:

```text
GET /public/market/insight/PETR4?is_premium=true -> 200
master_score=3.9
strategic_panel presente
premium_locked ausente
```

### 3.2 AI tools direto

O código real mostrou que `/public/market/ai-tools` retornava diretamente
`build_public_ai_tools_payload`, sem entitlement. O runtime antigo retornou:

```text
status=READY
displayable_count=9
9 ferramentas visíveis para anônimo
```

Esse é o mesmo defeito de política do insight e foi tratado no mesmo patch.

### 3.3 Liquidez

Reprodução pura do contrato produtor:

```text
price=100.0
lower_liquidity=92.5
upper_liquidity=107.5
```

Resultado anterior:

```text
status=INSUFFICIENT_DATA
reason=missing_liquidity_geometry
low/high removidos do payload público
```

O consumidor aceitava somente uma zona inteira de um lado do preço, embora o
produtor `ai_liquidity_map` possa criar uma faixa envolvendo o preço.

### 3.4 Sentimento sem classificação

Antes do patch:

```text
1 notícia fresca sem impact -> READY / neutral
1 notícia fresca impact=neutral -> READY / neutral
```

Os dois estados eram indistinguíveis.

### 3.5 Timestamps e gauges

O frontend passava `detected_at` para `aiFreshnessStatus`, portanto uma análise
detectada hoje com `source_as_of` da sessão anterior recebia “Status: atualizado
hoje”. O painel também expunha `READY` cru ao lado dos timestamps.

O script Mission 68 continha duas expectativas incompatíveis com o requisito
77C:

- exigia ponteiro neutro quando sentimento era `null`;
- exigia `dailyVolumeRatio * 100`, colocando `1×` no fim do gauge.

## 4. Causas raiz

### 4.1 Bypass premium

A política era aplicada apenas no fim de `public_market_bundle`. O endpoint
direto de insight e o endpoint direto de AI tools nunca passavam pela projeção
de acesso.

Além disso, `STOCKNEWS_PREMIUM_GATING` tinha default OFF. Uma configuração
ausente equivalia a exposição integral.

### 4.2 Liquidez

Há duas situações distintas:

1. Envelope válido (`low < price < high`): incompatibilidade de representação
   entre produtor e consumidor.
2. Bounds iguais ou ausentes: dado realmente insuficiente; publicar zona ou
   lado seria fabricação.

No runtime pós-patch, PETR4, CSNA3, HYPE3 e VALE3 apresentaram bounds iguais.
Esses casos permanecem corretamente `value=null`, agora com
`reason=invalid_liquidity_range`.

### 4.3 Sentimento

O agregador contava apenas bullish/bearish e assumia que todo item restante era
neutral. Faltava contar explicitamente `neutral`, `classified_total` e
`missing_impact_count`.

### 4.4 Freshness

O rótulo amigável usava timestamp do finding em vez de `source_as_of`.
`evaluated_at` e `source_as_of`, já produzidos pelo backend, não eram usados nos
rótulos principais.

## 5. Correções implementadas

### 5.1 Premium fail-closed

Em `app/api/routes_public_market_live.py`:

- o default do gating passou a ON; somente `0/false/no/off` o desliga
  explicitamente;
- `public_market_insight` recebe
  `Depends(resolve_premium_entitlement)`;
- `_gate_insight_for_entitlement` remove master score, strategic panel, flow,
  decisões, convicção, ranking e evidências derivadas;
- `_gate_bundle_for_entitlement` reutiliza a projeção do insight, remove
  `operational_view`/liquidez premium e bloqueia AI tools;
- o bundle chama o insight como consumidor interno e aplica o gate no payload
  final, impedindo cache premium de atravessar a fronteira pública.

Em `app/api/routes_public_market.py`:

- `/public/market/ai-tools` recebe entitlement server-side;
- anônimo/Basic recebe somente
  `{"tools": {}, "status": "PREMIUM_LOCKED", "locked": true}`.

Query, header ou body não participam da elevação de plano. Token ausente ou
inválido, Basic, trial expirado e exceção de resolução permanecem `False`.

### 5.2 Contrato de liquidez

Em `_ai_metric_component`:

- zona acima: `SELL_SIDE`;
- zona abaixo: `BUY_SIDE`;
- envelope válido: `BOTH_SIDES`;
- ausência de bounds, preço, timestamp ou faixa válida permanece sem valor,
  com motivo específico;
- nenhum score, side ou range é fabricado quando `low >= high`.

O frontend aceita `BOTH_SIDES` e mostra o motivo específico quando a liquidez
não está disponível.

### 5.3 Sentimento

O backend agora publica:

- `neutral_count`;
- `classified_total`;
- `missing_impact_count`;
- `total_fresh`.

Se existe notícia fresca, mas nenhuma possui impacto reconhecido:

```text
value=null
status=INSUFFICIENT_DATA
reason=no_classified_sentiment
```

Neutral explícito continua `READY/neutral`. O frontend não desenha ponteiro sem
valor numérico e mostra categoria/amostra quando existe classificação real.

### 5.4 Timestamps e volume

O painel usa:

- `evaluated_at` → “Análise calculada em”;
- `source_as_of` → “Dados usados até”;
- freshness amigável baseado no dado-fonte;
- sem `READY` cru e sem “atualizado hoje” baseado apenas na análise.

O gauge de volume manteve a escala correta:

```text
0× = 0%
1× = 50%
>=2× = 100% visual, com valor real ainda exibido
4,42× = 100% visual
```

## 6. Arquivos alterados pela Missão 77C

Alterações de código/teste atribuíveis ao Codex:

- `app/api/routes_public_market_live.py`;
- `app/api/routes_public_market.py`;
- `apps/web/components/workspace-shell.tsx`;
- `apps/web/lib/types.ts`;
- `apps/web/scripts/mission-68-functional-recovery.mjs`;
- `tests/test_premium_gating.py`;
- `tests/test_on_demand_hydration.py`;
- `tests/test_public_market_routes.py`;
- este relatório.

`apps/web/tsconfig.tsbuildinfo` já estava modificado no estado inicial e foi
tocado novamente pelo build. Não foi restaurado, conforme a instrução.

## 7. Testes adicionados ou fortalecidos

- insight direto exige dependency de entitlement;
- claim `?is_premium=true` não substitui entitlement server-side;
- insight Pro mantém conteúdo;
- AI tools direto é gated;
- gating ausente no ambiente é fail-closed;
- trial/Pro/enterprise/Basic/token inválido/token ausente/trial expirado;
- envelope de liquidez `BOTH_SIDES`;
- notícia sem impact não vira neutral;
- neutral explícito permanece neutral e contabilizado;
- testes de bundle passaram a declarar entitlement premium ao testar o contrato
  completo, sem depender do antigo default fail-open;
- Mission 68 valida ausência de ponteiro para `null`, amostra classificada e
  escala/clamping de 4,42×.

Os dois testes de bundle em `test_public_market_routes.py` mantiveram todos os
asserts e passaram a chamar a função de rota diretamente. O `TestClient` deste
ambiente não despachava o endpoint e travava no portal anyio; o gating HTTP é
coberto por introspecção da dependency e pela reprodução no runtime real.

## 8. Evidência depois

### 8.1 Runtime anônimo com claim falso

Após recarregar backend com `STOCKNEWS_PREMIUM_GATING=1`:

```text
GET bundle PETR4/JPM/LCID/CSNA3/HYPE3/VALE3?is_premium=true -> 200
access_status=basic
premium_locked=true
insight.master_score=null
insight.strategic_panel=null
ai_tools.status=PREMIUM_LOCKED
market_metrics.operational_view=null
market_metrics.liquidity=null
```

```text
GET /public/market/insight/PETR4?is_premium=true -> 200
master_score=null
strategic_panel=null
institutional_flow=null
premium_locked=true
```

```text
GET /public/market/ai-tools?symbol=PETR4&is_premium=true -> 200
status=PREMIUM_LOCKED
tools={}
locked=true
```

### 8.2 Liquidez premium em execução direta

Sem criar usuário/credencial artificial, a execução do bundle com entitlement
interno explícito observou:

| Símbolo | Resultado | Motivo |
|---|---|---|
| PETR4 | `INSUFFICIENT_DATA`, `value=null` | `invalid_liquidity_range` |
| CSNA3 | `INSUFFICIENT_DATA`, `value=null` | `invalid_liquidity_range` |
| HYPE3 | `INSUFFICIENT_DATA`, `value=null` | `invalid_liquidity_range` |
| VALE3 | `INSUFFICIENT_DATA`, `value=null` | `invalid_liquidity_range` |
| JPM | `INSUFFICIENT_DATA`, `value=null` | nenhuma row de liquidez |
| LCID | `INSUFFICIENT_DATA`, `value=null` | nenhuma row de liquidez |

O teste determinístico prova que um envelope válido é `READY/BOTH_SIDES`. O
runtime prova que bounds degenerados não são promovidos artificialmente.

### 8.3 Sentimento e conclusões

Runtime:

```text
JPM  -> bearish, classified_total=6
LCID -> bearish, classified_total=2
PETR4/CSNA3/HYPE3/VALE3 -> value=null, no_fresh_sentiment_source
```

JPM e LCID possuíam preços diferentes (`353.2534` e `6.28`) e amostras
diferentes, mas ambos estavam sem Master Score, flow e liquidez. `WAIT` é
legítimo por insuficiência; não foi reproduzida colisão de cache nem conclusão
LLM compartilhada. PETR4 e HYPE3 produziram resumos diferentes quando o flow
material diferiu (comprador versus vendedor).

## 9. Pytest direcionado

Comando solicitado:

```text
PYTHONPATH=. venv/bin/pytest -q -p no:cacheprovider \
  tests/test_premium_gating.py \
  tests/test_public_market_routes.py \
  tests/test_single_snapshot_source.py \
  tests/test_strategic_panel.py \
  tests/test_on_demand_hydration.py \
  tests/test_safe_float.py
```

Resultado real:

```text
82 passed, 3 subtests passed in 36.16s
```

Regressões finais de premium/liquidez/sentimento:

```text
32 passed in 2.57s
```

Contratos adicionais de AI tools, freshness e news:

```text
45 passed, 10 subtests passed in 0.72s
```

## 10. Pytest completo

Comando executado:

```text
PYTHONPATH=. venv/bin/pytest tests/ -p no:cacheprovider
```

Resultado real, sem inventar conclusão:

```text
collected 1173 items
5 testes observados como passed
travamento no primeiro TestClient de Stripe
execução interrompida sem resumo final
```

O node isolado
`StripeWebhookAtomicityTests::test_stripe_different_integrity_error_not_duplicate`
também excedeu o timeout. O faulthandler mostrou:

- thread principal esperando `starlette.testclient.TestClient.post`;
- portal anyio com event loop ocioso;
- nenhuma thread executando o endpoint.

Log: `/tmp/stocknewsbr-m77c-codex/pytest-full-blocker.log`.

Portanto, não há resultado `passed/failed/skipped/xfailed/duração` da suíte
completa. Também não há falha de assert comprovada. O bloqueio é do harness
Starlette/httpx atual e ocorre fora dos arquivos funcionais da 77C.

## 11. Frontend

### Lint

```text
npm run lint
exit 0
0 errors
26 warnings preexistentes (hooks, <img>, workspace root)
```

### TypeScript

```text
npm run tsc
exit 0
```

### Contrato Mission 68

```text
npm run test:mission68
48/48 PASS
```

### Build

```text
npm run build
exit 0
Next.js 15.5.19
compiled successfully
5/5 static pages
/site gerado
26 warnings, 0 errors
```

O build interfere com `.next` de um `next dev` simultâneo. O frontend foi
reiniciado depois do build e `/site` voltou a HTTP 200.

## 12. Runtime

Processos finais executam a partir do repositório canônico:

- backend `127.0.0.1:8000`;
- frontend `127.0.0.1:3000`.

Resultados:

```text
GET /                         -> 200, status=running
GET /openapi.json             -> 200
GET /site                     -> 200
GET /system/health            -> 503 internal_token_not_configured
```

O `503` do health interno é fail-closed esperado porque a rota exige
`X-Internal-Token` e o ambiente não possui token interno configurado. Nenhuma
credencial foi criada ou registrada.

A inspeção visual automatizada não foi concluída:

- `agent-browser`: binário ausente;
- Playwright instalado: Chromium não inicia por `libnspr4.so` ausente;
- nenhuma dependência foi instalada.

## 13. Problemas não reproduzidos ou não alterados

- AXIA3 → PETR4: refutado pela 77B; aliases intocados.
- Cache de conclusão JPM/LCID: chave já inclui ticker; colisão não reproduzida.
- Conclusão inteira idêntica com componentes materiais distintos: não
  reproduzida no payload atual.
- Título original em inglês em pt-BR: comportamento de contrato atual; nenhuma
  tradução foi inventada e nenhuma LLM é chamada no render.
- Liquidez a partir de volume alto: não implementado porque volume não substitui
  bounds válidos.
- Gauge 4,42×: código já o posicionava na região máxima com escala `×50`; o
  falso positivo estava no script antigo.

## 14. Bloqueadores restantes e veredito

Bloqueadores:

1. suíte pytest completa sem conclusão por deadlock do `TestClient`;
2. inspeção visual desktop/mobile indisponível por dependências do host;
3. health interno não auditável sem token interno configurado;
4. liquidez real permanece insuficiente quando o produtor entrega bounds iguais;
   isso agora é explícito, mas exige melhoria futura do produtor se o produto
   precisar de uma zona operacional;
5. símbolos sem rows de IA (JPM/LCID) continuam com conclusão determinística de
   insuficiência, não uma análise rica.

### NO-GO — BLOQUEADORES RESTANTES

Os dois achados centrais da 77B foram corrigidos sem tocar aliases e sem fabricar
liquidez. Entretanto, o critério formal de GO exige suíte backend completa
concluída e validação visual/runtime integral. Essas duas provas não estão
disponíveis neste ambiente.

Não houve `git add`, commit ou push.

## 15. Estado Git final

Captura completa:
`/tmp/stocknewsbr-m77c-codex/git-final.txt`.

```text
branch: fix/audit-remediation-2026-07
HEAD: a51c0847f2aa6169388ceb4b34a316600010742c
diff final: 51 files changed, 2841 insertions(+), 1643 deletions(-)
```

Comparação com o estado inicial:

- o HEAD e a branch permaneceram iguais;
- a working tree preexistente permaneceu intacta;
- a Missão 77C acrescentou alterações focalizadas nos nove itens listados na
  seção 6;
- o único documento novo criado nesta missão foi este relatório;
- nenhum arquivo preexistente foi descartado, restaurado, limpo ou sobrescrito
  em massa.
