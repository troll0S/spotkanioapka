import { useEffect, useRef, useState } from "react";
import type { IdeaView, Snapshot } from "../lib/types";

type Send = (type: string, payload?: unknown) => void;

/** Lista pomysłów widoczna dla wszystkich — sedno etapu 1. */
export function IdeaList({
  snapshot,
  send,
  readOnly = false,
}: {
  snapshot: Snapshot;
  send: Send;
  readOnly?: boolean;
}) {
  const [editing, setEditing] = useState<number | null>(null);
  const yourId = snapshot.you?.id;

  if (snapshot.ideas.length === 0) {
    return <p className="muted">Jeszcze nie ma żadnych pomysłów.</p>;
  }

  return (
    <ul className="ideas">
      {snapshot.ideas.map((idea) =>
        editing === idea.id ? (
          <li key={idea.id} className="idea idea-editing">
            <IdeaForm
              snapshot={snapshot}
              send={send}
              editing={idea}
              onDone={() => setEditing(null)}
            />
          </li>
        ) : (
          <IdeaCard
            key={idea.id}
            idea={idea}
            mine={!readOnly && idea.authorId === yourId}
            onEdit={() => setEditing(idea.id)}
            onDelete={() => send("idea.delete", { id: idea.id })}
          />
        ),
      )}
    </ul>
  );
}

function IdeaCard({
  idea,
  mine,
  onEdit,
  onDelete,
}: {
  idea: IdeaView;
  mine: boolean;
  onEdit: () => void;
  onDelete: () => void;
}) {
  const [confirming, setConfirming] = useState(false);

  return (
    <li className={`idea${idea.isSpecial ? " idea-special" : ""}`}>
      <div className="idea-head">
        <span className="idea-title">
          {idea.isSpecial && <span className="pin" title="Wpis ustalony">📌</span>}
          {idea.title}
        </span>
        {mine && !confirming && (
          <span className="idea-tools">
            <button className="btn-icon" onClick={onEdit} aria-label="Edytuj">
              Zmień
            </button>
            <button className="btn-icon" onClick={() => setConfirming(true)} aria-label="Usuń">
              Usuń
            </button>
          </span>
        )}
        {mine && confirming && (
          <span className="idea-tools">
            <button className="btn-icon danger" onClick={onDelete}>
              Na pewno
            </button>
            <button className="btn-icon" onClick={() => setConfirming(false)}>
              Nie
            </button>
          </span>
        )}
      </div>

      {idea.description && <p className="idea-desc">{idea.description}</p>}

      <div className="idea-meta">
        {idea.isSpecial ? "ustalone · " : ""}
        {idea.authorName}
      </div>
    </li>
  );
}

/** Formularz dodawania i edycji — ten sam, bo pola są identyczne. */
export function IdeaForm({
  snapshot,
  send,
  editing,
  onDone,
}: {
  snapshot: Snapshot;
  send: Send;
  editing?: IdeaView;
  onDone?: () => void;
}) {
  const [title, setTitle] = useState(editing?.title ?? "");
  const [description, setDescription] = useState(editing?.description ?? "");
  const [isSpecial, setIsSpecial] = useState(editing?.isSpecial ?? false);

  const you = snapshot.you;
  const limits = snapshot.limits;
  const atLimit = !editing && (you?.ideaCount ?? 0) >= limits.maxPerParticipant;

  // Pole czyścimy dopiero, gdy **moja własna** liczba wpisów wzrośnie —
  // czyli gdy serwer potwierdził, że przyjął to, co wysłałem.
  //
  // Wcześniej był tu globalny licznik pomysłów w sesji i efekt był taki, że
  // czyjekolwiek dodanie wpisu kasowało tekst wszystkim pozostałym w trakcie
  // pisania. Wzrost, a nie zmiana: usunięcie mojego wpisu przez admina też
  // zmienia licznik, ale nie jest potwierdzeniem zapisu.
  const mojeWpisy = you?.ideaCount ?? 0;
  const poprzednieWpisy = useRef(mojeWpisy);

  useEffect(() => {
    if (editing) return;
    if (mojeWpisy > poprzednieWpisy.current) {
      setTitle("");
      setDescription("");
      setIsSpecial(false);
    }
    poprzednieWpisy.current = mojeWpisy;
  }, [mojeWpisy, editing]);

  const submit = (event: React.FormEvent) => {
    event.preventDefault();
    const cleanTitle = title.trim();
    if (!cleanTitle) return;

    if (editing) {
      send("idea.update", {
        id: editing.id,
        title: cleanTitle,
        description: description.trim() || null,
      });
      onDone?.();
    } else {
      // Pól nie czyścimy tutaj — robi to efekt wyżej, dopiero po
      // potwierdzeniu z serwera. Gdyby zapis został odrzucony (host właśnie
      // zamknął etap, przekroczony limit), tekst zostaje na ekranie.
      send("idea.create", {
        title: cleanTitle,
        description: description.trim() || null,
        isSpecial,
      });
    }
  };

  return (
    <form className="stack idea-form" onSubmit={submit}>
      <label>
        {editing ? "Tytuł" : "Twój pomysł"}
        <input
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          maxLength={limits.maxTitle}
          placeholder="np. Wyjazd w Bieszczady"
          disabled={atLimit}
          required
          autoFocus={!!editing}
        />
      </label>

      <label>
        Opis (opcjonalny)
        <textarea
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          maxLength={limits.maxDescription}
          rows={2}
          placeholder="Kilka słów, jeśli tytuł nie mówi wszystkiego"
          disabled={atLimit}
        />
      </label>

      {you?.canAddSpecial && !editing && (
        <label className="checkbox">
          <input
            type="checkbox"
            checked={isSpecial}
            onChange={(e) => setIsSpecial(e.target.checked)}
          />
          Wpis ustalony — nie do odrzucenia
        </label>
      )}

      {isSpecial && (
        <p className="muted small">
          Ten wpis pominie etap wybierania i od razu przejdzie do ustalania terminu.
        </p>
      )}

      {atLimit && (
        <p className="warn">
          Dodałeś już {limits.maxPerParticipant} pomysłów — to maksimum. Usuń któryś,
          jeśli chcesz dopisać nowy.
        </p>
      )}

      <div className="row">
        <button className="btn btn-primary" type="submit" disabled={!title.trim() || atLimit}>
          {editing ? "Zapisz" : "Dodaj pomysł"}
        </button>
        {editing && (
          <button className="btn" type="button" onClick={onDone}>
            Anuluj
          </button>
        )}
      </div>

      {!editing && you && (
        <p className="muted small">
          Twoje pomysły: {you.ideaCount} / {limits.maxPerParticipant}
        </p>
      )}
    </form>
  );
}
