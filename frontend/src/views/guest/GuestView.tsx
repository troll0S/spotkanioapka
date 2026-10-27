import { useEffect, useState } from "react";
import { ConnectionBadge, NotYet, PeopleList, RoleChip } from "../../components/Common";
import { AdminPanel } from "../../components/AdminPanel";
import { AssignmentReview } from "../../components/AssignmentReview";
import { AvailabilityRound } from "../../components/Availability";
import { CalendarView } from "../../components/CalendarView";
import { Downloads } from "../../components/Downloads";
import { IdeaForm, IdeaList } from "../../components/Ideas";
import { SwipeDeck } from "../../components/SwipeDeck";
import { lastLogin, loadAdmin, saveAdmin } from "../../lib/adminSession";
import { api, ApiError } from "../../lib/api";
import { clearIdentity, loadIdentity, saveIdentity } from "../../lib/storage";
import type { Identity, SwipingState } from "../../lib/types";
import { useSession } from "../../lib/useSession";

export default function GuestView({ codeFromUrl }: { codeFromUrl: string | null }) {
  const [identity, setIdentity] = useState<Identity | null>(() => {
    const stored = loadIdentity("guest");
    // Kod z QR ma pierwszeństwo: jeśli ktoś skanuje nową sesję, nie chcemy
    // przywracać go do poprzedniej.
    if (stored && codeFromUrl && stored.code !== codeFromUrl.toUpperCase()) return null;
    return stored;
  });

  if (!identity) {
    return (
      <JoinForm
        codeFromUrl={codeFromUrl}
        onJoined={(joined) => {
          saveIdentity("guest", joined);
          setIdentity(joined);
        }}
      />
    );
  }

  return (
    <GuestConsole
      identity={identity}
      onIdentityChange={(next) => {
        saveIdentity("guest", next);
        setIdentity(next);
      }}
      onLeave={() => {
        clearIdentity("guest");
        setIdentity(null);
      }}
    />
  );
}

function JoinForm({
  codeFromUrl,
  onJoined,
}: {
  codeFromUrl: string | null;
  onJoined: (identity: Identity) => void;
}) {
  const [code, setCode] = useState(codeFromUrl?.toUpperCase() ?? "");
  const [name, setName] = useState("");
  const [sessionName, setSessionName] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // Podgląd nazwy sesji, gdy tylko kod ma pełną długość — potwierdza
  // użytkownikowi, że trafił tam, gdzie chciał, zanim poda nick.
  useEffect(() => {
    if (code.length !== 6) {
      setSessionName(null);
      return;
    }
    let alive = true;
    api
      .sessionInfo(code)
      .then((info) => alive && setSessionName(info.name))
      .catch(() => alive && setSessionName(null));
    return () => {
      alive = false;
    };
  }, [code]);

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      onJoined(await api.join(code, name.trim()));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Nie udało się dołączyć.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="card">
      <h1>Dołącz do sesji</h1>
      <p className="sub">{sessionName ?? "Wpisz kod z ekranu prowadzącego."}</p>

      <form className="stack" onSubmit={submit}>
        <label>
          Kod sesji
          <input
            className="code-input"
            value={code}
            onChange={(e) => setCode(e.target.value.toUpperCase().replace(/[^A-Z0-9]/g, ""))}
            maxLength={6}
            placeholder="ABCDEF"
            inputMode="text"
            autoCapitalize="characters"
            autoCorrect="off"
            spellCheck={false}
            required
          />
        </label>

        <label>
          Twoje imię
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            maxLength={40}
            placeholder="np. Ania"
            required
          />
        </label>

        {error && <p className="error">{error}</p>}

        <button
          className="btn btn-primary"
          type="submit"
          disabled={busy || code.length !== 6 || !name.trim()}
        >
          {busy ? "Dołączam…" : "Dołącz"}
        </button>
      </form>
    </main>
  );
}

