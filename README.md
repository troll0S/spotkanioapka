# Spotkaniooapka

Aplikacja do wspólnego planowania. Laptop jest serwerem, telefony łączą się
przeglądarką — **nic nie instalują**.

Cała sesja działa od początku do końca, razem z eksportem, trybem zdalnym,
panelem admina i archiwum.

Przebieg sesji, sześć etapów:

1. **Pomysły** — każdy wpisuje na telefonie, wszyscy widzą listę rosnącą na żywo
2. **Wybór** — swipe w prawo/lewo; prowadzący rozstrzyga ostatecznie
3. **Terminy** — prowadzący ustala datę, tydzień, przedział albo miesiąc
4. **Dostępność** — runda pytań: chcę / mogę / nie chcę / absolutnie nie
5. **Kto to zrobi** — odsłonięcie odpowiedzi, przydział wykonawców,
   zatwierdzenie albo odrzucenie wydarzenia
6. **Kalendarz** — gotowy plan z przypisanymi osobami

Na koniec każdy pobiera ze swojego telefonu:

| Plik | Co daje |
|---|---|
| **`.ics`** | Jedno kliknięcie i wydarzenia są w kalendarzu telefonu |
| **`plan.pdf`** | Kalendarz + lista wydarzeń z osobami, do wydruku |
| `plan.pdf?layout=list` | Sama lista, bez siatki |
| `plan.csv` | Do arkusza |
| **`odrzucone.pdf` / `.txt`** | Co nie weszło do planu i dlaczego |

## Konta administratorów

Zamiast jednego wspólnego hasła — konta z loginem. Zwykły **admin** prowadzi
spotkania i widzi archiwum; **superadmin** dodatkowo zarządza kontami.

Pierwsze konto powstaje automatycznie z `.env` (`SUPERADMIN_LOGIN` +
`ADMIN_PASSWORD`), bo inaczej nie dałoby się zalogować, żeby założyć pierwsze
konto. Potem hasła żyją w bazie i zmienia się je w panelu — zmienne z `.env`
przestają mieć znaczenie.

### Wymagania wobec haseł

Co najmniej **8 znaków**, w tym **wielka litera, mała litera, cyfra i znak
specjalny**. Spacja nie liczy się jako znak specjalny. Dotyczy wszystkich
haseł, także konta startowego z `.env` — gdyby superadmin omijał politykę,
cała polityka byłaby dekoracją.

```powershell
.\start.ps1 -CheckPassword "Moje-Haslo1!"   # czy przejdzie?
.\start.ps1 -NewPassword                    # wygeneruj mocne
```

### Konta a sieć

Konta siedzą w bazie (`data/spotkania.db`), więc są **te same w trybie
lokalnym i zdalnym** — `--profile remote` uruchamia tę samą aplikację, tylko
dokłada tunel. Przeniesienie na inny komputer wymaga skopiowania katalogu
`data/`; samo `.env` nie wystarczy.

Zmiana hasła albo wyłączenie konta **wylogowuje je natychmiast**. Ostatniego
superadmina nie da się wyłączyć ani usunąć.

## Jedno logowanie na całą aplikację

Logujesz się **raz** i zostajesz zalogowany we wszystkich miejscach, które
tego wymagają:

- **archiwum** — lista sesji, podgląd, pobieranie, usuwanie;
- **zakładanie sesji** — podajesz już tylko nazwę;
- **przejęcie uprawnień admina** w trwającej sesji — jedno kliknięcie.

Z archiwum przejdziesz prosto do nowej sesji przyciskiem **„+ Nowa sesja"**
i odwrotnie — bez wylogowywania.

Zalogowanie znika razem z kartą przeglądarki (`sessionStorage`), bo to dostęp
do wszystkiego, co aplikacja pamięta. Login jest podpowiadany przy następnym
wejściu, hasło nigdy.

## Panel admina i archiwum

