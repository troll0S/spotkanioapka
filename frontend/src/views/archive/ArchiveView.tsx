import { useCallback, useEffect, useState } from "react";
import { type AdminMe, clearAdmin, loadAdmin } from "../../lib/adminSession";
import { api, ApiError } from "../../lib/api";
import type { AdminUserRow, ArchiveDetail, ArchiveEntry } from "../../lib/types";
import { AdminLogin } from "../../components/AdminLogin";

/**
 * Archiwum sesji.
 *
 * Za osobnym logowaniem, bo to jedyne miejsce w aplikacji widoczne **ponad**
 * pojedynczą sesją. Rola admina działa wewnątrz sesji, do której się dołączyło;
 * lista wszystkich spotkań z nazwami wymaga czegoś więcej.
 */

type Me = AdminMe;

export default function ArchiveView() {
  const [admin, setAdmin] = useState(() => loadAdmin());

  const wyloguj = useCallback(() => {
    clearAdmin();
    setAdmin(null);
  }, []);

  if (!admin) {
    return (
      <AdminLogin
        onLogged={setAdmin}
        title="Archiwum i panel"
        sub="Wszystkie spotkania, jakie przeszły przez tę aplikację. Nie musisz zakładać ani dołączać do żadnej sesji."
      />
    );
  }

  return <Archive token={admin.token} me={admin.me} onLogout={wyloguj} />;
}

function Archive({
  token,
  me,
  onLogout,
}: {
  token: string;
  me: Me;
  onLogout: () => void;
}) {
  const [sessions, setSessions] = useState<ArchiveEntry[] | null>(null);
  const [open, setOpen] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<"sessions" | "users">("sessions");

  const odswiez = useCallback(async () => {
    try {
      setSessions(await api.adminSessions(token));
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        onLogout();
        return;
      }
      setError(err instanceof ApiError ? err.message : "Nie udało się pobrać listy.");
    }
  }, [token, onLogout]);

  useEffect(() => {
    void odswiez();
  }, [odswiez]);

  if (error) {
    return (
      <main className="card">
        <h1>Archiwum</h1>
        <p className="error">{error}</p>
        <button className="btn" onClick={onLogout}>
          Zaloguj ponownie
        </button>
      </main>
    );
  }

  if (!sessions) {
    return (
      <main className="card">
        <h1>Archiwum</h1>
        <p className="muted">Wczytuję…</p>
      </main>
    );
  }

  return (
    <main className="card card-wide">
      <header className="head">
        <div>
          <h1>Archiwum i panel</h1>
          <p className="sub">
            {me.login}
            {me.isSuperadmin && <span className="chip chip-admin">superadmin</span>}
          </p>
        </div>
        <div className="row">
          {/* Zalogowany administrator może stąd od razu poprowadzić
              spotkanie — nie ma po co wracać na stronę główną. */}
          <a className="btn btn-primary" href="/host">
            + Nowa sesja
          </a>
          <button className="btn-link" onClick={onLogout}>
            Wyloguj
          </button>
        </div>
      </header>

      {me.isSuperadmin && (
        <div className="term-tabs" role="tablist">
          <button
            type="button"
            role="tab"
            aria-selected={tab === "sessions"}
            className={`term-tab${tab === "sessions" ? " active" : ""}`}
            onClick={() => setTab("sessions")}
          >
            Sesje ({sessions.length})
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={tab === "users"}
            className={`term-tab${tab === "users" ? " active" : ""}`}
            onClick={() => setTab("users")}
          >
            Konta
          </button>
        </div>
      )}

      {tab === "users" ? (
        <Users token={token} me={me} />
      ) : sessions.length === 0 ? (
        <p className="muted">Jeszcze nic tu nie ma.</p>
      ) : (
        <ul className="ideas">
          {sessions.map((s) => (
            <li key={s.code} className={`idea${s.isActive ? " idea-active" : ""}`}>
              <div className="idea-head">
                <span className="idea-title">
                  {s.name}
                  {s.isActive && <span className="chip chip-host">trwa</span>}
                </span>
                <button
                  className="btn-icon"
                  onClick={() => setOpen(open === s.code ? null : s.code)}
                >
                  {open === s.code ? "Zwiń" : "Pokaż"}
                </button>
              </div>

              <div className="idea-meta">
                {new Date(s.createdAt).toLocaleDateString("pl-PL")} · kod {s.code} ·{" "}
                {s.participants} uczestników · {s.ideas} pomysłów · {s.statusLabel}
                {s.createdBy && ` · prowadził ${s.createdBy}`}
              </div>

              {open === s.code && (
                <Detail code={s.code} token={token} onDeleted={odswiez} />
              )}
            </li>
          ))}
        </ul>
      )}
    </main>
  );
}

