# Auditoria Social Guardian - Missão 31A

**Data:** 2026-07-08  
**Status:** ANÁLISE COMPLETA  
**Repositório:** /c/Users/dcima/stocknewsbr-backend  
**Branch:** feat/github-workflow-ai-tools  

---

## ✅ IMPLEMENTADO CORRETAMENTE

### 1. Bloqueio de Links/Domínios
- **Status:** ✅ FUNCIONAL
- **Padrões detectados:**
  - `http://`, `https://`
  - `www`, `w.w.w` (variações com espaços)
  - Domínios: `.com`, `.com.br`, `.net`, `.org`, `.gov`, `.io`, `.ai`, `.xyz`, `.co`, `.co.uk`
  - **Arquivo:** `app/social/guardian.py:39-48`
  - **Testes:** `tests/test_social_guardian.py:26-51`

### 2. Bloqueio de Emails
- **Status:** ✅ FUNCIONAL
- **Padrões detectados:**
  - Padrão RFC5322 básico: `[a-z0-9._%+\-]+@[a-z0-9.\-]+\.[a-z]{2,}`
  - Provedores: `gmail`, `hotmail`, `outlook`, `yahoo`, `icloud`, `proton`
  - **Arquivo:** `app/social/guardian.py:49-52`

### 3. Bloqueio de Telefone/Contato
- **Status:** ✅ FUNCIONAL
- **Padrões detectados:**
  - DDI Brasil: `+55`
  - Formato: `(16)`, `11 99999-9999`, `16999999999`
  - Aplicativos: `WhatsApp`, `Telegram`
  - **Arquivo:** `app/social/guardian.py:53-58`

### 4. Bloqueio de Apostas (PARCIAL)
- **Status:** ⚠️ INCOMPLETO
- **Implementado:**
  - `bet`, `betting`, `casino`, `cassino`, `aposta`, `apostar`, `tigrinho`, `blaze`, `stake`, `betano`, `superbet`, `bet365`, `brazino`, `esportes da sorte`, `pixbet`
  - **Arquivo:** `app/social/guardian.py:59-81`
- **FALTANDO:** muitos nomes de casas de apostas da lista do usuário

### 5. Normalização de Texto
- **Status:** ✅ FUNCIONAL
- **Recursos:**
  - Conversão para minúsculas
  - Remoção de acentos (NFKD)
  - Remoção de espaços extras
  - **Arquivo:** `app/social/guardian.py:84-87`

### 6. Sistema de Auditoria
- **Status:** ✅ FUNCIONAL
- **Recursos:**
  - Registro de ações: `content_blocked`, `post_created`, `post_reported`, `user_reported`, `post_removed`
  - Limite de 20.000 eventos
  - **Arquivo:** `app/social/moderation.py:150-164`

### 7. Guardian Score (Confiança de Usuário)
- **Status:** ✅ FUNCIONAL
- **Recursos:**
  - Labels: Verde (≥75), Amarelo (45-74), Vermelho (<45)
  - Deltas: +2 post aprovado, +1 interação, -10 relatório, -15 post removido
  - **Arquivo:** `app/social/guardian.py:22-28, 165-172`

### 8. Integração nos Fluxos Sociais
- **Status:** ✅ FUNCIONAL
- **Pontos de entrada validados:**
  - Posts: `app/social/posts.py` → `SocialGuardian.validate_content()`
  - Comentários: `app/social/comments.py` → `can_publish()`
  - Reposts: `app/social/reposts.py` → `can_publish()`
  - Chat: `app/services/ticker_room_service.py:53` → `can_publish()`
  - Anexos: `validate_attachment_url()`

---

## ❌ CRÍTICOS - NÃO IMPLEMENTADOS

### 1. Bloqueio de Conteúdo Adulto/Ofensivo
- **Status:** ❌ NÃO IMPLEMENTADO
- **Faltando:**
  - Palavras-chave: `onlyfans`, `sexo`, `anal`, `puta`, `cu`, `cuzão`, `buceta`, `pau`, `penis`, `caralho`, `pornô`, `xxx`
  - Variações com espaços/pontos (ex: `p.o.r.n.o`, `p-o-r-n-o`)
  - URLs pornô (`.porn`, `.xxx`, `.adult`)
