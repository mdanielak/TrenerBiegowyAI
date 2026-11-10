# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Głównym użytkownikiem jest biegacz na dowolnym poziomie — od osoby zaczynającej biegać po zaawansowaną — korzystający z aplikacji lokalnie na swoim komputerze (jedna osoba na komputer). Celem może być wynik na zawodach (5 km, 10 km, półmaraton, maraton) albo forma i zdrowie. Korzysta z danych własnego zegarka Garmin, by podejmować decyzje o treningu. Interfejs i dokumentacja zakładają użytkownika nietechnicznego.

## Product Purpose

TrenerBiegowyAI pomaga biegaczowi planować i kontrolować trening w oparciu o cel, dostępność, dane z zegarka i samopoczucie. Sukces oznacza, że użytkownik potrafi zrozumieć swoją sytuację treningową i podjąć świadomą decyzję o kolejnym treningu w drodze do swojego celu.

Aplikacja nie udziela porad medycznych; decyzja o treningu należy do użytkownika.

## Positioning

Lokalny trener biegowy łączący dane Garmin, ocenę gotowości, plan tygodniowy i możliwość wysłania treningów do Garmina. Opcjonalne AI wspiera planowanie i rekomendacje, a lokalne reguły (te same limity w prompcie i w kodzie) dopasowują plan do profilu biegacza, dostępności i przerw treningowych oraz przycinają propozycje ponad limity.

## Operating Context

- Aplikacja działa na komputerze użytkownika i jest obsługiwana przez przeglądarkę; serwer nasłuchuje lokalnie.
- Głównym urządzeniem jest komputer i to pod niego interfejs jest dopracowywany. Widok na telefonie ma działać, ale jego dopracowanie jest zaplanowane na później (`docs/ui-mobile-todo.md`).
- Instalacja przez `install.bat`, uruchamianie przez `start.bat`, aktualizacja do najnowszego wydania z GitHuba przez `update.bat` z zachowaniem danych.
- Typowa droga to połączenie konta Garmin, pobranie danych, ustalenie celu i dostępności, a następnie regularne sprawdzanie gotowości i planu.
- Dane, profil, dziennik i plany są przechowywane lokalnie. Strategia długoterminowa może pochodzić z pliku przygotowanego przez użytkownika.
- Synchronizacja może być częściowa; aktualność i kompletność danych mają znaczenie przy podejmowaniu decyzji.

## Capabilities and Constraints

- Widoki obejmują stronę główną (dzień bieżący), plan treningowy, statystyki, analizę gotowości, dziennik, cel i ustawienia. Osobnego kalendarza nie ma — jego rolę pełnią Plan i Statystyki.
- Użytkownik może zapisać samopoczucie, wysiłek, ból i przerwy oraz porównać plan z wykonaniem.
- Profil biegacza (poziom liczony z danych, staż, kontuzje, wiek, cel, wybrana forma zwracania się: żeńska, męska albo bez form płciowych) i cotygodniowa decyzja „odpuść / utrzymaj / dołóż” sterują planem; długość treningów rośnie od tego, co osoba faktycznie biega.
- Działa z dowolnym dostawcą AI zgodnym z API OpenAI (np. DeepSeek, Gemini, OpenAI); klucze nie są pokazywane, a surowe komunikaty błędów dostawców nie trafiają do interfejsu.
- AI jest opcjonalne. Wysyłanie danych treningowych i zdrowotnych do dostawcy AI wymaga zgody użytkownika; bez AI nie działają generowanie planu, rekomendacja dnia i komentarz do treningu.
- Konflikty przy tworzeniu planu i wysyłce treningów wymagają decyzji użytkownika.
- Obsługiwanym językiem interfejsu jest polski. Nazwy i komunikaty powinny być zrozumiałe bez wiedzy technicznej.

## Brand Commitments

Nazwa produktu: TrenerBiegowyAI. Istniejące logo i zasoby aplikacji znajdują się w `static/`, `trener_biegowy_ai_assets/` i `docs/images/`. Zasady istniejącego interfejsu opisują `DESIGN.md` i `docs/UI_STYLE.md`; w przypadku rozbieżności z aktualną implementacją należy sprawdzić kod i stan dokumentacji.

## Evidence on Hand

- `README.md`: opis funkcji, uruchamiania, prywatności i ograniczeń.
- `scripts/demo_server.py`: demonstracja na danych przykładowych.
- `docs/images/screenshot-light.png` i `docs/images/screenshot-dark.png`: przykładowe zrzuty interfejsu.
- `docs/TRAINING_RULES.md`: reguły treningowe projektu (opis dla ludzi; aktualne prompty są w `ai/prompts/`).
- `testowanie.bat`: kopia aplikacji na zmyślonych danych (udawane Garmin i AI, wybór dnia i poziomu biegacza) do testów bez ruszania prawdziwych danych.
- `docs/ewaluacja-ai/`: ręczna ocena odpowiedzi modeli AI.
- `docs/ui-mobile-todo.md`: spisane problemy widoku na telefonie.
- Wydania z paczką ZIP na GitHubie (z nich korzysta `update.bat`).

## Product Principles

1. Ułatwiaj samodzielną decyzję treningową przez czytelne dane, ich aktualność i wyjaśnienie oceny.
2. Szanuj lokalny charakter produktu i świadomą zgodę na przekazanie danych do AI.
3. Dostosowuj plan do celu, dostępności, samopoczucia i rzeczywiście dostępnych pomiarów, a biegacza oceniaj wobec jego własnych norm i historii (np. tętno spoczynkowe wobec średniej z ostatnich tygodni), nigdy wobec wzorca autora aplikacji ani stałych progów.
4. Unikaj pozornej pewności przy niepełnych danych i zachowuj jasne granice porad zdrowotnych.
5. Prowadź użytkownika przez konfigurację i codzienne zadania prostym językiem.

## Accessibility & Inclusion

Informacje i stany powinny być czytelne i jednoznaczne; kolor nie powinien być ich jedynym nośnikiem. Interfejs ma pomagać również użytkownikowi bez zaplecza technicznego. Dalsze wymagania i poziom zgodności dostępności nie zostały odrębnie ustalone.
