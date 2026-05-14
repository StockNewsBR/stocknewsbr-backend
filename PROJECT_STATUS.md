# StockNewsBR Project Status

Atualizado em: 2026-05-14

## Estado Atual

- API local reiniciada pelo `venv` Python 3.11.9 via `scripts/start_api_venv.ps1`.
- Etapa 1 - Runtime e start local fechada em 100% via `scripts/start_all_local.ps1`.
- `scripts/start_all_local.ps1` mata processos antigos nas portas 8000 e 3000, sobe a API pelo `venv`, sobe o web em `127.0.0.1:3000`, registra fingerprints do codigo atual e roda smoke API + browser.
- Web local reiniciada em `http://127.0.0.1:3000`.
- Quotes publicos validam preco real; payload com apenas volume/variacao nao e quote valida.
- Contrato publico de quote/cache/chart/news fechado em 100% na Etapa 2.
- Quotes publicos agora classificam payload como `valid`, `stale`, `partial` ou `empty`; `source=empty` e `quote_status=partial` nunca contam como sucesso.
- Cache de quote foi reduzido e nao deve persistir quote sem preco real.
- Chart publico retorna estado vazio explicito com `status=empty`, `fallback=true` e `provider_status`, nunca `{}` silencioso.
- News publicas permanecem por ticker selecionado e o smoke valida Ford e Petrobras com `cache`/`report` explicitos.
- `/panel/F` abre Ford, com chart, news e abas IA no browser.
- IA Radar foi conectada ao payload institucional e as abas exibem metricas de lente diferentes.
- IA Mapa, Radar, Probabilidade/Breakout, Liquidity Map e Score Mestre nao sobrescrevem mais leitura institucional do backend; fallback publico inclui Score/RVOL/ADX/ATR para evitar analise clonada em scores diferentes.
- Noticias publicas usam `get_symbol_news` e expoem cache/report por ticker.
- Screenshot visual validado por fallback `tab.cua.get_visible_screenshot()` quando CDP falha.
- Git operacional via MinGit portatil em `C:\Users\dcima\.codex\tools\mingit-2.54.0\cmd\git.exe`.
- Painel `/panel/F` revalidado no browser real: Ford abre com variacao real, noticia do ticker, score efetivo, range buttons e dark mode legiveis.
- Noticias do painel foram ajustadas para priorizar textos editoriais em PT-BR e cabecalhos com acento.
- Grafico ganhou pan/zoom por botoes e formata fechamento em PT-BR no resumo.
- Abas de IA removem `BUY`/`Hora:` antes do horario e mostram `Encontrado: HH:mm`.
- Cada aba de IA agora seleciona ativos por uma lente propria, evita duplicar familias BDR/USA na mesma lista e mantem ate 20 achados, com reset visual diario as 07:00.
- Backend agora persiste historico diario de achados por lente em `runtime/ai_alerts/history.json`, preservando `detected_at`, atualizando `last_seen_at`, limitando 20 alertas por IA e zerando pelo corte de 07:00 America/Sao_Paulo.
- Etapa 3 - IA institucional backend fechada em 100% no escopo de contrato/ciclo: worker gera `ai_tools` em todo ciclo com 11 IAs, ate 20 alertas por IA, `detected_at`, `score`, `signal`, `state`, `trigger`, `invalidacao`, `metrics`, `reason` e `news_context`.
- Cada IA usa lente propria no backend: heat map por forca/fraqueza relativa, radar por aceleracao/momentum/anomalia, breakout por resistencia/volume/falha, compressao por ATR/squeeze, fluxo por volume/persistencia, smart money por absorcao/defesa, acumulacao por estabilidade/compra discreta, varredura por stop hunt/falso rompimento, liquidity map por zonas/reacao, regime por tendencia/lateralidade/reversao e Score Mestre por composicao ponderada.
- Worker preserva historico em arquivo, mas publica no snapshot a ordem calculada da lente atual; isso evita que a ordem cronologica antiga clone listas entre IAs.
- Quando o `signal_cache` vem sem preco real, as IAs marcam `data_quality=score_only`, usam o score do scanner como prior fraco e nao inventam volume, preco, zona de liquidez ou squeeze pronto.
- Rotas HTTP publicas nao chamam mais provider/cache externo proibido diretamente; provider/news/chart/quotes foram encapsulados em services para passar o guard operacional.
- `scripts/start_api_venv.ps1` sobe a API em background pelo `venv` Python 3.11.9, mata processo velho na porta 8000 e grava logs em `runtime/api-start.log`, `runtime/api-stdout.log` e `runtime/api-stderr.log`.
- Etapa 4 - Coerencia de trade e sinais fechada em 100% no escopo backend/chart: decisoes agora passam por regras explicitas de regime, liquidez, fluxo, tendencia e volatilidade antes de virarem entrada operacional.
- O motor de decisao bloqueia compra em downtrend sem reversao confirmada, venda/short contra squeeze comprador, breakout sem volume e short contra smart money/regime de alta.
- Score Mestre e eventos do grafico agora carregam `trigger`, `invalidation`, `risk`, `risk_level`, `coherence_status`, `blocked_reasons`, `warnings` e regras de coerencia aplicadas.
- Sinais de grafico (`BUY`, `SELL`, `SHORT`, `COVER`) foram revisados para explicar entrada, saida e risco; marcadores tecnicos derivados ficam como `derived_watch` e exigem confirmacao de regime/volume/fluxo.
- Etapa 5 - Grafico IA e Day Trade UX fechada em 100%: marcadores agora usam a linguagem operacional `Buy Long`, `Close Long`, `Sell Short` e `Close Short`.
- Tooltip de marcador passa a expor horario, motivo, trigger, invalidacao e risco; marcadores derivados aparecem como `Watch`, nao como ordem operacional.
- Guiado, Trader e Pro mostram leitura atual, direcao operacional, confirmacao necessaria, invalidacao e risco na mesma dobra.
- Engine do grafico ficou mais institucional para day trade: cooldown apos saida, bloqueio de pullback comprado colado em resistencia, bloqueio de short colado em suporte, protecao de ganho e saida por perda de microestrutura.
- Etapa 6 - News, Social e Polls fechada em 100%: news publicas/privadas filtram itens pelo ticker solicitado, nunca reaproveitam noticia de outro ativo sem estado explicito, e expoem `state`, `scope`, `cache` e `report`.
- Poll semanal agora usa contexto do ativo, bucket de timing, score de qualidade e evidencia de earnings; poll de resultado so entra quando ha data estruturada na semana corrente ou sinal/evento explicito de earnings/resultado/guidance.
- Perguntas antigas/genéricas de poll sao atualizadas ao reabrir o poll; a UI tambem bloqueia fallback generico e nao inventa mais earnings por lista fixa de tickers famosos.
- Feed social agora retorna `featured_posts` e `discussion_state`; discussoes em destaque sao ranqueadas por ticker, termos operacionais, engajamento e recencia.
- A aba de noticias mostra estado explicito quando falta noticia/discussao e usa discussoes destacadas por relevancia, nao apenas os primeiros posts.
- Etapa 7 - Testes e Smoke Continuo foi reaberta em 2026-05-14 por pendencia real: falta de stage/commit e regressao de idioma no modo USA.
- Etapa 7 foi fechada novamente em 100%: smoke Playwright agora cobre `F`, `PETR4`, `BTCUSD`, `META34`, dark/light, troca de ticker, 11 abas IA, anti-clone, falha de provider de news, screenshot e modo USA sem labels/textos PT em top/help/IA/grafico/news/poll/social/lista ativa.
- Lista B3 agora inclui contratos futuros rolantes `WIN` e `WDO` por letra do mes/ano; lista USA inclui CME, NQ, MNQ/MNO, ES/MES e MYM.
- Top tab `IA Grafico` virou `IA Grafico/ Rede Social` em PT-BR e `AI Chart / Social` em USA; seletor BR/USA com bandeiras fica no topo e alterna interface, ajuda, chats/social, poll e copy de assinatura.
- Assinatura USA mostra aviso de conta internacional com Premium a `$49/month` ou `$500 upfront` para cartao internacional fora do Brasil.
- Etapa 8 - SaaS / Acesso / Stripe / Referral fechada em 100%: trial novo com 30 dias ate a janela de lancamento e 14 dias depois, downgrade automatico para Basico ao vencer, precos BR/USA separados, janela de refund de 7 dias, webhook Stripe sandbox validado, acesso web/app/telegram atualizado por pagamento/cancelamento e referral validado apenas no 8o dia apos pagamento.
- Referral agora exige indicado pagante ativo, nao conta antes da janela de refund, credita 1 mes a cada 3 indicacoes validas, nao gera cash/money back, aplica `Badge Vip` em 10 indicacoes, `Leaderboard VIP` em 100+ e expoe ranking mascarado na aba `Indicacoes`/`Referrals`.

