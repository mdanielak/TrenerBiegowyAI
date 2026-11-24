# Wiedza trenerska: źródła reguł aplikacji

Streszczenia badań i praktyki trenerskiej, na których opierają się liczby w `services/training_specs.py`,
`services/week_decision.py`, `services/runner_profile.py`, `services/strategy_builder.py` i `services/plan.py`.
Dokument dla ludzi; do promptu nie trafia (aktualne prompty są w `ai/prompts/`).

## 1. Tempo wzrostu objętości tygodnia („zasada 10%”)

- **Buist i in., 2008 (Groningen).** Około 530 osób zaczynających biegać, przygotowanie do biegu na 4 mile.
  Grupa z wolną progresją (ok. 10% tygodniowo) i grupa ze standardową miała prawie tę samą liczbę urazów
  (ok. 20%). Zasada 10% nie chroniła lepiej.
- **Nielsen i in., 2012 (Aarhus).** 60 osób początkujących. Kontuzjowani mieli tygodniowe skoki objętości
  powyżej 30%, osoby zdrowe średnio około 22%. To obserwacja, a nie zwalidowany próg.
- **Wniosek dla aplikacji:** „10%” to umowna liczba, nie prawo. Aplikacja ma sufity zależne od decyzji tygodnia
  (110–115%) i twardy bezpiecznik 130% średniej z czterech tygodni.

## 2. Skok pojedynczego biegu (BJSM 2025)

- **Frandsen, Nielsen i in., 2025.** Około 5200 osób. Ryzyko przeciążenia wiązało się z tym, o ile pojedynczy bieg
  był dłuższy od najdłuższego biegu z ostatnich 30 dni. Powyżej ok. 10% ryzyko rosło, a powyżej 30% wyraźnie.
  Tygodniowe sumy i wskaźnik obciążenia ostre/przewlekłe (ACWR) słabo przewidywały urazy.
  Autor badania sugeruje, że ostrożniej byłoby nawet ok. 5%.
- **Wniosek dla aplikacji:** limit długiego biegu liczy się od najdłuższego biegu z 28 dni: +10%
  (na prośbę biegacza +15%, poza lekkimi stopniami), ale co najmniej +5 min, żeby krótkie biegi mogły rosnąć
  (`services/week_decision.py::long_run_limit`). Np. 67 → 74 min, a 30 → 35 min.

## 3. Tydzień cofnięcia i stabilizacja

- **Praktyka trenerska:** schemat „3 tygodnie w górę, 1 w dół”. W tygodniu w dół objętość spada o 10–25%.
  Częstotliwość cofnięć zależy od osoby: jednym wystarcza co 5 tygodni, inni potrzebują co 3.
