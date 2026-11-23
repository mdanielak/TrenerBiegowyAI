# Audyt trenerski kodu i promptów — 23 listopada 2026

Audyt wykonał Claude (Opus 5.5) na gałęzi `feature/five-week-stages`, po commicie `373fc68`.
Punkt widzenia: trener biegowy i jakość kodu. Projekt ma działać dla osoby początkującej przed 5 km,
średnio zaawansowanej i zaawansowanej przygotowującej się do maratonu.

## Zakres

- **Przeczytane:**
  - wszystkie prompty w `ai/prompts/`,
  - twarde reguły w `ai/plan_generation.py`,
  - `services/runner_profile.py`, `services/plan.py`, `services/strategy_builder.py`, `services/strategy.py`.
- **Symulacja:** cztery syntetyczne osoby przepuszczone przez prawdziwą logikę aplikacji (profil biegacza, decyzja tygodnia, limity, moduły promptu, strategia):
  - **A:** początkująca przed 5 km, staż do pół roku, 3 × 20–25 min;
  - **B:** średnio zaawansowana przed półmaratonem, 4 biegi w tygodniu, długi bieg 80 min;
  - **C:** zaawansowany przed maratonem, 6 biegów, ok. 90 km tygodniowo, długi bieg 150 min;
  - **D:** maratończyk z nowym zegarkiem (1 tydzień danych, w kreatorze staż „ponad 2 lata”).
- **Nieaudytowane szczegółowo:** liczenie gotowości dnia (`services/readiness.py`), rekomendacja dzienna, interfejs.

Uzasadnienie progów i źródła: `docs/wiedza-trenerska.md`.

## Oceny

| Obszar | Ocena | Krótko |
|---|---|---|
| Prompty | **8/10** | Świetna struktura i bezpieczeństwo, ale kilka sprzeczności z kodem |
| Kod | **7/10** | Mocne bezpieczniki i ponad 1100 testów; słabsze: dystans celu ignorowany w taperze i strategii, duże moduły |
| Dopasowanie: początkujący 5 km | **6/10** | Tygodnie są dobre, strategia jest za ambitna |
| Dopasowanie: średnio zaawansowany | **8/10** | Najlepiej dopasowany przypadek |
| Dopasowanie: zaawansowany maraton | **6/10** | Taper za krótki, przy nowym zegarku brak limitu tygodnia |

## Mocne strony

- **Prompty:**
  - dobra hierarchia decyzji (bezpieczeństwo > samopoczucie > historia > cel),
  - bramka objawów STOP/PAUZA,
  - zakaz odrabiania treningów,
  - kotwice intensywności (oddech, odczucie, tętno),
  - dane biegacza traktowane jako dane, a nie polecenia.
- **Kod:**
  - pilnuje tych samych limitów, które obiecuje prompt (linia „LIMITY APLIKACJI”),
  - odpowiedź AI zawsze przechodzi przez deterministyczne bezpieczniki (`normalize_plan`).
- **Osoba B:** wszystko wychodzi sensownie: poziom regularny, 1 akcent, limit 253 min, długi bieg do 88 min.

## Wyniki symulacji

| Osoba | Poziom | Decyzja | Akcenty | Limit tygodnia | Długi bieg | Strategia |
|---|---|---|---|---|---|---|
| A — początkująca 5 km | początkujący | dołóż | 0 | 75 min | 30 min | Baza 9–16 km, … aż do 30 km i long 12 km |
| B — półmaraton | regularny | dołóż | 1 | 253 min | 88 min | Baza 38–42 km, potem ok. 42 km, long 20 km |
| C — maraton | zaawansowany | dołóż | 2 | 523 min | 165 min | ok. 91 km we wszystkich fazach, long 30–32 km |
| D — maraton, nowy zegarek | regularny | dołóż | 2 | **brak** | 165 min | start od **23 km** (biega ok. 90) |

## Sprzeczności i błędy

1. **Reguła 15 w `ai/plan_generation.py` nadal mówi „długi bieg najwyżej 10 minut dłuższy”.**
   Kod liczy już +10% najdłuższego biegu, co najmniej +5 min (`long_run_limit`). Ta sama reguła żyje w dwóch
   miejscach (moduły promptu i `_PLAN_RULES`), dlatego się rozjechała.