## Validado

- `venv\Scripts\python.exe -m unittest tests.test_public_market_routes tests.test_market_data_loader tests.test_news_service tests.test_workspace_ai_tools tests.test_ai_radar`
- `venv\Scripts\python.exe -m unittest tests.test_workspace_ai_tools tests.test_ai_tab_audit`
- `venv\Scripts\python.exe -m unittest tests.test_ai_alert_history_service tests.test_workspace_ai_tools tests.test_ai_tab_audit`
- `npm run build` em `apps/web`
- `scripts\smoke_public_market.ps1` com `F`, `AAPL`, `PETR4`, `BBDC4`, `BTCUSD`, `META34`, `quote_status`, ranges `1D`, `1W`, `1M`, `3M`, `1Y`, e news `F`/`PETR4`.
- `powershell -NoProfile -ExecutionPolicy Bypass -File scripts\start_all_local.ps1`
- Browser real em `http://127.0.0.1:3000/panel/F`
- Browser real dark mode: ponteiros de Sentimento/Volume, labels do grafico, chips e ranges ficam visiveis.
- Browser real chart: `1D`, `1W` e `3M` recarregaram com contagem de barras diferente e sem erro de console.
- Browser real news: aba `Noticias` mostra `Notícias de F`, `Discussões em destaque` e textos principais em PT-BR.
- Playwright em `http://127.0.0.1:3000/panel/F`: 11 abas IA validadas com `Encontrado`, sem `sem horario`, sem `Hora:`, `Score`, trigger, invalidacao e metricas de lente.
- Playwright confirmou `identicalPairs=[]` entre as 11 listas top-8 das abas IA, incluindo separacao de `IA Fluxo` e `IA Liquidity Map`.
- Playwright confirmou medidores do grafico em `/panel/F`: `Sentimento` nao zera quando ha leitura (`Urso 43`) e `Volume do ativo` nao zera quando ha volume baixo (`Baixo 22`).
- Playwright confirmou chips do grafico com labels explicitas: `Viés do gráfico`, `Sinais no gráfico`, `Barras visíveis` e nota de sessao; os textos antigos `Bias`, `Marcadores` e `Janela` nao aparecem mais.
- Playwright confirmou faixas amarelas reais de pre/after-hours para `F` (`04:00` a `20:00`) e ausencia de faixa falsa para `ITUB4`, com nota de que o provider publico da B3 inicia perto de `10:00`.
- Playwright em `http://127.0.0.1:3000/panel/F`: IA Mapa, IA Radar, IA Breakout/Probabilidade, IA Liquidity Map e Score Mestre passaram sem erro de console; cada aba exibiu Score/RVOL/ADX e triggers distintos entre cards.
- `venv\Scripts\python.exe -m unittest tests.test_ai_institutional_backend tests.test_market_snapshot_ai_tools tests.test_workspace_ai_tools tests.test_ai_alert_history_service tests.test_ai_tab_audit tests.test_ai_worker_health`
- `venv\Scripts\python.exe -m unittest tests.test_http_provider_guard tests.test_public_market_routes`
- `venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py"`: 106 testes OK.
- `run_ai_worker_cycle()` validado: `tools_ready=11`, `required_fields_ok=True`, `history_persisted=True`, 20 alertas por IA, `blocked_tools=0`, `clone_audit=ok`; status geral `warning` apenas porque o cache atual de sinais esta `score_only` sem preco real.
- Validacao direta do snapshot: `clones=[]` entre top-8 das 11 IAs e nenhum campo obrigatorio faltando nos alertas.
- `venv\Scripts\python.exe -m unittest tests.test_trade_decision_engine tests.test_trend_breakout_signal_engine tests.test_market_snapshot_ai_tools tests.test_workspace_ai_tools`: 23 testes OK.
- `venv\Scripts\python.exe -m unittest tests.test_ai_institutional_backend tests.test_market_snapshot_ai_tools tests.test_workspace_ai_tools tests.test_ai_alert_history_service tests.test_ai_tab_audit tests.test_ai_worker_health tests.test_trade_decision_engine tests.test_trend_breakout_signal_engine`: 41 testes OK.
- `venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py"`: 112 testes OK.
- `npm run build` em `apps/web`: build OK apos revisao dos sinais/coerencia.
- `git diff --check -- app/ai/trade_decision.py app/ai/ai_master_score.py app/engine/signal_engine.py app/engine/trend_breakout_signal_engine.py app/services/chart_overlay_service.py tests/test_trade_decision_engine.py tests/test_trend_breakout_signal_engine.py`: sem erro; apenas avisos esperados de LF para CRLF no Windows.
- `run_ai_worker_cycle()` revalidado apos Etapa 4: `tools_ready=11`, `required_fields_ok=True`, `trade_action=BUY`, `coherence_status=ok`, `risk_level=baixo`, `trigger_present=True`, `invalidation_present=True`, `risk_present=True`, `blocked_reasons=[]`, `warnings=[]`; status geral ainda `warning` por dado externo/cache sem preco real em alguns caminhos.
- `powershell -NoProfile -ExecutionPolicy Bypass -File scripts\start_all_local.ps1`: API pelo `venv` Python 3.11.9, web em `127.0.0.1:3000`, smoke API OK e `/panel/F` com status 200.
- `venv\Scripts\python.exe -m unittest tests.test_chart_overlay_service tests.test_trend_breakout_signal_engine`: 10 testes OK.
- `venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py"`: 113 testes OK.
- `npm run build` em `apps/web`: build OK apos UX do grafico, tooltips e modos Guiado/Trader/Pro.
- Browser interno em `http://127.0.0.1:3000/panel/F`: modos Guiado/Trader/Pro validados com `Leitura atual`, `Direcao operacional`, `Confirmacao necessaria`, `Invalidacao` e `Risco`.
- Browser interno validou zoom/pan (`Zoom +`, `Zoom -`, `Direita`) e ranges `1D`, `1W`, `1M`, `3M`, `1Y`, todos com botao unico e estado ativo correto.
- Browser interno validou dark mode alternando claro/escuro, sem erro de console.
- Browser interno confirmou contrato de tooltip no DOM (`Horario`, `Motivo`, `Trigger`, `Invalidacao`, `Risco`) e ausencia dos textos antigos `Close entry / SELL` e `LONG entry`.
- `venv\Scripts\python.exe -m unittest tests.test_public_news_service tests.test_social_discussion_service tests.test_poll_service`: 21 testes OK.
- `venv\Scripts\python.exe -m unittest tests.test_public_market_routes tests.test_public_news_service tests.test_poll_service tests.test_social_discussion_service`: 31 testes OK.
- `venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py"`: 123 testes OK.
- `npm run build` em `apps/web`: build OK apos contrato de news/feed/poll.
- `powershell -NoProfile -ExecutionPolicy Bypass -File scripts\start_all_local.ps1`: API pelo `venv` Python 3.11.9, web em `127.0.0.1:3000`, smoke API OK e browser smoke OK em `/panel/F`.
- Smoke direto: `/public/market/news/F?limit=6` retornou `symbol=F`, `status=ok`, `count=6`, `mixed_ticker_allowed=false`.
- Smoke direto: `/public/market/news/PETR4?limit=6` retornou `symbol=PETR4`, `status=ok`, `count=6`, `mixed_ticker_allowed=false`.
- Smoke direto: `/poll/F` retornou poll ativa com pergunta contextual (`sem evento dominante... confirmar fluxo comprador...`) e sem texto antigo `vai bater o anúncio do trimestre`.
- Playwright em `http://127.0.0.1:3000/panel/F`: poll nao generica, aba `Noticias de F`, `Discussões em destaque`, ausencia do poll antigo de earnings e `console_errors=0`.
- `npm run build` em `apps/web`: build OK em 2026-05-14 apos correcoes finais de USA/listas/grafico.
- `powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start_all_local.ps1`: API pelo `venv` Python 3.11.9 e web em `127.0.0.1:3000` revalidados antes do smoke final da Etapa 7.
- `npm run smoke:etapa7`: OK em 2026-05-14; validou `F`, `PETR4`, `BTCUSD`, `META34`, dark/light, troca de ticker, USA/BR, 11 abas IA, horario/Score/Trigger/Invalidacao, anti-clone, screenshots e PETR4/USA sem termos PT em news/poll/social/lista ativa.
- Varredura extra Playwright em USA para `F` e `PETR4`: zero hits para `ativo`, `preco`, `sem preco`, `Abrir`, `Excluir`, `Ajuda`, `Grafico`, `Leitura`, `Invalidacao`, `Risco`, `medio`, `baixo`, `alto` e `tendencia`.
- `venv\Scripts\python.exe scripts\smoke_news_provider_failure.py`: OK com `status=provider_error` explicito para `PETR4`.
- `venv\Scripts\python.exe -m unittest tests.test_public_news_service tests.test_news_service`: 13 testes OK.
- `git diff --check -- PROJECT_STATUS.md apps/web/app/globals.css apps/web/components/workspace-shell.tsx apps/web/components/workspace-rails.tsx apps/web/components/workspace-sections.tsx apps/web/components/ticker-chart.tsx apps/web/package.json apps/web/scripts/smoke-etapa7.mjs scripts/smoke_news_provider_failure.py`: sem erro; apenas avisos esperados de LF para CRLF no Windows.
- `venv\Scripts\python.exe -m unittest tests.test_access_service tests.test_referral_service tests.test_stripe_webhook`: 10 testes OK cobrindo trial 30/14, pricing BR/USA, downgrade/acesso, anti-fraude de referral no 8o dia, recompensa a cada 3 indicacoes, badges e webhook Stripe sandbox.
- `venv\Scripts\python.exe -m compileall app\services\access_service.py app\services\referrals.py app\services\legal_service.py app\api\stripe_webhook.py app\auth.py`: sintaxe OK.
- `npm run build` em `apps/web`: build/typecheck OK apos adicionar a aba `Indicacoes`/`Referrals`.
- Smoke API isolado em `127.0.0.1:8001`: `/billing/pricing?market=USA` retornou `currency=USD`, `$49/$500`, `trial_days=30`, `refund_window_days=7`; `/billing/referrals/leaderboard?limit=10` retornou lista estruturada e `valid_after_days=8`.
- Browser real em `http://127.0.0.1:3001/panel/F`: aba `Indicacoes` abriu em PT-BR, seletor USA trocou a aba para `Referrals` e a copy da etapa para ingles; screenshots em `runtime/stage8-referrals.png` e `runtime/stage8-referrals-en.png`.

