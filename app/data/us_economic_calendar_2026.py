"""Versioned US economic calendar for 2026.

Major US macro releases used by the weekly poll policy. Dates are ISO
(YYYY-MM-DD, US release date). Keep the list ordered by date; same-date
order expresses importance (first wins ties).
"""

from datetime import UTC, datetime, timedelta
from typing import Any, Dict, List

CALENDAR_VERSION = "2026.1"

US_ECONOMIC_EVENTS_2026: List[Dict[str, str]] = [
    {"name": "Sentimento do Consumidor UMich (prévia)", "date": "2026-07-17", "note": "leitura preliminar de julho"},
    {"name": "Housing Starts + Building Permits", "date": "2026-07-17", "note": "atividade imobiliária nos EUA"},
    {"name": "New Home Sales", "date": "2026-07-24", "note": "vendas de casas novas"},
    {"name": "Durable Goods", "date": "2026-07-27", "note": "encomendas de bens duráveis"},
    {"name": "Consumer Confidence", "date": "2026-07-28", "note": "Conference Board"},
    {"name": "Decisão do FOMC", "date": "2026-07-29", "note": "reunião 28-29/07"},
    {"name": "PCE + Core PCE", "date": "2026-07-30", "note": "inflação preferida do Fed"},
    {"name": "GDP Advance Q2", "date": "2026-07-30", "note": "primeira estimativa do PIB do 2º trimestre"},
    {"name": "Sentimento do Consumidor UMich (final)", "date": "2026-07-31", "note": "leitura final de julho"},
    {"name": "ISM Manufacturing", "date": "2026-08-03", "note": "PMI industrial"},
    {"name": "JOLTS", "date": "2026-08-04", "note": "vagas de emprego em aberto"},
    {"name": "ISM Services", "date": "2026-08-05", "note": "PMI de serviços"},
    {"name": "ADP", "date": "2026-08-05", "note": "emprego privado"},
    {"name": "Payroll (NFP)", "date": "2026-08-07", "note": "relatório oficial de emprego"},
    {"name": "CPI", "date": "2026-08-12", "note": "inflação ao consumidor"},
    {"name": "PPI", "date": "2026-08-13", "note": "inflação ao produtor"},
    {"name": "Retail Sales", "date": "2026-08-14", "note": "vendas no varejo"},
]

JOBLESS_CLAIMS_NAME = "Initial Jobless Claims"
# Weekly release, every Thursday; anchor = next release known at authoring time.
JOBLESS_CLAIMS_ANCHOR = datetime(2026, 7, 23, tzinfo=UTC)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def events_in_window(start: datetime, end: datetime) -> List[Dict[str, Any]]:
    """Events whose release date falls in [start, end), sorted by date.

    Same-date events keep list order (importance). Initial Jobless Claims is
    generated weekly (every Thursday from the anchor onward).
    """
    start = _as_utc(start)
    end = _as_utc(end)

    found: List[Dict[str, Any]] = []
    for event in US_ECONOMIC_EVENTS_2026:
        event_dt = datetime.fromisoformat(event["date"]).replace(tzinfo=UTC)
        if start <= event_dt < end:
            found.append(dict(event))

    cursor = JOBLESS_CLAIMS_ANCHOR
    while cursor < end:
        if cursor >= start:
            found.append(
                {
                    "name": JOBLESS_CLAIMS_NAME,
                    "date": cursor.date().isoformat(),
                    "note": "semanal, toda quinta-feira",
                }
            )
        cursor += timedelta(days=7)

    found.sort(key=lambda item: str(item["date"]))
    return found
