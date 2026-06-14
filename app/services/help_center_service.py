from copy import deepcopy

from app.services.legal_service import AI_MODULES, HELP_CENTER_MODULES
from app.services.video_library_service import get_help_video_entry, get_help_video_library


HELP_GUIDES = {
    "flow": {
        "slug": "flow",
        "title": "Fluxo IA",
        "tagline": "Entenda a direcao do fluxo institucional sem duplicar leitura.",
        "what_it_does": [
            "Mostra pressao institucional compradora ou vendedora.",
            "Separa fluxo real de ruido visual.",
            "Ajuda a responder se o mercado esta favorecendo um lado.",
        ],
        "how_to_use": [
            "Use como contexto de fluxo, nao como ordem isolada.",
            "Cruze com Risco IA antes de agir.",
            "Evite tratar interesse institucional como trade pronto.",
        ],
        "example": "PETR4 com Fluxo IA forte vira candidato, mas so opera se Risco IA liberar.",
    },
    "liquidity": {
        "slug": "liquidity",
        "title": "Liquidez IA",
        "tagline": "Zonas, sweeps e traps em uma leitura unica.",
        "what_it_does": [
            "Consolida mapa e sweep de liquidez.",
            "Mostra armadilhas e invalidacao.",
            "Evita ver liquidez como tres confirmacoes diferentes.",
        ],
        "how_to_use": [
            "Use zonas como referencia, nao como entrada automatica.",
            "Aguarde reacao e volume.",
            "Se a liquidez for fina, deixe Risco IA bloquear.",
        ],
        "example": "VALE3 varre liquidez e rejeita a zona; Liquidez IA mostra trap, Risco IA decide se vale operar.",
    },
    "grafico": {
        "slug": "grafico",
        "title": "IA Grafico",
        "tagline": "Grafico com contexto, overlays e marcacoes operacionais.",
        "what_it_does": [
            "Entrega OHLC, medias, zonas e marcacoes de eventos.",
            "Resume score, tendencia, risco e leitura do ativo.",
            "Ajuda a visualizar compra, venda, continuidade e reversao.",
        ],
        "how_to_use": [
            "Observe as medias e as zonas antes de agir.",
            "Use as marcacoes de evento para entender aceleracao ou exaustao.",
            "Cruze o grafico com poll, feed e ranking para ter mais conviccao.",
        ],
        "example": "Um marcador de BUY proximo da media curta com score crescente ajuda a enxergar continuidade de alta.",
    },
}


def _demo_url(slug: str) -> str:
    return f"/web/help-center/demo/{slug}"


def get_help_guides():
    guides = []

    for item in HELP_CENTER_MODULES:
        slug = item["slug"]
        guide = deepcopy(HELP_GUIDES.get(slug, {}))
        video_entry = get_help_video_entry(slug)
        merged = {
            **item,
            **guide,
            "demo_video_url": video_entry.get("public_url") or _demo_url(slug),
            "demo_mode": "mp4" if video_entry.get("video_ready") else "interactive_preview",
            "video_status": video_entry.get("status"),
            "mp4_url": video_entry.get("public_url"),
        }
        guides.append(merged)

    return guides


def get_help_guide(slug: str):
    slug = (slug or "").strip().lower()

    for guide in get_help_guides():
        if guide.get("slug") == slug:
            return guide

    return None


def get_help_center_blueprint():
    guides = get_help_guides()
    video_library = get_help_video_library()

    return {
        "guides": guides,
        "ai_modules": list(AI_MODULES),
        "video_status": video_library["status"],
        "video_library": video_library["items"],
    }
