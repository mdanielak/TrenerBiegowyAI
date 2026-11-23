# Zasady tworzenia treningów

Dokument dla ludzi pracujących nad aplikacją. Do AI trafiają prompty z `ai/prompts/` (trener i moduły
dobierane do profilu biegacza) oraz twarde reguły z `ai/plan_generation.py`; plan po odpowiedzi AI
pilnują bezpieczniki w `services/plan.py::normalize_plan`. Ten plik do promptu nie trafia.
Własne, prywatne zasady dla trenera można dopisać w `local/moje-zasady-trenera.md`.

## Bezpieczeństwo i dane

1. Odróżniaj fakty z danych od wniosków. Nie uzupełniaj luk domysłami.
2. Przed rekomendacją oceń aktualność snapshotu oraz czy synchronizacja była częściowa. Niepewność nazwij wprost.
3. Nie stawiaj diagnoz medycznych. Ból, nowe objawy lub objawy alarmowe oznaczają przerwanie treningu i konsultację z odpowiednim specjalistą.
4. Zdrowie > regularność > objętość > tempo. Pojedyncza metryka nie może nadpisać długoterminowej strategii.

## Intensywność i struktura

- Aktualne strefy, częstotliwość treningów i cel pobieraj z prywatnego profilu runtime `local/profile.json`. Nie używaj historycznych pól `hrz_*` jako aktualnych stref.
- Biegi łatwe, regeneracyjne i długie prowadź przede wszystkim według tętna. Każdy bieg Z2 zaczyna się 5–6 minutami spokojnej rozgrzewki bez alarmu HR, potem stosuj alarm strefy.
- Tempo jest wskazówką pomocniczą; warunki, zmęczenie i tętno mogą uzasadniać jego korektę.
- Główny akcent tygodniowo to maksimum; ile mocnych treningów się mieści, zależy od profilu (punkt niżej). Liczba biegów w tygodniu ma respektować profil i strategię, a nie stałą z góry ustaloną wartość.
- Liczba mocnych treningów w tygodniu (0, 1 albo 2) pochodzi z profilu biegacza, a początkujący nie dostaje żadnego. Podaje ją aplikacja — nie zakładaj jej z góry i nie podawaj własnej.
- Okno dostępności dnia to górna granica czasu: może skrócić trening, nigdy go nie wydłużyć.
- Decyzja tygodnia ma pięć stopni (`services/runner_profile.py`): **regeneracja** (ok. 60% zwykłego tygodnia: ból albo tętno spoczynkowe o co najmniej 8 bpm wyższe niż zwykle), **odpuść** (75%: tętno spoczynkowe +5…7 bpm, mało wykonanych i krótsze treningi, tydzień po starcie, albo cofnięcie po czterech tygodniach rosnącej objętości, każdy o co najmniej 3% większy; przed startem taper: tydzień przed startem 80%, tydzień startu 55%, intensywność zostaje), **utrzymaj** (cel 100%, sufit 110%: niepełne wykonanie planu, powrót po przerwie, za mocne tętno w spokojnych biegach, brak danych o planie, trzeci tydzień przed startem, tydzień po wyraźnie lżejszym), **dołóż** (+5–10%, sufit 115%: plan wykonany w co najmniej 90% i brak sygnałów ostrzegawczych) oraz **odbuduj** (powrót do znanej objętości, patrz niżej). Trzy tygodnie dokładania z rzędu kończą się tygodniem cofnięcia, więc „dołóż” nie trwa bez końca.
- Limit czasu tygodnia liczy się od zwykłego tygodnia (ostatni albo mediana z czterech, co większe), nie od największego, razy sufit stopnia, a nigdy ponad 130% średniej z czterech tygodni. Gdy biegacz zostawił trenerowi wiadomość na tydzień, sufit rośnie o 20% (a długi bieg może być o 15 zamiast 10 minut dłuższy niż najdłuższy niedawny), poza „regeneracją” i „odpuść”. Poza tymi dwoma lekkimi stopniami limit nie schodzi poniżej ostatniego tygodnia, jeśli ten mieści się w znanym obciążeniu (najwyżej 130% największego wcześniejszego tygodnia albo zwykłego tygodnia sprzed 5–12 tygodni). Suma maksymalnych minut z dni, które biegacz ma dostępne, jest dodatkowym sufitem widocznym w limitach aplikacji.
- Odbuduj (powrót do znanej objętości): gdy 5–12 tygodni temu bieganie było regularne (co najmniej 6 tygodni z 8) i większe, limit rośnie o najwyżej 25% wobec ostatniego tygodnia, aż do tamtego zwykłego tygodnia. Nie po przerwie od 3 tygodni, nie przy opuszczonych treningach z planu i nie przy zbyt mocnych spokojnych biegach.
- Dwa mocne dni z rzędu (akcent, długi bieg) są niedozwolone: drugi z nich aplikacja zamienia na spokojny bieg. Akcent nie jest dłuższy niż najdłuższy niedawny bieg.
- Opuszczone treningi same w sobie nie wymuszają lżejszego tygodnia; „odpuść” dopiero, gdy wykonane też wychodziły wyraźnie krótsze.
- Poziom liczy częstotliwość z 4 tygodni bez dni krótkiej przerwy (10–20 dni bez biegania): wyjazd czy przeziębienie nie robią z osoby biegającej regularnie początkującej. Rzadkie bieganie bez przerwy obniża poziom od razu, a przerwa od 3 tygodni to powrót (ostrożnie, poziom początkujący do odbudowy).
- Przy podanym stażu od pół roku poziom początkujący daje dopiero bieg krótszy niż 30 minut (bez stażu: 45 minut).
- Ocena gotowości uwzględnia wczorajszy trening: mocny (efekt beztlenowy 2,5+, tlenowy 4+ albo ponad 90 min) obniża ją.
- Do akcentów preferuj wiarygodny pomiar tętna; gdy dane czujnika są niewiarygodne, nie udawaj precyzji.

## Strategia i pliki

- Opcjonalna, prywatna strategia długoterminowa (`training-plans/long-term/strategia.md`, wzór w `przyklad-strategii.md`) wyznacza kierunek, jeśli istnieje.
- Tygodniowy JSON jest opcjonalnym planem wykonawczym; jego brak nie blokuje analizy ani rekomendacji.
- `local/workout-registry.jsonl` jest prywatnym rejestrem operacji na treningach Garmin, nie planem treningowym.
- Treningi twórz przez CLI: `python -m trainer workouts create easy|tempo|intervals|long|strides ...`. Polecenie zmienia dane treningów na Garminie.
- `python -m trainer workouts usage --delete` może usuwać nieużywane treningi na Garminie. Nie modyfikuj bezpośrednio baz GarminDB.

Uzasadnienie liczb (źródła i ich streszczenia): `docs/wiedza-trenerska.md`.