## Smoke Atual

- Quotes: `F`, `AAPL`, `PETR4`, `BBDC4`, `BTCUSD`, `META34` retornaram preco real com `quote_status=valid`.
- Quote vazio: `/public/market/quote/ZZZZ999` retornou `source=empty` e `quote_status=empty`, sem ser tratado como sucesso.
- Charts: `F` em `1D`, `1W`, `1M`, `3M`, `1Y`; `AAPL`, `PETR4`, `BTCUSD`, `META34` em `1D`.
- News: `/public/market/news/F?limit=6` e `/public/market/news/PETR4?limit=6` retornaram noticias por ticker com `cache=ok` e `report=ok`.
- Runtime: `scripts\start_all_local.ps1` confirmou `python_executable=C:\Users\dcima\stocknewsbr-backend\venv\Scripts\python.exe`, Python `3.11.9`, API em `127.0.0.1:8000`, web em `127.0.0.1:3000` e `/panel/F` com status 200.
- Browser smoke: `runtime/browser-smoke-stdout.log` confirmou `browser_panel_ok status=200 body_chars=8306 console_errors=0`.
- Codigo atual: `runtime/start-all-local.log` registrou fingerprints de `main.py`, `apps/web/app/panel/[slug]/page.tsx` e `apps/web/components/workspace-shell.tsx` antes de subir API/web; fingerprint final do `workspace-shell.tsx`: `CEE220093B76`.
- Runtime revalidado em 2026-05-13 14:13:51 pelo `venv` Python 3.11.9; API 8000 e web 3000 subiram, smoke API passou e `/panel/F` retornou `browser_panel_ok status=200 body_chars=8098 console_errors=0`.
- Runtime revalidado em 2026-05-13 15:06:33 pelo `venv` Python 3.11.9; API 8000 e web 3000 subiram, smoke API passou e `/panel/F` retornou `browser_panel_ok status=200 body_chars=8420 console_errors=0`.
- Runtime revalidado em 2026-05-13 15:25:38 pelo `venv` Python 3.11.9; API 8000 e web 3000 subiram, smoke API passou e `/panel/F` retornou `browser_panel_ok status=200 body_chars=8353 console_errors=0`.
- Runtime revalidado em 2026-05-13 19:02:35 pelo `venv` Python 3.11.9; API 8000 e web 3000 subiram, smoke API passou e `/panel/F` retornou `browser_panel_ok status=200 body_chars=8687 console_errors=0`.
- Etapa 6 smoke: news de Ford e Petrobras vieram com ticker correto, `mixed_ticker_allowed=false`; poll de Ford veio contextual e sem pergunta generica de earnings.

