import { useState } from "react";
import { ConnectionBadge, NotYet, PeopleList } from "../../components/Common";
import { IdeaList } from "../../components/Ideas";
import { AssignmentReview } from "../../components/AssignmentReview";
import { AvailabilityBoard } from "../../components/Availability";
import { CalendarView } from "../../components/CalendarView";
import { Downloads } from "../../components/Downloads";
import { ScheduleEditor } from "../../components/ScheduleEditor";
import { SwipeBoard } from "../../components/SwipeBoard";
import { AdminLogin } from "../../components/AdminLogin";
import { type AdminMe, clearAdmin, loadAdmin } from "../../lib/adminSession";
import { api, ApiError } from "../../lib/api";
import { clearIdentity, loadIdentity, saveIdentity } from "../../lib/storage";
import type { Identity, Snapshot } from "../../lib/types";
import { useSession } from "../../lib/useSession";

export default function HostView() {
  const [identity, setIdentity] = useState<Identity | null>(() => loadIdentity("host"));

  if (!identity) {
    return <CreateSession onCreated={(created) => {
      saveIdentity("host", created);
      setIdentity(created);
    }} />;
  }

  return (
    <HostConsole
      identity={identity}
      onLeave={() => {
        clearIdentity("host");
        setIdentity(null);
      }}
    />
  );
}

function CreateSession({ onCreated }: { onCreated: (identity: Identity) => void }) {
  const [admin, setAdmin] = useState(() => loadAdmin());

  if (!admin) {
    return (
      <AdminLogin
        onLogged={(sesja) => setAdmin(sesja)}
        title="Nowa sesja"
        sub="Zaloguj się kontem administratora. Pozostaniesz zalogowany także w archiwum."
      />
    );
  }

  return (
    <NameSession
      me={admin.me}
      onCreated={onCreated}
      onLogout={() => {
        clearAdmin();
        setAdmin(null);
      }}
    />
  );
}

function NameSession({
  me,
  onCreated,
  onLogout,
}: {
  me: AdminMe;
  onCreated: (identity: Identity) => void;
  onLogout: () => void;
}) {
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      // Bez loginu i hasła — token zalogowanego idzie w nagłówku.
      onCreated(await api.createSession(name.trim()));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Nie udało się założyć sesji.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="card">
      <header className="head">
        <div>
          <h1>Nowa sesja</h1>
          <p className="sub">
            jako {me.login}
            {me.isSuperadmin && <span className="chip chip-admin">superadmin</span>}
          </p>
        </div>
        <button className="btn-link" onClick={onLogout}>
          Wyloguj
        </button>
      </header>

      <p className="muted">Ten ekran prowadzi proces. Nie bierze udziału w głosowaniu.</p>

      <form className="stack" onSubmit={submit} style={{ marginTop: "1rem" }}>
        <label>
          Nazwa sesji
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="np. Plany na wiosnę"
            maxLength={120}
            required
            autoFocus
          />
        </label>

        {error && <p className="error">{error}</p>}

        <button className="btn btn-primary" type="submit" disabled={busy || !name.trim()}>
          {busy ? "Zakładam…" : "Załóż sesję"}
        </button>
      </form>

      <footer>
        <a href="/archive">Archiwum poprzednich sesji</a> — jesteś już zalogowany,
        nie zapyta o hasło.
      </footer>
    </main>
  );
}

