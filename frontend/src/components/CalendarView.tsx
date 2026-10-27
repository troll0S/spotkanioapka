import type {
  AnswerValue,
  CalendarEvent,
  CalendarMonth,
  CalendarState,
} from "../lib/types";

/**
 * Etap 5 — kalendarz i lista wydarzeń.
 *
 * Komponent **nic nie liczy**. Cały układ — które wydarzenie w którym
 * tygodniu, ile kolumn zajmuje, w którym rzędzie leży — przychodzi gotowy
 * z serwera. Powód jest praktyczny: w K7 ta sama struktura nakarmi szablon
 * PDF-a, a WeasyPrint nie uruchomi Reacta. Rozkładanie wydarzeń na siatkę
 * musi istnieć w jednym miejscu, inaczej obie wersje zaczną się rozjeżdżać.
 */

const KOLEJNOSC: AnswerValue[] = ["WANT", "CAN", "DONT_WANT", "ABSOLUTELY_NOT"];

const TONY: Record<AnswerValue, string> = {
  WANT: "want",
  CAN: "can",
  DONT_WANT: "dont",
  ABSOLUTELY_NOT: "never",
};

export function CalendarView({ calendar }: { calendar: CalendarState }) {
  if (calendar.events.length === 0) {
    return (
      <div className="stage">
        <div className="stage-label">Pusty kalendarz</div>
        <p className="muted">Żadne wydarzenie nie doszło do tego etapu.</p>
      </div>
    );
  }

  return (
    <section className="stage-live">
      {calendar.conflicts.length > 0 && (
        <div className="conflicts">
          <strong>Terminy, które na siebie wchodzą</strong>
          <ul>
            {calendar.conflicts.map((k, i) => (
              <li key={i}>
                „{k.a.title}" i „{k.b.title}" — {k.label}
              </li>
            ))}
          </ul>
        </div>
      )}

      {calendar.months.map((month) => (
        <Month key={`${month.year}-${month.month}`} month={month} weekdays={calendar.weekdays} />
      ))}

      {calendar.truncated && (
        <p className="muted small">
          Pokazujemy pierwsze 12 miesięcy — dalsze terminy są na liście poniżej.
        </p>
      )}

      <h2>Wydarzenia ({calendar.events.length})</h2>
      <ul className="ideas">
        {calendar.events.map((event) => (
          <EventRow key={event.ideaId} event={event} labels={calendar.answerLabels} />
        ))}
      </ul>
    </section>
  );
}

function Month({ month, weekdays }: { month: CalendarMonth; weekdays: string[] }) {
  return (
    <div className="cal-month">
      <h3 className="cal-title">{month.label}</h3>

      <div className="cal-head">
        {weekdays.map((d) => (
          <div key={d} className="cal-weekday">
            {d}
          </div>
        ))}
      </div>

      {month.weeks.map((week, i) => (
        <div key={i} className="cal-week">
          <div className="cal-days">
            {week.days.map((day) => (
              <div
                key={day.date}
                className={`cal-day${day.inMonth ? "" : " outside"}${
                  day.isToday ? " today" : ""
                }${day.isWeekend ? " weekend" : ""}`}
              >
                {day.day}
              </div>
            ))}
          </div>

          {/* Wysokość rośnie z liczbą nakładających się pasów, żeby żaden
              nie został przykryty przez sąsiedni. */}
          <div
            className="cal-bands"
            style={{ minHeight: `${Math.max(week.lanes, 1) * 1.5}rem` }}
          >
            {week.bands.map((band) => (
              <div
                key={`${band.ideaId}-${band.startCol}`}
                className={`cal-band tone-${band.level} color-${band.colorIndex}${
                  band.continuesLeft ? " cont-left" : ""
                }${band.continuesRight ? " cont-right" : ""}`}
                style={{
                  gridColumn: `${band.startCol + 1} / span ${band.span}`,
                  gridRow: band.lane + 1,
                }}
                title={band.title}
              >
                {band.continuesLeft && <span className="cont">‹</span>}
                {band.isSpecial && "📌 "}
                {band.title}
                {band.continuesRight && <span className="cont">›</span>}
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

function EventRow({
  event,
  labels,
}: {
  event: CalendarEvent;
  labels: Record<AnswerValue, string>;
}) {
  return (
    <li className={`idea event-row tone-${event.level}${event.isSpecial ? " idea-special" : ""}`}>
      <div className="idea-head">
        <span className="idea-title">
          {event.isSpecial && <span className="pin">📌</span>}
          {event.title}
        </span>
      </div>

      {event.schedule && <div className="term">{event.schedule.label}</div>}
      {event.description && <p className="idea-desc">{event.description}</p>}

      {/* Kto to robi — najważniejsza informacja po etapie 5, więc na wierzchu. */}
      <div className="assign-result">
        <span className="assign-label">Kto to zrobi</span>
        {event.assigned.length === 0 ? (
          <span className="muted">nikt nie przypisany</span>
        ) : (
          <span className="assign-names">
            {event.assigned.map((o) => o.name).join(", ")}
          </span>
        )}
      </div>

      {/* Deklaracje z etapu 4 zostają jako tło decyzji — same liczby, bo
          imiona były pokazane w momencie przydzielania. */}
      <div className="tally-line">
        {KOLEJNOSC.map((answer) => {
          const ile = event.tally[answer] ?? 0;
          if (ile === 0) return null;
          return (
            <span key={answer} className={`ans-${TONY[answer]}`}>
              {ile} {labels[answer]}
            </span>
          );
        })}
        {event.answered === 0 && <span className="muted">nikt nie odpowiedział</span>}
      </div>

      {event.level === "blocked" && (
        <p className="warn">Sporo osób zaznaczyło „absolutnie nie".</p>
      )}
    </li>
  );
}