- **Prioridade:** ALTA (essencial para profissionalismo do site)

### 2. Bloqueio de Conteúdo Sensível (Racismo/Homofobia/Antissemitismo)
- **Status:** ❌ NÃO IMPLEMENTADO
- **Faltando:**
  - Termos racistas
  - Palavras-chave LGBTQ+ pejorativas: `viado`, `gay` (contextos pejorativos)
  - Antissemitismo: `holocausto` (negacionismo), `judeu` (em contexto ofensivo)
  - Variações codificadas
- **Prioridade:** ALTA (responsabilidade legal e de segurança)

### 3. Palavrões e Xingamentos
- **Status:** ❌ NÃO IMPLEMENTADO
- **Faltando:**
  - Lista completa de palavrões em português
  - Variações com espaços/pontos/asteriscos (ex: `c*ralho`, `c**alho`, `c-ralho`)
- **Prioridade:** MÉDIA (impacto em comunidade profissional)

### 4. Bloqueio Completo de Apostas
- **Status:** ⚠️ INCOMPLETO - faltam termos críticos
- **Faltando (conforme lista do usuário):**
  ```
  kto, 5kto, betboom, 7kbet, vbet, playuzu, br4bet, bet7k, rivalo, novibet, sportingbet, 
  betfair, betmgm, 1xbet, betnacional, estrela bet, estrelabet, hiperbet, vaidebet,
  "bet da sorte", fortune tiger, aviator, foguetinho, mines, crash, double, 
  caça-niquel, caça níquel, roleta, blackjack, bingo, jackpot, pay, slot, slots,
  "renda garantida", "lucro garantido", "ganho garantido", "dobro seu dinheiro",
  "multiplique seu dinheiro", "robô milagroso", "sinal garantido", "sem risco", 
  "100% certo", "certeza absoluta", "ganhe dinheiro fácil", jogo de azar
  ```
- **Prioridade:** CRÍTICA (problema legal e reputacional)

### 5. Bloqueio de URLs de Contato Externo (Incompleto)
- **Status:** ⚠️ PARCIAL
- **Faltando:**
  - `t.me`, `telegram.me`, `wa.me`, `whatsapp` (já tem WhatsApp, mas `wa.me` não)
  - Grupos/canais: `grupo`, `grupo vip`, `grupo pago`, `sala vip`, `sinal vip`
  - `discord`, `discord.gg`
  - `chama no privado`, `me chama`, `manda direct`, `pix no privado`
- **Arquivo:** `app/social/guardian.py:53-58` (limitado)
- **Prioridade:** MÉDIA

### 6. Variações Codificadas de Palavras Bloqueadas
- **Status:** ❌ NÃO IMPLEMENTADO
- **Faltando:**
  - `b e t`, `b.e.t`, `b-e-t`, `b_e_t`, `b3t`, `be7`
  - `c a s s i n o`, `c.a.s.s.i.n.o`
  - `a p o s t a`, `a.p.o.s.t.a`
  - `t i g r i n h o`, `t.i.g.r.i.n.h.o`
  - Variações com emojis (ex: `b🎰t`)
  - Base64 encoding: `YmV0` (bet)
- **Padrão necessário:** remover separadores antes de validar
- **Prioridade:** MÉDIA-ALTA (evasão ativa)

### 7. Impersonação (Verificação Parcial)
- **Status:** ⚠️ NECESSITA REFORÇO
- **Atual:** Apenas padrões básicos no `blocked_terms()`
- **Faltando:**
  - `stocknewsbr`, `stocknewsbr_oficial`, `oficialstocknewsbr`, etc
  - Detecção de clones com carateres Unicode similares (homografia)
  - Badges falsas de "verificado", "oficial", "admin"
- **Arquivo:** `app/social/guardian.py:186-192`
- **Prioridade:** MÉDIA

