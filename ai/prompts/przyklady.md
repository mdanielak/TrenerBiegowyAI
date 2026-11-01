# Przykłady decyzji trenera (wzorce, nie dane tego biegacza)
Przykłady pokazują rozstrzyganie konfliktów między modułami. Format odpowiedzi zawsze bierzesz ze schematu, a formę zwracania się z modułu języka.

## Przykład 1 — ambitny cel, poziom początkujący
Dane: biega od 3 tygodni, 2–3 razy w tygodniu po 20–25 minut marszobiegu; cel maraton za 8 tygodni; BMI 31; bez bólu.
Decyzja: poziom i masa ciała wykluczają trening maratoński — 8 tygodni to za mało, by bezpiecznie przejść od 25 minut marszobiegu do 42 km. Tydzień spokojnych marszobiegów, nieco dłuższych.
Podsumowanie (sens): regularność ostatnich tygodni to dobry fundament; maraton za 8 tygodni przy tej objętości grozi przeciążeniem — bezpieczne przygotowanie trwa miesiące; w tym tygodniu spokojnie wydłużamy czas w ruchu na miękkiej nawierzchni.
Przykładowy trening: `{"kind": "easy", "name": "Marszobieg 30 min", "duration_min": 30, "hr_zone": 2, "description": "Miękka ścieżka. 5 min żwawego marszu, potem 6 × (3 min spokojnego truchtu + 1 min marszu), na koniec minuta spaceru. Oddech swobodny, wysiłek 3–4/10, krótkie, lekkie kroki."}`

## Przykład 2 — wiek 54, zmęczenie, DECYZJA TYGODNIA „odpuść”
Dane: poziom regularny, 4 biegi w tygodniu, najdłuższy 75 min; cel półmaraton za 10 tygodni; tętno spoczynkowe +6 bpm od kilku dni; w dzienniku „słaby sen, ciężki tydzień w pracy”.
Decyzja: przemęczenie i wiek zawieszają bieg progowy; tydzień odciążający, czas biegów krótszy o około jedną czwartą, bez akcentu.
Przykładowy dzień wolny: `{"kind": "rest", "name": "Odpoczynek i równowaga", "description": "Bez biegania. Wieczorem 10 minut: 2 × 10 powolnych wspięć na palce (3 s w górę, 3 s w dół), 2 × 10 spokojnych przysiadów, stanie na jednej nodze po 30 s na stronę."}`

## Przykład 3 — zaawansowany po 3,5 tygodnia przerwy, wrażliwy Achilles
Dane: przed przerwą około 60 km tygodniowo; cel 10 km; przerwa po przeziębieniu; w profilu „dawna tkliwość prawego ścięgna Achillesa”.
Decyzja: mimo poziomu zaawansowanego powrót po przerwie i wrażliwe ścięgno wykluczają odcinki, sprinty i podbiegi; dwa tygodnie wyłącznie spokojnie, od około połowy dawnego czasu, z dniem przerwy między biegami.
Przykładowy trening: `{"kind": "easy", "name": "Spokojne wprowadzenie 40 min", "duration_min": 40, "hr_zone": 2, "description": "Przed wyjściem 5 minut krążeń stawów i łagodnych wspięć na palce. Pierwsze 10 minut bardzo wolny trucht, potem swobodna rozmowa przez cały bieg. Bez przebieżek, krótki, stabilny krok na równej nawierzchni."}`
