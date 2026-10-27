"""Etap 5 — układ kalendarza.

**Układ liczy serwer, nie przeglądarka.** To nie jest ozdobna decyzja: w K7 ten
sam kalendarz trafi do PDF-a generowanego z szablonu HTML, a WeasyPrint nie
uruchomi kodu Reacta. Gdyby rozkładanie wydarzeń na siatkę tygodni siedziało
w komponencie, trzeba by napisać je drugi raz — i od tego momentu obie wersje
zaczęłyby się rozjeżdżać.

Tutaj powstaje więc gotowa struktura: miesiące → tygodnie → dni oraz pasy
wydarzeń z przypisanymi kolumnami i pasami. Klient (i przyszły szablon PDF-a)
mają już tylko to narysować.
"""

import calendar as stdlib_calendar
from datetime import date

from sqlalchemy.orm import Session as DbSession

from . import assignments, availability, dates_pl
from .models import Answer, Session

#: Kalendarz dłuższy niż rok przestaje być czytelny, a przy pomyłkowej dacie
#: potrafiłby urosnąć do setek miesięcy.
MAX_MIESIECY = 12

#: Powyżej tylu dni termin przestaje być „konkretny". Nakładanie się dwóch
#: takich okien nie jest kolizją — „gdzieś w marcu" i „gdzieś w marcu" mogą
#: spokojnie współistnieć.
DNI_KONKRETNEGO_TERMINU = 7


def _parse(iso: str) -> date:
    return date.fromisoformat(iso)


def month_grid(rok: int, miesiac: int) -> list[list[date]]:
    """Siatka miesiąca: pełne tygodnie od poniedziałku."""
    kal = stdlib_calendar.Calendar(firstweekday=0)
    return kal.monthdatescalendar(rok, miesiac)


def _months_between(od: date, do: date) -> list[tuple[int, int]]:
    miesiace = []
    rok, miesiac = od.year, od.month
    while (rok, miesiac) <= (do.year, do.month) and len(miesiace) < MAX_MIESIECY:
        miesiace.append((rok, miesiac))
        miesiac += 1
        if miesiac > 12:
            miesiac = 1
            rok += 1
    return miesiace


def _assign_lanes(pasy: list[dict]) -> None:
    """Układa nachodzące na siebie pasy jeden pod drugim.

    Zachłannie, od lewej: każdy pas ląduje w najniższym wolnym pasie, w którym
    nie zderzy się z już położonym. Przy kilku wydarzeniach w tygodniu to
    wystarcza, a wynik jest przewidywalny — ten sam wejściowy zestaw zawsze
    daje ten sam układ, także w PDF-ie.
    """
    zajete: list[int] = []  # dla każdego pasa: ostatnia zajęta kolumna
    for pas in sorted(pasy, key=lambda p: (p["startCol"], -p["span"])):
        for numer, ostatnia in enumerate(zajete):
            if pas["startCol"] > ostatnia:
                pas["lane"] = numer
                zajete[numer] = pas["startCol"] + pas["span"] - 1
                break
        else:
            pas["lane"] = len(zajete)
            zajete.append(pas["startCol"] + pas["span"] - 1)


def _warning_level(tally: dict[str, int]) -> str:
    """Jak mocno wydarzenie zgrzyta z grupą.

    Wyłącznie sygnał dla człowieka — system niczego nie odrzuca. Decyzja
    należy do prowadzącego, zgodnie z ustaleniami.
    """
    odpowiedzi = sum(tally.values())
    if odpowiedzi == 0:
        return "empty"
    sprzeciw = tally.get(Answer.ABSOLUTELY_NOT.value, 0)
    if sprzeciw and sprzeciw * 3 >= odpowiedzi:
        return "blocked"
    if sprzeciw:
        return "warn"
    return "ok"


def _conflicts(wydarzenia: list[dict]) -> list[dict]:
    """Pary wydarzeń, które realnie się zderzają.

    Sprawdzamy tylko terminy konkretne (do tygodnia). Dwa okna miesięczne
    zawsze by się nakładały, a taka „kolizja" nie niesie żadnej informacji —
    zalałaby ekran ostrzeżeniami, które trzeba ignorować.
    """
    konkretne = [
        w
        for w in wydarzenia
        if w["schedule"]
        and (_parse(w["schedule"]["dateTo"]) - _parse(w["schedule"]["dateFrom"])).days + 1
        <= DNI_KONKRETNEGO_TERMINU
    ]

    pary = []
    for i, a in enumerate(konkretne):
        for b in konkretne[i + 1 :]:
            a_od, a_do = _parse(a["schedule"]["dateFrom"]), _parse(a["schedule"]["dateTo"])
            b_od, b_do = _parse(b["schedule"]["dateFrom"]), _parse(b["schedule"]["dateTo"])
            if a_od <= b_do and b_od <= a_do:
                pary.append(
                    {
                        "a": {"ideaId": a["ideaId"], "title": a["title"]},
                        "b": {"ideaId": b["ideaId"], "title": b["title"]},
                        "label": dates_pl.przedzial(max(a_od, b_od), min(a_do, b_do)),
                    }
                )
    return pary


