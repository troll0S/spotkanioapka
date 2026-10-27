"""Rejestr otwartych połączeń WebSocket i rozsyłanie snapshotów.

Jedno połączenie na uczestnika — ale trzymamy zbiór gniazd na uczestnika,
bo ktoś otworzy dwie karty albo telefon zdąży wrócić, zanim serwer zauważy
zerwanie poprzedniego połączenia.
"""

import asyncio
import logging
from collections.abc import Callable

from fastapi import WebSocket

log = logging.getLogger("spotkanioapka.ws")

#: Ile czekamy na przyjęcie snapshotu przez jednego klienta.
#: W sieci lokalnej to ułamek sekundy, przez tunel pojedyncze setki milisekund —
#: pięć sekund oznacza, że po drugiej stronie coś naprawdę stanęło.
SEND_TIMEOUT_S = 5.0

#: Widzowie nie mają wpisu w bazie, więc nie mają też identyfikatora uczestnika.
#: Dostają ujemne numery z osobnej puli — dzięki temu ten sam rejestr połączeń
#: obsługuje jednych i drugich, a rozróżnienie jest testem znaku.
_spectator_counter = 0


def next_spectator_id() -> int:
    global _spectator_counter
    _spectator_counter -= 1
    return _spectator_counter


def is_spectator(connection_id: int) -> bool:
    return connection_id < 0


class ConnectionManager:
    def __init__(self) -> None:
        # kod sesji -> id uczestnika -> zbiór gniazd
        self._rooms: dict[str, dict[int, set[WebSocket]]] = {}

    async def connect(self, code: str, participant_id: int, websocket: WebSocket) -> None:
        await websocket.accept()
        room = self._rooms.setdefault(code, {})
        room.setdefault(participant_id, set()).add(websocket)

    def disconnect(self, code: str, participant_id: int, websocket: WebSocket) -> bool:
        """Usuwa gniazdo. Zwraca True, jeśli uczestnik nie ma już żadnego.

        Rozróżnienie jest istotne: zamknięcie jednej z dwóch kart nie powinno
        oznaczać, że uczestnik zniknął z sesji.
        """
        room = self._rooms.get(code)
        if not room:
            return False
        sockets = room.get(participant_id)
        if not sockets:
            return False
        sockets.discard(websocket)
        if sockets:
            return False
        room.pop(participant_id, None)
        if not room:
            self._rooms.pop(code, None)
        return True

    def is_online(self, code: str, participant_id: int) -> bool:
        return bool(self._rooms.get(code, {}).get(participant_id))

    def participant_ids(self, code: str) -> list[int]:
        return list(self._rooms.get(code, {}).keys())

    def spectator_count(self, code: str) -> int:
        return sum(1 for cid in self._rooms.get(code, {}) if is_spectator(cid))

    async def send_to(self, code: str, participant_id: int, payload: dict) -> None:
        for socket in list(self._rooms.get(code, {}).get(participant_id, ())):
            await self._safe_send(code, participant_id, socket, payload)

    async def broadcast(self, code: str, build_for: Callable[[int], dict | None]) -> None:
        """Rozsyła snapshot zbudowany osobno dla każdego odbiorcy.

        `build_for` dostaje id uczestnika i zwraca snapshot przefiltrowany pod
        jego rolę — stąd budowanie per odbiorca zamiast jednego wspólnego ładunku.
        """
        room = self._rooms.get(code)
        if not room:
            return
        for participant_id, sockets in list(room.items()):
            payload = build_for(participant_id)
            if payload is None:
                continue
            for socket in list(sockets):
                await self._safe_send(code, participant_id, socket, payload)

    async def close_room(self, code: str, payload: dict | None = None) -> None:
        room = self._rooms.get(code, {})
        for participant_id, sockets in list(room.items()):
            for socket in list(sockets):
                if payload is not None:
                    await self._safe_send(code, participant_id, socket, payload)
                try:
                    await socket.close()
                except RuntimeError:
                    pass
        self._rooms.pop(code, None)

    async def _safe_send(
        self, code: str, participant_id: int, socket: WebSocket, payload: dict
    ) -> None:
        """Wysyłka, która nie wywraca broadcastu z powodu jednego złego gniazda.

        Limit czasu jest tu istotny: rozsyłamy sekwencyjnie, więc klient,
        który przestał odbierać (telefon w windzie, zawieszona karta), bez
        tego zatrzymałby snapshot dla całej reszty sesji. Po przekroczeniu
        limitu wypisujemy go z rejestru — wróci przy ponownym połączeniu,
        a reconnect i tak przywraca mu tożsamość.
        """
        try:
            async with asyncio.timeout(SEND_TIMEOUT_S):
                await socket.send_json(payload)
        except (RuntimeError, ConnectionError, TimeoutError) as exc:
            log.debug("Gniazdo %s/%s odpada przy wysyłce: %s", code, participant_id, exc)
            self.disconnect(code, participant_id, socket)


manager = ConnectionManager()
