# StockNewsBR Mobile

Scaffold real em `Expo/React Native` para Android primeiro e iOS depois.

## Arquivos principais

- `app/index.tsx`
- `app/_layout.tsx`
- `lib/api.ts`
- `.env.example`
- `app.json`

## Fluxos incluidos

- login com `/auth/login-json`
- leitura de `/auth/access`
- workspace/ranking via `/web/workspace/data`
- grafico via `/web/chart/{ticker}`
- poll via `/poll/{ticker}`

## Rodar depois de instalar Node

1. instalar Node.js
2. instalar dependencias com `npm install`
3. copiar `.env.example` para `.env`
4. rodar `npx expo start`
