"""Ograniczanie liczby prób — potrzebne dopiero, gdy adres jest publiczny.

W sieci lokalnej zabezpieczeniem jest sama sieć. Po włączeniu tunelu hasło
admina staje się jedyną przeszkodą i można je skubać w nieskończoność, więc
liczymy nieudane próby.

Uwaga na rozpoznawanie klienta. W trybie lokalnym Docker na Windowsie podmienia
adres klienta na adres bramy — wszystkie telefony wyglądają jak jeden host.
Dlatego:
  * limit **nieudanych logowań** jest ostry (to on chroni hasło),
  * limit **dołączeń** jest luźny, bo trzydzieści osób wchodzących w tej samej
    minucie z jednego widzianego adresu to normalna sytuacja, nie atak.

Stan siedzi w pamięci procesu. Restart go czyści i to jest w porządku:
chodzi o spowolnienie zgadywania w trakcie sesji, nie o trwały rejestr.
"""

import time
from collections import defaultdict, deque


class RateLimiter:
    def __init__(self, limit: int, window_seconds: float) -> None:
        self.limit = limit
        self.window = window_seconds
        self._events: dict[str, deque[float]] = defaultdict(deque)

    def _trim(self, key: str, now: float) -> deque[float]:
        events = self._events[key]
        cutoff = now - self.window
        while events and events[0] < cutoff:
            events.popleft()
        return events

    def hit(self, key: str) -> None:
        """Zapisuje zdarzenie (np. nieudaną próbę hasła)."""
        now = time.monotonic()
        self._trim(key, now).append(now)

    def exceeded(self, key: str) -> bool:
        return len(self._trim(key, time.monotonic())) >= self.limit

    def retry_after(self, key: str) -> int:
        """Ile sekund do zwolnienia najstarszego zdarzenia w oknie."""
        events = self._trim(key, time.monotonic())
        if not events:
            return 0
        return max(1, int(self.window - (time.monotonic() - events[0])) + 1)

    def reset(self, key: str) -> None:
        """Po udanym logowaniu licznik nieudanych prób przestaje mieć znaczenie."""
        self._events.pop(key, None)

    def clear(self) -> None:
        self._events.clear()


#: Zwłoka po błędnym haśle. Nie boli przy literówce, a zgadywanie hurtem
#: spowalnia nawet wtedy, gdy atakujący rozkłada próby na wiele adresów
#: i nie łapie się na limit poniżej. Testy zerują tę wartość.
FAILED_AUTH_DELAY = 0.3

#: Nieudane logowania. Dziesięć prób na pięć minut — człowiek, który się pomylił,
#: tego nie odczuje, a zgadywanie 24-znakowego hasła staje się bezcelowe.
failed_auth = RateLimiter(limit=10, window_seconds=300)

#: Dołączanie do sesji. Luźno, bo w trybie lokalnym cała grupa dzieli jeden
#: widziany adres — to ma odsiewać skrypty, nie uczestników.
joins = RateLimiter(limit=60, window_seconds=60)


def client_key(headers, client_host: str | None) -> str:
    """Identyfikator klienta do liczenia prób.

    Za tunelem Cloudflare prawdziwy adres jest w `CF-Connecting-IP` — bez tego
    wszyscy w trybie zdalnym wyglądaliby jak jeden klient i pierwszy atakujący
    zablokowałby limit dla całej reszty.

    Nagłówkowi ufamy świadomie: aplikacja jest wystawiana albo w sieci lokalnej
    (gdzie nagłówka nie ma), albo przez tunel, który go ustawia i nadpisuje.
    Najgorsze, co daje podrobienie go, to ominięcie własnego limitu — a hasło
    i tak zostaje nie do zgadnięcia.
    """
    forwarded = headers.get("cf-connecting-ip") or headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return client_host or "nieznany"
