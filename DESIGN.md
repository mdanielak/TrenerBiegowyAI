---
name: TrenerBiegowyAI
description: Przejrzyste centrum treningu biegowego
colors:
  accent: "#2563EB"
  accent-strong: "#1D4ED8"
  accent-soft: "#EFF6FF"
  accent-soft-2: "#DBEAFE"
  bg: "#EEF2F6"
  surface: "#FCFDFE"
  surface-alt: "#E9EEF4"
  border: "#DAE1E9"
  border-strong: "#C3CDD8"
  fg: "#0F172A"
  fg-mid: "#475569"
  fg-muted: "#5B6A7E"
  on-accent: "#FFFFFF"
  ok-fg: "#15803D"
  ok-bg: "#DCFCE7"
  ok-soft: "#F0FDF4"
  ok-icon: "#16A34A"
  warn-fg: "#B45309"
  warn-bg: "#FEF3C7"
  warn-soft: "#FFFBEB"
  warn-icon: "#D97706"
  danger-fg: "#B91C1C"
  danger-bg: "#FEE2E2"
  danger-soft: "#FEF2F2"
  danger-icon: "#DC2626"
  dark-bg: "#131D30"
  dark-surface: "#1B273C"
  dark-surface-alt: "#223149"
  dark-border: "#2C3C56"
  dark-border-strong: "#435775"
  dark-fg: "#E6EDF5"
  dark-fg-mid: "#B4C2D3"
  dark-fg-muted: "#8EA0B6"
  dark-accent: "#60A5FA"
  dark-accent-strong: "#93C5FD"
  dark-accent-soft: "#1B3152"
  dark-accent-soft-2: "#23406B"
  dark-on-accent: "#0B1730"
  dark-ok-fg: "#4ADE80"
  dark-ok-bg: "#163A25"
  dark-ok-soft: "#12301E"
  dark-ok-icon: "#22C55E"
  dark-warn-fg: "#FBBF24"
  dark-warn-bg: "#3D2E10"
  dark-warn-soft: "#30240D"
  dark-warn-icon: "#F59E0B"
  dark-danger-fg: "#F87171"
  dark-danger-bg: "#3F1A1D"
  dark-danger-soft: "#311517"
  dark-danger-icon: "#EF4444"
typography:
  headline:
    fontFamily: '"Segoe UI", system-ui, -apple-system, "Helvetica Neue", Arial, sans-serif'
    fontSize: "24px"
    fontWeight: 650
    lineHeight: 1.25
    letterSpacing: "-0.01em"
  title:
    fontFamily: '"Segoe UI", system-ui, -apple-system, "Helvetica Neue", Arial, sans-serif'
    fontSize: "17px"
    fontWeight: 650
    lineHeight: 1.25
  body:
    fontFamily: '"Segoe UI", system-ui, -apple-system, "Helvetica Neue", Arial, sans-serif'
    fontSize: "15px"
    lineHeight: 1.55
  label:
    fontFamily: '"Segoe UI", system-ui, -apple-system, "Helvetica Neue", Arial, sans-serif'
    fontSize: "12px"
  brand:
    fontFamily: '"Archivo Logo", "Segoe UI", system-ui, sans-serif'
    fontSize: "16px"
    fontWeight: 800
    lineHeight: 1.2
  code:
    fontFamily: 'Consolas, "Courier New", monospace'
    fontSize: "13px"
rounded:
  icon-tiny: "3px"
  detail: "4px"
  compact: "6px"
  sm: "8px"
  icon-small: "10px"
  card: "12px"
  icon-medium: "13px"
  icon-large: "15px"
  pill: "999px"
spacing:
  compact: "8px"
  row: "10px"
  card: "18px"
  gap: "20px"
components:
  button-primary:
    backgroundColor: "{colors.accent}"
    textColor: "{colors.on-accent}"
    rounded: "{rounded.sm}"
    padding: "9px 16px"
  button-primary-hover:
    backgroundColor: "{colors.accent-strong}"
  button-secondary:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.fg-mid}"
    rounded: "{rounded.sm}"
    padding: "9px 16px"
  card:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.fg}"
    rounded: "{rounded.card}"
    padding: "18px"
  input:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.fg}"
    rounded: "{rounded.sm}"
    padding: "10px"
    height: "44px"
---

# Design System: TrenerBiegowyAI

## Overview

**Creative North Star: "Przejrzyste centrum treningu"**

Interfejs jest spokojny, rzeczowy i czytelny. Dane i działania są pogrupowane w proste, powściągliwe karty; pierwszeństwo mają informacja i zadanie użytkownika. Kolorowe ilustracje i sportowy kobalt nadają produktowi charakter, nie konkurując z treścią.

Główny obszar zachowuje gęstość odpowiednią dla pulpitu z danymi. Obramowania, różnice powierzchni i subtelne cienie oddzielają elementy. Jasny i ciemny motyw są równorzędnymi wariantami tej samej struktury.

**Key Characteristics:**
- Spokojny pulpit z czytelną hierarchią danych.
- Sportowy kobalt dla nawigacji i działań.
- Stany opisane tekstem, wspierane kolorem i ikoną.
- Subtelnie oddzielone karty oraz lokalne ilustracje.

## Colors

Sportowy kobalt prowadzi do działań, a chłodne neutralne tła utrzymują czytelność informacji.

### Primary

