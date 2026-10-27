import { useEffect, useRef, useState } from "react";
import type { SwipeCard } from "../lib/types";

/**
 * Talia kart z gestem przeciągania.
 *
 * Napisana ręcznie na Pointer Events, mimo że zwykle sięgnąłbym po bibliotekę.
 * Powód: potrzebujemy tu dokładnie czterech rzeczy — przeciągnięcia, progu,
 * odlotu i przycisków zastępczych — a gotowe biblioteki do kart dorzucają do
 * tego zależność, która musi nadążać za wersją Reacta. Przy aplikacji
 * uruchamianej lokalnie i rzadko aktualizowanej to zły interes.
 *
 * Animacja jest optymistyczna: karta odlatuje od razu po puszczeniu palca,
 * nie czekając na serwer. Przez tunel dochodzi ~150 ms opóźnienia i bez tego
 * każdy ruch wydawałby się zacięty. Prawdą i tak pozostaje snapshot — jeśli
 * serwer odrzuci głos, następny snapshot przywróci kartę na miejsce.
 */

/** Po ilu pikselach poziomego ruchu uznajemy gest za decyzję. */
const PROG_PX = 90;

/** Maksymalne przechylenie karty przy przeciąganiu. */
const MAX_OBROT_DEG = 12;

type Kierunek = "RIGHT" | "LEFT";

export function SwipeDeck({
  cards,
  onSwipe,
}: {
  cards: SwipeCard[];
  onSwipe: (ideaId: number, direction: Kierunek) => void;
}) {
  const [drag, setDrag] = useState(0);
  const [odlot, setOdlot] = useState<Kierunek | null>(null);
  const startX = useRef<number | null>(null);
  const karta = cards[0];

  // Nowa karta na wierzchu = koniec animacji odlotu poprzedniej.
  useEffect(() => {
    setDrag(0);
    setOdlot(null);
  }, [karta?.id]);

  if (!karta) return null;

  const wyslij = (direction: Kierunek) => {
    if (odlot) return;
    setOdlot(direction);
    onSwipe(karta.id, direction);
  };

  const onPointerDown = (e: React.PointerEvent) => {
    if (odlot) return;
    startX.current = e.clientX;
    (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
  };

  const onPointerMove = (e: React.PointerEvent) => {
    if (startX.current === null) return;
    setDrag(e.clientX - startX.current);
  };

  const onPointerUp = () => {
    if (startX.current === null) return;
    const przesuniecie = drag;
    startX.current = null;

    if (Math.abs(przesuniecie) >= PROG_PX) {
      wyslij(przesuniecie > 0 ? "RIGHT" : "LEFT");
    } else {
      setDrag(0);
    }
  };

  const przesuniecie = odlot ? (odlot === "RIGHT" ? 1000 : -1000) : drag;
  const obrot = Math.max(-MAX_OBROT_DEG, Math.min(MAX_OBROT_DEG, przesuniecie / 12));
  const sila = Math.min(1, Math.abs(drag) / PROG_PX);

  return (
    <div className="deck">
      {/* Karta pod spodem sygnalizuje, że to nie ostatnia — bez tego talia
          wygląda jak pojedynczy element i nie widać postępu. */}
      {cards[1] && <div className="card-behind" aria-hidden="true" />}

      <div
        className={`swipe-card${odlot ? " leci" : ""}${startX.current !== null ? " chwytana" : ""}`}
        style={{
          transform: `translateX(${przesuniecie}px) rotate(${obrot}deg)`,
        }}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerCancel={onPointerUp}
      >
        <div
          className="stamp stamp-tak"
          style={{ opacity: drag > 0 ? sila : 0 }}
          aria-hidden="true"
        >
          TAK
        </div>
        <div
          className="stamp stamp-nie"
          style={{ opacity: drag < 0 ? sila : 0 }}
          aria-hidden="true"
        >
          NIE
        </div>

        <h3>{karta.title}</h3>
        {karta.description && <p>{karta.description}</p>}
      </div>

      {/* Przyciski nie są awaryjne — na części telefonów gest bywa przechwycony
          przez przeglądarkę, a poza tym nie każdy chce przeciągać. */}
      <div className="deck-buttons">
        <button
          className="btn-round btn-nie"
          onClick={() => wyslij("LEFT")}
          disabled={!!odlot}
          aria-label="Nie"
        >
          ✕
        </button>
        <button
          className="btn-round btn-tak"
          onClick={() => wyslij("RIGHT")}
          disabled={!!odlot}
          aria-label="Tak"
        >
          ✓
        </button>
      </div>
    </div>
  );
}