2. **Schemat wymaga `pace_target` dla każdego akcentu** (reguła 4). Prompty (`core/02`, `core/04`, moduły celu) mówią
   jednocześnie „nie wymyślasz tempa bez wyniku”. Osoba bez wyniku z zawodów zmusza model do zmyślenia tempa.
   Tempo powinno być opcjonalne albo opisane wysiłkiem i tętnem.
3. **Taper jest jeden dla wszystkich dystansów:** tydzień przed startem 80%, tydzień startu 55%, trzeci tydzień 100%.
   - Maraton potrzebuje ok. 3 tygodni zmniejszania. Moduł maratonu sam mówi „taper zwykle 2–3 tygodnie”, a kod w trzecim tygodniu trzyma 100%.
   - Osoba A przed pierwszym 5 km dostałaby w tygodniu startu ok. 36 minut biegania. Przy 5 km wystarczy lżejszy ostatni tydzień.

   Metaanaliza Bosqueta dotyczyła osób wytrenowanych, nie 5 km dla początkujących.
4. **Strategia ignoruje poziom.** Osoba A (3 × 20 min) dostaje cel 30 km tygodniowo i długi bieg 12 km (ok. 90 minut).
   Dla początkującej przed 5 km to przesada. Faza „Budowanie” obiecuje też „odcinki progowe”, a aplikacja na poziomie
   początkującym blokuje akcenty.
5. **Wzrost w strategii jest za szybki.** `_WEEKLY_GROWTH = 1.08` daje ok. +36% miesięcznie
   (np. styczeń 26 km → luty 37 km). Decyzje tygodnia („dołóż” +5–10% i cofnięcie co 4. tydzień) dają ok. +10–15%
   miesięcznie, więc strategia obiecuje tempo, którego plan tygodnia nie zrealizuje. Realniej jest ok. 3% tygodniowo.
6. **Nowy zegarek u doświadczonej osoby (D):**
   - brak limitu tygodnia (krótka historia wyłącza go całkiem), a jednocześnie 2 akcenty;
   - strategia zaczyna od 23 km, bo dzieli 1 tydzień danych przez 4 tygodnie, choć ta osoba biega ok. 90.

   Dzieje się tak, mimo że kreator zna staż „ponad 2 lata”.
7. **Strategia i kod mówią o akcentach co innego.** Strategia zawsze pisze „maksymalnie jeden główny akcent tygodniowo”.
   Osoba C ma limit 2 akcentów z preferencji. Moduł zaawansowanego to wyjaśnia (drugi lekki bodziec),
   ale strategia brzmi jak zakaz.
8. **Dwie jednostki objętości.** Strategia mówi w kilometrach, limity tygodnia w minutach. Model dostaje oba naraz,
   bez przeliczenia, co sprzyja sprzecznym planom.

## Drobne sprawy

- `services/runner_profile.py` ma ok. 760 linii i łączy poziom, decyzję tygodnia, limity, teksty do promptu i HRV.
  Warto go podzielić, np. decyzja tygodnia osobno.
- Strategia jest zapisywana jako Markdown i z powrotem czytana wyrażeniami regularnymi (`services/strategy.py`).
  Zmiana formatu tabeli psuje parser, co wyszło w testach przy poprawce `373fc68`.
- Progi trenerskie są opisane w `docs/wiedza-trenerska.md`, ale nie mają odnośników w kodzie przy każdej stałej.

## Rekomendowana kolejność poprawek

1. Punkty 1 i 2: sprzeczności w regułach i tempo w schemacie (małe, pewne).
2. Taper zależny od dystansu (5 km: tylko tydzień startu ok. 75%; maraton: 3 tygodnie ok. 85/70/50%).
3. Strategia zależna od poziomu i realistycznego tempa wzrostu (ok. 3% tygodniowo, szczyt objętości i długiego biegu niższy dla początkujących).
4. Nowy zegarek przy znanym stażu: ostrożny limit tygodnia z dostępnych danych i strategia liczona z tygodni z danymi.
5. Jednostki: przeliczać km strategii na minuty przy tempie biegacza albo pokazać oba.

---

## Ponowna ocena po poprawkach (ten sam dzień, commity `f5626c2`–`c432f63`)

### Co poprawiono

