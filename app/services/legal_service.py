from app.services.access_service import pricing_catalog


LEGAL_NOTICE_TEXT = (
    "O StockNewsBR e uma plataforma de inteligencia de mercado com IA, analise "
    "quantitativa e comunidade financeira. Todo o conteudo possui carater "
    "exclusivamente educacional e informativo. O StockNewsBR nao realiza "
    "recomendacao personalizada de investimentos, nao atua como consultoria "
    "financeira e nao substitui a analise independente do usuario. Investimentos "
    "envolvem riscos e podem resultar em perdas financeiras."
)

DISCLOSURE_TEXT = (
    "As informacoes, sinais, rankings, enquetes, graficos, comentarios e alertas "
    "disponibilizados pelo StockNewsBR sao fornecidos para fins educacionais e "
    "informativos. Nenhum conteudo da plataforma deve ser interpretado como oferta, "
    "solicitacao, promessa de rentabilidade ou recomendacao de compra ou venda de "
    "ativos. Conteudos publicados por usuarios, parceiros e anunciantes representam "
    "apenas a opiniao de seus autores. O uso da plataforma implica ciencia de que "
    "o usuario e o unico responsavel por suas decisoes de investimento."
)

SUBSCRIPTION_TERMS_TEXT = (
    "O acesso a plataforma e pessoal, individual e intransferivel. O lancamento "
    "principal acontece no app Google Play. Preco, pagamentos, mudanca de planos, "
    "cancelamentos e reembolsos ficam no Google Play. A assinatura Trial ou Premium "
    "libera o ecossistema da marca, incluindo app Android, website profissional com "
    "login e senha e canal oficial do Telegram. A versao Apple ficara preparada para "
    "a proxima etapa de lancamento."
)

GOOGLE_PLAY_DESCRIPTION = (
    "StockNewsBR e uma plataforma brasileira de inteligencia de mercado para traders, "
    "com IA, engine quantitativa, grafico com alertas, comunidade por ticker e "
    "ferramentas inspiradas em desks institucionais."
)

EDUCATION_DESCRIPTION = (
    "O StockNewsBR tambem oferece uma central de ajuda educacional em portugues, "
    "com explicacoes simples, exemplos praticos e visao amigavel das ferramentas "
    "da plataforma."
)

PRICING = {
    "trial_days": 90,
    "trial_policy": "Trial inicial de 90 dias. Ao vencer, a conta migra automaticamente para Basico se nao houver Premium ativo.",
    "refund_window_days": 7,
    "refund_policy": "Cancelamento com reembolso em ate 7 dias para contas Brasil e internacionais. Apos 7 dias nao ha reembolso.",
    "free_plan": {
        "name": "Basico",
        "price_brl_monthly": 0,
        "includes": ["app", "feed social", "perfil", "enquetes", "conteudo educacional"],
    },
    "premium_monthly": {
        "name": "Premium Mensal",
        "price_brl": 49,
        "billing_cycle": "mensal",
        "includes": ["app", "website", "telegram", "ferramentas de IA", "ranking", "alertas"],
    },
    "premium_annual": {
        "name": "Premium Anual",
        "price_brl": 500,
        "billing_cycle": "anual",
        "includes": ["app", "website", "telegram", "ferramentas de IA", "ranking", "alertas"],
    },
    "international_monthly": {
        "name": "USA Premium Monthly",
        "price_usd": 49,
        "billing_cycle": "monthly",
        "includes": ["app", "website", "telegram", "AI tools", "rankings", "alerts"],
    },
    "international_annual": {
        "name": "USA Premium Annual",
        "price_usd": 500,
        "billing_cycle": "annual",
        "includes": ["app", "website", "telegram", "AI tools", "rankings", "alerts"],
    },
}

LAUNCH_ROADMAP = {
    "current": "google_app",
    "next": "apple_app",
    "domain": "https://www.stocknewsbr.com",
}

AI_MODULES = [
    "Fluxo IA",
    "Liquidez IA",
    "Tendência IA",
    "Momento IA",
    "Smart Money IA",
    "Risco IA",
    "Notícias IA",
    "Macro IA",
    "Regime IA",
    "IA Grafico",
]

