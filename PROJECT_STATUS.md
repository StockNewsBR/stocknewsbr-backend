# StockNewsBR Project Status

Atualizado em: 2026-05-07

## Estado Atual

- API local reiniciada pelo `venv` Python 3.11.9 via `scripts/start_api_venv.ps1`.
- Web local reiniciada em `http://127.0.0.1:3000`.
- Quotes publicos validam preco real; payload com apenas volume/variacao nao e quote valida.
- Cache de quote foi reduzido e nao deve persistir quote sem preco real.
- `/panel/F` abre Ford, com chart, news e abas IA no browser.
- IA Radar foi conectada ao payload institucional e as abas exibem metricas de lente diferentes.
- Noticias publicas usam `get_symbol_news` e expoem cache/report por ticker.
- Screenshot visual validado por fallback `tab.cua.get_visible_screenshot()` quando CDP falha.
- Git operacional via MinGit portatil em `C:\Users\dcima\.codex\tools\mingit-2.54.0\cmd\git.exe`.

## Validado

- `venv\Scripts\python.exe -m unittest tests.test_public_market_routes tests.test_market_data_loader tests.test_news_service tests.test_workspace_ai_tools tests.test_ai_radar`
- `npm run build` em `apps/web`
- `scripts\smoke_public_market.ps1`
- Browser real em `http://127.0.0.1:3000/panel/F`

## Smoke Atual

- Quotes: `F`, `AAPL`, `PETR4`, `BBDC4`, `BTCUSD`, `META34` retornaram preco real.
- Charts: `F` em `1D`, `1W`, `1M`, `3M`, `1Y`; `MSFT` em `1D`.
- News: `/public/market/news/F?limit=6` retornou noticias de Ford com ticker direto.

## Riscos Restantes

- Yahoo Finance segue sendo provider externo de noticias. Se ele falhar, a API deve expor `provider_status`, `provider_error`, `attempted_candidates`, `cache.status` e `report.status`; nao deve inventar noticia nem reutilizar noticia de outro ticker.
- O PATH do usuario foi atualizado para MinGit, mas o processo atual do Codex pode precisar ser reiniciado para reconhecer `git` sem caminho absoluto.
- Existem muitas alteracoes antigas no working tree. Ao commitar, stage apenas arquivos do patch atual para nao misturar trabalho anterior.

## Proximo TODO

- Reexecutar smoke completo apos qualquer mudanca em provider/cache.
- Se for criar commit, usar o MinGit por caminho absoluto enquanto o Codex nao recarregar PATH.
- Separar refatoracoes institucionais maiores em commits pequenos por area: data/api, ai, web, tests.
