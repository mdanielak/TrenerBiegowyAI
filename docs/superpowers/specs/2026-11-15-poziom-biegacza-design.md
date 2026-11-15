# Poziom biegacza nadąża za biegaczem (wydanie 0.8.1)

Zatwierdzone w rozmowie 15.11.2026 (wariant A). Rzeczy oznaczone „decyzja wykonawcy” zaproponował asystent.

## Po co

Trener ma z tygodnia na tydzień odświeżać wiedzę o biegaczu i zauważać postęp, np. że ktoś nie jest już
początkujący, tylko biega regularnie. Dzisiaj tak się nie dzieje:

- `services/runner_profile.py::build_runner_profile` liczy poziom od zera z ostatnich 28 dni i ze stażu z kreatora.
- Staż (`running_since`: `start`, `under6`, `6to24`, `over24`) jest zapisany bez daty, więc nie rośnie z czasem.
  Kto zaznaczył „dopiero zaczynam”, ma zawsze 0 miesięcy i przez regułę `months < 6` zostaje początkujący na zawsze.
- Jeden słabszy miesiąc albo tydzień choroby potrafi od razu cofnąć poziom, bo nic nie pamięta wcześniejszych tygodni.
- Poziom nigdzie się nie wyświetla, więc biegacz nie wie, jak traktuje go trener.

## Cele

1. Staż z kreatora rośnie razem z kalendarzem.
2. Poziom jest stabilny: awans po kilku tygodniach, które konsekwentnie go potwierdzają; spadek wolniejszy niż awans.
3. Trener zmienia poziom sam i mówi o tym jednym zdaniem z powodem w liczbach (Strona główna).
4. Biegacz widzi swój poziom w Ustawieniach i może ustawić go ręcznie (cofnięcie decyzji trenera).

## Poza zakresem

- Uczenie się reakcji na obciążenie, regeneracji i form tlenowej (wariant B) — osobny projekt później.
- Zmiana progów poziomów (2 biegi tygodniowo, 45/30 min, 4 biegi + 90 min albo 40 km, staż) — zostają jak są.
- Wersja na telefon.

## Czego nie może zrobić (antycele)

- Poziom nie może skakać z tygodnia na tydzień — to gorsze niż dzisiejszy stan.
- Zmiana poziomu nie może poluzować bezpieczników: limity (`week_cap`, `quality_sessions_limit`,
  `_space_hard_days`) nadal liczą się z bieżących danych, a poziom wpływa na nie tak samo jak dziś.
- Po przerwie bezpieczeństwo jak dziś: przez okres „powrotu” (`_returning`) trener traktuje osobę jak początkującą.
- Żadnego żargonu w komunikacie; neutralnie płciowo albo zgodnie z wybraną formą zwracania się.

## Podejścia, które rozważyliśmy

- **A — profil nadąża za danymi (wybrane).** Staż z datą, poziom liczony z dłuższej historii z histerezą, komunikat
  o zmianie. Mała zmiana, przewidywalna, nie potrzebuje miesięcy zbierania danych.
- **B — A plus nauka reakcji** (tolerancja obciążenia, regeneracja, forma tlenowa). Odłożone: wnioski dopiero po
  2–3 miesiącach, większe ryzyko pozornej pewności.
- **Zapis stanu poziomu w pliku co tydzień** (wcześniej zaproponowany w ramach A) — zastąpiony liczeniem z historii
  (niżej). Decyzja wykonawcy: historia z zegarka (120 dni w `data_latest.json`) wystarcza, wynik jest ten sam po
  reinstalacji i nie ma pliku, który może się rozjechać z danymi.

## Jak (ustalone)

### Staż rośnie z czasem
- Przy zapisie kreatora zapisywana jest data odpowiedzi o stażu (`running_since_at`, data ISO).
- Miesiące stażu = wartość z `RUNNING_SINCE` + pełne miesiące od `running_since_at` do dziś. Gdy zegarek pokazuje
  bieganie krócej niż 90 dni, staż rośnie najwyżej o tyle, ile widać biegania (poprawka po przeglądzie: sam kalendarz
  bez biegania nie może dać akcentów).
- Starsze profile bez tej daty: data z `onboarding_completed_at`; gdy i jej brak — staż bez wzrostu (jak dziś).
- Ponowne przejście kreatora z tą samą odpowiedzią nie zeruje daty (decyzja wykonawcy: data zmienia się tylko wtedy,
  gdy zmienia się odpowiedź).

