"""
Praćenje tri najpopularnije valute (CCXT): kao ccxt_valute_change + graf promjena u %.

Promjena = razlika zadnje cijene u odnosu na prethodno očitanje u petlji.
"""

import json
import math
import sys
import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from queue import Empty, Queue
from typing import Any

import ccxt
import matplotlib.dates as mdates
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
import tkinter as tk

BROJ_VALUTA = 3
ID_BURZE = "binance"
VALUTA_CIJENE = "USDT"
INTERVAL_SEKUNDI = 10  # privremeno za testiranje (inace 60)
STABILNE_VALUTE = frozenset(
    {"USDT", "USDC", "BUSD", "FDUSD", "DAI", "TUSD", "USDP", "USDD", "EUR", "USD"}
)

MAPA_LOGOVA = Path(__file__).resolve().parent / "logs"
DATOTEKA_ZADNJI_JSON = MAPA_LOGOVA / "valute_zadnji.json"
DATOTEKA_POVIJEST_JSONL = MAPA_LOGOVA / "valute_povijest.jsonl"

BOJE_VALUTA = ("#f7931a", "#627eea", "#14f195", "#9945ff", "#23292f")


def ispisi_upute_za_prekid() -> None:
    print(
        f"Program u petlji čita podatke svakih {INTERVAL_SEKUNDI} s i sprema ih u log."
    )
    print("Za prekid: Ctrl+C u terminalu ili zatvorite prozor grafa.")
    print(f"Log datoteke: {DATOTEKA_ZADNJI_JSON}")
    print(f"              {DATOTEKA_POVIJEST_JSONL}\n")


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


def promjena_cijene(
    cijena_prethodna: float | None,
    cijena_nova: float | None,
) -> dict[str, Any]:
    if cijena_nova is None:
        return {
            "cijena_zadnja": None,
            "cijena_prethodna": cijena_prethodna,
            "promjena_apsolutna": None,
            "promjena_postotak": None,
        }

    if cijena_prethodna is None:
        return {
            "cijena_zadnja": cijena_nova,
            "cijena_prethodna": None,
            "promjena_apsolutna": None,
            "promjena_postotak": None,
            "prvo_ocitanje": True,
        }

    apsolutna = cijena_nova - cijena_prethodna
    postotak = (apsolutna / cijena_prethodna) * 100 if cijena_prethodna else None
    return {
        "cijena_zadnja": cijena_nova,
        "cijena_prethodna": cijena_prethodna,
        "promjena_apsolutna": apsolutna,
        "promjena_postotak": postotak,
        "prvo_ocitanje": False,
    }


def formatiraj_promjenu_za_ispis(
    simbol: str,
    promjena: dict[str, Any],
    valuta_cijene: str = VALUTA_CIJENE,
) -> str:
    if promjena.get("prvo_ocitanje"):
        cijena = promjena.get("cijena_zadnja")
        return f"  {simbol}: prvo očitanje, cijena {cijena} {valuta_cijene}"

    apsolutna = promjena.get("promjena_apsolutna")
    postotak = promjena.get("promjena_postotak")
    if apsolutna is None or postotak is None:
        return f"  {simbol}: promjena nije dostupna"

    predznak_iznos = "+" if apsolutna >= 0 else ""
    predznak_postotak = "+" if postotak >= 0 else ""
    return (
        f"  {simbol}: promjena {predznak_iznos}{apsolutna:.8g} {valuta_cijene} "
        f"({predznak_postotak}{postotak:.4f} %)"
    )