function GuestConsole({
  identity,
  onIdentityChange,
  onLeave,
}: {
  identity: Identity;
  onIdentityChange: (identity: Identity) => void;
  onLeave: () => void;
}) {
  const { snapshot, connection, fatalError, lastError, send } = useSession(
    identity.code,
    identity.token,
  );

  if (fatalError) {
    return (
      <main className="card">
        <h1>Nie ma cię już w tej sesji</h1>
        <p className="error">{fatalError}</p>
        <button className="btn" onClick={onLeave}>
          Dołącz ponownie
        </button>
      </main>
    );
  }

  if (!snapshot) {
    return (
      <main className="card">
        <h1>Łączę…</h1>
        <ConnectionBadge state={connection} />
      </main>
    );
  }

  const { session, you, participants } = snapshot;

  return (
    <main className="card">
      <header className="head">
        <div>
          <h1>{session.name}</h1>
          <p className="sub">
            {you?.displayName}
            {you && you.role !== "GUEST" && <RoleChip role={you.role} />}
          </p>
        </div>
        <ConnectionBadge state={connection} />
      </header>

      {session.status === "LOBBY" && (
        <div className="stage">
          <div className="stage-label">Jesteś w środku</div>
          <p className="muted">Czekamy, aż prowadzący rozpocznie pierwszy etap.</p>
        </div>
      )}

      {session.status === "COLLECTING" && (
        <section className="stage-live">
          <div className="stage-label">Etap 1 — wpisz swoje pomysły</div>
          {you?.canAddIdeas ? (
            <IdeaForm snapshot={snapshot} send={send} />
          ) : (
            <p className="muted">Ten ekran prowadzi sesję i nie dodaje pomysłów.</p>
          )}

          <h2>Wszystkie pomysły ({snapshot.ideaCounts.total})</h2>
          <IdeaList snapshot={snapshot} send={send} />
        </section>
      )}

      {session.status === "SWIPING" && snapshot.swiping && (
        <Swiping
          swiping={snapshot.swiping}
          onSwipe={(ideaId, direction) => send("swipe", { ideaId, direction })}
        />
      )}

      {session.status === "SCHEDULING" && snapshot.scheduling && (
        <div className="stage">
          <div className="stage-label">Prowadzący układa terminy</div>
          <p className="muted">
            Ustalone: {snapshot.scheduling.scheduled} z {snapshot.scheduling.total}.
            Nie musisz nic robić — za chwilę wrócimy do Ciebie.
          </p>
          <div className="progress" aria-hidden="true">
            <div
              className="progress-fill"
              style={{
                width: `${
                  snapshot.scheduling.total === 0
                    ? 0
                    : (snapshot.scheduling.scheduled / snapshot.scheduling.total) * 100
                }%`,
              }}
            />
          </div>
        </div>
      )}

      {session.status === "AVAILABILITY" && snapshot.availability && (
        <AvailabilityRound
          availability={snapshot.availability}
          onAnswer={(ideaId, answer) => send("availability.answer", { ideaId, answer })}
        />
      )}

      {session.status === "ASSIGNMENT" && snapshot.assignment && (
        <AssignmentReview assignment={snapshot.assignment} send={send} />
      )}

      {session.status === "CALENDAR" && snapshot.calendar && (
        <>
          <div className="stage-label">Gotowy plan</div>
          <CalendarView calendar={snapshot.calendar} />
          {snapshot.exports && <Downloads exports={snapshot.exports} />}
        </>
      )}

      {session.status === "CLOSED" && (
        <>
          <div className="stage">
            <div className="stage-label">Sesja zakończona</div>
            <p className="muted">Plan zostaje — możesz go pobrać w każdej chwili.</p>
          </div>
          {snapshot.exports && <Downloads exports={snapshot.exports} />}
        </>
      )}

      {![
        "LOBBY",
        "COLLECTING",
        "SWIPING",
        "SCHEDULING",
        "AVAILABILITY",
        "ASSIGNMENT",
        "CALENDAR",
        "CLOSED",
      ].includes(session.status) && (
        <NotYet stage={session.statusLabel} milestone="kolejnym" />
      )}

      {lastError && <p className="error">{lastError}</p>}

      {session.status === "LOBBY" && (
        <section>
          <h2>W sesji ({participants.length})</h2>
          <PeopleList people={participants} />
        </section>
      )}

      {you?.role === "GUEST" && (
        <AdminUnlock identity={identity} onPromoted={onIdentityChange} />
      )}

      {snapshot.admin && <AdminPanel snapshot={snapshot} send={send} />}

      <div className="actions">
        <button className="btn btn-ghost" onClick={onLeave}>
          Wyjdź
        </button>
      </div>
    </main>
  );
}

