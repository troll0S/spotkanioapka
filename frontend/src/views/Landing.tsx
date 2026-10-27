import { loadAdmin } from "../lib/adminSession";

export default function Landing() {
  // Jedno logowanie obsługuje archiwum i zakładanie sesji — warto pokazać
  // od razu, że nikt nie będzie o nie pytał drugi raz.
  const admin = loadAdmin();

  return (
    <main className="card">
      <h1>Spotkaniooapka</h1>
      <p className="sub">
        {admin
          ? `Zalogowany jako ${admin.me.login}`
          : "Wspólne planowanie — laptop prowadzi, telefony dołączają."}
      </p>

      <div className="stack">
        <a className="btn btn-primary" href="/host">
          Prowadzę sesję
        </a>
        <a className="btn" href="/join">
          Dołączam do sesji
        </a>
        <a className="btn btn-ghost" href="/spectator">
          Tylko oglądam
        </a>
        <a className="btn btn-ghost" href="/archive">
          Archiwum i panel administratora
        </a>
      </div>

      <footer>
        Telefony niczego nie instalują — wystarczy przeglądarka i kod sesji
        albo zeskanowany kod QR z ekranu prowadzącego. Do archiwum wchodzisz
        bez zakładania czegokolwiek — wystarczy konto administratora.
      </footer>
    </main>
  );
}