def build(db: DbSession, session: Session, today: date | None = None) -> dict:
    """Pełny widok etapu 6: siatka kalendarza, lista wydarzeń i ostrzeżenia.

    Do kalendarza wchodzą **wyłącznie wydarzenia zatwierdzone w etapie 5**.
    Odrzucone znikają całkowicie — także z eksportów.
    """
    dzis = today or date.today()
    zatwierdzone = assignments.confirmed_ideas(db, session.id)
    wydarzenia = availability.summary(db, session, ideas_subset=zatwierdzone)
    przypisania = assignments.assignments_by_idea(db, session.id)

    for pozycja in wydarzenia:
        tally = pozycja["tally"]
        pozycja["attending"] = tally.get(Answer.WANT.value, 0) + tally.get(Answer.CAN.value, 0)
        pozycja["level"] = _warning_level(tally)
        pozycja["assigned"] = [
            {"id": w.id, "name": w.name, "isParticipant": w.participant_id is not None}
            for w in przypisania.get(pozycja["ideaId"], [])
        ]

    z_terminem = [w for w in wydarzenia if w["schedule"]]

    miesiace: list[dict] = []
    if z_terminem:
        najwczesniej = min(_parse(w["schedule"]["dateFrom"]) for w in z_terminem)
        najpozniej = max(_parse(w["schedule"]["dateTo"]) for w in z_terminem)

        # Kolejność kolorów musi być stabilna: ten sam wydarzenie ma ten sam
        # odcień w kalendarzu, na liście i w przyszłym PDF-ie.
        indeksy = {w["ideaId"]: numer for numer, w in enumerate(z_terminem)}

        for rok, miesiac in _months_between(najwczesniej, najpozniej):
            tygodnie = []
            for dni in month_grid(rok, miesiac):
                poczatek, koniec = dni[0], dni[6]
                pasy = []
                for w in z_terminem:
                    od = _parse(w["schedule"]["dateFrom"])
                    do = _parse(w["schedule"]["dateTo"])
                    if do < poczatek or od > koniec:
                        continue
                    start = max(od, poczatek)
                    stop = min(do, koniec)
                    pasy.append(
                        {
                            "ideaId": w["ideaId"],
                            "title": w["title"],
                            "startCol": (start - poczatek).days,
                            "span": (stop - start).days + 1,
                            # Strzałki na krawędziach: bez nich nie widać,
                            # że pas biegnie dalej w następnym tygodniu.
                            "continuesLeft": od < poczatek,
                            "continuesRight": do > koniec,
                            "isSpecial": w["isSpecial"],
                            "level": w["level"],
                            "colorIndex": indeksy[w["ideaId"]] % 8,
                            "lane": 0,
                        }
                    )
                _assign_lanes(pasy)

                tygodnie.append(
                    {
                        "days": [
                            {
                                "date": d.isoformat(),
                                "day": d.day,
                                "inMonth": d.month == miesiac,
                                "isToday": d == dzis,
                                "isWeekend": d.weekday() >= 5,
                            }
                            for d in dni
                        ],
                        "bands": sorted(pasy, key=lambda p: (p["lane"], p["startCol"])),
                        "lanes": max((p["lane"] for p in pasy), default=-1) + 1,
                    }
                )

            miesiace.append(
                {
                    "year": rok,
                    "month": miesiac,
                    "label": f"{dates_pl.miesiac_mianownik(miesiac)} {rok}",
                    "weeks": tygodnie,
                }
            )

    return {
        "months": miesiace,
        "events": wydarzenia,
        "conflicts": _conflicts(wydarzenia),
        "weekdays": ["pon", "wt", "śr", "czw", "pt", "sob", "ndz"],
        "answerLabels": {
            odp.value: etykieta for odp, etykieta in availability.ANSWER_LABELS.items()
        },
        "truncated": len(miesiace) >= MAX_MIESIECY,
    }
