import type { BoardEntry, SwipingState } from "../lib/types";

/**
 * Ekran prowadzącego na etapie 2.
 *
 * Z opisu: „na ekranie hosta pojawiają się kolejne pomysły, ile przesunięć
 * w prawo, ile w lewo — i w momencie kiedy host przesunie na którąś ze stron,
 * to wtedy dopiero jest zatwierdzony i ostateczny".
 *
 * Host pracuje po kolei: na wierzchu jest pierwszy nierozstrzygnięty pomysł,
 * reszta czeka niżej. Decyzje już podjęte zostają widoczne i da się je zmienić,
 * dopóki etap trwa.
 */
export function SwipeBoard({
  swiping,
  onDecide,
  readOnly = false,
}: {
  swiping: SwipingState;
  onDecide: (ideaId: number, accepted: boolean) => void;
  readOnly?: boolean;
}) {
  const board = swiping.board ?? [];
  const oczekujace = board.filter((b) => b.decision === null);
  const rozstrzygniete = board.filter((b) => b.decision !== null);
  const biezacy = oczekujace[0];

  if (board.length === 0) {
    return (
      <div className="stage">
        <div className="stage-label">Nie ma czego wybierać</div>
        <p className="muted">
          Wszystkie pomysły są ustalone albo nikt nic nie dopisał w etapie 1.
        </p>
      </div>
    );
  }

  return (
    <section className="stage-live">
      <div className="stage-label">Etap 2 — wybór pomysłów</div>

      {biezacy ? (
        <div className="decision-card">
          <div className="decision-progress">
            {swiping.decided ?? 0} / {board.length} rozstrzygniętych
          </div>

          <h3>{biezacy.title}</h3>
          {biezacy.description && <p className="idea-desc">{biezacy.description}</p>}

          <Tally entry={biezacy} expected={swiping.votersExpected} />

          {!readOnly && (
            <div className="decision-buttons">
              <button className="btn btn-danger" onClick={() => onDecide(biezacy.id, false)}>
                ✕ Odrzuć
              </button>
              <button className="btn btn-primary" onClick={() => onDecide(biezacy.id, true)}>
                ✓ Przyjmij
              </button>
            </div>
          )}

          <p className="muted small">
            Twoja decyzja jest ostateczna — głosy uczestników są tylko podpowiedzią.
          </p>
        </div>
      ) : (
        <div className="decision-card">
          <h3>Wszystko rozstrzygnięte</h3>
          <p className="muted">
            Przyjętych: {swiping.accepted ?? 0} z {board.length}. Możesz przejść dalej.
          </p>
        </div>
      )}

      {oczekujace.length > 1 && (
        <>
          <h2>W kolejce ({oczekujace.length - 1})</h2>
          <ul className="ideas">
            {oczekujace.slice(1).map((entry) => (
              <li key={entry.id} className="idea">
                <div className="idea-head">
                  <span className="idea-title">{entry.title}</span>
                  <span className="muted small">
                    {entry.voted} / {swiping.votersExpected}
                  </span>
                </div>
              </li>
            ))}
          </ul>
        </>
      )}

      {rozstrzygniete.length > 0 && (
        <>
          <h2>Rozstrzygnięte ({rozstrzygniete.length})</h2>
          <ul className="ideas">
            {rozstrzygniete.map((entry) => (
              <li key={entry.id} className={`idea idea-${entry.decision ? "yes" : "no"}`}>
                <div className="idea-head">
                  <span className="idea-title">
                    {entry.decision ? "✓" : "✕"} {entry.title}
                  </span>
                  {!readOnly && (
                    <button
                      className="btn-icon"
                      onClick={() => onDecide(entry.id, !entry.decision)}
                    >
                      Zmień
                    </button>
                  )}
                </div>
                <div className="idea-meta">
                  {entry.right} za · {entry.left} przeciw
                </div>
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  );
}

function Tally({ entry, expected }: { entry: BoardEntry; expected: number }) {
  const brakuje = Math.max(0, expected - entry.voted);
  const szerokoscTak = entry.voted === 0 ? 0 : (entry.right / entry.voted) * 100;

  return (
    <div className="tally">
      <div className="tally-bar" aria-hidden="true">
        <div className="tally-yes" style={{ width: `${szerokoscTak}%` }} />
      </div>
      <div className="tally-numbers">
        <span className="tally-yes-text">{entry.right} za</span>
        <span className="muted">
          {brakuje > 0 ? `czekam na ${brakuje}` : "wszyscy zagłosowali"}
        </span>
        <span className="tally-no-text">{entry.left} przeciw</span>
      </div>
    </div>
  );
}
