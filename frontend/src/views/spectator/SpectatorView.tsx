import { useState } from "react";
import { ConnectionBadge, NotYet, PeopleList } from "../../components/Common";
import { IdeaList } from "../../components/Ideas";
import { AssignmentReview } from "../../components/AssignmentReview";
import { AvailabilityBoard } from "../../components/Availability";
import { CalendarView } from "../../components/CalendarView";
import { Downloads } from "../../components/Downloads";
import { ScheduleEditor } from "../../components/ScheduleEditor";
import { SwipeBoard } from "../../components/SwipeBoard";
import { useSession } from "../../lib/useSession";

/**
 * Podgląd tylko do odczytu.
 *
 * Powstał dla trybu zdalnego: etapy 2, 3 i 5 dzieją się na ekranie hosta,
 * a przez internet nikt na niego nie patrzy. Przydaje się też lokalnie —
 * na telewizorze albo drugim monitorze.
 */
export default function SpectatorView({ codeFromUrl }: { codeFromUrl: string | null }) {
  const [code, setCode] = useState(codeFromUrl?.toUpperCase() ?? "");
  const [watching, setWatching] = useState(!!codeFromUrl);

  if (!watching) {
    return (
      <main className="card">
        <h1>Podgląd sesji</h1>
        <p className="sub">Widzisz przebieg, ale w nim nie uczestniczysz.</p>

        <form
          className="stack"
          onSubmit={(e) => {
            e.preventDefault();
            setWatching(true);
          }}
        >
          <label>
            Kod sesji
            <input
              className="code-input"
              value={code}
              onChange={(e) => setCode(e.target.value.toUpperCase().replace(/[^A-Z0-9]/g, ""))}
              maxLength={6}
              placeholder="ABCDEF"
              autoCapitalize="characters"
              autoCorrect="off"
              spellCheck={false}
              required
            />
          </label>
          <button className="btn btn-primary" type="submit" disabled={code.length !== 6}>
            Oglądaj
          </button>
        </form>

        <footer>
          Chcesz brać udział, a nie tylko patrzeć? Wejdź na <a href="/join">/join</a>.
        </footer>
      </main>
    );
  }

  return <SpectatorScreen code={code} onLeave={() => setWatching(false)} />;
}

function SpectatorScreen({ code, onLeave }: { code: string; onLeave: () => void }) {
  // Widz łączy się bez tokenu — nie ma tożsamości, więc nie ma czego zapamiętać.
  const { snapshot, connection, fatalError, send } = useSession(code, "", { spectator: true });

  if (fatalError) {
    return (
      <main className="card">
        <h1>Nie można oglądać</h1>
        <p className="error">{fatalError}</p>
        <button className="btn" onClick={onLeave}>
          Wpisz inny kod
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

  const { session, counts, participants } = snapshot;

  return (
    <main className="card card-wide">
      <header className="head">
        <div>
          <h1>{session.name}</h1>
          <p className="sub">
            {session.statusLabel}
            <span className="chip">podgląd</span>
          </p>
        </div>
        <ConnectionBadge state={connection} />
      </header>

      {session.status === "LOBBY" && (
        <div className="stage">
          <div className="stage-label">Poczekalnia</div>
          <p className="muted">Sesja jeszcze się nie zaczęła.</p>
        </div>
      )}

      {session.status === "COLLECTING" && (
        <section className="stage-live">
          <div className="stage-label">Etap 1 — zbieranie pomysłów</div>
          <p className="muted">Uczestnicy wpisują na telefonach.</p>
          <IdeaList snapshot={snapshot} send={send} readOnly />
        </section>
      )}

      {session.status === "SWIPING" && snapshot.swiping && (
        <SwipeBoard swiping={snapshot.swiping} onDecide={() => {}} readOnly />
      )}

      {session.status === "SCHEDULING" && snapshot.scheduling && (
        <ScheduleEditor scheduling={snapshot.scheduling} send={send} readOnly />
      )}

      {session.status === "AVAILABILITY" && snapshot.availability && (
        <AvailabilityBoard availability={snapshot.availability} send={send} readOnly />
      )}

      {session.status === "ASSIGNMENT" && snapshot.assignment && (
        <AssignmentReview assignment={snapshot.assignment} send={send} />
      )}

      {session.status === "CALENDAR" && snapshot.calendar && (
        <>
          <CalendarView calendar={snapshot.calendar} />
          {snapshot.exports && <Downloads exports={snapshot.exports} />}
        </>
      )}

      {session.status === "CLOSED" && (
        <div className="stage">
          <div className="stage-label">Sesja zakończona</div>
        </div>
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

      <section className="counters">
        <div>
          <strong>{counts.votingConnected}</strong>
          <span>/ {counts.voting} głosujących online</span>
        </div>
        {session.status !== "LOBBY" && (
          <div>
            <strong>{snapshot.ideaCounts.total}</strong>
            <span>pomysłów</span>
          </div>
        )}
      </section>

      <section>
        <h2>Uczestnicy</h2>
        <PeopleList people={participants.filter((p) => p.role !== "HOST")} />
      </section>

      <div className="actions">
        <button className="btn btn-ghost" onClick={onLeave}>
          Zakończ podgląd
        </button>
      </div>
    </main>
  );
}
