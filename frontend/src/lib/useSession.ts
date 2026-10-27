import { useCallback, useEffect, useRef, useState } from "react";
import type { ConnectionState, Snapshot } from "./types";

/** Kody zamknięcia, po których ponawianie nie ma sensu — coś jest nie tak z tożsamością. */
const FATAL_CLOSE_CODES = new Set([
  4401, // nieznany token
  4404, // nie ma takiej sesji
  4409, // sesja zakończona — anonimowy podgląd odcięty
]);

const PING_INTERVAL_MS = 25_000;
const BACKOFF_MS = [500, 1000, 2000, 4000, 8000, 15_000];

/**
 * Buduje adres WebSocketu z aktualnego protokołu strony.
 *
 * To jedna linijka, która przesądza o trybie zdalnym: na HTTPS przeglądarka
 * blokuje nieszyfrowany WebSocket, więc wpisany na sztywno `ws://` działa
 * lokalnie i cicho przestaje działać przez tunel.
 */
function socketUrl(code: string, token: string, spectator: boolean): string {
  const protocol = location.protocol === "https:" ? "wss:" : "ws:";
  const query = spectator ? "spectator=true" : `token=${encodeURIComponent(token)}`;
  return `${protocol}//${location.host}/ws/session/${code}?${query}`;
}

export type SessionChannel = {
  snapshot: Snapshot | null;
  connection: ConnectionState;
  /** Ustawiane tylko przy błędach, po których nie ponawiamy połączenia. */
  fatalError: string | null;
  lastError: string | null;
  send: (type: string, payload?: unknown) => void;
};

export function useSession(
  code: string | null,
  token: string | null,
  options: { spectator?: boolean } = {},
): SessionChannel {
  const spectator = options.spectator ?? false;
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [connection, setConnection] = useState<ConnectionState>("connecting");
  const [fatalError, setFatalError] = useState<string | null>(null);
  const [lastError, setLastError] = useState<string | null>(null);

  const socketRef = useRef<WebSocket | null>(null);
  const attemptRef = useRef(0);
  // Flaga rozmontowania: bez niej timer reconnectu potrafi ożywić połączenie
  // po opuszczeniu widoku.
  const closedByUsRef = useRef(false);

  const send = useCallback((type: string, payload?: unknown) => {
    const socket = socketRef.current;
    if (socket?.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify({ type, payload }));
    }
  }, []);

  useEffect(() => {
    // Widz nie ma tokenu — sam kod sesji wystarczy.
    if (!code || (!token && !spectator)) return;

    closedByUsRef.current = false;
    let reconnectTimer: number | undefined;
    let pingTimer: number | undefined;

    const connect = () => {
      setConnection(attemptRef.current === 0 ? "connecting" : "reconnecting");

      const socket = new WebSocket(socketUrl(code, token ?? "", spectator));
      socketRef.current = socket;

      socket.onopen = () => {
        attemptRef.current = 0;
        setConnection("open");
        setLastError(null);
        pingTimer = window.setInterval(() => {
          if (socket.readyState === WebSocket.OPEN) {
            socket.send(JSON.stringify({ type: "ping" }));
          }
        }, PING_INTERVAL_MS);
      };

      socket.onmessage = (event) => {
        const message = JSON.parse(event.data as string);
        if (message.type === "state") {
          setSnapshot(message.payload as Snapshot);
        } else if (message.type === "error") {
          setLastError(message.payload?.text ?? "Nieznany błąd");
        }
        // "pong" celowo ignorujemy — liczy się samo dojście pakietu.
      };

      socket.onclose = (event) => {
        window.clearInterval(pingTimer);
        socketRef.current = null;

        if (closedByUsRef.current) return;

        if (FATAL_CLOSE_CODES.has(event.code)) {
          setFatalError(event.reason || "Połączenie odrzucone przez serwer.");
          setConnection("closed");
          return;
        }

        const delay = BACKOFF_MS[Math.min(attemptRef.current, BACKOFF_MS.length - 1)];
        attemptRef.current += 1;
        setConnection("reconnecting");
        reconnectTimer = window.setTimeout(connect, delay);
      };
    };

    connect();

    return () => {
      closedByUsRef.current = true;
      window.clearTimeout(reconnectTimer);
      window.clearInterval(pingTimer);
      socketRef.current?.close();
      socketRef.current = null;
    };
  }, [code, token, spectator]);

  return { snapshot, connection, fatalError, lastError, send };
}
