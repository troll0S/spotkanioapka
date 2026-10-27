"""Wykrywanie adresu, pod którym aplikacja jest osiągalna."""

import os
import socket


def lan_ip() -> str | None:
    """Adres IPv4 interfejsu używanego do wyjścia na zewnątrz.

    Uwaga: wywołane wewnątrz kontenera zwraca adres kontenera (172.x.x.x),
    a nie adres laptopa w sieci Wi-Fi. Do kodu QR (K1) służy PUBLIC_URL.
    Nie nawiązuje żadnego połączenia — UDP connect tylko wybiera interfejs.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("8.8.8.8", 80))
        return sock.getsockname()[0]
    except OSError:
        return None
    finally:
        sock.close()


def in_container() -> bool:
    """Heurystyka: czy proces działa w kontenerze Dockera."""
    if os.path.exists("/.dockerenv"):
        return True
    try:
        with open("/proc/1/cgroup", encoding="utf-8") as handle:
            return "docker" in handle.read()
    except OSError:
        return False