**Bez zakładania ani dołączania do żadnej sesji** — wejdź na
<http://localhost:8000/archive> (albo kliknij „Archiwum i panel administratora"
na stronie głównej) i zaloguj się swoim kontem. Zobaczysz listę wszystkich
sesji, podgląd ich zawartości, pobieranie planu i usuwanie. Superadmin ma tam
jeszcze zakładkę **Konta**.

**W trakcie sesji** — dołącz jak każdy, a potem kliknij „Jestem
administratorem" i zaloguj się kontem. Pod ekranem pojawi się panel: poprawisz
w nim czyjąś odpowiedź (to jedyna droga — uczestnik odpowiada raz), odpowiesz
za kogoś, komu padł telefon, poprawisz literówkę w cudzym wpisie i usuniesz
osobę, która dołączyła dwa razy. **Usunięcie uczestnika zostawia jego
pomysły** — tracą tylko autora.

## Jak to uruchomić na spotkaniu

1. Na laptopie: `docker compose up` → otwórz <http://localhost:8000/host>
2. Podaj nazwę sesji i hasło z `.env` → dostajesz kod i QR
3. Telefony skanują QR albo wchodzą na adres z ekranu i wpisują kod + imię
4. Admin (np. Ty z telefonu) dołącza jak każdy i klika „Jestem administratorem"
5. Ekran laptopa prowadzi proces przyciskiem „Dalej"

Ekran hosta **nie bierze udziału w głosowaniu** — liczniki liczą tylko gości.

---

## Szybki start

```powershell
copy .env.example .env
.\start.ps1 -Rebuild
```

W trybie zdalnym skrypt sprawdza hasło, **ale tylko wtedy, gdy ma ono jeszcze
znaczenie** — czyli gdy w bazie nie ma żadnego konta i `ADMIN_PASSWORD` z `.env`
dopiero je założy. Wtedy wymaga pełnej polityki haseł i co najmniej 12 znaków,
bo adres tunelu jest publiczny. Gdy konta już istnieją, skrypt tylko przypomina,
że chronią hasła kont. Świadome pominięcie: `.\start.ps1 -Remote -Force`.

Skrypt sam wykrywa adres laptopa w sieci i wypisuje go na ekranie. **Otwórz
ekran hosta pod tym adresem, nie przez `localhost`** — wtedy kod QR na pewno
będzie wskazywał to, co powinien.

Kolejne uruchomienia: `.\start.ps1`

## Zmieniłeś sieć Wi-Fi?

Nic nie edytujesz — wystarczy uruchomić apkę ponownie:

```powershell
docker compose down
.\start.ps1
```

Adres laptopa zmienia się razem z siecią, dlatego **nie jest nigdzie zapisany
na stałe**. `start.ps1` ustala go przy każdym starcie, a jeśli uruchomisz
aplikację zwykłym `docker compose up`, adres zostanie wzięty z tego, jak sam
wszedłeś do aplikacji w przeglądarce.

Gdyby telefony i tak nie mogły się połączyć, ekran hosta ma pod kodem QR link
**„Telefony nie mogą się połączyć? Podaj inny adres"** — możesz wpisać adres
ręcznie bez restartu. Tego samego pola użyj, żeby wkleić adres tunelu w trybie
zdalnym.

⚠️ Nie wpisuj adresu IP do `PUBLIC_URL` w `.env`. To pole ma pierwszeństwo nad
wszystkim innym, więc po zmianie sieci stałoby się martwym wpisem — a objaw jest
podstępny: telefon ładuje stronę w nieskończoność, bo próbuje dobić się do
adresu, którego już nie ma. `PUBLIC_URL` zostaw puste albo wpisz tam wyłącznie
adres, który się nie zmienia (własna domena w tunelu).

---

## Tryb deweloperski

```bash
docker compose -f docker-compose.dev.yml up --build
```

Wchodzisz na **port 5173**, nie 8000 — to Vite, który serwuje frontend
z hot-reloadem i przekazuje `/api` oraz `/ws` do backendu na 8000.