function HostConsole({ identity, onLeave }: { identity: Identity; onLeave: () => void }) {
  const { snapshot, connection, fatalError, lastError, send } = useSession(
    identity.code,
    identity.token,
  );
  const [confirmingAbort, setConfirmingAbort] = useState(false);

  if (fatalError) {
    return (
      <main className="card">
        <h1>Sesja niedostępna</h1>
        <p className="error">{fatalError}</p>
        <button className="btn" onClick={onLeave}>
          Zacznij od nowa
        </button>
      </main>
    );
  }

  if (!snapshot) {
    return (
      <main className="card">
        <h1>Łączę z sesją…</h1>
        <ConnectionBadge state={connection} />
      </main>
    );
  }

  const { session, counts, host, participants } = snapshot;
  const guests = participants.filter((p) => p.role !== "HOST");

  return (
    <main className="card card-wide">
      <header className="head">
        <div>
          <h1>{session.name}</h1>
          <p className="sub">{session.statusLabel}</p>
        </div>
        <ConnectionBadge state={connection} />
      </header>

      {session.status === "LOBBY" ? (
        <Lobby snapshot={snapshot} />
      ) : session.status === "COLLECTING" ? (
        <Collecting snapshot={snapshot} send={send} />
      ) : session.status === "SWIPING" && snapshot.swiping ? (
        <SwipeBoard
          swiping={snapshot.swiping}
          onDecide={(ideaId, accepted) => send("host.decide", { ideaId, accepted })}
        />
      ) : session.status === "SCHEDULING" && snapshot.scheduling ? (
        <ScheduleEditor scheduling={snapshot.scheduling} send={send} />
      ) : session.status === "AVAILABILITY" && snapshot.availability ? (
        <AvailabilityBoard availability={snapshot.availability} send={send} />
      ) : session.status === "ASSIGNMENT" && snapshot.assignment ? (
        <AssignmentReview assignment={snapshot.assignment} send={send} />
      ) : session.status === "CALENDAR" && snapshot.calendar ? (
        <>
          <CalendarView calendar={snapshot.calendar} />
          {snapshot.exports && <Downloads exports={snapshot.exports} />}
        </>
      ) : session.status === "CLOSED" ? (
        <>
          <div className="stage">
            <div className="stage-label">Sesja zakończona</div>
            <p className="muted">Plan zostaje — możesz go pobrać w każdej chwili.</p>
          </div>
          {snapshot.exports && <Downloads exports={snapshot.exports} />}
        </>
      ) : (
        <NotYet stage={session.statusLabel} milestone={nextMilestone(session.status)} />
      )}

      <section className="counters">
        <div>
          <strong>{counts.votingConnected}</strong>
          <span>/ {counts.voting} głosujących online</span>
        </div>
        <div>
          <strong>{counts.connected}</strong>
          <span>/ {counts.total} wszystkich online</span>
        </div>
        {session.status !== "LOBBY" && (
          <div>
            <strong>{snapshot.ideaCounts.total}</strong>
            <span>
              pomysłów
              {snapshot.ideaCounts.special > 0 && ` (${snapshot.ideaCounts.special} ustalonych)`}
            </span>
          </div>
        )}
        {counts.spectators > 0 && (
          <div>
            <strong>{counts.spectators}</strong>
            <span>oglądających</span>
          </div>
        )}
      </section>

      <section>
        <h2>Uczestnicy</h2>
        <PeopleList people={guests} emptyText="Czekam, aż ktoś dołączy." />
      </section>

      {lastError && <p className="error">{lastError}</p>}

      <div className="actions">
        {host?.canAdvance && host.nextLabel && (
          <button className="btn btn-primary" onClick={() => send("host.advance")}>
            Dalej → {host.nextLabel}
          </button>
        )}

        {session.isActive &&
          (confirmingAbort ? (
            <div className="confirm">
              <span>Przerwać sesję? Tego nie da się cofnąć.</span>
              <button className="btn btn-danger" onClick={() => send("host.abort")}>
                Tak, przerwij
              </button>
              <button className="btn" onClick={() => setConfirmingAbort(false)}>
                Anuluj
              </button>
            </div>
          ) : (
            <button className="btn btn-ghost" onClick={() => setConfirmingAbort(true)}>
              Przerwij sesję
            </button>
          ))}

        {!session.isActive && (
          <button className="btn" onClick={onLeave}>
            Nowa sesja
          </button>
        )}
      </div>
    </main>
  );
}

/**
 * Etap 1 u hosta: podgląd rosnącej listy.
 *
 * Host nie dodaje pomysłów — prowadzi proces. Lista jest tu tylko do patrzenia
 * i do decyzji, kiedy etap zamknąć.
 */
function Collecting({
  snapshot,
  send,
}: {
  snapshot: Snapshot;
  send: (type: string, payload?: unknown) => void;
}) {
  return (
    <section className="stage-live">
      <div className="stage-label">Etap 1 — zbieranie pomysłów</div>
      <p className="muted">
        Uczestnicy wpisują na telefonach. Zamknij etap, gdy przestaną dopisywać.
      </p>
      <IdeaList snapshot={snapshot} send={send} readOnly />
    </section>
  );
}

const ORIGIN_OVERRIDE_KEY = "spotkanio.origin";