- **Sportowy kobalt** (`accent`): linki, główne przyciski i zaznaczenia; mocniejszy wariant wspiera stan aktywny i hover, a miękkie warianty tła informacyjne.

### Neutral

- **Chłodne tło i powierzchnie** (`bg`, `surface`, `surface-alt`): oddzielają stronę, karty i elementy drugoplanowe.
- **Grafit i przygaszony łupek** (`fg`, `fg-mid`, `fg-muted`): budują hierarchię tekstu; `border` i `border-strong` wyznaczają granice.
- **Ciemny granat** (`dark-bg`, `dark-surface`, `dark-surface-alt`): odpowiedniki powierzchni w motywie ciemnym; jasne teksty i akcenty są zdefiniowane osobno.

### Named Rules

**The Text With Color Rule.** Zieleń, bursztyn i czerwień sygnalizują stan wraz z tekstem; nie niosą informacji samodzielnie. Warianty `ok`, `warn` i `danger` mają osobne kolory tekstu, tła i ikon.

## Typography

**Body Font:** Segoe UI z systemowymi alternatywami. Lokalny krój Archivo jest używany w znaku słownym, a kod korzysta ze stosu monospace.

Hierarchię tworzą rozmiar i grubość: nagłówek strony ma 24px, nagłówek sekcji 17px, a tekst podstawowy 15px z interlinią 1.55. Etykiety i opisy wartości są mniejsze; liczby treningowe są wyróżnione. Na wąskim ekranie tekst podstawowy ma 14.5px, a nagłówek strony 21px — są to wartości obecnej implementacji, nie gwarancja dostępności.

Poza głównymi rolami arkusz zawiera rozmiary 9.5, 10.5, 11, 11.5, 12.5, 13.5, 14, 18, 20, 22, 23 i 34px, używane m.in. w logo, metrykach i opisach. Są to obecne wartości szczegółowe, a nie dodatkowe obowiązkowe role typografii.

## Layout

Na szerokim ekranie przyklejony panel nawigacji ma 248px szerokości, a obszar treści maksymalnie 1180px. Karty układają się w siatki z odstępem 20px; ekran główny łączy węższą kolumnę oceny z szerszą kolumną sygnałów. Standardowy wewnętrzny odstęp karty wynosi 18px.

Przy szerokości do 1080px część siatek się zwęża. Do 760px nawigacja przechodzi na górę i przewija się poziomo, a wykresy metryk układają się w jednej kolumnie. Do 520px większość siatek przechodzi do jednej kolumny, a zestawy liczbowych kafelków pozostają dwukolumnowe. To opis obecnego zachowania, nie wynik osobnego testu mobilnego.

## Elevation & Depth

Cienie są subtelne i strukturalne: oddzielają karty oraz zaznaczone elementy od sąsiednich powierzchni. Krawędzie i zmiana odcienia współtworzą głębię; wartości cieni dla obu motywów znajdują się w `.impeccable/design.json` i arkuszu stylów.

## Shapes

Karty mają łagodne rogi 12px, przyciski i pola 8px, a znaczniki statusu formę kapsuły. Powtarzające się wykresy i pierścienie mają prostą geometrię; pasek treningu pokazuje proporcje odcinków i odpowiadającą im listę kroków.

## Components

### Buttons

Proste i powściągliwe. Przycisk główny ma tło akcentu, tekst `on-accent`, promień 8px i odstęp 9px 16px. Przycisk drugorzędny ma tło powierzchni, tekst `fg-mid` i obramowanie. Hover zmienia tło, naciśnięcie skaluje element do 0.98, a nieaktywny przycisk otrzymuje stonowany wygląd.

### Cards / Containers

Powierzchnia karty, obramowanie, cień i odstęp wewnętrzny tworzą powtarzalny kontener. Nagłówek sekcji może łączyć lokalną ilustrację, tytuł i drugorzędny odnośnik.

### Inputs / Fields

Pola mają tło powierzchni, wyraźne obramowanie i minimalną wysokość 44px. Etykiety są widoczne; błędy mogą pojawiać się przy polu i w podsumowaniu. Fokus klawiatury jest oznaczony obrysem 2px z odsunięciem 2px.

### Navigation

Pionowe menu łączy lokalne ikony i podpisy. Aktywna pozycja ma miękkie tło akcentu oraz mocniejszy tekst; motyw można wybrać na dole menu. Na węższych ekranach menu przechodzi w poziomy przewijany wiersz.

### Status and training profile

Kapsuły i banery łączą tekst ze stanem kolorystycznym. Ocena gotowości jest przedstawiona jako liczba w pierścieniu z tekstowym opisem; przebieg treningu łączy proporcjonalne odcinki z opisem czasu i celu każdego kroku.

## Do's and Don'ts

### Do:
- **Do** stosuj istniejące zmienne semantyczne i sprawdzaj oba motywy osobno.
- **Do** łącz stan kolorystyczny z widoczną etykietą lub opisem.
- **Do** zachowuj widoczny fokus oraz szanuj ustawienie ograniczonego ruchu.
- **Do** korzystaj z lokalnych zasobów i istniejących komponentów.

### Don't:
- **Don't** komunikuj znaczenia wyłącznie kolorem.
- **Don't** zakładaj, że wartości i kontrast motywu jasnego działają również w ciemnym.
- **Don't** dodawaj zewnętrznych zasobów wizualnych wymagających połączenia z siecią.