| Punkt audytu | Poprawka |
|---|---|
| 1. Reguła 15 („+10 minut”) | Reguły planu odsyłają do jednej linii LIMITY APLIKACJI (`long_run_limit`: +10%, min. +5 min, sufit 3 h). |
| 2. Wymuszone tempo | Akcent bez tempa z danych celuje w strefę tętna (Z3–Z5) na zegarku i w krokach; schemat nie wymusza zmyślania tempa. |
| 3. Jeden taper | Taper zależny od dystansu: 5 km 75%; 10 km 85/65%; półmaraton 80/55%; maraton 85/70/50%; po maratonie tydzień regeneracji i tydzień lżejszy. |
| 4. Strategia ignoruje poziom | Szczyt objętości i długiego biegu zależny od dystansu i poziomu; opisy faz zgodne z limitem akcentów. |
| 5. Za szybki wzrost | Strategia rośnie ok. 3% tygodniowo, z krokami miesięcznymi. |
| 6. Nowy zegarek | Limit tygodnia z tygodni w danych, bez dokładania; strategia liczy średnią z dni z danymi. |
| 7. Akcenty w strategii | Początkujący bez akcentów, regularny jeden (drugi przy 4+ biegach w tygodniu, tak samo w kodzie i prompcie), zaawansowany główny akcent i ewentualnie lekki drugi. |
| 8. Jednostki | Kilometry strategii mają obok minuty przy tempie biegacza. |

Dodatkowo:
- decyzja tygodnia wydzielona do `services/week_decision.py` (czysta, testowana `decide_week`);
- przykłady w prompcie nie podają wieku ani BMI jako powodów; nowe przykłady: akcent bez tempa i tydzień cofnięcia;
- test pilnuje, żeby przykłady w prompcie przechodziły przez reguły aplikacji;
- prompty celów mówią o taperze to samo co kod;
- trening siłowy jest zalecany, a nie luźną opcją.

### Symulacja po poprawkach

| Osoba | Poziom | Decyzja | Akcenty | Limit tygodnia | Długi bieg | Strategia |
|---|---|---|---|---|---|---|
| A — początkująca 5 km | początkujący | dołóż | 0 | 75 min | 30 min | 9 → 16 km, long do 6 km, bez akcentów |
| B — półmaraton | regularny | dołóż | 1 | 253 min | 88 min | 38 → 42 km, long 14 → 20 km |
| C — maraton | zaawansowany | dołóż | 2 | 523 min | 165 min (sufit 180) | ok. 91 km, long do 34 km, drugi bodziec lekki |
| D — maraton, nowy zegarek | regularny | utrzymaj | 1 | 446 min | 165 min | ok. 80 km (z dni z danymi) |

### Oceny po poprawkach

| Obszar | Przed | Po |
|---|---|---|
| Prompty | 8/10 | **9/10** |
| Kod | 7/10 | **8/10** |
| Dopasowanie: początkujący 5 km | 6/10 | **9/10** |
| Dopasowanie: średnio zaawansowany | 8/10 | **9/10** |
| Dopasowanie: zaawansowany maraton | 6/10 | **9/10** |

### Co zostało (świadomie)

- Strategia jest nadal zapisywana jako Markdown i czytana wyrażeniami regularnymi; chroni ją test zapisu i odczytu,
  ale zmiana formatu tabeli wymaga zmiany parsera.
- Liczenie gotowości dnia i rekomendacja dzienna nie były audytowane szczegółowo.
- Oceny opierają się na symulacji reguł aplikacji, nie na planach wygenerowanych przez prawdziwy model AI —
  warto ułożyć po jednym planie dla każdej grupy (np. w `testowanie.sh` z prawdziwym kluczem) i przejrzeć je okiem trenera.

---

## Weryfikacja na prawdziwym modelu AI

Żeby oceny nie opierały się tylko na symulacji reguł, ułożyłem prawdziwym modelem (dostawca i model z ustawień aplikacji)
plan tygodnia dla czterech zmyślonych osób. Bez danych użytkownika: profil, dostępność, dziennik, wiadomość
tygodnia i strategia były syntetyczne; prywatne zasady trenera wyłączone. Pełne przejście przez aplikację:
`build_plan_context` → prompt systemowy ze strategią osoby → model → `normalize_plan`.

