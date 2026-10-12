"""
Primjer: trenutno stanje tri najpopularnije valute (CCXT) — prikaz i spremanje u log.

Popularnost = najveći 24h volumen na spot parovima protiv USDT na odabranoj burzi.
Podaci se spremaju u JSON (zadnji snapshot) i JSONL (povijest pokretanja).
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import ccxt

BROJ_VALUTA = 3
ID_BURZE = "binance"
VALUTA_CIJENE = "USDT"
STABILNE_VALUTE = frozenset(
    {"USDT", "USDC", "BUSD", "FDUSD", "DAI", "TUSD", "USDP", "USDD", "EUR", "USD"}
)

MAPA_LOGOVA = Path(__file__).resolve().parent / "logs"
DATOTEKA_ZADNJI_JSON = MAPA_LOGOVA / "valute_zadnji.json"
DATOTEKA_POVIJEST_JSONL = MAPA_LOGOVA / "valute_povijest.jsonl"


def ucitaj_burzu(id_burze: str = ID_BURZE) -> ccxt.Exchange:
    klasa_burze = getattr(ccxt, id_burze)
    burza = klasa_burze({"enableRateLimit": True})
    burza.load_markets()
    return burza


def volumen_quote_24h(ticker: dict[str, Any]) -> float:
    volumen = ticker.get("quoteVolume")
    if volumen is None:
        volumen = ticker.get("baseVolume")
    if volumen is None:
        return 0.0
    return float(volumen)


def najpopularnije_valute(
    burza: ccxt.Exchange,
    tickeri: dict[str, Any],
    broj: int = BROJ_VALUTA,
    valuta_cijene: str = VALUTA_CIJENE,
) -> list[str]:
    """Simboli base valuta s najvećim 24h volumenom (spot, par */USDT)."""
    rang: list[tuple[str, float]] = []

    for simbol_para, ticker in tickeri.items():
        trziste = burza.markets.get(simbol_para)
        if not trziste or not trziste.get("active") or not trziste.get("spot"):
            continue
        if trziste.get("quote") != valuta_cijene:
            continue

        simbol_baze = trziste["base"]
        if simbol_baze in STABILNE_VALUTE:
            continue

        rang.append((simbol_baze, volumen_quote_24h(ticker)))

    rang.sort(key=lambda stavka: stavka[1], reverse=True)
    odabrano: list[str] = []
    for simbol_baze, _ in rang:
        if simbol_baze in odabrano:
            continue
        odabrano.append(simbol_baze)
        if len(odabrano) >= broj:
            break
    return odabrano


def trenutno_stanje_valute(
    burza: ccxt.Exchange,
    simbol: str,
    tickeri: dict[str, Any],
    valuta_cijene: str = VALUTA_CIJENE,
) -> dict[str, Any]:
    par = f"{simbol}/{valuta_cijene}"
    ticker = tickeri.get(par)
    podaci_valute = burza.currencies.get(simbol) or {}

    if not ticker:
        return {
            "simbol": simbol,
            "par": par,
            "greska": "Ticker za par nije dostupan.",
        }

    vrijeme_ms = ticker.get("timestamp")
    vrijeme_iso = None
    if vrijeme_ms:
        vrijeme_iso = datetime.fromtimestamp(vrijeme_ms / 1000, tz=timezone.utc).isoformat()

    return {
        "simbol": simbol,
        "ime": podaci_valute.get("name") or simbol,
        "par": par,
        "cijena_zadnja": ticker.get("last"),
        "najbolja_kupnja_bid": ticker.get("bid"),
        "najbolja_prodaja_ask": ticker.get("ask"),
        "promjena_postotak_24h": ticker.get("percentage"),
        "promjena_apsolutna_24h": ticker.get("change"),
        "najvisa_cijena_24h": ticker.get("high"),
        "najniza_cijena_24h": ticker.get("low"),
        "volumen_baza_24h": ticker.get("baseVolume"),
        "volumen_quote_24h": ticker.get("quoteVolume"),
        "vrijeme_podataka_utc": vrijeme_iso,
    }


def sastavi_izvjestaj(
    burza: ccxt.Exchange,
    tickeri: dict[str, Any],
    popularne: list[str],
    vrijeme_generiranja_utc: str,
) -> dict[str, Any]:
    return {
        "vrijeme_generiranja_utc": vrijeme_generiranja_utc,
        "burza": burza.id,
        "kriterij_popularnosti": (
            f"24h volumen na spot parovima */{VALUTA_CIJENE}"
        ),
        "broj_valuta": len(popularne),
        "simboli_po_redoslijedu": popularne,
        "valute": [
            trenutno_stanje_valute(burza, simbol, tickeri) for simbol in popularne
        ],
    }


def spremi_json(putanja: Path, podaci: dict[str, Any]) -> None:
    putanja.parent.mkdir(parents=True, exist_ok=True)
    with putanja.open("w", encoding="utf-8") as datoteka:
        json.dump(podaci, datoteka, indent=2, ensure_ascii=False, default=str)
        datoteka.write("\n")


def dodaj_u_jsonl(putanja: Path, podaci: dict[str, Any]) -> None:
    putanja.parent.mkdir(parents=True, exist_ok=True)
    redak = json.dumps(podaci, ensure_ascii=False, default=str)
    with putanja.open("a", encoding="utf-8") as datoteka:
        datoteka.write(redak + "\n")


def formatiraj_podatke(podaci: Any) -> str:
    return json.dumps(podaci, indent=2, ensure_ascii=False, default=str)


def glavno() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    burza = ucitaj_burzu(ID_BURZE)
    tickeri = burza.fetch_tickers()

    popularne = najpopularnije_valute(burza, tickeri)
    sada_utc = datetime.now(timezone.utc).isoformat()
    izvjestaj = sastavi_izvjestaj(burza, tickeri, popularne, sada_utc)

    spremi_json(DATOTEKA_ZADNJI_JSON, izvjestaj)
    dodaj_u_jsonl(DATOTEKA_POVIJEST_JSONL, izvjestaj)

    print(f"Burza: {ID_BURZE}")
    print(f"Kriterij popularnosti: 24h volumen na spot parovima */{VALUTA_CIJENE}")
    print(f"Snapshot generiran (UTC): {sada_utc}")
    print(f"\nTri najpopularnije valute (po volumenu): {', '.join(popularne)}\n")

    for redni_broj, stanje in enumerate(izvjestaj["valute"], start=1):
        print("=" * 60)
        print(f"{redni_broj}. {stanje.get('simbol', '?')}")
        print(formatiraj_podatke(stanje))

    print("\nPodaci spremljeni:")
    print(f"  Zadnji snapshot (JSON):  {DATOTEKA_ZADNJI_JSON}")
    print(f"  Povijest (JSON Lines):   {DATOTEKA_POVIJEST_JSONL}")


if __name__ == "__main__":
    glavno()
