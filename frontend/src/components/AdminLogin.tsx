import { useState } from "react";
import { type AdminSession, lastLogin, saveAdmin } from "../lib/adminSession";
import { api, ApiError } from "../lib/api";

/**
 * Logowanie kontem administratora.
 *
 * Jeden ekran dla wszystkich wejść: archiwum, zakładanie sesji, przejęcie
 * uprawnień w trwającej sesji. Token trafia do wspólnego magazynu, więc
 * kolejne miejsca już nie pytają — to jest cały sens tego, że komponent
 * jest jeden.
 */
export function AdminLogin({
  onLogged,
  title,
  sub,
}: {
  onLogged: (sesja: AdminSession) => void;
  title: string;
  sub: string;
}) {
  // Login pamiętamy na stałe, hasła nigdy — to zwykle ta sama osoba przy
  // tym samym urządzeniu.
  const [login, setLogin] = useState(() => lastLogin());
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const res = await api.adminLogin(login.trim(), password);
      const me = { login: res.login, isSuperadmin: res.isSuperadmin };
      saveAdmin(res.token, me);
      onLogged({ token: res.token, me });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Nie udało się zalogować.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="card">
      <h1>{title}</h1>
      <p className="sub">{sub}</p>

      <form className="stack" onSubmit={submit}>
        <label>
          Login
          <input
            value={login}
            onChange={(e) => setLogin(e.target.value)}
            autoCapitalize="none"
            autoCorrect="off"
            spellCheck={false}
            autoFocus
            required
          />
        </label>
        <label>
          Hasło
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />
        </label>

        {error && <p className="error">{error}</p>}

        <button
          className="btn btn-primary"
          type="submit"
          disabled={busy || !login.trim() || !password}
        >
          {busy ? "Sprawdzam…" : "Zaloguj"}
        </button>
      </form>

      <footer>
        Chcesz tylko dołączyć do cudzej sesji? <a href="/join">Dołącz</a> —
        tam konto nie jest potrzebne.
      </footer>
    </main>
  );
}
