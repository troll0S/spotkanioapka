import type { ExportsState } from "../lib/types";

/**
 * Pobieranie wyników — dostępne na każdym urządzeniu, także po zamknięciu sesji.
 *
 * Zwykłe linki, nie przyciski wysyłające żądanie: przeglądarka sama wie, co
 * zrobić z plikiem, a na telefonie „otwórz w kalendarzu" dla .ics działa
 * dokładnie tak, jak powinno.
 */
export function Downloads({ exports: eksport }: { exports: ExportsState }) {
  return (
    <section className="downloads">
      <h2>Zabierz ze sobą</h2>

      <div className="download-row">
        <a className="btn btn-primary" href={`${eksport.base}/calendar.ics`} download>
          📅 Dodaj do kalendarza
        </a>
        <span className="muted small">
          Plik .ics — telefon wpisze wydarzenia do swojego kalendarza.
        </span>
      </div>

      <div className="download-row">
        <a className="btn" href={`${eksport.base}/calendar.pdf`} download>
          📄 Plan (PDF)
        </a>
        <a className="btn" href={`${eksport.base}/calendar.pdf?layout=list`} download>
          Sama lista (PDF)
        </a>
        <a className="btn" href={`${eksport.base}/calendar.csv`} download>
          Arkusz (CSV)
        </a>
      </div>

      {eksport.rejectedCount > 0 && (
        <div className="download-row">
          <span className="muted small">
            Odrzucone pomysły ({eksport.rejectedCount}):
          </span>
          <a className="btn btn-ghost" href={`${eksport.base}/rejected.pdf`} download>
            PDF
          </a>
          <a className="btn btn-ghost" href={`${eksport.base}/rejected.txt`} download>
            TXT
          </a>
        </div>
      )}
    </section>
  );
}
