"""
Verzija C: simboli dostupnih valuta i trenutna cijena u USD (preko USDT/USDC/…).

Valute se izvode iz aktivnih spot tržišta (kao ccxt_valute_graph.py).
Cijena = zadnja cijena na paru protiv dolarskog ekvivalenta (npr. BTC/USDT).
"""

import sys

import ccxt

ID_BURZE = "binance"
DOLARSKI_KVOTE = ("USDT", "USDC", "USD", "BUSD", "FDUSD")


def ucitaj_burzu(id_burze: str = ID_BURZE) -> ccxt.Exchange:
    klasa_burze = getattr(ccxt, id_burze)
    burza = klasa_burze({"enableRateLimit": True})
    burza.load_markets()
    return burza


def simboli_s_aktivnih_spot_trzista(burza: ccxt.Exchange) -> set[str]:
    """Jedinstveni base/quote simboli s aktivnih spot parova."""
    simboli: set[str] = set()
    for trziste in burza.markets.values():
        if not trziste.get("active") or not trziste.get("spot"):
            continue
        baza = trziste.get("base")
        kvota = trziste.get("quote")
        if baza:
            simboli.add(baza)
        if kvota:
            simboli.add(kvota)
    return simboli


def cijena_u_dolarima(
    burza: ccxt.Exchange,
    simbol: str,
    tickeri: dict,
) -> float | None:
    """Trenutna vrijednost 1 jedinice valute u USD (USDT ≈ 1 USD)."""
    if simbol in DOLARSKI_KVOTE:
        return 1.0

    for kvota in DOLARSKI_KVOTE:
        par = f"{simbol}/{kvota}"
        trziste = burza.markets.get(par)
        if not trziste or not trziste.get("active") or not trziste.get("spot"):
            continue
        ticker = tickeri.get(par)
        if not ticker:
            continue
        zadnja = ticker.get("last")
        if zadnja is not None:
            return float(zadnja)

    return None


def formatiraj_usd(iznos: float) -> str:
    if iznos >= 1:
        return f"{iznos:,.2f}"
    if iznos >= 0.0001:
        return f"{iznos:.6f}".rstrip("0").rstrip(".")
    return f"{iznos:.8g}"


def popis_simbola_i_cijena(id_burze: str = ID_BURZE) -> list[tuple[str, float | None]]:
    burza = ucitaj_burzu(id_burze)
    tickeri = burza.fetch_tickers()
    simboli = simboli_s_aktivnih_spot_trzista(burza)

    stavke: list[tuple[str, float | None]] = []
    for simbol in sorted(simboli, key=str.casefold):
        stavke.append((simbol, cijena_u_dolarima(burza, simbol, tickeri)))
    return stavke


def glavno() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    stavke = popis_simbola_i_cijena(ID_BURZE)

    print(f"Burza: {ID_BURZE}")
    print("Cijena u USD: zadnja spot cijena na paru */USDT (ili USDC/USD/BUSD/FDUSD).")
    print(f"Valuta: {len(stavke)}\n")
    print(f"{'Simbol':<12} {'USD':>16}")
    print("-" * 30)

    for simbol, cijena in stavke:
        if cijena is None:
            tekst_cijene = "n/d"
        else:
            tekst_cijene = formatiraj_usd(cijena)
        print(f"{simbol:<12} {tekst_cijene:>16}")


if __name__ == "__main__":
    glavno()