/** Etap 2 na telefonie: talia kart albo ekran „gotowe". */
function Swiping({
  swiping,
  onSwipe,
}: {
  swiping: SwipingState;
  onSwipe: (ideaId: number, direction: "RIGHT" | "LEFT") => void;
}) {
  if (swiping.poolSize === 0) {
    return (
      <div className="stage">
        <div className="stage-label">Nie ma czego wybierać</div>
        <p className="muted">Wszystkie pomysły są już ustalone.</p>
      </div>
    );
  }

  if (swiping.youAreDone) {
    return (
      <div className="stage">
        <div className="stage-label">Gotowe — przeszedłeś wszystkie pomysły</div>
        <p className="muted">
          Czekamy na pozostałych i na decyzje prowadzącego. Nie musisz nic robić.
        </p>
      </div>
    );
  }

  return (
    <section className="stage-live">
      <div className="swipe-header">
        <div className="stage-label">Przesuń w prawo na tak, w lewo na nie</div>
        <div className="muted small">
          {swiping.yourDone} / {swiping.yourTotal}
        </div>
      </div>

      <SwipeDeck cards={swiping.cards} onSwipe={onSwipe} />
    </section>
  );
}

/**
 * Awans na admina — bez osobnego przepływu dołączania. Ta sama tożsamość
 * i to samo połączenie, tylko z podniesionymi uprawnieniami.
 */
function AdminUnlock({
  identity,
  onPromoted,
}: {
  identity: Identity;
  onPromoted: (identity: Identity) => void;
}) {
  const [open, setOpen] = useState(false);
  const [login, setLogin] = useState(() => lastLogin());
  const [password, setPassword] = useState("");
  const [isVoting, setIsVoting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Jeśli ta sama karta jest już zalogowana (np. zakładałeś stąd sesję),
  // nie ma po co pytać o hasło drugi raz.
  const zalogowany = loadAdmin();

  if (!open) {
    return (
      <button className="btn btn-link" onClick={() => setOpen(true)}>
        Jestem administratorem
      </button>
    );
  }

  const awansuj = async (dane?: { login: string; password: string }) => {
    setError(null);
    try {
      const awansowany = await api.promote(
        identity.code,
        identity.token,
        isVoting,
        dane,
      );
      if (dane) {
        const res = await api.adminLogin(dane.login, dane.password);
        saveAdmin(res.token, { login: res.login, isSuperadmin: res.isSuperadmin });
      }
      onPromoted(awansowany);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Nie udało się zalogować.");
    }
  };

  if (zalogowany) {
    return (
      <div className="stack admin-box">
        <p className="muted small">
          Jesteś zalogowany jako <strong>{zalogowany.me.login}</strong>.
        </p>

        <label className="checkbox">
          <input
            type="checkbox"
            checked={isVoting}
            onChange={(e) => setIsVoting(e.target.checked)}
          />
          Biorę udział w głosowaniu
        </label>

        {error && <p className="error">{error}</p>}

        <div className="row">
          <button className="btn btn-primary" onClick={() => void awansuj()}>
            Przejmij uprawnienia admina
          </button>
          <button className="btn" onClick={() => setOpen(false)}>
            Anuluj
          </button>
        </div>
      </div>
    );
  }

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    await awansuj({ login: login.trim(), password });
  };

  return (
    <form className="stack admin-box" onSubmit={submit}>
      <label>
        Login administratora
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

      <label className="checkbox">
        <input
          type="checkbox"
          checked={isVoting}
          onChange={(e) => setIsVoting(e.target.checked)}
        />
        Biorę udział w głosowaniu
      </label>
      <p className="muted small">
        Domyślnie administrator nie głosuje — zwykle to ta sama osoba,
        która prowadzi sesję. Zaznacz, jeśli prowadzi kto inny.
      </p>

      {error && <p className="error">{error}</p>}

      <div className="row">
        <button
          className="btn btn-primary"
          type="submit"
          disabled={!password || !login.trim()}
        >
          Zaloguj
        </button>
        <button className="btn" type="button" onClick={() => setOpen(false)}>
          Anuluj
        </button>
      </div>
    </form>
  );
}
