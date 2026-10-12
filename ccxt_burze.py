"""
Primjer: burze podržane u CCXT — broj i detaljni popis imena.

Mrežni poziv nije potreban; koristi se lokalni popis iz biblioteke.
"""

import sys

import ccxt


def popis_imena_burza() -> list[tuple[str, str]]:
    """Za svaku burzu vraća (id, prikazno ime), sortirano po imenu."""
    stavke: list[tuple[str, str]] = []
    for id_burze in ccxt.exchanges:
        klasa_burze = getattr(ccxt, id_burze)
        burza = klasa_burze()
        ime = burza.name or id_burze
        stavke.append((id_burze, ime))
    stavke.sort(key=lambda par: par[1].casefold())
    return stavke


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    burze = popis_imena_burza()
    broj = len(burze)

    print(f"Broj burza u CCXT: {broj}\n")
    print("Detaljni popis imena burza:")
    for redni_broj, (_, ime) in enumerate(burze, start=1):
        print(f"  {redni_broj:3}. {ime}")


if __name__ == "__main__":
    main()