function Lobby({ snapshot }: { snapshot: Snapshot }) {
  const host = snapshot.host;
  // Nadpisanie adresu przeżywa odświeżenie strony, ale nie jest zapisywane
  // w pliku konfiguracyjnym — po zmianie sieci wystarczy je wyczyścić.
  const [override, setOverride] = useState<string | null>(() =>
    localStorage.getItem(ORIGIN_OVERRIDE_KEY),
  );
  const [editing, setEditing] = useState(false);

  if (!host) return null;

  const joinUrl = override
    ? `${override}/join?code=${snapshot.session.code}`
    : host.joinUrl;
  const qrUrl = override
    ? `${host.qrUrl}?origin=${encodeURIComponent(override)}`
    : host.qrUrl;
  const unreachable = override ? false : host.joinUrlSuspicious;

  const apply = (value: string | null) => {
    if (value) localStorage.setItem(ORIGIN_OVERRIDE_KEY, value);
    else localStorage.removeItem(ORIGIN_OVERRIDE_KEY);
    setOverride(value);
    setEditing(false);
  };

  return (
    <>
      <section className="lobby">
        <div className="qr">
          <img src={qrUrl} alt="Kod QR do dołączenia" />
        </div>

        <div className="join-info">
          <div className="code-label">Kod sesji</div>
          <div className="code">{snapshot.session.code}</div>

          {joinUrl && (
            <>
              <div className="code-label">albo wejdź na</div>
              <div className="url">{joinUrl}</div>

              {/* Potrzebne głównie zdalnie: etapy 2, 3 i 5 dzieją się na tym
                  ekranie, którego nikt poza laptopem nie widzi. */}
              <div className="code-label">podgląd bez udziału</div>
              <div className="url">
                {joinUrl.replace("/join?", "/spectator?")}
              </div>
            </>
          )}

          {unreachable && (
            <p className="warn">
              Ten adres wskazuje na sam laptop, więc telefony go nie otworzą.
              Otwórz ten ekran przez adres IP laptopa w sieci — albo wpisz adres
              ręcznie poniżej.
            </p>
          )}

          {override && (
            <p className="muted small">
              Adres ustawiony ręcznie.{" "}
              <button className="btn-link" onClick={() => apply(null)}>
                Wróć do wykrytego
              </button>
            </p>
          )}

          {!editing ? (
            <button className="btn-link" onClick={() => setEditing(true)}>
              Telefony nie mogą się połączyć? Podaj inny adres
            </button>
          ) : (
            <OriginForm current={override ?? ""} onSave={apply} onCancel={() => setEditing(false)} />
          )}
        </div>
      </section>

      {unreachable && (
        <p className="muted small">
          Najprościej: zatrzymaj aplikację i uruchom ją przez{" "}
          <code>.\start.ps1</code> — skrypt sam ustali aktualny adres laptopa.
        </p>
      )}
    </>
  );
}

/**
 * Ręczne podanie adresu bazowego. Potrzebne w dwóch sytuacjach: host wszedł
 * przez localhost albo trzeba wskazać adres tunelu z trybu zdalnego.
 */
function OriginForm({
  current,
  onSave,
  onCancel,
}: {
  current: string;
  onSave: (value: string) => void;
  onCancel: () => void;
}) {
  const [value, setValue] = useState(current);
  const valid = /^https?:\/\/[A-Za-z0-9._-]+(:\d{1,5})?$/.test(value.trim().replace(/\/$/, ""));

  return (
    <form
      className="stack origin-form"
      onSubmit={(e) => {
        e.preventDefault();
        if (valid) onSave(value.trim().replace(/\/$/, ""));
      }}
    >
      <label>
        Adres, pod którym telefony widzą laptopa
        <input
          value={value}
          onChange={(e) => setValue(e.target.value)}
          placeholder="http://192.168.2.172:8000"
          autoFocus
        />
      </label>
      <div className="row">
        <button className="btn btn-primary" type="submit" disabled={!valid}>
          Ustaw
        </button>
        <button className="btn" type="button" onClick={onCancel}>
          Anuluj
        </button>
      </div>
    </form>
  );
}

/** Który kamień dostarcza dany etap — do komunikatu zastępczego. */
function nextMilestone(status: string): string {
  return (
    {
      COLLECTING: "K2",
      SWIPING: "K3",
      SCHEDULING: "K4",
      AVAILABILITY: "K5",
      CALENDAR: "K6",
    }[status] ?? "kolejnym"
  );
}
