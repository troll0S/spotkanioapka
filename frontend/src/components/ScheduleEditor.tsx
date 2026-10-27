import { useState } from "react";
import type { AgendaItem, ScheduleKind, SchedulingState } from "../lib/types";

/**
 * Etap 3 — ustalanie terminów. Dzieje się w całości na ekranie prowadzącego.
 *
 * Jeden widżet z przełącznikiem trybu, nie cztery osobne ekrany: rodzaj
 * terminu to decyzja podejmowana przy konkretnym wydarzeniu („wiem, że
 * w marcu" kontra „wiem, że czternastego"), więc przełączanie musi być
 * o jedno kliknięcie, a nie o powrót i wybór innej ścieżki.
 */

const TRYBY: { kind: ScheduleKind; label: string; hint: string }[] = [
  { kind: "EXACT_DATE", label: "Dokładna data", hint: "Wiadomo, którego dnia." },
  { kind: "WEEK", label: "Tydzień", hint: "Wskaż dowolny dzień — weźmiemy cały tydzień." },
  { kind: "RANGE", label: "Przedział", hint: "Od kiedy do kiedy." },
  { kind: "MONTH", label: "Miesiąc", hint: "Gdzieś w tym miesiącu." },
];

const MIESIACE = [
  "styczeń", "luty", "marzec", "kwiecień", "maj", "czerwiec",
  "lipiec", "sierpień", "wrzesień", "październik", "listopad", "grudzień",
];

type Send = (type: string, payload?: unknown) => void;

export function ScheduleEditor({
  scheduling,
  send,
  readOnly = false,
}: {
  scheduling: SchedulingState;
  send: Send;
  readOnly?: boolean;
}) {
  const [editing, setEditing] = useState<number | null>(null);
  const items = scheduling.items ?? [];

  if (items.length === 0) {
    return (
      <div className="stage">
        <div className="stage-label">Nie ma czego planować</div>
        <p className="muted">Żaden pomysł nie przeszedł do tego etapu.</p>
      </div>
    );
  }

  return (
    <section className="stage-live">
      <div className="swipe-header">
        <div className="stage-label">Etap 3 — terminy</div>
        <div className="muted small">
          {scheduling.scheduled} / {scheduling.total} ustalonych
        </div>
      </div>

      {scheduling.missing > 0 && !readOnly && (
        <p className="muted">
          Każde wydarzenie potrzebuje terminu — bez niego nie pojawi się
          w kolejnym etapie ani w kalendarzu.
        </p>
      )}

      <ul className="ideas">
        {items.map((item) => (
          <li
            key={item.ideaId}
            className={`idea${item.isSpecial ? " idea-special" : ""}${
              item.schedule ? "" : " idea-todo"
            }`}
          >
            <div className="idea-head">
              <span className="idea-title">
                {item.isSpecial && <span className="pin">📌</span>}
                {item.title}
              </span>
              {!readOnly && editing !== item.ideaId && (
                <span className="idea-tools">
                  <button className="btn-icon" onClick={() => setEditing(item.ideaId)}>
                    {item.schedule ? "Zmień" : "Ustal termin"}
                  </button>
                  {item.schedule && (
                    <button
                      className="btn-icon"
                      onClick={() => send("schedule.clear", { ideaId: item.ideaId })}
                    >
                      Wyczyść
                    </button>
                  )}
                </span>
              )}
            </div>

            {item.description && <p className="idea-desc">{item.description}</p>}

            {item.schedule ? (
              <div className={`term${item.schedule.isPast ? " term-past" : ""}`}>
                {item.schedule.label}
                {item.schedule.isPast && <span className="chip">termin minął</span>}
              </div>
            ) : (
              <div className="term term-missing">bez terminu</div>
            )}

            {editing === item.ideaId && (
              <TermForm
                item={item}
                send={send}
                onDone={() => setEditing(null)}
              />
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}

function TermForm({
  item,
  send,
  onDone,
}: {
  item: AgendaItem;
  send: Send;
  onDone: () => void;
}) {
  const dzis = new Date().toISOString().slice(0, 10);
  const [kind, setKind] = useState<ScheduleKind>(item.schedule?.kind ?? "EXACT_DATE");
  const [date, setDate] = useState(item.schedule?.dateFrom ?? dzis);
  const [dateTo, setDateTo] = useState(item.schedule?.dateTo ?? dzis);
  const [year, setYear] = useState(
    Number((item.schedule?.dateFrom ?? dzis).slice(0, 4)),
  );
  const [month, setMonth] = useState(
    Number((item.schedule?.dateFrom ?? dzis).slice(5, 7)),
  );

  const rokTeraz = new Date().getFullYear();
  const zakresBledny = kind === "RANGE" && dateTo < date;

  const submit = (event: React.FormEvent) => {
    event.preventDefault();
    if (zakresBledny) return;

    const payload: Record<string, unknown> = { ideaId: item.ideaId, kind };
    if (kind === "EXACT_DATE" || kind === "WEEK") payload.date = date;
    if (kind === "RANGE") {
      payload.dateFrom = date;
      payload.dateTo = dateTo;
    }
    if (kind === "MONTH") {
      payload.year = year;
      payload.month = month;
    }

    send("schedule.set", payload);
    onDone();
  };

  const tryb = TRYBY.find((t) => t.kind === kind)!;

  return (
    <form className="term-form" onSubmit={submit}>
      <div className="term-tabs" role="tablist">
        {TRYBY.map((t) => (
          <button
            key={t.kind}
            type="button"
            role="tab"
            aria-selected={kind === t.kind}
            className={`term-tab${kind === t.kind ? " active" : ""}`}
            onClick={() => setKind(t.kind)}
          >
            {t.label}
          </button>
        ))}
      </div>

      <p className="muted small">{tryb.hint}</p>

      {(kind === "EXACT_DATE" || kind === "WEEK") && (
        <label>
          {kind === "WEEK" ? "Dowolny dzień z tego tygodnia" : "Data"}
          <input type="date" value={date} onChange={(e) => setDate(e.target.value)} required />
        </label>
      )}

      {kind === "RANGE" && (
        <div className="term-range">
          <label>
            Od
            <input type="date" value={date} onChange={(e) => setDate(e.target.value)} required />
          </label>
          <label>
            Do
            <input
              type="date"
              value={dateTo}
              min={date}
              onChange={(e) => setDateTo(e.target.value)}
              required
            />
          </label>
        </div>
      )}

      {kind === "MONTH" && (
        <div className="term-range">
          <label>
            Miesiąc
            <select value={month} onChange={(e) => setMonth(Number(e.target.value))}>
              {MIESIACE.map((nazwa, i) => (
                <option key={nazwa} value={i + 1}>
                  {nazwa}
                </option>
              ))}
            </select>
          </label>
          <label>
            Rok
            <select value={year} onChange={(e) => setYear(Number(e.target.value))}>
              {[0, 1, 2].map((offset) => (
                <option key={offset} value={rokTeraz + offset}>
                  {rokTeraz + offset}
                </option>
              ))}
            </select>
          </label>
        </div>
      )}

      {zakresBledny && <p className="error">Koniec wypada przed początkiem.</p>}

      <div className="row">
        <button className="btn btn-primary" type="submit" disabled={zakresBledny}>
          Zapisz termin
        </button>
        <button className="btn" type="button" onClick={onDone}>
          Anuluj
        </button>
      </div>
    </form>
  );
}