HELP_CENTER_MODULES = [
    {
        "slug": "flow",
        "title": "Fluxo IA",
        "description": "Le fluxo institucional, agressao e pressao compradora ou vendedora.",
        "example": "Fluxo forte em PETR4 reforca interesse institucional, mas nao libera trade sozinho.",
        "demo_video_url": None,
    },
    {
        "slug": "liquidity",
        "title": "Liquidez IA",
        "description": "Consolida zonas de liquidez, sweeps, traps e invalidacao.",
        "example": "Uma varredura de stops em VALE3 vira apenas contexto ate haver confirmacao.",
        "demo_video_url": None,
    },
    {
        "slug": "trend",
        "title": "Tendência IA",
        "description": "Avalia direcao predominante e estrutura de tendencia.",
        "example": "Tendencia de alta sem volume suficiente continua como watchlist.",
        "demo_video_url": None,
    },
    {
        "slug": "momentum",
        "title": "Momento IA",
        "description": "Consolida radar, breakout e heat map em uma leitura de aceleracao.",
        "example": "Momentum em expansao indica que o ativo entrou no radar, nao que a entrada esta liberada.",
        "demo_video_url": None,
    },
    {
        "slug": "smart-money",
        "title": "Smart Money IA",
        "description": "Le atuacao institucional combinando flow, acumulacao e absorcao.",
        "example": "Defesa institucional em suporte pode indicar acumulacao ou absorcao.",
        "demo_video_url": None,
    },
    {
        "slug": "risk",
        "title": "Risco IA",
        "description": "Mostra risco operacional, bloqueios, can trade e motivo de nao operar.",
        "example": "Score alto com baixa liquidez vira NAO OPERAR AGORA.",
        "demo_video_url": None,
    },
    {
        "slug": "news-ia",
        "title": "Notícias IA",
        "description": "Mostra estado da noticia, relevancia, confianca, impacto e provider status.",
        "example": "Noticia relevante vira contexto, nao gatilho isolado de compra.",
        "demo_video_url": None,
    },
    {
        "slug": "macro",
        "title": "Macro IA",
        "description": "Separa macro real de macro derivado apenas de noticias.",
        "example": "Macro-news nao e apresentado como macro quantitativo.",
        "demo_video_url": None,
    },
    {
        "slug": "regime",
        "title": "Regime IA",
        "description": "Classifica contexto de mercado: tendencia, lateralidade e volatilidade.",
        "example": "Regime favoravel ajuda o contexto, mas nao substitui decisao operacional.",
        "demo_video_url": None,
    },
    {
        "slug": "grafico",
        "title": "IA Grafico",
        "description": "Entrega o grafico com alertas de compra, venda e regioes de decisao.",
        "example": "O trader ve no grafico as regioes de compra, venda e mudanca de fluxo.",
        "demo_video_url": None,
    },
]

SOCIAL_FEATURES = {
    "ticker_rooms": True,
    "post_images": True,
    "likes": True,
    "user_block": True,
    "weekly_ai_polls": True,
    "telegram_alerts": True,
    "multi_monitor_web": True,
}

WEEKLY_AI_POLLS = {
    "stocks": {
        "earnings_week": [
            "A empresa vai bater o trimestre e o ativo tende a subir?",
            "A empresa nao vai bater o trimestre e o ativo tende a decepcionar?",
        ],
        "regular_week": [
            "Semana com tendencia de alta para este ativo?",
            "Semana sem tendencia aparente para este ativo?",
        ],
    },
    "crypto": [
        "Semana com tendencia de alta baseada no fluxo e no mercado?",
        "Semana com tendencia de baixa ou indecisao baseada no fluxo e no mercado?",
    ],
}

OFFICIAL_CHANNELS = {
    "telegram": {
        "role": "alertas",
        "description": "Canal principal de alertas, ranking diario e market pulse.",
    },
    "website": {
        "role": "terminal",
        "description": "Versao profissional com scanner, graficos, abas soltas e modulos de IA.",
    },
    "google_app": {
        "role": "primary",
        "description": "Aplicativo principal do lancamento com assinatura central da plataforma.",
    },
    "apple_app": {
        "role": "planned",
        "description": "Expansao planejada para a Apple Store em fase posterior ao lancamento Android.",
    },
}


def get_public_pricing():
    catalog = pricing_catalog()
    selected = catalog["selected"]
    return {
        **PRICING,
        "trial_days": selected["trial_days"],
        "trial_shortens_after_days": catalog["trial_shortens_after_days"],
        "post_launch_trial_days": catalog["post_launch_trial_days"],
        "markets": catalog["plans"],
        "selected_market": catalog["market"],
    }


def get_public_bootstrap():
    return {
        "brand": "StockNewsBR",
        "primary_launch_platform": "google_app",
        "subscription_unlocks": ["google_app", "website", "telegram"],
        "launch_roadmap": LAUNCH_ROADMAP,
        "pricing": get_public_pricing(),
        "google_play_description": GOOGLE_PLAY_DESCRIPTION,
        "education_description": EDUCATION_DESCRIPTION,
        "subscription_terms": SUBSCRIPTION_TERMS_TEXT,
        "legal_notice": LEGAL_NOTICE_TEXT,
        "disclosure": DISCLOSURE_TEXT,
        "ai_modules": AI_MODULES,
        "help_center_modules": HELP_CENTER_MODULES,
        "social_features": SOCIAL_FEATURES,
        "weekly_ai_polls": WEEKLY_AI_POLLS,
        "official_channels": OFFICIAL_CHANNELS,
    }