## Controle da Etapa Atual

- Etapa 0 - Trava de controle: revisada em 2026-05-14; `PROJECT_STATUS.md` foi lido antes de continuar.
- Estado atual conhecido: Etapa 1 fechada em 100%; Etapa 2 fechada em 100%; Etapa 3 fechada em 100%; Etapa 4 fechada em 100%; Etapa 5 fechada em 100%; Etapa 6 fechada em 100%; Etapa 7 fechada em 100%; Etapa 8 fechada em 100%.
- Arquivos alterados nesta etapa: `app/services/access_service.py`, `app/services/legal_service.py`, `app/services/referrals.py`, `app/api/stripe_webhook.py`, `app/auth.py`, `apps/web/components/workspace-shell.tsx`, `tests/test_access_service.py`, `tests/test_referral_service.py`, `tests/test_stripe_webhook.py` e `PROJECT_STATUS.md`.
- Testes/smokes registrados: `venv\Scripts\python.exe -m unittest tests.test_access_service tests.test_referral_service tests.test_stripe_webhook`; `venv\Scripts\python.exe -m compileall app\services\access_service.py app\services\referrals.py app\services\legal_service.py app\api\stripe_webhook.py app\auth.py`; `npm run build` em `apps/web`; smoke API em `127.0.0.1:8001`; browser real em `127.0.0.1:3001/panel/F` com screenshots PT/USA da aba de referrals.
- Proxima etapa clara: iniciar apenas a proxima etapa formal que o usuario indicar, mantendo a regra de nao abrir nova etapa antes da anterior ficar fechada.
- Stage/commit: fechado nesta rodada somente com os arquivos listados nesta etapa, sem incluir alteracoes antigas de outras etapas.

