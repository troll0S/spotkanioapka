import { useState } from "react";
import type { AnswerValue, IdeaView, Snapshot } from "../lib/types";

/**
 * Panel administratora — poprawianie tego, co poszło nie tak.
 *
 * Schowany za rozwinięciem, bo to narzędzie awaryjne, a nie część przebiegu
 * sesji. Admin przez większość czasu uczestniczy jak każdy inny; tu zagląda
 * wtedy, gdy ktoś kliknął nie ten przycisk albo dołączył dwa razy.
 */

const TONY: Record<AnswerValue, string> = {
  WANT: "want",
  CAN: "can",
  DONT_WANT: "dont",
  ABSOLUTELY_NOT: "never",
};

type Send = (type: string, payload?: unknown) => void;

export function AdminPanel({ snapshot, send }: { snapshot: Snapshot; send: Send }) {
  const [open, setOpen] = useState(false);
  const admin = snapshot.admin;
  if (!admin) return null;

  if (!open) {
    return (
      <button className="btn-link" onClick={() => setOpen(true)}>
        Panel administratora
      </button>
    );
  }

  return (
    <section className="admin-panel">
      <div className="head">
        <h2>Panel administratora</h2>
        <button className="btn-icon" onClick={() => setOpen(false)}>
          Zwiń
        </button>
      </div>

      {admin.answers.length > 0 && <Answers snapshot={snapshot} send={send} />}
      <Ideas snapshot={snapshot} send={send} />
      <People snapshot={snapshot} send={send} />
    </section>
  );
}

/** Korekta zablokowanych odpowiedzi — jedyna droga do ich zmiany. */
function Answers({ snapshot, send }: { snapshot: Snapshot; send: Send }) {
  const admin = snapshot.admin!;
  const ideaId = admin.currentIdeaId;
  if (ideaId === null) return null;

  return (
    <div className="admin-block">
      <h3>Odpowiedzi — bieżące wydarzenie</h3>
      <p className="muted small">
        Uczestnik odpowiada raz i nie może się rozmyślić. Tu da się poprawić
        pomyłkę albo odpowiedzieć za kogoś, komu padł telefon.
      </p>

      <ul className="admin-rows">
        {admin.answers.map((row) => (
          <li key={row.participantId}>
            <span className="admin-name">
              {row.displayName}
              {row.wasEdited && (
                <span className="chip" title={`pierwotnie: ${row.originalAnswer}`}>
                  poprawione
                </span>
              )}
            </span>
            <span className="admin-choices">
              {admin.options.map((option) => (
                <button
                  key={option.value}
                  className={`btn-icon${row.answer === option.value ? ` active ans-${TONY[option.value]}` : ""}`}
                  onClick={() =>
                    send("admin.correctAnswer", {
                      ideaId,
                      participantId: row.participantId,
                      answer: option.value,
                    })
                  }
                >
                  {option.label}
                </button>
              ))}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

/** Moderacja wpisów — literówki i treści, które nie powinny zostać. */
function Ideas({ snapshot, send }: { snapshot: Snapshot; send: Send }) {
  const [editing, setEditing] = useState<number | null>(null);
  const canDelete = snapshot.admin!.canDeleteIdeas;

  if (snapshot.ideas.length === 0) return null;

  return (
    <div className="admin-block">
      <h3>Pomysły ({snapshot.ideas.length})</h3>
      {!canDelete && (
        <p className="muted small">
          Usuwanie działa tylko w etapie 1 — później pomysł ma już głosy
          i termin, więc służy do tego odrzucenie.
        </p>
      )}

      <ul className="admin-rows">
        {snapshot.ideas.map((idea) =>
          editing === idea.id ? (
            <li key={idea.id}>
              <EditIdea idea={idea} send={send} onDone={() => setEditing(null)} />
            </li>
          ) : (
            <li key={idea.id}>
              <span className="admin-name">
                {idea.isSpecial && "📌 "}
                {idea.title}
                <span className="muted small"> · {idea.authorName}</span>
              </span>
              <span className="idea-tools">
                <button className="btn-icon" onClick={() => setEditing(idea.id)}>
                  Popraw
                </button>
                {canDelete && (
                  <button
                    className="btn-icon danger"
                    onClick={() => send("admin.deleteIdea", { id: idea.id })}
                  >
                    Usuń
                  </button>
                )}
              </span>
            </li>
          ),
        )}
      </ul>
    </div>
  );
}

function EditIdea({
  idea,
  send,
  onDone,
}: {
  idea: IdeaView;
  send: Send;
  onDone: () => void;
}) {
  const [title, setTitle] = useState(idea.title);
  const [description, setDescription] = useState(idea.description ?? "");

  return (
    <form
      className="stack"
      onSubmit={(e) => {
        e.preventDefault();
        if (!title.trim()) return;
        send("admin.editIdea", { id: idea.id, title, description });
        onDone();
      }}
    >
      <input value={title} onChange={(e) => setTitle(e.target.value)} maxLength={120} autoFocus />
      <textarea
        value={description}
        onChange={(e) => setDescription(e.target.value)}
        maxLength={500}
        rows={2}
        placeholder="Opis (można zostawić pusty)"
      />
      <div className="row">
        <button className="btn btn-primary" type="submit" disabled={!title.trim()}>
          Zapisz
        </button>
        <button className="btn" type="button" onClick={onDone}>
          Anuluj
        </button>
      </div>
    </form>
  );
}

/** Skład sesji — głównie po to, żeby usunąć kogoś, kto dołączył dwa razy. */
function People({ snapshot, send }: { snapshot: Snapshot; send: Send }) {
  const [confirming, setConfirming] = useState<number | null>(null);
  const usuwalni = snapshot.participants.filter(
    (p) => p.role !== "HOST" && p.id !== snapshot.you?.id,
  );

  if (usuwalni.length === 0) return null;

  return (
    <div className="admin-block">
      <h3>Uczestnicy</h3>
      <p className="muted small">
        Usunięcie zabiera głosy tej osoby, ale <strong>zostawia jej pomysły</strong> —
        tracą tylko autora.
      </p>

      <ul className="admin-rows">
        {usuwalni.map((person) => (
          <li key={person.id}>
            <span className="admin-name">
              {person.displayName}
              {person.role !== "GUEST" && <span className="chip">{person.role}</span>}
            </span>
            {confirming === person.id ? (
              <span className="idea-tools">
                <button
                  className="btn-icon danger"
                  onClick={() => {
                    send("admin.removeParticipant", { id: person.id });
                    setConfirming(null);
                  }}
                >
                  Na pewno
                </button>
                <button className="btn-icon" onClick={() => setConfirming(null)}>
                  Nie
                </button>
              </span>
            ) : (
              <button className="btn-icon" onClick={() => setConfirming(person.id)}>
                Usuń z sesji
              </button>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}
