import type { AnswerValue, AvailabilityState, EventView } from "../lib/types";

/**
 * Etap 4 — deklaracje dostępności, prowadzone przez hosta jak w Kahoocie.
 * Jedno wydarzenie naraz, wszyscy odpowiadają na to samo.
 */

/** Kolory niosą tu znaczenie, więc nie zostają same — przy każdym jest podpis. */
const TONY: Record<AnswerValue, string> = {
  WANT: "want",
  CAN: "can",
  DONT_WANT: "dont",
  ABSOLUTELY_NOT: "never",
};

export function EventCard({ event }: { event: EventView }) {
  return (
    <div className="event">
      <div className="event-head">
        {event.isSpecial && <span className="pin">📌</span>}
        <h3>{event.title}</h3>
      </div>
      {event.schedule && <div className="term">{event.schedule.label}</div>}
      {event.description && <p className="idea-desc">{event.description}</p>}
    </div>
  );
}

/** Widok telefonu: cztery duże przyciski albo ekran oczekiwania. */
export function AvailabilityRound({
  availability,
  onAnswer,
}: {
  availability: AvailabilityState;
  onAnswer: (ideaId: number, answer: AnswerValue) => void;
}) {
  const { current, yourAnswer, canAnswer, options, index, total } = availability;

  if (!current) {
    return (
      <div className="stage">
        <div className="stage-label">Czekamy na prowadzącego</div>
      </div>
    );
  }

  if (!canAnswer) {
    return (
      <section className="stage-live">
        <div className="swipe-header">
          <div className="stage-label">Wydarzenie {index + 1} z {total}</div>
        </div>
        <EventCard event={current} />
        <p className="muted">Nie bierzesz udziału w deklarowaniu dostępności.</p>
      </section>
    );
  }

  return (
    <section className="stage-live">
      <div className="swipe-header">
        <div className="stage-label">Wydarzenie {index + 1} z {total}</div>
        {yourAnswer && <div className="muted small">odpowiedź wysłana</div>}
      </div>

      <EventCard event={current} />

      {yourAnswer ? (
        <div className="answered">
          <div className="answered-label">
            Twoja odpowiedź:{" "}
            <strong className={`ans-${TONY[yourAnswer]}`}>
              {options.find((o) => o.value === yourAnswer)?.label}
            </strong>
          </div>
          <p className="muted">
            Odpowiedzi nie da się zmienić. Czekamy na pozostałych — prowadzący
            przejdzie dalej.
          </p>
        </div>
      ) : (
        <>
          <div className="answers">
            {options.map((option) => (
              <button
                key={option.value}
                className={`btn-answer ans-${TONY[option.value]}`}
                onClick={() => onAnswer(current.ideaId, option.value)}
              >
                {option.label}
              </button>
            ))}
          </div>
          <p className="muted small">
            Wybierasz raz — odpowiedzi nie da się później zmienić.
          </p>
        </>
      )}
    </section>
  );
}

/** Ekran prowadzącego: rozkład odpowiedzi i sterowanie przebiegiem. */
export function AvailabilityBoard({
  availability,
  send,
  readOnly = false,
}: {
  availability: AvailabilityState;
  send: (type: string, payload?: unknown) => void;
  readOnly?: boolean;
}) {
  const { current, tally, answered = 0, expected, index, total, options } = availability;

  if (!current) {
    return (
      <div className="stage">
        <div className="stage-label">Nie ma wydarzeń</div>
        <p className="muted">Żaden pomysł nie doszedł do tego etapu.</p>
      </div>
    );
  }

  return (
    <section className="stage-live">
      <div className="swipe-header">
        <div className="stage-label">
          Etap 4 — wydarzenie {index + 1} z {total}
        </div>
        <div className="muted small">
          {answered} / {expected} odpowiedziało
        </div>
      </div>

      <EventCard event={current} />

      {tally && (
        <div className="tally-grid">
          {options.map((option) => (
            <div key={option.value} className={`tally-cell ans-${TONY[option.value]}`}>
              <strong>{tally[option.value] ?? 0}</strong>
              <span>{option.label}</span>
            </div>
          ))}
        </div>
      )}

      {!readOnly && (
        <div className="row" style={{ marginTop: "1.25rem" }}>
          <button
            className="btn"
            onClick={() => send("host.availability.prev")}
            disabled={index === 0}
          >
            ← Poprzednie
          </button>
          <button
            className="btn btn-primary"
            onClick={() => send("host.availability.next")}
            disabled={availability.allPresented}
          >
            Następne wydarzenie →
          </button>
        </div>
      )}

      {!readOnly && availability.allPresented && (
        <p className="muted small">
          To ostatnie wydarzenie. Gdy odpowiedzi przestaną napływać, przejdź do kalendarza.
        </p>
      )}
    </section>
  );
}