## Riscos Restantes

- Yahoo Finance segue sendo provider externo de noticias. Se ele falhar, a API deve expor `provider_status`, `provider_error`, `attempted_candidates`, `cache.status` e `report.status`; nao deve inventar noticia nem reutilizar noticia de outro ticker.
- O smoke browser passou, mas Yahoo Finance segue sujeito a falhas externas; a Etapa 2 agora valida o estado explicito em vez de tratar vazio como sucesso.
- O PATH do usuario foi atualizado para MinGit, mas o processo atual do Codex pode precisar ser reiniciado para reconhecer `git` sem caminho absoluto.
- Existem muitas alteracoes antigas no working tree. Ao commitar, stage apenas arquivos do patch atual para nao misturar trabalho anterior.
- O Windows pode mostrar o processo da porta 8000 como Python base por causa do redirector do `venv`; a validacao confiavel e o log `Runtime bootstrap` do app com `sys.executable`.
- O worker agora alimenta `ai_tools` por ciclo, mas o `signal_cache` atual ainda pode chegar sem preco/volume real; nesses casos o backend marca `data_quality=score_only`, mantem trigger/invalidacao conservadores e a auditoria fica em `watch` ate o cache trazer dados reais.
- Yahoo/market provider ainda pode imprimir 404 para aliases como `META34.SA`; isso nao bloqueou o contrato `ai_tools`, mas deve continuar monitorado no pipeline de dados.
- O arquivo `C:\Users\dcima\OneDrive\Dokumenty\A ONDE ESTAMOS EM 05.12 -lista.odt` estava bloqueado por outro processo durante a revisao; reabrir quando liberar para confirmar a proxima etapa.
- Sinais tecnicos derivados do grafico agora sao marcados como `derived_watch`; eles nao devem ser tratados como entrada institucional sem confirmacao de regime, fluxo, volume e liquidez.
- A coerencia bloqueia conflitos obvios, mas a qualidade final ainda depende do `signal_cache` receber preco/volume reais em vez de somente score do scanner.
- O grafico agora reduz sinais operacionais falsos em lateralizacao, mas a qualidade do day trade ainda depende da granularidade do OHLC e de volume real do provider.
- `Watch` no grafico significa observacao/confirmacao pendente; nao deve ser tratado como ordem de compra/venda.
- News ainda depende do Yahoo Finance; quando o provider falhar, o contrato agora deve expor `provider_status`, `provider_error`, `cache`, `report` e estado vazio em vez de misturar outro ticker.
- Poll de earnings fica mais forte quando o snapshot/trading signal traz `earnings_date` estruturado; se vier apenas texto de earnings/resultado/guidance, o poll marca a origem como `signal_text` e deve ser tratado como evidencia mais fraca.
- Discussao em destaque depende de posts reais do ticker. Quando nao houver post util, a API retorna `discussion_state=empty` ou `no_relevant_discussion` para a UI nao fingir contexto social.
- Etapa 7: modo USA tem trava Playwright contra regressao de PT em interface, ajuda, rails, lista ativa, social, chart, poll, news e PETR4; conteudo bruto externo de provider ainda deve ser monitorado se vier em idioma original da fonte.
- Etapa 7: `pytest` nao esta instalado no `venv`/Python global desta sessao; os testes Python focados foram executados via `unittest` e o smoke Playwright cobriu o contrato anti-clone/coerencia visual.
- Etapa 8: Stripe foi validado em sandbox/webhook local; antes de producao ainda e necessario conferir os Price IDs reais no painel Stripe e garantir que metadata `user_id`/`product_id` esteja vindo do checkout real.
- Etapa 8: referral depende de evento pago em `subscription_audit_logs`; eventos externos sem usuario resolvido ficam `unresolved` e nao validam indicacao, como esperado para evitar fraude basica.

