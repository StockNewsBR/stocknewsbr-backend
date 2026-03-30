from copy import deepcopy

from app.services.legal_service import AI_MODULES, HELP_CENTER_MODULES
from app.services.video_library_service import get_help_video_entry, get_help_video_library


HELP_GUIDES = {
    "heat-map": {
        "slug": "heat-map",
        "title": "IA Heat Map",
        "tagline": "Descubra onde esta a forca do mercado em segundos.",
        "what_it_does": [
            "Mostra quais ativos e setores estao puxando o mercado.",
            "Ajuda a identificar dominancia compradora ou vendedora.",
            "Destaca concentracao de fluxo e momentum do dia.",
        ],
        "how_to_use": [
            "Veja onde a intensidade esta crescendo antes de abrir uma posicao.",
            "Cruze o mapa com o radar e com o grafico para confirmar contexto.",
            "Evite operar ativos sem suporte de fluxo quando o mapa estiver fraco.",
        ],
        "example": "PETR4 e VALE3 em destaque no mapa junto com score forte reforcam uma leitura de lideranca do indice.",
    },
    "radar": {
        "slug": "radar",
        "title": "IA Radar",
        "tagline": "Scanner de aceleracao e oportunidade em tempo real.",
        "what_it_does": [
            "Rankeia ativos com aumento de score e momentum.",
            "Combina sinais, fluxo e eventos para destacar oportunidades.",
            "Serve como porta de entrada para o trader decidir o que estudar primeiro.",
        ],
        "how_to_use": [
            "Olhe os primeiros nomes do radar logo no pre-mercado.",
            "Abra o grafico e a sala do ticker para validar contexto.",
            "Use o score junto com breakout e smart money para filtrar entrada.",
        ],
        "example": "Quando VALE3 sobe no radar com breakout e score acima de 80, o ativo vira candidato prioritario da mesa.",
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