| | zmiana w `.tsx` | zmiana w `.py` |
|---|---|---|
| efekt | natychmiast w przeglądarce | uvicorn sam się przeładowuje |
| przebudowa obrazu | nie trzeba | nie trzeba |

Obrazu nie przebudowujesz dopóki nie ruszasz `requirements.txt` ani `package.json`.

### Testy

```bash
docker compose -f docker-compose.dev.yml run --rm --no-deps backend pytest -q
docker compose -f docker-compose.dev.yml run --rm --no-deps --entrypoint sh frontend -c "npm install && npx tsc --noEmit"
```

## Kopie zapasowe

```powershell
.\backup.ps1                                    # kopia do backups\
.\backup.ps1 -List                              # co już jest
.\backup.ps1 -Restore spotkania-2026-10-04.db   # przywrócenie
```

**Nie kopiuj `data\spotkania.db` ręcznie.** Baza chodzi w trybie WAL, więc
część zapisów siedzi w osobnym pliku `-wal`; skopiowany na piechotę plik bywa
starszy, niż się wydaje, albo uszkodzony, jeśli trafi w środek zapisu. Skrypt
prosi SQLite o spójną kopię (`VACUUM INTO`) i działa przy uruchomionej
aplikacji.

Przywracanie zatrzymuje aplikację, odkłada obecny stan jako
`przed-przywroceniem-*.db` i dopiero wtedy nadpisuje bazę. Domyślnie trzymamy
20 ostatnich kopii (`-Keep`).

## Skrót na ekranie głównym telefonu

Aplikacja ma manifest PWA, więc z przeglądarki na telefonie można ją dodać do
ekranu głównego („Dodaj do ekranu głównego" w Chrome, „Do ekranu początkowego"
w Safari). Otwiera się wtedy bez paska adresu i ma własną ikonę; długie
przytrzymanie daje skróty do **Dołącz** i **Prowadzę**.

Ikony generuje `scripts/gen_ikony.py` — czysty `zlib` + `struct`, bez żadnej
biblioteki graficznej, więc nie dokładają się do zależności projektu.

---

## Firewall Windows — konieczne raz

Docker wystawi port, ale Windows domyślnie odrzuci połączenia z sieci lokalnej.
To najczęstsza przyczyna „nie działa mi z telefonu".

**PowerShell jako administrator**, jednorazowo:

```powershell
New-NetFirewallRule -DisplayName "Spotkaniooapka (8000)" `
  -Direction Inbound -Protocol TCP -LocalPort 8000 `
  -Action Allow -Profile Private

New-NetFirewallRule -DisplayName "Spotkaniooapka dev (5173)" `
  -Direction Inbound -Protocol TCP -LocalPort 5173 `
  -Action Allow -Profile Private
```

`-Profile Private` celowo — reguła działa w sieci domowej, a nie w publicznej
kawiarnianej. Upewnij się, że Windows uznaje Twoje Wi-Fi za sieć **prywatną**:

```powershell
Get-NetConnectionProfile | Select-Object Name, NetworkCategory
```

Usunięcie reguł, gdyby kiedyś były zbędne:

```powershell
Remove-NetFirewallRule -DisplayName "Spotkaniooapka (8000)"
Remove-NetFirewallRule -DisplayName "Spotkaniooapka dev (5173)"
```

---

## Tryb zdalny — każdy na swoim internecie

Laptop na Wi-Fi, telefony w sieci komórkowej, ktoś z drugiego końca kraju —
bez znaczenia.

```powershell
.\start.ps1 -Remote
```

Skrypt poczeka na tunel i wypisze publiczny adres HTTPS. **Otwórz ekran hosta
właśnie pod tym adresem** — wtedy kod QR wskaże tunel, a nie sieć lokalną.

Jak to działa: tunel Cloudflare tworzy połączenie **wychodzące** z laptopa
i publikuje je pod adresem HTTPS. Nie otwierasz żadnych portów na routerze,
nie walczysz z operatorem, a HTTPS dostajesz za darmo.