/**
 * Zarządzanie kontami — tylko dla superadmina.
 *
 * Konta wyłączamy zamiast usuwać, gdy ktoś przestaje prowadzić spotkania:
 * sesje mają dalej wskazywać na konkretną osobę. Usunięcie zostaje na
 * pomyłki przy zakładaniu.
 */
function Users({ token, me }: { token: string; me: Me }) {
  const [users, setUsers] = useState<AdminUserRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);

  const odswiez = useCallback(async () => {
    try {
      setUsers(await api.adminUsers(token));
      setError(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Nie udało się pobrać kont.");
    }
  }, [token]);

  useEffect(() => {
    void odswiez();
  }, [odswiez]);

  const dzialaj = async (akcja: () => Promise<unknown>) => {
    try {
      await akcja();
      setError(null);
      await odswiez();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Operacja się nie udała.");
    }
  };

  if (!users) return <p className="muted">Wczytuję…</p>;

  return (
    <section>
      {error && <p className="error">{error}</p>}

      <ul className="admin-rows">
        {users.map((u) => (
          <li key={u.login}>
            <span className="admin-name">
              {u.login}
              {u.isSuperadmin && <span className="chip chip-admin">superadmin</span>}
              {!u.isActive && <span className="chip">wyłączone</span>}
              {u.login === me.login && <span className="chip chip-host">to Ty</span>}
            </span>
            <span className="idea-tools">
              <button
                className="btn-icon"
                onClick={() => {
                  const haslo = prompt(`Nowe hasło dla „${u.login}" (min. 8 znaków)`);
                  if (haslo) void dzialaj(() => api.adminUpdateUser(token, u.login, { password: haslo }));
                }}
              >
                Zmień hasło
              </button>
              <button
                className="btn-icon"
                onClick={() =>
                  void dzialaj(() =>
                    api.adminUpdateUser(token, u.login, { is_active: !u.isActive }),
                  )
                }
              >
                {u.isActive ? "Wyłącz" : "Włącz"}
              </button>
              {u.login !== me.login && (
                <button
                  className="btn-icon danger"
                  onClick={() => void dzialaj(() => api.adminDeleteUser(token, u.login))}
                >
                  Usuń
                </button>
              )}
            </span>
          </li>
        ))}
      </ul>

      {adding ? (
        <NewUser
          token={token}
          onDone={async () => {
            setAdding(false);
            await odswiez();
          }}
          onError={setError}
        />
      ) : (
        <button className="btn" style={{ marginTop: "1rem" }} onClick={() => setAdding(true)}>
          + Nowe konto
        </button>
      )}

      <p className="muted small" style={{ marginTop: "1rem" }}>
        Zmiana hasła albo wyłączenie konta wylogowuje je natychmiast. Ostatniego
        superadmina nie da się wyłączyć ani usunąć — bez niego nikt nie dodałby
        kolejnych kont.
      </p>
    </section>
  );
}

