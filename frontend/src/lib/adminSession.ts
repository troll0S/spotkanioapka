/**
 * Zalogowanie administratora — wspólne dla całej aplikacji.
 *
 * Jedno logowanie obsługuje archiwum, zakładanie sesji i awans na admina
 * w trwającej sesji. Wcześniej każde z tych miejsc pytało osobno, co przy
 * jednej osobie prowadzącej spotkanie oznaczało trzy razy to samo hasło.
 *
 * `sessionStorage`, nie `localStorage`: to dostęp do wszystkiego, co aplikacja
 * pamięta, więc ma zniknąć razem z kartą. Przetrwa odświeżenie i przejście
 * między ekranami, bo to wciąż ta sama karta.
 */

const TOKEN_KEY = "spotkanio.adminToken";
const ME_KEY = "spotkanio.adminMe";

/** Ostatni login pamiętamy na stałe — hasła nigdy. */
const LAST_LOGIN_KEY = "spotkanio.lastLogin";

export type AdminMe = {
  login: string;
  isSuperadmin: boolean;
};

export type AdminSession = {
  token: string;
  me: AdminMe;
};

export function loadAdmin(): AdminSession | null {
  try {
    const token = sessionStorage.getItem(TOKEN_KEY);
    const raw = sessionStorage.getItem(ME_KEY);
    if (!token || !raw) return null;
    return { token, me: JSON.parse(raw) as AdminMe };
  } catch {
    return null;
  }
}

export function saveAdmin(token: string, me: AdminMe): void {
  sessionStorage.setItem(TOKEN_KEY, token);
  sessionStorage.setItem(ME_KEY, JSON.stringify(me));
  localStorage.setItem(LAST_LOGIN_KEY, me.login);
}

export function clearAdmin(): void {
  sessionStorage.removeItem(TOKEN_KEY);
  sessionStorage.removeItem(ME_KEY);
}

export function lastLogin(): string {
  return localStorage.getItem(LAST_LOGIN_KEY) ?? "";
}

/** Nagłówek dla żądań, które mogą skorzystać z zalogowania. */
export function authHeader(): Record<string, string> {
  const token = loadAdmin()?.token;
  return token ? { Authorization: `Bearer ${token}` } : {};
}
