# Missão 33 — Android Go Live

Data: 10/07/2026 · Branch: `feat/github-workflow-ai-tools` · BASE_COMMIT: `8caba1764f90a3df428115f651504538148cd336` (Missão 32)

## Escopo executado

Auditoria e QA do app Android (Expo SDK 53 / RN 0.79.7) em emulador real, mais correções e features autorizadas pelo owner durante a missão.

### Bugs corrigidos (descobertos no emulador)

1. **`lib/api.ts` — `DOMException` inexistente no Hermes.** Qualquer erro de API (incluindo login inválido) exibia `Property 'DOMException' doesn't exist` na UI. Corrigido detectando abort por `error.name === "AbortError"`.
2. **Render loop no logout — "Maximum update depth exceeded".** `<Redirect>` declarativos pareados entre `/` e `/(tabs)` entravam em ping-pong. Corrigido com `router.replace` em `useEffect` + render `null` (em `app/index.tsx` e `app/(tabs)/_layout.tsx`). Pré-existente; o logout nunca havia sido exercitado.
3. **Gráfico nunca carregava.** O app chamava `GET /chart/{symbol}`, rota não montada no backend (404). O contrato real é `GET /web/chart/{ticker}`. Corrigido em `lib/api.ts:getChart`. Validado com 53 candles reais de PETR4 (worker + `warm_charts_once`).
4. **Erro 422 de validação exibia JSON bruto.** `readErrorDetail` agora agrega `detail[].msg` de erros de validação FastAPI em mensagem legível.

### Features autorizadas pelo owner (10/07)

- **i18n PT/EN completo** (`lib/i18n.tsx`): `LanguageProvider` + dicionários pt/en cobrindo todas as telas, persistência em SecureStore (`stocknewsbr.lang`), toggle com bandeiras 🇧🇷 PT / 🇺🇸 EN no topo (login, home, perfil).
- **Logo da marca** (`assets/brand-logo.png`, 256px, copiado de `apps/web/public/brand/stocknewsbr-brand.png`) à esquerda de "StockNewsBR Mobile" no login.
- **"Esqueci minha senha"**: botão no login que usa o fluxo passwordless existente `POST /auth/request-code` → OTP → `POST /auth/login/verify-otp`. Resposta genérica (sem enumeração de contas).
- **Tiles de desconto anual** ("BR anual desconto" / "USA anual desconto", −15% calculado de `12×mensal vs anual`) no login e no resumo comercial do perfil.
- **Web** (`apps/web/components/workspace-rails.tsx`): logo movido para a ESQUERDA do título "StockNewsBR" (igual ao app). Requer `npm run build` — build feito e servidor reiniciado.
- **Composer estilo website** na tela do ticker: "Compartilhe sua ideia em {ticker}", placeholder "Escreva sua tese em {ticker}", dica de gatilho/timeframe/invalidação, pills 🐂 Touro / 🐻 Urso (sentiment bullish/bearish, toggle → neutral), botões 🎯 (insere template de previsão), 🖼️/GIF (campo de URL de imagem → `image_url` do post), 😊 (linha de emojis), botão "Post". Sem dependências novas.

### Smoke test atualizado

`scripts/smoke-mobile.mjs`: os checks de contrato textual (Painel mobile do ativo, Grafico indisponivel, Trigger/Invalidacao/Risco, Trial BR, planos) foram redirecionados para `lib/i18n.tsx` exigindo presença de **ambas** as variantes PT e EN, e ganhou o check `language toggle pt/en flags`. Nenhum check removido.

## Evidências (runtime/mission_33/ — gitignored)

25 screenshots (login PT/EN, tabs, ticker com candles, deep links válido/inválido/rota inexistente, API indisponível, sessão revogada, logout, esqueci-senha, descontos, logo), logcat final (0 FATAL/ANR, 0 tokens/segredos), logs de backend/metro/worker.

## Resultados dos gates

- Gate 0: PASS (HEAD == origin == commit final da 32, tree limpo no início).
- `npm ci`: PASS · typecheck: PASS · smoke:mobile (com emulador): PASS · export:android: PASS.
- Emulador primário: AVD `Medium_Phone_API_36.1`, Android 16 (SDK 36), x86_64, 1080×2400\@420dpi, via Expo Go 2.33.22 (sem projeto nativo android/ versionado — build nativo/EAS não executado, não autorizado).
- Fluxos: login válido/inválido (sem enumeração), OTP por email, logout, troca de usuário A→B (sem vazamento entre usuários), sessão revogada (`session_replaced` → SecureStore limpo → login), deep links (válido, ticker inválido sanitizado p/ PETR4, rota inexistente → Unmatched Route sem crash), API indisponível (estados "n/a" honestos, sem preço zero fabricado), recuperação, background/foreground, force-stop/reopen.
- Segurança: tokens só em SecureStore + header Authorization; zero token/PII em logcat/UI/URLs; permissions `[]` no app.json; sem WebView; sem cleartext além do default dev `http://127.0.0.1:8000` (build de produção exige `EXPO_PUBLIC_API_BASE` https — risco documentado).
- Push nativo: NOT_APPLICABLE (app ainda não integra push client; backend da Missão 32 pronto). POST_NOTIFICATIONS não declarado.
- Rotação: NOT_APPLICABLE (portrait-only).
- CodeRabbit: executado sobre o diff não commitado ao final (ver relatório da sessão).

## Riscos residuais / backlog

- Unmatched Route do expo-router em inglês fixo (UX menor).
- `API_BASE` fallback dev `http://127.0.0.1:8000` — garantir `EXPO_PUBLIC_API_BASE` https em builds de produção.
- Sem `accessibilityLabel` na maioria dos controles (toggle de idioma já tem); backlog de acessibilidade.
- Push client mobile (registro/rotação/invalidacão de token com backend 32) ainda não implementado — próxima etapa natural.
- App icon/adaptiveIcon do app.json ainda não usam o brand-logo.

## Regras

Sem `git add`/commit/push. Sem publicação, EAS, keystore ou credenciais reais. Usuários e senhas de teste são sintéticos, existentes apenas no SQLite local de dev.