function NewUser({
  token,
  onDone,
  onError,
}: {
  token: string;
  onDone: () => void;
  onError: (message: string) => void;
}) {
  const [login, setLogin] = useState("");
  const [password, setPassword] = useState("");
  const [isSuperadmin, setIsSuperadmin] = useState(false);

  return (
    <form
      className="stack admin-box"
      onSubmit={async (e) => {
        e.preventDefault();
        try {
          await api.adminCreateUser(token, login.trim(), password, isSuperadmin);
          onDone();
        } catch (err) {
          onError(err instanceof ApiError ? err.message : "Nie udało się założyć konta.");
        }
      }}
    >
      <label>
        Login
        <input
          value={login}
          onChange={(e) => setLogin(e.target.value)}
          placeholder="małe litery, cyfry, . _ -"
          autoCapitalize="none"
          autoCorrect="off"
          spellCheck={false}
          autoFocus
          required
        />
      </label>
      <label>
        Hasło (min. 8 znaków)
        <input
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
        />
      </label>
      <label className="checkbox">
        <input
          type="checkbox"
          checked={isSuperadmin}
          onChange={(e) => setIsSuperadmin(e.target.checked)}
        />
        Superadmin — może zarządzać kontami
      </label>
      <div className="row">
        <button
          className="btn btn-primary"
          type="submit"
          disabled={!login.trim() || password.length < 8}
        >
          Załóż konto
        </button>
        <button className="btn" type="button" onClick={onDone}>
          Anuluj
        </button>
      </div>
    </form>
  );
}

function Detail({
  code,
  token,
  onDeleted,
}: {
  code: string;
  token: string;
  onDeleted: () => void;
}) {
  const [detail, setDetail] = useState<ArchiveDetail | null>(null);
  const [confirming, setConfirming] = useState(false);

  useEffect(() => {
    let alive = true;
    api
      .adminSession(code, token)
      .then((d) => alive && setDetail(d))
      .catch(() => alive && setDetail(null));
    return () => {
      alive = false;
    };
  }, [code, token]);

  if (!detail) return <p className="muted small">Wczytuję…</p>;

  const wPlanie = detail.ideas.filter((i) => i.planDecision === true);

  return (
    <div className="archive-detail">
      <div className="archive-grid">
        <div>
          <div className="label">Uczestnicy ({detail.participants.length})</div>
          <div className="people-names">
            {detail.participants.map((p) => p.displayName).join(", ")}
          </div>
        </div>
      </div>

      {wPlanie.length > 0 && (
        <>
          <div className="label">W planie ({wPlanie.length})</div>
          <ul className="archive-list">
            {wPlanie.map((i) => (
              <li key={i.id}>
                <strong>{i.title}</strong>
                {i.schedule && <span className="term"> · {i.schedule}</span>}
                {i.assigned.length > 0 && (
                  <span className="muted"> · {i.assigned.join(", ")}</span>
                )}
              </li>
            ))}
          </ul>
        </>
      )}

      {detail.rejected.length > 0 && (
        <>
          <div className="label">Odpadło ({detail.rejected.length})</div>
          <ul className="archive-list muted">
            {detail.rejected.map((r, i) => (
              <li key={i}>
                {r.title} <span className="reason">— {r.reason}</span>
              </li>
            ))}
          </ul>
        </>
      )}

      <div className="row" style={{ marginTop: "1rem" }}>
        {detail.canExport && (
          <>
            <a className="btn" href={`${detail.exportBase}/calendar.pdf`} download>
              Plan (PDF)
            </a>
            <a className="btn" href={`${detail.exportBase}/calendar.ics`} download>
              .ics
            </a>
            {detail.rejected.length > 0 && (
              <a className="btn btn-ghost" href={`${detail.exportBase}/rejected.pdf`} download>
                Odrzucone (PDF)
              </a>
            )}
          </>
        )}

        {confirming ? (
          <span className="confirm">
            Usunąć bezpowrotnie?
            <button
              className="btn btn-danger"
              onClick={async () => {
                await api.adminDeleteSession(code, token);
                onDeleted();
              }}
            >
              Tak, usuń
            </button>
            <button className="btn" onClick={() => setConfirming(false)}>
              Anuluj
            </button>
          </span>
        ) : (
          <button className="btn btn-ghost" onClick={() => setConfirming(true)}>
            Usuń sesję
          </button>
        )}
      </div>
    </div>
  );
}