### 8. Detecção de Caracteres Ocultos
- **Status:** ❌ NÃO IMPLEMENTADO
- **Faltando:**
  - Zero-width spaces (`​`, `‌`, `‍`)
  - Right-to-left marks (`‮`)
  - Emojis invisíveis/combinadores
- **Prioridade:** BAIXA (evasão avançada)

---

## ⚠️ RECOMENDAÇÕES PRIORITÁRIAS

### **IMEDIATO (Bloqueador de Reputação)**
1. **Expandir lista de apostas** conforme fornecido pelo usuário
2. **Implementar bloqueio de conteúdo adulto** (pornô, onlyfans, etc)
3. **Adicionar termos sensíveis** (racismo, homofobia, antissemitismo)

### **PRÓXIMO SPRINT**
4. Bloqueio de variações com espaços/pontos (ex: `b.e.t`, `b e t`)
5. Palavrões e xingamentos em português
6. Detecção de impersonação reforçada

### **OPCIONAL**
7. Caracteres ocultos (zero-width, RTL marks)
8. Emojis codificados em variações

---

## 📋 CHECKLIST DE IMPLEMENTAÇÃO

```python
# Adicionar ao app/social/guardian.py

# 1. CONTEÚDO ADULTO
_ADULT_TERMS = (
    "onlyfans", "sexo", "anal", "puta", "cu", "cuzao", "buceta",
    "pau", "penis", "caralho", "pornô", "porno", "xxx", "adult"
)

# 2. CONTEÚDO SENSÍVEL
_HATE_TERMS = (
    "racismo", "racista",  # adicionar variações
    "holocausto", "negacionista",  # antissemitismo
    "viado", "gay" (contextos)  # homofobia
)

# 3. PALAVRÕES
_SWEAR_TERMS = (
    "caralho", "merda", "porra", "bosta", "desgraça", "arrombado"
    # ... mais termos
)

# 4. APOSTAS COMPLETO
_BETTING_TERMS = (
    # ... expandir lista do usuário
    "kto", "5kto", "betboom", "7kbet", "vbet", "playuzu",
    "br4bet", "bet7k", "rivalo", "novibet", "sportingbet",
    "betfair", "betmgm", "1xbet", "betnacional", "estrela bet",
    "hiperbet", "vaidebet", "fortune tiger", "aviator", "foguetinho",
    "mines", "crash", "double", "caça-niquel", "roleta", "blackjack",
    "bingo", "jackpot", "pay", "slot", "slots",
    "renda garantida", "lucro garantido", "ganho garantido",
    "dobro seu dinheiro", "multiplique seu dinheiro",
    "robô milagroso", "sinal garantido", "sem risco",
    "100% certo", "certeza absoluta", "ganhe dinheiro fácil",
    "jogo de azar"
)

# 5. CONTATOS/URLS DIRETOS
_CONTACT_SHORTCUTS = (
    "t.me", "telegram.me", "wa.me", "discord", "discord.gg",
    "grupo", "grupo vip", "grupo pago", "sala vip", "sinal vip",
    "chama no privado", "me chama", "manda direct", "pix no privado"
)
```

---

## 🧪 TESTES EXISTENTES
- ✅ `tests/test_social_guardian.py` (5 testes, todos passando)
- ✅ `tests/test_database_schema_runtime.py`
- ✅ `apps/web/scripts/mission-31a-social-guardian-audit.mjs` (Playwright)
- **Sugestão:** Adicionar testes para variações (espaços, pontos, casos mistos)

---

## 📊 IMPACTO ATUAL
- **Cobertura de riscos:** ~60% (links, emails, telefones, apostas básicas)
- **Gaps principais:** Conteúdo adulto, sensível e palavrões (0%)
- **Evasão detectada:** Baixa (não testa variações com separadores)
- **Reputação do site:** Faltando 40% para "profissional"

**Recomendação:** Implementar IMEDIATAMENTE os termos sensíveis e adultos (CRÍTICO).
