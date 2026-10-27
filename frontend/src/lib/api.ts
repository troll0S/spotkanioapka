import { authHeader } from "./adminSession";
import type { AdminUserRow, ArchiveDetail, ArchiveEntry, Identity } from "./types";

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });

  if (!res.ok) {
    let detail = `Błąd ${res.status}`;
    try {
      const body = await res.json();
      // FastAPI zwraca komunikat w "detail" — dla błędów walidacji jako listę.
      if (typeof body.detail === "string") detail = body.detail;
    } catch {
      /* odpowiedź bez JSON-a — zostaje komunikat domyślny */
    }
    throw new ApiError(detail, res.status);
  }

  return (await res.json()) as T;
}

export type SessionInfo = {
  code: string;
  name: string;
  status: string;
  status_label: string;
  is_active: boolean;
  participants: number;
};

export const api = {
  /**
   * Zakłada sesję. Zalogowany administrator nie podaje nic poza nazwą —
   * token panelu idzie w nagłówku.
   */
  createSession: (
    name: string,
    dane?: { login: string; password: string },
    hostName = "Host",
  ) =>
    request<Identity>("/api/session", {
      method: "POST",
      headers: authHeader(),
      body: JSON.stringify({ name, ...dane, host_name: hostName }),
    }),

  sessionInfo: (code: string) => request<SessionInfo>(`/api/session/${code}`),

  join: (code: string, displayName: string, token?: string) =>
    request<Identity>(`/api/session/${code}/join`, {
      method: "POST",
      body: JSON.stringify({ display_name: displayName, token: token ?? null }),
    }),

  promote: (
    code: string,
    token: string,
    isVoting: boolean,
    dane?: { login: string; password: string },
  ) =>
    request<Identity>(`/api/session/${code}/promote`, {
      method: "POST",
      headers: authHeader(),
      body: JSON.stringify({ token, ...dane, is_voting: isVoting }),
    }),

  // ── archiwum i konta ──────────────────────────────────────────────────
  // Osobne logowanie, bo to dostęp ponad pojedynczą sesją.

  adminLogin: (login: string, password: string) =>
    request<{ token: string; expiresIn: number; login: string; isSuperadmin: boolean }>(
      "/api/admin/login",
      { method: "POST", body: JSON.stringify({ login, password }) },
    ),

  adminUsers: (token: string) =>
    request<AdminUserRow[]>("/api/admin/users", { headers: bearer(token) }),

  adminCreateUser: (
    token: string,
    login: string,
    password: string,
    isSuperadmin: boolean,
  ) =>
    request<AdminUserRow>("/api/admin/users", {
      method: "POST",
      headers: bearer(token),
      body: JSON.stringify({ login, password, is_superadmin: isSuperadmin }),
    }),

  adminUpdateUser: (
    token: string,
    login: string,
    zmiany: { password?: string; is_active?: boolean; is_superadmin?: boolean },
  ) =>
    request<AdminUserRow>(`/api/admin/users/${login}`, {
      method: "PATCH",
      headers: bearer(token),
      body: JSON.stringify(zmiany),
    }),

  adminDeleteUser: async (token: string, login: string) => {
    const res = await fetch(`/api/admin/users/${login}`, {
      method: "DELETE",
      headers: bearer(token),
    });
    if (!res.ok) {
      let detail = `Błąd ${res.status}`;
      try {
        detail = (await res.json()).detail ?? detail;
      } catch {
        /* bez treści */
      }
      throw new ApiError(detail, res.status);
    }
  },

  adminSessions: (token: string) =>
    request<ArchiveEntry[]>("/api/admin/sessions", { headers: bearer(token) }),

  adminSession: (code: string, token: string) =>
    request<ArchiveDetail>(`/api/admin/sessions/${code}`, { headers: bearer(token) }),

  adminDeleteSession: async (code: string, token: string) => {
    const res = await fetch(`/api/admin/sessions/${code}`, {
      method: "DELETE",
      headers: bearer(token),
    });
    if (!res.ok) throw new ApiError(`Błąd ${res.status}`, res.status);
  },
};

function bearer(token: string): Record<string, string> {
  return { Authorization: `Bearer ${token}` };
}