### Poziom z historii tygodni (histereza)
- Dzisiejsza reguła poziomu zostaje jako „surowa ocena tygodnia”: dla każdego z ostatnich do 12 poniedziałków
  liczona jest z 28 dni przed tym poniedziałkiem (to samo okno co dziś), ze stażem z tamtego dnia.
- Tygodnie bez biegania (przerwa) nie są dowodem — pomija się je przy ustalaniu poziomu.
- Poziom = poziom z poprzedniej oceny, chyba że:
  - **awans**: 3 ostatnie oceniane tygodnie z rzędu wskazują wyższy poziom;
  - **spadek**: 4 ostatnie oceniane tygodnie z rzędu wskazują niższy poziom — dotyczy zaawansowany → regularny;
    ocena „początkujący” (np. mniej niż 2 biegi w tygodniu) obniża poziom od razu, bo bezpiecznik jest ważniejszy niż
    stabilność (poprawka po przeglądzie).
  - start łańcucha: najniższa z pierwszych 3 ocen, żeby przesuwające się okno samo nie podnosiło poziomu.
  Poziom zmienia się o jeden stopień naraz. Na starcie historii (najstarszy tydzień) poziom = jego surowa ocena.
- Krótka historia (`short_history`, < 3 tygodnie danych): jak dziś, bez histerezy.
- Powrót po przerwie (`returning`): przez te 14 dni `level` = początkujący jak dziś. Tygodnie przerwy nie obniżają
  poziomu, ale rzadkie bieganie po powrocie tak (zob. spadek), więc wcześniejszy poziom wraca przez zwykły awans.
- Ręczne ustawienie poziomu w Ustawieniach (`level_override` w profilu): obniża dowolnie, podnosi najwyżej o jeden
  stopień ponad wynik z historii i wcale przy krótkiej historii; nie działa w okresie powrotu.
- Liczby do decyzji (biegi na tydzień, najdłuższy bieg, km) — z tych samych pól co dziś; obliczenie zostaje czystą
  funkcją danych (bez zapisu stanu), żeby prompt, bezpieczniki i ekran dostawały ten sam poziom.

### Komunikat o zmianie
- `build_runner_profile` zwraca dodatkowo: `level_since` (poniedziałek, od którego obowiązuje poziom),
  `level_changed` (`"up"`, `"down"` albo `None` — gdy zmiana nastąpiła w bieżącym tygodniu, od poniedziałku zmiany)
  i `level_reason` (jedno zdanie z liczbami tej osoby).
- Strona główna pokazuje komunikat przez tydzień od zmiany, np.:
  „Od 3 tygodni biegasz 4 razy w tygodniu, najdłużej 55 minut. Trener traktuje Cię teraz jak osobę biegającą regularnie.”
  Przy spadku spokojniej: „Ostatni miesiąc był lżejszy, więc trener na razie planuje ostrożniej — jak dla osoby
  zaczynającej.” Zwrot do biegacza zgodny z `address_form`.
- Kształt i miejsce na stronie głównej (karta, notka przy werdykcie) — decyzja wykonawcy, zgodnie z `DESIGN.md`;
  zrzuty przez `zrzut-testowy` w obu motywach przed włączeniem do `main`.

### Ustawienia
- Sekcja „Poziom”: aktualny poziom, od kiedy i jedno zdanie powodu.
- Wybór: „Automatycznie (zalecane)” albo jeden z trzech poziomów na stałe. Zapis do `level_override`
  (pusty = automatycznie).

### Prompt
- `profile_lines` dalej podaje `poziom: …`; nowe pola nie trafiają do promptu (decyzja wykonawcy: model nie
  potrzebuje historii zmian, a ładowarka `ai/prompts/__init__.py` wybiera moduł `poziom/<level>` jak dziś).

## Ograniczenia
- Limity w prompcie i w kodzie z jednego źródła — bez zmian.
- Testy: nowe w `tests/test_runner_profile.py` (staż z datą, awans po 3 tygodniach, brak awansu po 2, spadek po 4,
  pominięcie tygodni przerwy, powrót, ręczne ustawienie), kreator (zapis daty) i widok. Cały zestaw zielony.
- Po zmianie logiki — przegląd agentem `straznik-limitow`; po tekstach — `korektor-tekstow`.
- Wydanie 0.8.1 według `CLAUDE.md` (z `git archive`; `testowanie.sh` jest już wykluczony).

## Dla wykonawcy
- Dokładne nazwy funkcji pomocniczych, układ testów, wygląd komunikatu w ramach `DESIGN.md`.
- Czy surowe oceny tygodni liczyć jedną pętlą, czy wywołaniem obecnej funkcji dla przesuniętego `today`.
