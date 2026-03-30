# AGENTS.md

## Runtime

- Python: `3.11.9`
- API local: `uvicorn main:app --reload`
- Worker local: `py -3.11 worker.py`
- Telegram bot local: `py -3.11 app/telegram/bot.py`

## Product Model

- Launch principal: app Google Play
- Trial padrao: 90 dias
- Pos-trial: conta migra automaticamente para `free`
- Premium mensal: `R$49`
- Premium anual: `R$500`
- Premium libera: `app`, `website`, `telegram`
- Apple Store: preparada para etapa posterior

## Product Surfaces

- Superficie ativa hoje: backend FastAPI + workspace/landing HTML em `app/web/` e `app/Frontend/`
- App web dedicado (`Next.js`) agora existe em `apps/web/`
- App mobile dedicado (`Expo/React Native`) agora existe em `apps/mobile/`
- Quando esses shells forem criados, preferir separar em `apps/web/` e `apps/mobile/`

## Engine Overview

Fluxo principal:

`market data -> feature matrix -> scanners -> ranking -> signal cache -> snapshot -> API/web/telegram`

## API Rules

- Nunca chamar provedores externos de mercado diretamente dentro de endpoints HTTP.
- Sempre priorizar cache compartilhado, snapshot e dados do worker.
- Rotas de `web` devem exigir acesso `web`.
- Rotas internas e operacionais devem usar `X-Internal-Token`.

## Critical Areas

Revisar com cuidado antes de alterar:

- `main.py`
- `worker.py`
- `app/engine/engine_orchestrator.py`
- `app/engine/market_snapshot_engine.py`
- `app/services/access_service.py`
- `app/services/poll_service.py`
- `app/system/ai_worker.py`

## Social And Polls

- Ticker rooms e feed social vivem na camada `app/api/routes_feed.py` e `app/social/`
- Polls semanais de IA vivem em `app/services/poll_service.py`
- Telegram deve validar acesso por rota interna antes de entregar sinais

## Operational Notes

- `app/system/ai_worker.py` roda auditoria continua, auto-heal de snapshot e pregera polls semanais
- Relatorios do AI Worker ficam em `runtime/ai_worker/`
- Polls semanais ficam em `runtime/polls/`
- O dominio oficial do projeto e `https://www.stocknewsbr.com`
- O starter externo do ChatGPT web serve como referencia de UX/scaffold, nao como runtime principal