- **Daniels (Daniels' Running Formula), cytowany przez trenerów:** podnosić objętość skokowo,
  a potem utrzymać ją przez 3–4 tygodnie, zanim przyjdzie kolejny wzrost.
- **Wniosek dla aplikacji:** po trzech wzrostach z rzędu jest „odpuść” (cofnięcie), a potem „utrzymaj”.
  Gdy biegacz osiąga docelową objętość fazy ze strategii, wchodzi stabilizacja (`at_peak`), co pozwala
  rozwijać jakość akcentów bez sztucznego zwiększania kilometrażu.

## 4. Taper przed startem

- **Mujika & Padilla, 2003 (Med Sci Sports Exerc).** Klasyczny przegląd podstaw fizjologicznych taperu:
  progresywna redukcja objętości przy **utrzymaniu intensywności** i spadku częstotliwości najwyżej o 20%
  przynosi średnio ok. 3% poprawy wyniku (zakres 0,5–6%).
- **Bosquet i in., 2007 (metaanaliza, Med Sci Sports Exerc).** 27 badań. Najlepiej działał taper trwający około 2 tygodni,
  w którym objętość spada o 41–60%, stopniowo. Intensywność i częstotliwość zostają bez zmian.
  Sama redukcja intensywności nie poprawiała wyniku.
- **Przegląd systematyczny 2023 (sportowcy wytrzymałościowi):** potwierdza 41–60% przy tej samej intensywności i częstotliwości,
  w taperze trwającym do 21 dni.
- **Wniosek dla aplikacji:** taper zależy od dystansu (`services/training_specs.py::DISTANCE_SPECS`):

  | Dystans | Tygodnie przed startem (część zwykłego tygodnia) |
  |---|---|
  | 5 km | tydzień startu ok. 60% (dzień startu wypada z limitu i zastępuje długi bieg) |
  | 10 km | 85%, tydzień startu 65% |
  | półmaraton | 80%, tydzień startu 55% |
  | maraton | 85%, 70%, tydzień startu 50% |

  Tydzień przed taperem jest bez wzrostu. Intensywność zostaje u przygotowanych (u początkujących nadal bez akcentów).
  Po maratonie: tydzień regeneracji (`after_race`, 60%, biegi do 45 min) i drugi lżejszy tydzień (`after_marathon_2`, 75%,
  bez akcentów, długi bieg do 90 min); po półmaratonie jeden lżejszy tydzień; po 5–10 km 2–3 spokojne dni.

## 5. Przerwa w bieganiu i utrata formy

- **Coyle i in., 1984.** U wytrenowanych osób VO₂max spadł o ok. 7% po 21 dniach bez treningu
  i o ok. 16% po 56 dniach, potem się ustabilizował.
- **Podsumowania badań o biegaczach:** po 4 tygodniach VO₂max spada o ok. 6%, a przerwa krótsza niż 2 tygodnie
  niewiele zmienia. Wydolność na długim wysiłku może spadać szybciej niż sam VO₂max.
- **Daniels:** po przerwie do 8 tygodni na odbudowę potrzeba mniej więcej tyle czasu, ile trwała przerwa.
  Po 5 dniach przerwy obciążenie się nie zmienia.
- **Wniosek dla aplikacji:**
  - przerwa 10–20 dni nie obniża poziomu (częstotliwość liczy się bez dni przerwy);
  - od 21 dni to „powrót”: ostrożny plan i poziom początkujący do odbudowy;
  - „odbuduj” pozwala wracać do znanej objętości o najwyżej 25% na tydzień;
  - punkt wyjścia strategii (średnie km z 28 dni) też pomija dni krótkiej przerwy.

## 6. Udział i limit czasowy długiego biegu

- **Daniels (Daniels' Running Formula):** długi bieg najwyżej 25–30% tygodniowej objętości oraz twardy sufit **2,5–3 godzin**
  dla pojedynczego treningu — powyżej 3 godzin kumuluje się wyczerpanie glikogenu i ekscentryczne uszkodzenia mięśni,
  a zyski tlenowe przestają rosnąć proporcjonalnie do kosztu regeneracji.
- **Pfitzinger (*Advanced Marathoning*):** wolniejsi maratończycy budują wytrzymałość większą objętością w tygodniu
  (biegi średnio-długie w środku tygodnia) i ciągłym tempem maratońskim, zamiast wydłużać weekendowy bieg powyżej 3 godzin.
- **Wyjątek przy rzadkim bieganiu:** przy 3–4 biegach tygodniowo udział 25–45% jest naturalny, ale kod pilnuje,
  żeby długi bieg nie był dłuższy niż pozostałe biegi razem (`services/plan.py::_limit_long_run_share`).
- **Wniosek dla aplikacji:** twardy sufit 180 minut w tygodniu i w strategii maratońskiej (`max_long_min_by_level`),
  125 min w strategii półmaratonu dla początkujących oraz dopuszczenie do 60 min ciągłego tempa maratońskiego u zaawansowanych.

## 7. Rozkład intensywności 80/20 (polaryzacja i piramida)

- **Seiler, 2010; Casado i in., 2022.** Badania wyczynowych i zaawansowanych biegaczy pokazują, że ok. 80% objętości
  powinno odbywać się poniżej pierwszego progu wentylacyjnego (Z1–Z2), a pozostałe ~20% w rozkładzie spolaryzowanym
  (akcent na VO₂max) lub piramidalnym (próg + szybkość). Najczęstszy błąd amatorów to „szara strefa” w Z3 na biegach łatwych.
- **Wniosek dla aplikacji:**
  - gdy połowa spokojnych biegów ma średnie tętno w Z3 lub wyżej, decyzja to „utrzymaj”;
  - przy górnych 3 bpm Z2 model przypomina o zwolnieniu tempa;
  - zaawansowani przy limicie 2 akcentów mogą łączyć dwa bodźce (np. VO₂max + próg pod 5–10 km lub próg + tempo maratońskie)
    przy zachowaniu większości spokojnych biegów.

## 8. Kinetika tętna w krótkich interwałach (HR lag)

- **Billat i in., 2001; Seiler & Sjursen, 2004.** Na początku szybkiego odcinka tętno i pobór tlenu (VO₂) reagują
  z opóźnieniem (1–2 min). W krótkich interwałach z przerwami w truchcie średnie tętno z całej aktywności
  (wraz z rozgrzewką, przerwami i schłodzeniem) jest wyraźnie niższe niż docelowa strefa odcinków pracy.
- **Wniosek dla aplikacji:** `services/workout_scoring.py` nie karze interwałów (`threshold_intervals`) za średnie tętno
  poniżej dolnej granicy strefy docelowej; kontroluje jedynie przekroczenie górnej granicy oraz dystansowe kroki na zegarku (`work_m`).

## 9. Wzór Riegla u biegaczy rekreacyjnych

- **Vickers & Vertosick, 2016 (BMC Sports Sci Med Rehabil, n = 2303).** Klasyczny wykładnik Riegla (`1,06`) dobrze
  przewiduje wyniki do półmaratonu, ale systematycznie zaniża czas maratonu u większości amatorów (średnio o ponad 10 minut).
- **Wniosek dla aplikacji:** przy przeliczaniu celu maratonu na sprawdzian 10 km strategia używa wykładnika zależnego
  od poziomu wyniku (`1,06` do 3:15, `1,08` dla 3:15–3:59, `1,10` od 4:00), a dla celów 5 km i 10 km wyznacza sprawdzian 5 km.

## 10. HRV i tętno spoczynkowe

- Zasada aplikacji: pojedyncza metryka nie nadpisuje planu. Tygodniowa średnia HRV poniżej zakresu blokuje „dołóż”,
  a razem z tętnem spoczynkowym wyższym o ≥ 3 bpm daje „odpuść” (pomiar starszy niż 3 dni jest pomijany).

## Linki

- Vickers & Vertosick, 2016 (wzór Riegla u amatorów): https://pubmed.ncbi.nlm.nih.gov/27579175/
- Mujika & Padilla, 2003 (podstawy naukowe taperu): https://pubmed.ncbi.nlm.nih.gov/12840640/
- Bosquet 2007, metaanaliza taperu: https://pubmed.ncbi.nlm.nih.gov/17762369/
- Taper u sportowców wytrzymałościowych, 2023: https://pubmed.ncbi.nlm.nih.gov/37163550/
- Seiler, 2010 (rozkład intensywności): https://pubmed.ncbi.nlm.nih.gov/20861519/
- Casado i in., 2022 (piramidalny vs spolaryzowany trening biegaczy): https://pubmed.ncbi.nlm.nih.gov/35148511/
- Billat i in., 2001 (kinetika VO₂ i krótkie interwały): https://pubmed.ncbi.nlm.nih.gov/11327029/
- Seiler & Sjursen, 2004 (odpowiedź tętna i RPE na interwały): https://pubmed.ncbi.nlm.nih.gov/15003084/
- BJSM 2025, skok pojedynczego biegu: https://blogs.bmj.com/bjsm/?p=11751
- Outside, mit zasady 10%: https://run.outsideonline.com/training/getting-started/myth-of-the-10-percent-rule/?scope=anon
- Detraining, przegląd: https://pubmed.ncbi.nlm.nih.gov/11252068/
- Daniels i powrót po przerwie (blog trenerski): https://lauranorrisrunning.com/?p=666
