# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Głównym użytkownikiem jest biegacz, który świadomie korzysta z aplikacji lokalnie na komputerze i chce poprawić swój wynik. Korzysta z danych własnego zegarka Garmin, by podejmować decyzje o treningu. Dokumentacja interfejsu zakłada użytkownika nietechnicznego.

## Product Purpose

TrenerBiegowyAI pomaga biegaczowi planować i kontrolować trening w oparciu o cel, dostępność, dane z zegarka i samopoczucie. Sukces oznacza, że użytkownik potrafi zrozumieć swoją sytuację treningową i podjąć świadomą decyzję o kolejnym treningu w drodze do poprawy wyniku.

Aplikacja nie udziela porad medycznych; decyzja o treningu należy do użytkownika.

## Positioning

Lokalny trener biegowy łączący dane Garmin, ocenę gotowości, plan tygodniowy i możliwość wysłania treningów do Garmina. Opcjonalne AI wspiera planowanie i rekomendacje, a lokalne reguły uwzględniają dostępność i przerwy treningowe.

## Operating Context

- Aplikacja działa na komputerze użytkownika i jest obsługiwana przez przeglądarkę; serwer nasłuchuje lokalnie.
- Typowa droga to połączenie konta Garmin, pobranie danych, ustalenie celu i dostępności, a następnie regularne sprawdzanie gotowości i planu.
- Dane, profil, dziennik i plany są przechowywane lokalnie. Strategia długoterminowa może pochodzić z pliku przygotowanego przez użytkownika.
- Synchronizacja może być częściowa; aktualność i kompletność danych mają znaczenie przy podejmowaniu decyzji.

## Capabilities and Constraints

- Widoki obejmują dzień bieżący, plan, kalendarz, statystyki, analizę gotowości, dziennik, cel i ustawienia.
- Użytkownik może zapisać samopoczucie, wysiłek, ból i przerwy oraz porównać plan z wykonaniem.
- AI jest opcjonalne. Wysyłanie danych treningowych i zdrowotnych do dostawcy AI wymaga zgody użytkownika; bez AI nie działają generowanie planu, rekomendacja dnia i komentarz do treningu.
- Konflikty przy tworzeniu planu i wysyłce treningów wymagają decyzji użytkownika.
- Obsługiwanym językiem interfejsu jest polski. Nazwy i komunikaty powinny być zrozumiałe bez wiedzy technicznej.

## Brand Commitments

Nazwa produktu: TrenerBiegowyAI. Istniejące logo i zasoby aplikacji znajdują się w `static/`, `trener_biegowy_ai_assets/` i `docs/images/`. Zasady istniejącego interfejsu opisuje `docs/UI_STYLE.md`; w przypadku rozbieżności z aktualną implementacją należy sprawdzić kod i stan dokumentacji.

## Evidence on Hand

- `README.md`: opis funkcji, uruchamiania, prywatności i ograniczeń.
- `scripts/demo_server.py`: demonstracja na danych przykładowych.
- `docs/images/screenshot-light.png` i `docs/images/screenshot-dark.png`: przykładowe zrzuty interfejsu.
- `docs/TRAINING_RULES.md`: reguły treningowe projektu.

## Product Principles

1. Ułatwiaj samodzielną decyzję treningową przez czytelne dane, ich aktualność i wyjaśnienie oceny.
2. Szanuj lokalny charakter produktu i świadomą zgodę na przekazanie danych do AI.
3. Dostosowuj plan do celu, dostępności, samopoczucia i rzeczywiście dostępnych pomiarów.
4. Unikaj pozornej pewności przy niepełnych danych i zachowuj jasne granice porad zdrowotnych.
5. Prowadź użytkownika przez konfigurację i codzienne zadania prostym językiem.

## Accessibility & Inclusion

Informacje i stany powinny być czytelne i jednoznaczne; kolor nie powinien być ich jedynym nośnikiem. Interfejs ma pomagać również użytkownikowi bez zaplecza technicznego. Dalsze wymagania i poziom zgodności dostępności nie zostały odrębnie ustalone.
