#!/usr/bin/env python
"""One-shot generator for the watchlist ticker -> local logo map.

Run from the repo root:

    python scripts/generate_ticker_logos.py            # resume: keeps existing PNGs
    python scripts/generate_ticker_logos.py --force    # re-download everything

Writes:
    apps/web/public/logos/<TICKER>.png   (<= 64x64, so the runtime never calls an external host)
    apps/web/lib/ticker-logos.ts         (generated TICKER_LOGOS map)

Resolution order per ticker:
    1. equities/BDRs: yfinance .info website -> domain -> logo host
       (logo.clearbit.com first; Clearbit shut the free API down, so the script
        probes it once and falls back to icons.duckduckgo.com / google s2 favicons)
    2. crypto: spothq/cryptocurrency-icons via jsDelivr
    3. give up -> ticker is left out of the map and the UI shows an initials circle

No API keys, no new dependencies (yfinance / requests / Pillow already ship with the backend env).
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import sys
import tempfile
import time
from pathlib import Path
from urllib.parse import urlparse

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

import requests  # noqa: E402
from PIL import Image  # noqa: E402

from app.market.universe_registry import PUBLIC_UNIVERSES  # noqa: E402

LOGO_DIR = REPO_ROOT / "apps" / "web" / "public" / "logos"
TS_OUT = REPO_ROOT / "apps" / "web" / "lib" / "ticker-logos.ts"
CACHE = Path(tempfile.gettempdir()) / "stocknewsbr_ticker_logo_domains.json"

MAX_PX = 64
DELAY = 0.4  # be polite
TIMEOUT = 20
UA = {"User-Agent": "Mozilla/5.0 (StockNewsBR logo generator)"}

CRYPTO_ICON = "https://cdn.jsdelivr.net/gh/spothq/cryptocurrency-icons@master/128/color/{base}.png"

# Tickers whose yfinance `website` is missing or points at a host no icon service indexes
# (IR sub-domains, renamed groups). Checked against the icon hosts before being added here.
DOMAIN_OVERRIDES = {
    "ABEV3": "ri.ambev.com.br",
    "BYDDY": "byd.com",
    "CCRO3": "grupoccr.com.br",
    "CSAN3": "cosan.com",
    "CSNA3": "ri.csn.com.br",
    "DXCO3": "dexco.com.br",
    "GGBR4": "ri.gerdau.com",
    "IVVB11": "ishares.com",
    "NTCO3": "natura.com.br",
    "SMTO3": "saomartinho.com",
    "UGPA3": "ri.ultra.com.br",
    "VIIA3": "grupocasasbahia.com.br",
}


def load_cache() -> dict:
    try:
        return json.loads(CACHE.read_text())
    except Exception:
        return {}


def save_cache(cache: dict) -> None:
    CACHE.write_text(json.dumps(cache, indent=0, sort_keys=True))


def fetch(url: str) -> bytes | None:
    try:
        r = requests.get(url, timeout=TIMEOUT, headers=UA)
    except requests.RequestException:
        return None
    if r.status_code != 200 or not r.content:
        return None
    if "image" not in r.headers.get("content-type", ""):
        return None
    return r.content


def domain_for(ticker: str, provider: str, cache: dict) -> str | None:
    if ticker in DOMAIN_OVERRIDES:
        return DOMAIN_OVERRIDES[ticker]
    if ticker in cache:
        return cache[ticker] or None
    website = None
    try:
        import yfinance as yf

        website = (yf.Ticker(provider).info or {}).get("website")
    except Exception:
        website = None
    host = urlparse(website).netloc if website else ""
    host = host.lower().removeprefix("www.")
    cache[ticker] = host
    time.sleep(DELAY)
    return host or None


def logo_urls(domain: str, clearbit_alive: bool) -> list[str]:
    urls = []
    if clearbit_alive:
        urls.append(f"https://logo.clearbit.com/{domain}")
    urls.append(f"https://icons.duckduckgo.com/ip3/{domain}.ico")
    urls.append(f"https://www.google.com/s2/favicons?domain={domain}&sz=128")
    return urls


def save_png(raw: bytes, dest: Path) -> int | None:
    """Normalise to a <=64x64 RGBA PNG. Returns bytes written, None if undecodable."""
    try:
        im = Image.open(io.BytesIO(raw))
        im.load()
    except Exception:
        return None
    if min(im.size) < 16:
        return None
    im = im.convert("RGBA")
    im.thumbnail((MAX_PX, MAX_PX), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, "PNG", optimize=True)
    dest.write_bytes(buf.getvalue())
    return len(buf.getvalue())


def probe_clearbit() -> bool:
    return fetch("https://logo.clearbit.com/apple.com") is not None


def google_placeholder_hash() -> str | None:
    """google s2 answers 200 with a generic globe for unknown domains - fingerprint it."""
    raw = fetch("https://www.google.com/s2/favicons?domain=nonexistent-xyz-abc-123.invalid&sz=128")
    return hashlib.sha1(raw).hexdigest() if raw else None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="re-download logos that already exist")
    args = ap.parse_args()

    LOGO_DIR.mkdir(parents=True, exist_ok=True)
    cache = load_cache()
    clearbit_alive = probe_clearbit()
    globe = google_placeholder_hash()
    print(f"clearbit reachable: {clearbit_alive} | google globe fingerprint: {globe}")

    from app.services.symbol_registry import provider_symbol

    found: dict[str, str] = {}
    missing: list[str] = []

    for category, symbols in PUBLIC_UNIVERSES.items():
        for ticker in symbols:
            dest = LOGO_DIR / f"{ticker}.png"
            if dest.exists() and not args.force:
                found[ticker] = f"/logos/{ticker}.png"
                print(f"  skip  {ticker} (exists)")
                continue

            if category == "Crypto":
                base = ticker.removesuffix("USDT").removesuffix("USD").lower()
                candidates = [CRYPTO_ICON.format(base=base)]
            else:
                domain = domain_for(ticker, provider_symbol(ticker), cache)
                candidates = logo_urls(domain, clearbit_alive) if domain else []

            written = None
            for url in candidates:
                raw = fetch(url)
                time.sleep(DELAY)
                if not raw:
                    continue
                if globe and hashlib.sha1(raw).hexdigest() == globe:
                    continue  # generic globe, not a real logo
                written = save_png(raw, dest)
                if written:
                    print(f"  ok    {ticker:8s} {written:6d}B  {url}")
                    break

            if written:
                found[ticker] = f"/logos/{ticker}.png"
            else:
                missing.append(ticker)
                print(f"  MISS  {ticker}")

    save_cache(cache)

    entries = "\n".join(f'  "{t}": "{p}",' for t, p in sorted(found.items()))
    TS_OUT.write_text(
        "// GENERATED FILE - do not edit by hand.\n"
        "// Generated by scripts/generate_ticker_logos.py\n"
        "// Re-run: python scripts/generate_ticker_logos.py  (--force to re-download)\n"
        "// Images live in apps/web/public/logos/ so the runtime never hits an external host.\n"
        "// A ticker absent from this map has no logo: the UI falls back to an initials circle.\n"
        "\n"
        "export const TICKER_LOGOS: Record<string, string> = {\n"
        f"{entries}\n"
        "};\n",
        encoding="utf-8",
    )

    total = sum(f.stat().st_size for f in LOGO_DIR.glob("*.png"))
    universe = sum(len(s) for s in PUBLIC_UNIVERSES.values())
    print(f"\n{len(found)}/{universe} logos | {total} bytes on disk | {TS_OUT}")
    if missing:
        print(f"no logo ({len(missing)}): {', '.join(missing)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