## Proximo TODO

- Etapa 1 esta 100% concluida.
- Etapa 2 esta 100% concluida.
- Etapa 3 esta 100% concluida no backend institucional: worker gera `ai_tools`, historico preservado, listas nao clonadas, campos obrigatorios completos e Score Mestre com composicao ponderada.
- Etapa 4 esta 100% concluida: coerencia de trade bloqueia sinais operacionalmente ruins, grafico explica trigger/invalidacao/risco e Score Mestre expoe a composicao de risco/coerencia.
- Etapa 5 esta 100% concluida: grafico usa labels operacionais, tooltips completos, modos Guiado/Trader/Pro com decisao clara, dark mode, zoom/pan e ranges validados.
- Etapa 6 esta 100% concluida: news por ticker, poll semanal contextual, earnings poll com evidencia, discussao destacada por relevancia e estados vazios explicitos.
- Etapa 7 esta 100% concluida: smoke Playwright multi-ticker/dark-light/troca de ticker/IA tabs/anti-clone, USA/BR, PETR4/USA sem textos PT, screenshot de UI, smoke de falha de provider de news e stage/commit da etapa atual registrados.
- Etapa 8 esta 100% concluida: trial 30/14, pricing BR/USA, refund 7 dias, downgrade para Basico, Stripe sandbox, acesso web/app/telegram, referral antifraude, recompensa a cada 3, badges e ranking `Indicacoes`/`Referrals` validados.
- Reexecutar smoke completo apos qualquer mudanca em provider/cache/chart/news, worker ou nas abas IA.
- Se for criar commit, usar o MinGit por caminho absoluto enquanto o Codex nao recarregar PATH.
- Separar refatoracoes institucionais maiores em commits pequenos por area: data/api, ai, web, tests.
- Proxima melhoria de produto: ligar preco/volume real ao `signal_cache` que alimenta o worker para elevar a auditoria IA de `watch` para `approved`, sem inventar dado de mercado.
- Proxima melhoria de dados B3: se o produto exigir leilao/pre-abertura antes de 10:00, integrar provider que entregue esse feed; o chart atual nao inventa barras antes da primeira barra recebida.
