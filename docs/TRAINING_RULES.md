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
- Planuj najwyżej jeden główny akcent tygodniowo. Liczba biegów w tygodniu ma respektować profil i strategię, a nie stałą z góry ustaloną wartość.
- Do akcentów preferuj wiarygodny pomiar tętna; gdy dane czujnika są niewiarygodne, nie udawaj precyzji.

## Strategia i pliki

- Opcjonalna, prywatna strategia długoterminowa (`training-plans/long-term/half-marathon-2027.md`, wzór w `przyklad-strategii.md`) wyznacza kierunek, jeśli istnieje.
- Tygodniowy JSON jest opcjonalnym planem wykonawczym; jego brak nie blokuje analizy ani rekomendacji.
- `local/workout-registry.jsonl` jest prywatnym rejestrem operacji na treningach Garmin, nie planem treningowym.
- Treningi twórz przez CLI: `python -m trainer workouts create easy|tempo|intervals|long|strides ...`. Polecenie zmienia dane treningów na Garminie.
- `python -m trainer workouts usage --delete` może usuwać nieużywane treningi na Garminie. Nie modyfikuj bezpośrednio baz GarminDB.