Aplikacja jest wtedy osiągalna pod dwoma adresami naraz — lokalnym i tunelowym —
i każdy dostaje ten, który u niego działa, bo adres bierze się z żądania.

### Podgląd dla uczestników

W jednym pomieszczeniu wszyscy patrzą na ekran hosta. Zdalnie nikt go nie widzi,
a część etapów dzieje się właśnie tam. Dlatego jest `/spectator` — ten sam obraz,
tylko do odczytu, bez tokenu i bez możliwości kliknięcia czegokolwiek. Link
pokazuje się na ekranie hosta pod kodem QR. Przydaje się też lokalnie, na
telewizorze albo drugim monitorze.

### Zanim udostępnisz adres

Adres tunelu jest **publiczny** — trafi tam każdy, kto go dostanie. Chroni cię
wtedy tylko hasło, więc:

- `ADMIN_PASSWORD` w `.env` musi być długie i losowe (jest takie domyślnie),
- zgadywanie hasła jest ograniczane: 10 nieudanych prób na 5 minut z adresu,
  plus stała zwłoka po każdej pomyłce,
- zamknięta sesja przestaje być widoczna dla anonimowego podglądu.

Adres znika po `docker compose down` i przy każdym starcie jest inny. Jeśli
potrzebujesz stałego — użyj nazwanego tunelu z własną domeną i dopiero wtedy
wpisz go do `PUBLIC_URL`.

---

## Gdy coś nie działa

| Objaw | Przyczyna | Rozwiązanie |
|---|---|---|
| **Telefon ładuje bez końca, laptop pisze „nieosiągalny"** | Adres wskazuje na sieć, w której laptopa już nie ma (zmiana Wi-Fi, nowy przydział DHCP) | `docker compose down` i `.\start.ps1`; upewnij się, że `PUBLIC_URL` w `.env` jest **puste** |
| **Strona ładuje się i nic się nie dzieje, konsola milczy** | Przeglądarka trzyma stary `index.html` wskazujący na plik JS, którego już nie ma | Twarde odświeżenie (`Ctrl+Shift+R`). Od K2 serwer wysyła `no-cache`, więc to jednorazowe |
| Telefon: „nie można połączyć" | Firewall Windows | Reguły wyżej; sprawdź, czy sieć jest **prywatna** |
| To samo, reguły są | Izolacja klientów na routerze (sieć gościnna, hotel) | Hotspot z telefonu albo tryb zdalny |
| QR prowadzi w złe miejsce | Ekran hosta otwarty przez `localhost` | Otwórz go pod adresem IP; albo użyj „Podaj inny adres" pod kodem QR |
| Urywa się w połowie sesji | Laptop zasnął | Wyłącz uśpienie na czas sesji |
| `port is already allocated` | Port 8000 zajęty | `docker compose down` albo zmień mapowanie portu |

Diagnostyka serwera: <http://localhost:8000/api/health> ·
Dokumentacja API: <http://localhost:8000/api/docs>

---

## Struktura

```
backend/app/
  state_machine.py   przejścia między etapami — jedyne miejsce z sekwencją
  ws_manager.py      rejestr połączeń WebSocket i broadcast
  snapshots.py       stan sesji filtrowany per rola
  participants.py    voting_participants() — jedyny mianownik liczników
  routers/           REST (sesja, dołączanie, QR) i WebSocket
backend/alembic/     migracje, odpalane automatycznie przy starcie
backend/tests/       pytest
frontend/src/
  lib/useSession.ts  WebSocket, reconnect, ping — serce warstwy klienta
  views/host/        ekran prowadzącego
  views/guest/       ekran telefonu + logowanie admina
data/                baza SQLite, poza repozytorium
```

Trzy pliki niosą ciężar całego systemu: `state_machine.py`, `ws_manager.py`
i `useSession.ts`. Reszta to w dużej mierze formularze.

---

## Licencja

[MIT](LICENSE)