### Kryteria oceny planu (po 1 punkcie)

1. Mieści się w limitach aplikacji (tydzień, długi bieg, liczba treningów).
2. Liczba akcentów pasuje do poziomu.
3. Mocne dni rozdzielone, po długim biegu i akcencie dzień lżejszy.
4. Intensywność opisana oddechem i odczuciem oraz strefą; bez zmyślonego tempa.
5. Długi bieg rośnie ostrożnie i ma rozsądny udział w tygodniu.
6. Treść pasuje do celu i fazy (5 km początkujący, półmaraton w bazie, maraton w bazie i w taperze).
7. Jest wariant awaryjny na zmęczenie albo brak czasu.
8. Prosty język bez żargonu i angielskich kodów.
9. `summary` wyjaśnia decyzję tygodnia.
10. Zegarek dostanie kompletny trening (akcent ma cel: tempo albo strefę).

### Wyniki

| Osoba | Decyzja aplikacji | Plan modelu | Punkty |
|---|---|---|---|
| A — początkująca 5 km | utrzymaj, limit 72 min, 0 akcentów | 20 + 20 + 25 min w Z2, rozgrzewka, „swobodna rozmowa”, wariant 15 min; razem 65 min | **9/10** — jedna literówka modelu („z tępa”) |
| B — półmaraton | utrzymaj, limit 242 min, 1 akcent | łatwy 45, odcinki 4 × 4 min w Z4 bez tempa, łatwy 45, długi 80; razem 220 min | **10/10** |
| C — maraton, baza | utrzymaj, limit 501 min, do 2 akcentów | regeneracja po długim, odcinki 3 × 10 min Z4, łatwe z przebieżkami, sprawność, długi 150 min; razem 435 min | **10/10** |
| C2 — maraton, taper (start za 13 dni) | odpuść/taper 70%, limit 318 min | dzień wolny po ostatnim długim, 4 × 6 min w tempie maratońskim (Z3), regeneracja, bez długiego biegu; razem 260 min (57%) | **9/10** — zszedł niżej niż 70%, co nadal mieści się w 41–60% z badań, ale prompt mógłby wyraźniej podać cel tygodnia |

Przy pierwszym uruchomieniu odpowiedź modelu dla tapera raz została ucięta limitem długości. Aplikacja w takim przypadku
pyta drugi raz (`generate_week_plan`), drugie uruchomienie przeszło za pierwszym razem.

Przy okazji poprawiono: cel w kontekście planu był czytany z profilu na dysku, a nie z profilu przekazanego do
`build_plan_context`. W aplikacji to ten sam plik, ale dwa źródła profilu to ryzyko rozjazdu, więc cel bierze się
teraz z jednego miejsca.

### Ocena gotowości dnia (dotąd nieaudytowana)

- Tętno spoczynkowe, sen i stres są oceniane wobec normy tej osoby z 28 dni, HRV wobec zakresu z zegarka.
  Brak pomiaru to „brak danych”, a nie zła ocena. Tak samo dobrze dla początkującej i dla maratończyka.
- Wczorajszy trening liczy się przez efekt treningowy Garmina (względny dla osoby) i stałe progi czasu: 75 i 90 minut.
  **Drobna uwaga:** u maratończyka 75-minutowy spokojny bieg obniża gotowość następnego dnia o punkt.
  Do rozważenia: progi czasu względem najdłuższego niedawnego biegu.

### Ocena końcowa

| Obszar | Ocena | Na czym oparta |
|---|---|---|
| Prompty | **9/10** | Brak sprzeczności z kodem w przeglądzie; prawdziwy model trzyma się limitów, akcentów bez tempa i tapera |
| Kod | **8/10** | 1129 testów, czysty pyflakes, decyzja tygodnia wydzielona; minusy: strategia przez Markdown, stałe progi czasu w gotowości |
| Początkujący, 5 km | **9/10** | Plan modelu 9/10 według kryteriów |
| Średnio zaawansowany | **9/10** | Plan modelu 10/10 według kryteriów |
| Zaawansowany, maraton | **9/10** | Plany modelu 10/10 (baza) i 9/10 (taper) |

Kryteria i ich wagi to propozycja autora audytu, nie przyjęty wcześniej standard projektu.
