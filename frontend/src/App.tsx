import { useEffect, useState } from "react";
import GuestView from "./views/guest/GuestView";
import HostView from "./views/host/HostView";
import ArchiveView from "./views/archive/ArchiveView";
import Landing from "./views/Landing";
import SpectatorView from "./views/spectator/SpectatorView";

/**
 * Router na trzy ścieżki.
 *
 * Świadomie bez biblioteki: adresów jest tyle, ile wejść do aplikacji, bo
 * o tym, co widzisz, decyduje status sesji ze snapshotu, a nie URL. Dokładanie
 * react-routera oznaczałoby zależność obsługującą problem, którego nie mamy.
 */
export default function App() {
  const [path, setPath] = useState(() => location.pathname);

  useEffect(() => {
    const onPop = () => setPath(location.pathname);
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);

  const code = new URLSearchParams(location.search).get("code");

  if (path.startsWith("/host")) return <HostView />;
  if (path.startsWith("/join")) return <GuestView codeFromUrl={code} />;
  if (path.startsWith("/spectator")) return <SpectatorView codeFromUrl={code} />;
  if (path.startsWith("/archive")) return <ArchiveView />;

  return <Landing />;
}
