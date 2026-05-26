# StockNewsBR Mobile

App `Expo / React Native` para o lançamento principal em Android, com suporte preparado para iOS.

## O que o app cobre

- login com email e senha
- OTP por email para contas Premium
- plano BR e USA sincronizado com `/billing/pricing`
- trial inicial de 30 dias e trial definitivo de 14 dias apos a janela de lancamento
- aviso de refund/cancelamento de 7 dias
- dashboard do workspace
- mercado, heatmap, radar e top movers
- feed social por ticker
- enquete semanal por ticker
- painel mobile por ticker com preco, ranges, candles, zonas, marcadores, news, feed e poll
- perfil, Telegram e logout
- configuracao EAS para build Android App Bundle da Google Play

## Arquivos principais

- `app/index.tsx`
- `app/_layout.tsx`
- `app/(tabs)/index.tsx`
- `app/(tabs)/market.tsx`
- `app/(tabs)/social.tsx`
- `app/(tabs)/polls.tsx`
- `app/(tabs)/profile.tsx`
- `app/ticker/[symbol].tsx`
- `lib/api.ts`
- `lib/session.tsx`
- `components/ui.tsx`
- `components/mobile-price-chart.tsx`
- `eas.json`
- `scripts/smoke-mobile.mjs`

## Rodar

1. instalar dependencias em `apps/mobile`
2. copiar `.env.example` para `.env`
3. ajustar `EXPO_PUBLIC_API_BASE` se necessario
4. rodar `npm start`

## Validar

```powershell
npm run typecheck
npm run smoke:mobile
npm run export:android
```

Para exigir aparelho ou emulador visivel no smoke:

```powershell
$env:REQUIRE_MOBILE_DEVICE="1"; npm run smoke:mobile
```

## Google Play

Checklist antes de enviar para producao:

- `app.json` usa pacote Android `com.stocknewsbr.mobile` e `versionCode` incremental.
- `eas.json` gera `app-bundle` no profile `production`.
- Produtos comerciais esperados no backend e na Play Console:
  - `premium_br_monthly`
  - `premium_br_annual`
  - `premium_usa_monthly`
  - `premium_usa_annual`
- Checkout/assinatura deve respeitar 7 dias de cancelamento/refund.
- Conta internacional usa assinatura USA: `$49/month` ou `$500 upfront`.
- Build de envio:

```powershell
npx eas build --platform android --profile production
npx eas submit --platform android --profile production
```