def sastavi_izvjestaj(
    burza: ccxt.Exchange,
    tickeri: dict[str, Any],
    pracene_valute: list[str],
    vrijeme_citanja_utc: str,
    vrijeme_citanja_lokalno: str,
    promjene: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    stanja = [
        trenutno_stanje_valute(burza, simbol, tickeri) for simbol in pracene_valute
    ]
    return {
        "vrijeme_citanja_utc": vrijeme_citanja_utc,
        "vrijeme_citanja_lokalno": vrijeme_citanja_lokalno,
        "burza": burza.id,
        "pracene_valute": pracene_valute,
        "promjene_od_proslog_ocitanja": promjene,
        "valute": stanja,
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


def spavaj_s_prekidom(zaustavi: threading.Event, sekundi: int) -> None:
    for _ in range(sekundi):
        if zaustavi.is_set():
            return
        time.sleep(1)


@dataclass
class PovijestGrafa:
    pracene_valute: list[str] = field(default_factory=list)
    vremena: list[datetime] = field(default_factory=list)
    postotci: dict[str, list[float]] = field(default_factory=dict)
    prethodne_cijene: dict[str, float | None] = field(default_factory=dict)


def parsiraj_vrijeme_zapisa(zapis: dict[str, Any]) -> datetime | None:
    lokalno = zapis.get("vrijeme_citanja_lokalno")
    if isinstance(lokalno, str):
        try:
            return datetime.strptime(lokalno, "%Y-%m-%d %H:%M:%S %z")
        except ValueError:
            pass

    for kljuc in ("vrijeme_citanja_utc", "vrijeme_generiranja_utc"):
        vrijednost = zapis.get(kljuc)
        if isinstance(vrijednost, str):
            try:
                return datetime.fromisoformat(vrijednost)
            except ValueError:
                continue
    return None


def parsiraj_vrijeme_teksta(tekst: str) -> datetime:
    try:
        return datetime.strptime(tekst, "%Y-%m-%d %H:%M:%S %z")
    except ValueError:
        return datetime.fromisoformat(tekst)


def simboli_iz_zapisa(zapis: dict[str, Any]) -> list[str]:
    eksplicitno = zapis.get("pracene_valute") or zapis.get("simboli_po_redoslijedu")
    if isinstance(eksplicitno, list) and eksplicitno:
        return [str(s) for s in eksplicitno]
    valute = zapis.get("valute")
    if isinstance(valute, list):
        return [str(v["simbol"]) for v in valute if v.get("simbol")]
    return []


def postotak_iz_zapisa(
    zapis: dict[str, Any],
    simbol: str,
    prethodne_cijene: dict[str, float | None],
) -> tuple[float, dict[str, float | None]]:
    promjene = zapis.get("promjene_od_proslog_ocitanja")
    if isinstance(promjene, dict) and simbol in promjene:
        podatak = promjene[simbol]
        postotak = podatak.get("promjena_postotak")
        cijena = podatak.get("cijena_zadnja")
        if cijena is not None:
            prethodne_cijene[simbol] = float(cijena)
        if postotak is None:
            return math.nan, prethodne_cijene
        return float(postotak), prethodne_cijene

    cijena_nova: float | None = None
    for valuta in zapis.get("valute") or []:
        if valuta.get("simbol") == simbol:
            sirovo = valuta.get("cijena_zadnja")
            if sirovo is not None:
                cijena_nova = float(sirovo)
            break

    izracun = promjena_cijene(prethodne_cijene.get(simbol), cijena_nova)
    if cijena_nova is not None:
        prethodne_cijene[simbol] = cijena_nova
    postotak = izracun.get("promjena_postotak")
    if postotak is None:
        return math.nan, prethodne_cijene
    return float(postotak), prethodne_cijene


def ucitaj_zapise_iz_datoteka() -> list[dict[str, Any]]:
    zapisi: list[dict[str, Any]] = []

    if DATOTEKA_POVIJEST_JSONL.is_file():
        with DATOTEKA_POVIJEST_JSONL.open(encoding="utf-8") as datoteka:
            for redak in datoteka:
                redak = redak.strip()
                if not redak:
                    continue
                try:
                    zapisi.append(json.loads(redak))
                except json.JSONDecodeError:
                    continue

    if DATOTEKA_ZADNJI_JSON.is_file():
        try:
            zadnji = json.loads(DATOTEKA_ZADNJI_JSON.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            zadnji = None
        if isinstance(zadnji, dict):
            vrijeme_zadnjeg = parsiraj_vrijeme_zapisa(zadnji)
            if vrijeme_zadnjeg and zapisi:
                vrijeme_u_povijesti = parsiraj_vrijeme_zapisa(zapisi[-1])
                if vrijeme_u_povijesti != vrijeme_zadnjeg:
                    zapisi.append(zadnji)
            elif vrijeme_zadnjeg and not zapisi:
                zapisi.append(zadnji)

    def kljuc_vremena(zapis: dict[str, Any]) -> datetime:
        vrijeme = parsiraj_vrijeme_zapisa(zapis)
        if vrijeme is None:
            return datetime.min.replace(tzinfo=timezone.utc)
        if vrijeme.tzinfo is None:
            return vrijeme.replace(tzinfo=timezone.utc)
        return vrijeme

    zapisi.sort(key=kljuc_vremena)
    return zapisi


def ucitaj_povijest_iz_log_datoteka() -> PovijestGrafa:
    povijest = PovijestGrafa()
    prethodne_cijene: dict[str, float | None] = {}

    for zapis in ucitaj_zapise_iz_datoteka():
        vrijeme = parsiraj_vrijeme_zapisa(zapis)
        if vrijeme is None:
            continue

        simboli = simboli_iz_zapisa(zapis)
        if not simboli:
            continue

        if not povijest.pracene_valute:
            povijest.pracene_valute = list(simboli)
            for simbol in simboli:
                povijest.postotci[simbol] = []

        if povijest.vremena and povijest.vremena[-1] == vrijeme:
            continue

        povijest.vremena.append(vrijeme)
        for simbol in povijest.pracene_valute:
            postotak, prethodne_cijene = postotak_iz_zapisa(zapis, simbol, prethodne_cijene)
            povijest.postotci.setdefault(simbol, []).append(postotak)

    povijest.prethodne_cijene = prethodne_cijene
    return povijest


def formatiraj_datum_za_legendu(vremena: list[datetime]) -> str:
    if not vremena:
        return "—"
    datumi = {v.astimezone().date() for v in vremena}
    if len(datumi) == 1:
        return next(iter(datumi)).strftime("%d.%m.%Y")
    prvi = min(datumi).strftime("%d.%m.%Y")
    zadnji = max(datumi).strftime("%d.%m.%Y")
    return f"{prvi} – {zadnji}"


class GrafPromjenaPostotaka:
    """Tkinter prozor s linijskim grafom promjena u % za sve praćene valute."""

    def __init__(self, korak_sekunde: int) -> None:
        self.korak_sekunde = korak_sekunde
        self.vremena: list[datetime] = []
        self.postotci: dict[str, list[float]] = defaultdict(list)
        self.pracene_valute: list[str] = []
        self.prethodne_cijene: dict[str, float | None] = {}

        self.root = tk.Tk()
        self.root.title("CCXT — promjena cijena u % (po očitanju)")
        self.root.geometry("920x560")

        self.fig = Figure(figsize=(8.5, 4.5), dpi=100)
        self.ax = self.fig.add_subplot(111)
        self.ax.set_xlabel("Vrijeme učitavanja")
        self.ax.set_ylabel("Promjena u odnosu na prethodno očitanje (%)")
        self.ax.axhline(0, color="#888888", linewidth=0.8, linestyle="--")
        self.ax.grid(True, alpha=0.3)

        self.canvas = FigureCanvasTkAgg(self.fig, master=self.root)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        self.status = tk.StringVar(value="Čekam prvo očitanje…")
        tk.Label(self.root, textvariable=self.status, anchor="w").pack(
            fill=tk.X, padx=8, pady=(0, 8)
        )

        self.ucitaj_povijest_iz_logova()

    def ucitaj_povijest_iz_logova(self) -> None:
        povijest = ucitaj_povijest_iz_log_datoteka()
        if povijest.pracene_valute:
            self.pracene_valute = list(povijest.pracene_valute)
        self.vremena = list(povijest.vremena)
        self.postotci = defaultdict(list, povijest.postotci)
        self.prethodne_cijene = dict(povijest.prethodne_cijene)

        if self.vremena:
            zadnje = self.vremena[-1].astimezone().strftime("%Y-%m-%d %H:%M:%S %z")
            self._osvjezi_graf()
            self.status.set(
                f"Učitano iz loga: {len(self.vremena)} očitanja. Zadnje: {zadnje}"
            )

    def postavi_valute(self, simboli: list[str]) -> None:
        if self.pracene_valute:
            return
        self.pracene_valute = list(simboli)
        for simbol in simboli:
            self.postotci.setdefault(simbol, [])

    def dodaj_ocitanje(
        self,
        vrijeme: datetime,
        promjene: dict[str, dict[str, Any]],
    ) -> None:
        if not self.pracene_valute:
            return

        if self.vremena and self.vremena[-1] == vrijeme:
            return

        self.vremena.append(vrijeme)

        for simbol in self.pracene_valute:
            promjena = promjene.get(simbol, {})
            postotak = promjena.get("promjena_postotak")
            if postotak is None:
                vrijednost = math.nan
            else:
                vrijednost = float(postotak)
            self.postotci[simbol].append(vrijednost)

        self._osvjezi_graf()
        tekst_vrijeme = vrijeme.astimezone().strftime("%Y-%m-%d %H:%M:%S %z")
        self.status.set(
            f"Zadnje očitanje: {tekst_vrijeme}  |  ukupno očitanja: {len(self.vremena)}"
        )

    def _osvjezi_graf(self) -> None:
        self.ax.clear()
        self.ax.set_xlabel("Vrijeme učitavanja")
        self.ax.set_ylabel("Promjena u odnosu na prethodno očitanje (%)")
        self.ax.axhline(0, color="#888888", linewidth=0.8, linestyle="--")
        self.ax.grid(True, alpha=0.3)

        if not self.vremena:
            self.fig.subplots_adjust(top=0.88)
            self.canvas.draw_idle()
            return

        x = self.vremena
        for i, simbol in enumerate(self.pracene_valute):
            y = self.postotci.get(simbol, [])
            if not y:
                continue
            broj_tocka = min(len(x), len(y))
            boja = BOJE_VALUTA[i % len(BOJE_VALUTA)]
            self.ax.plot(
                x[:broj_tocka],
                y[:broj_tocka],
                marker="o",
                markersize=4,
                label=simbol,
                color=boja,
                linewidth=1.8,
            )

        self.ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M:%S"))
        self.ax.xaxis.set_major_locator(mdates.AutoDateLocator())
        for oznaka in self.ax.get_xticklabels():
            oznaka.set_rotation(35)
            oznaka.set_ha("right")

        datum_legenda = formatiraj_datum_za_legendu(self.vremena)
        if self.pracene_valute:
            self.ax.legend(
                loc="upper center",
                bbox_to_anchor=(0.5, 1.14),
                ncol=len(self.pracene_valute),
                title=f"Datum: {datum_legenda}",
            )
        self.fig.subplots_adjust(top=0.82, bottom=0.18)
        self.canvas.draw_idle()

    def pokreni_glavnu_petlju(self) -> None:
        self.root.mainloop()


def petlja_ocitanja(
    red_poruka: Queue,
    zaustavi: threading.Event,
    pocetne_valute: list[str] | None = None,
    pocetne_cijene: dict[str, float | None] | None = None,
) -> None:
    burza = ucitaj_burzu(ID_BURZE)
    pracene_valute: list[str] | None = list(pocetne_valute) if pocetne_valute else None
    prethodne_cijene: dict[str, float | None] = dict(pocetne_cijene or {})

    while not zaustavi.is_set():
        vrijeme_citanja = datetime.now().astimezone()
        vrijeme_citanja_lokalno = vrijeme_citanja.strftime("%Y-%m-%d %H:%M:%S %z")
        vrijeme_citanja_utc = datetime.now(timezone.utc).isoformat()

        try:
            tickeri = burza.fetch_tickers()
        except ccxt.NetworkError as greska:
            print(f"Vrijeme čitanja: {vrijeme_citanja_lokalno}")
            print(f"  Mrežna greška, podaci nisu učitani: {greska}\n")
            red_poruka.put(("greska", vrijeme_citanja_lokalno, str(greska)))
            spavaj_s_prekidom(zaustavi, INTERVAL_SEKUNDI)
            continue

        if pracene_valute is None:
            pracene_valute = najpopularnije_valute(burza, tickeri)
            print(
                f"Praćene valute (top {BROJ_VALUTA} po volumenu): "
                f"{', '.join(pracene_valute)}\n"
            )
            red_poruka.put(("valute", pracene_valute))

        assert pracene_valute is not None
        promjene: dict[str, dict[str, Any]] = {}
        for simbol in pracene_valute:
            stanje = trenutno_stanje_valute(burza, simbol, tickeri)
            cijena_sirovo = stanje.get("cijena_zadnja")
            cijena_nova = float(cijena_sirovo) if cijena_sirovo is not None else None
            promjene[simbol] = promjena_cijene(
                prethodne_cijene.get(simbol), cijena_nova
            )
            prethodne_cijene[simbol] = cijena_nova

        izvjestaj = sastavi_izvjestaj(
            burza,
            tickeri,
            pracene_valute,
            vrijeme_citanja_utc,
            vrijeme_citanja_lokalno,
            promjene,
        )
        spremi_json(DATOTEKA_ZADNJI_JSON, izvjestaj)
        dodaj_u_jsonl(DATOTEKA_POVIJEST_JSONL, izvjestaj)

        print(f"Vrijeme čitanja: {vrijeme_citanja_lokalno}")
        for simbol in pracene_valute:
            print(formatiraj_promjenu_za_ispis(simbol, promjene[simbol]))
        print()

        red_poruka.put(("ocitanje", vrijeme_citanja, promjene))

        spavaj_s_prekidom(zaustavi, INTERVAL_SEKUNDI)


def glavno() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    ispisi_upute_za_prekid()

    zaustavi = threading.Event()
    red_poruka: Queue = Queue()

    graf = GrafPromjenaPostotaka(INTERVAL_SEKUNDI)
    pocetne_valute = graf.pracene_valute or None
    pocetne_cijene = graf.prethodne_cijene or None

    def pri_zatvaranju() -> None:
        zaustavi.set()
        graf.root.destroy()

    graf.root.protocol("WM_DELETE_WINDOW", pri_zatvaranju)

    def obradi_red() -> None:
        try:
            while True:
                poruka = red_poruka.get_nowait()
                vrsta = poruka[0]
                if vrsta == "valute":
                    graf.postavi_valute(poruka[1])
                elif vrsta == "ocitanje":
                    vrijeme = poruka[1]
                    if isinstance(vrijeme, str):
                        vrijeme = parsiraj_vrijeme_teksta(vrijeme)
                    graf.dodaj_ocitanje(vrijeme, poruka[2])
                elif vrsta == "greska":
                    graf.status.set(f"Greška ({poruka[1]}): {poruka[2]}")
        except Empty:
            pass
        if not zaustavi.is_set():
            graf.root.after(300, obradi_red)

    graf.root.after(300, obradi_red)

    nit = threading.Thread(
        target=petlja_ocitanja,
        args=(red_poruka, zaustavi, pocetne_valute, pocetne_cijene),
        daemon=True,
    )
    nit.start()

    try:
        graf.pokreni_glavnu_petlju()
    except KeyboardInterrupt:
        pass
    finally:
        zaustavi.set()
        print("\nProgram je zaustavljen.")


if __name__ == "__main__":
    glavno()
