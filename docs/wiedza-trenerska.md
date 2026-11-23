# Wiedza trenerska: źródła reguł aplikacji

Streszczenia badań i praktyki trenerskiej, na których opierają się liczby w `services/runner_profile.py`
i `services/plan.py`. Dokument dla ludzi; do promptu nie trafia (aktualne prompty są w `ai/prompts/`).

Uwaga o pewności (stan na listopad 2026): większość pozycji sprawdzono przez artykuły i streszczenia (PubMed, blogi trenerskie),
nie w pełnych tekstach książek. Przy zmianie progów warto sięgnąć do oryginału.

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
  (`services/runner_profile.py::long_run_limit`). Np. 67 → 74 min, a 30 → 35 min.

## 3. Tydzień cofnięcia i stabilizacja

- **Praktyka trenerska:** schemat „3 tygodnie w górę, 1 w dół”. W tygodniu w dół objętość spada o 10–25%.
  Częstotliwość cofnięć zależy od osoby: jednym wystarcza co 5 tygodni, inni potrzebują co 3.
- **Daniels (Daniels' Running Formula), cytowany przez trenerów:** podnosić objętość skokowo,
  a potem utrzymać ją przez 3–4 tygodnie, zanim przyjdzie kolejny wzrost.
- **Wniosek dla aplikacji:** po trzech wzrostach z rzędu jest „odpuść” (cofnięcie), a potem „utrzymaj”.
  Tydzień cofnięcia to planowa przerwa w budowaniu, nie zmęczenie: bez modułu regeneracji, jeden lżejszy akcent może zostać.
  Dzięki temu „dołóż” nie trwa w nieskończoność.

## 4. Taper przed startem

- **Bosquet i in., 2007 (metaanaliza, Med Sci Sports Exerc).** 27 badań. Najlepiej działał taper trwający około 2 tygodni,
  w którym objętość spada o 41–60%, stopniowo. Intensywność i częstotliwość zostają bez zmian.
  Sama redukcja intensywności nie poprawiała wyniku.
- **Przegląd systematyczny 2023 (sportowcy wytrzymałościowi):** potwierdza 41–60% przy tej samej intensywności i częstotliwości,
  w taperze trwającym do 21 dni.
- **Wniosek dla aplikacji:** tydzień przed startem około 80% zwykłego tygodnia, tydzień startu około 55%.
  Krótkie szybkie fragmenty zostają, a moduł regeneracji (który zakazuje akcentów) w taperze się nie włącza.

## 5. Przerwa w bieganiu i utrata formy

- **Coyle i in., 1984.** U wytrenowanych osób VO2max spadł o ok. 7% po 21 dniach bez treningu
  i o ok. 16% po 56 dniach, potem się ustabilizował.
- **Podsumowania badań o biegaczach:** po 4 tygodniach VO2max spada o ok. 6%, a przerwa krótsza niż 2 tygodnie
  niewiele zmienia. Wydolność na długim wysiłku może spadać szybciej niż sam VO2max.
- **Daniels (według trenerów):** po przerwie do 8 tygodni na odbudowę potrzeba mniej więcej tyle czasu, ile trwała przerwa.
  Po 5 dniach przerwy obciążenie się nie zmienia.
- **Wniosek dla aplikacji:**
  - przerwa 10–20 dni nie obniża poziomu (częstotliwość liczy się bez dni przerwy);
  - od 21 dni to „powrót”: ostrożny plan i poziom początkujący do odbudowy;
  - „odbuduj” pozwala wracać do znanej objętości o najwyżej 25% na tydzień;
  - punkt wyjścia strategii (średnie km z 28 dni) też pomija dni krótkiej przerwy.

## 6. Udział długiego biegu w tygodniu

- **Daniels (cytowany przez trenerów):** długi bieg najwyżej 25–30% tygodniowej objętości. Inne źródła podają 20–30%.
- **Wyjątek przy rzadkim bieganiu:** przy 3–4 biegach tygodniowo reguła się nie sprawdza. Jako punkt wyjścia podaje się
  25–40%, a u początkujących długi bieg bywa jeszcze większą częścią tygodnia.
- **Górna granica:** długi bieg regularnie większy niż połowa tygodnia uznaje się za zbyt duży.
- **Wniosek dla aplikacji:**
  - prompt podaje udział zależny od liczby biegów (5+: 25–30%, 4: ok. 35%, 3: 40–45%);
  - kod pilnuje, żeby długi bieg nie był dłuższy niż pozostałe biegi razem
    (`services/plan.py::_limit_long_run_share`, od 3 biegów w tygodniu).

## 7. Intensywność spokojnych biegów

- Większość czasu w strefie łatwej. Typowy rozkład to ok. 80% biegania spokojnie i 20% intensywnie.
  Przy wolnym bieganiu najczęstszy błąd to „szara strefa” w okolicy Z3.
- **Wniosek dla aplikacji:**
  - gdy połowa spokojnych biegów ma średnie tętno w Z3 lub wyżej, decyzja to „utrzymaj”;
  - prompt pilnuje, żeby łatwe biegi nie wchodziły w szarą strefę;
  - gdy co najmniej połowa spokojnych biegów ma średnie tętno w górnych 3 bpm Z2, model dostaje polecenie,
    żeby przypomnieć o wolniejszym tempie (bez zmiany decyzji tygodnia).

## 8. HRV i tętno spoczynkowe

- Zasada aplikacji: pojedyncza metryka nie nadpisuje planu. HRV z zegarka bywa zaszumione (alkohol, późny posiłek,
  stres), więc liczy się tygodniowa średnia wobec zakresu tej osoby, a nie jedna noc.
- **Wniosek dla aplikacji:**
  - średnia HRV z tygodnia poniżej zakresu (albo status Garmina „niski”) blokuje „dołóż” (zostaje „utrzymaj”);
  - razem z tętnem spoczynkowym wyższym o co najmniej 3 bpm daje „odpuść”;
  - pomiar starszy niż 3 dni jest pomijany.

## Linki

- Bosquet 2007, metaanaliza taperu: https://pubmed.ncbi.nlm.nih.gov/17762369/
- Taper u sportowców wytrzymałościowych, 2023: https://pubmed.ncbi.nlm.nih.gov/37163550/
- BJSM 2025, skok pojedynczego biegu: https://blogs.bmj.com/bjsm/?p=11751
- Outside, o badaniu z 2025: https://run.outsideonline.com/training/injuries-and-prevention/a-single-run-could-put-you-at-risk-for-an-overuse-injury-a-new-study-suggests/?scope=anon
- Outside, mit zasady 10%: https://run.outsideonline.com/training/getting-started/myth-of-the-10-percent-rule/?scope=anon
- RunnersConnect, zasada 10% i tygodnie w dół: https://runnersconnect.net/weekly-mileage-progression-10-percent-rule/
- TrainingPeaks, utrata formy: https://trainingpeaks.com/blog/how-much-down-time-is-too-much-the-concept-of-detr/
- Detraining, przegląd: https://pubmed.ncbi.nlm.nih.gov/11252068/
- Daniels i powrót po przerwie (blog trenerski): https://lauranorrisrunning.com/?p=666
