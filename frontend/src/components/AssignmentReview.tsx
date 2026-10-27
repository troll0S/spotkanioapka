import { useState } from "react";
import type { AnswerValue, AssignmentState, ReviewEvent } from "../lib/types";

/**
 * Etap 5 — przegląd wydarzeń, przydział wykonawców, zatwierdzenie.
 *
 * To tutaj odsłaniamy, kto jak odpowiedział. Do tego momentu rozkład był
 * ukryty, żeby nie przesądzać kolejnych deklaracji — teraz głosowanie jest
 * zamknięte i ta wiedza służy podjęciu decyzji.
 *
 * Uczestnicy dostają dokładnie ten sam ekran, tylko bez przycisków.
 */

const KOLEJNOSC: AnswerValue[] = ["WANT", "CAN", "DONT_WANT", "ABSOLUTELY_NOT"];

const TONY: Record<AnswerValue, string> = {
  WANT: "want",
  CAN: "can",
  DONT_WANT: "dont",
  ABSOLUTELY_NOT: "never",
};

type Send = (type: string, payload?: unknown) => void;

export function AssignmentReview({
  assignment,
  send,
}: {
  assignment: AssignmentState;
  send: Send;
}) {
  const { current, canEdit, index, total, decided } = assignment;

  if (!current) {
    return (
      <div className="stage">
        <div className="stage-label">Nie ma czego przydzielać</div>
        <p className="muted">Żadne wydarzenie nie doszło do tego etapu.</p>
      </div>
    );
  }

  return (
    <section className="stage-live">
      <div className="swipe-header">
        <div className="stage-label">
          Etap 5 — wydarzenie {index + 1} z {total}
        </div>
        <div className="muted small">{decided} / {total} rozstrzygniętych</div>
      </div>

      <div className={`review${current.decision === false ? " review-rejected" : ""}`}>
        <div className="event-head">
          {current.isSpecial && <span className="pin">📌</span>}
          <h3>{current.title}</h3>
        </div>
        {current.schedule && <div className="term">{current.schedule.label}</div>}
        {current.description && <p className="idea-desc">{current.description}</p>}

        <Answers event={current} labels={assignment.answerLabels} />

        <People assignment={assignment} event={current} send={send} />

        {current.decision !== null && (
          <div className={`verdict verdict-${current.decision ? "yes" : "no"}`}>
            {current.decision ? "✓ Zatwierdzone — wejdzie do kalendarza" : "✕ Odrzucone — nie pojawi się w kalendarzu"}
          </div>
        )}

        {canEdit && (
          <div className="decision-buttons">
            <button
              className="btn btn-danger"
              onClick={() => send("assignment.decide", { ideaId: current.ideaId, confirmed: false })}
            >
              ✕ Odrzuć
            </button>
            <button
              className="btn btn-primary"
              onClick={() => send("assignment.decide", { ideaId: current.ideaId, confirmed: true })}
            >
              ✓ Zatwierdź
            </button>
          </div>
        )}
      </div>

      {canEdit && (
        <div className="row" style={{ marginTop: "1rem" }}>
          <button
            className="btn"
            onClick={() => send("assignment.prev")}
            disabled={index === 0}
          >
            ← Poprzednie
          </button>
          <button
            className="btn"
            onClick={() => send("assignment.next")}
            disabled={assignment.isLast}
          >
            Następne →
          </button>
        </div>
      )}

      {!canEdit && (
        <p className="muted small">
          Prowadzący przydziela wykonawców. Za chwilę zobaczysz gotowy kalendarz.
        </p>
      )}
    </section>
  );
}

/** Odsłonięcie wyników: kto co zaznaczył w etapie 4. */
function Answers({
  event,
  labels,
}: {
  event: ReviewEvent;
  labels: Record<AnswerValue, string>;
}) {
  if (event.answered === 0) {
    return <p className="muted small">Nikt nie odpowiedział na to wydarzenie.</p>;
  }

  return (
    <div className="people-grid">
      {KOLEJNOSC.map((answer) => {
        const osoby = event.people[answer] ?? [];
        if (osoby.length === 0) return null;
        return (
          <div key={answer} className="people-group">
            <div className={`people-label ans-${TONY[answer]}`}>
              {labels[answer]} ({osoby.length})
            </div>
            <div className="people-names">{osoby.join(", ")}</div>
          </div>
        );
      })}
    </div>
  );
}

/** Kto to zrobi — uczestnicy sesji i osoby spoza niej. */
function People({
  assignment,
  event,
  send,
}: {
  assignment: AssignmentState;
  event: ReviewEvent;
  send: Send;
}) {
  const [name, setName] = useState("");
  const przypisani = new Set(event.assigned.map((o) => o.name.toLowerCase()));

  const dodaj = (value: string, participantId?: number) => {
    const czyste = value.trim();
    if (!czyste) return;
    send("assignment.add", {
      ideaId: event.ideaId,
      name: czyste,
      participantId: participantId ?? null,
    });
    setName("");
  };

  const wolni = assignment.roster.filter(
    (p) => !przypisani.has(p.displayName.toLowerCase()),
  );

  return (
    <div className="assign">
      <div className="assign-label">Kto to zrobi</div>

      {event.assigned.length === 0 ? (
        <p className="muted small">Nikt jeszcze nie przypisany.</p>
      ) : (
        <div className="assign-chips">
          {event.assigned.map((osoba) => (
            <span
              key={osoba.id}
              className={`assign-chip${osoba.isParticipant ? " from-session" : ""}`}
            >
              {osoba.name}
              {assignment.canEdit && (
                <button
                  className="chip-x"
                  onClick={() => send("assignment.remove", { id: osoba.id })}
                  aria-label={`Usuń ${osoba.name}`}
                >
                  ×
                </button>
              )}
            </span>
          ))}
        </div>
      )}

      {assignment.canEdit && (
        <>
          {wolni.length > 0 && (
            <div className="assign-quick">
              {wolni.map((p) => (
                <button
                  key={p.id}
                  className="btn-icon"
                  onClick={() => dodaj(p.displayName, p.id)}
                >
                  + {p.displayName}
                </button>
              ))}
            </div>
          )}

          <form
            className="assign-form"
            onSubmit={(e) => {
              e.preventDefault();
              dodaj(name);
            }}
          >
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              maxLength={40}
              placeholder="albo wpisz kogoś spoza sesji"
            />
            <button className="btn" type="submit" disabled={!name.trim()}>
              Dodaj
            </button>
          </form>
        </>
      )}
    </div>
  );
}
