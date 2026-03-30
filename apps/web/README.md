# StockNewsBR Web App

App web dedicado do StockNewsBR em `Next.js`, integrado com a API real do backend.

## Objetivo

- consumir o backend atual em `main.py`
- validar produto visual e comercial em uma superficie web propria
- substituir gradualmente as telas HTML de `app/Frontend/`

## Variaveis

Copie `apps/web/.env.example` para `.env.local` e ajuste:

- `NEXT_PUBLIC_API_BASE`
- `NEXT_PUBLIC_DEFAULT_TOKEN` opcional para desenvolvimento

## Rotas integradas

- `POST /auth/login-json`
- `GET /auth/access`
- `GET /public/bootstrap`
- `GET /web/workspace/data`
- `PUT /web/workspace/layout`
- `GET /web/chart/{ticker}`
- `GET /ticker/{ticker}/feed`
- `POST /ticker/{ticker}/post`
- `GET /poll/{ticker}`
- `POST /poll/{ticker}/vote`
- `GET /chat/{ticker}/history`
- `POST /chat/{ticker}/message`
- `GET /push/status`
- `POST /api/media/upload`

## Superficies

- `/` workspace principal
- `/panel/[slug]` popout para multi-monitor
