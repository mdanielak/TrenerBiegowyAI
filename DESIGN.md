---
name: TrenerBiegowyAI
description: Przejrzyste centrum treningu biegowego
colors:
  accent: "#2563EB"
  accent-strong: "#1D4ED8"
  accent-soft: "#EFF6FF"
  accent-soft-2: "#DBEAFE"
  on-accent: "#FFFFFF"
  bg: "#EEF2F6"
  surface: "#FCFDFE"
  surface-alt: "#E9EEF4"
  sidebar-bg: "#E4EAF2"
  border: "#DAE1E9"
  border-strong: "#C3CDD8"
  control-border: "#7A899C"
  fg: "#0F172A"
  fg-mid: "#475569"
  fg-muted: "#5B6A7E"
  fg-disabled: "#94A3B8"
  ok-fg: "#137336"
  ok-bg: "#DCFCE7"
  ok-soft: "#F0FDF4"
  ok-icon: "#16A34A"
  ok-border: "#BBF7D0"
  warn-fg: "#9A4507"
  warn-bg: "#FEF3C7"
  warn-soft: "#FFFBEB"
  warn-icon: "#D97706"
  warn-border: "#FDE68A"
  danger-fg: "#B91C1C"
  danger-bg: "#FEE2E2"
  danger-soft: "#FEF2F2"
  danger-icon: "#DC2626"
  danger-border: "#FECACA"
  on-danger: "#FFFFFF"
  z1-bg: "#E0F2FE"
  z1-fg: "#075985"
  z4-bg: "#FFEDD5"
  z4-fg: "#9A3412"
  seg-base: "#475569"
  seg-work: "#C2410C"
  seg-rest: "#64748B"
  seg-main: "#1D4ED8"
  seg-z1: "#0369A1"
  seg-z2: "#15803D"
  seg-z3: "#A16207"
  seg-z4: "#C2410C"
  seg-z5: "#B91C1C"
  seg-skipped: "#CBD5E1"
  dark-bg: "#131D30"
  dark-surface: "#1B273C"
  dark-surface-alt: "#223149"
  dark-sidebar-bg: "#27364F"
  dark-border: "#2C3C56"
  dark-border-strong: "#435775"
  dark-control-border: "#5E7391"
  dark-fg: "#E6EDF5"
  dark-fg-mid: "#B4C2D3"
  dark-fg-muted: "#8EA0B6"
  dark-fg-disabled: "#64748B"
  dark-accent: "#60A5FA"
  dark-accent-strong: "#93C5FD"
  dark-accent-soft: "#1B3152"
  dark-accent-soft-2: "#23406B"
  dark-on-accent: "#0B1730"
  dark-ok-fg: "#4ADE80"
  dark-ok-bg: "#163A25"
  dark-ok-soft: "#12301E"
  dark-ok-icon: "#22C55E"
  dark-ok-border: "#1F5C36"
  dark-warn-fg: "#FBBF24"
  dark-warn-bg: "#3D2E10"
  dark-warn-soft: "#30240D"
  dark-warn-icon: "#F59E0B"
  dark-warn-border: "#6B4E12"
  dark-danger-fg: "#F87171"
  dark-danger-bg: "#3F1A1D"
  dark-danger-soft: "#311517"
  dark-danger-icon: "#EF4444"
  dark-danger-border: "#6B2426"
  dark-on-danger: "#1B0A0C"
  dark-z1-bg: "#0F3550"
  dark-z1-fg: "#7DD3FC"
  dark-z4-bg: "#42230F"
  dark-z4-fg: "#FDBA74"
  dark-seg-base: "#7C8BA1"
  dark-seg-work: "#FB923C"
  dark-seg-rest: "#68798F"
  dark-seg-main: "#60A5FA"
  dark-seg-z1: "#38BDF8"
  dark-seg-z2: "#4ADE80"
  dark-seg-z3: "#FACC15"
  dark-seg-z4: "#FB923C"
  dark-seg-z5: "#F87171"
  dark-seg-skipped: "#3A4A63"
typography:
  headline:
    fontFamily: '"Segoe UI", system-ui, -apple-system, "Helvetica Neue", Arial, sans-serif'
    fontSize: "28px"
    fontWeight: 650
    lineHeight: 1.25
    letterSpacing: "-0.02em"
  title:
    fontFamily: '"Segoe UI", system-ui, -apple-system, "Helvetica Neue", Arial, sans-serif'
    fontSize: "19px"
    fontWeight: 650
    lineHeight: 1.25
  body:
    fontFamily: '"Segoe UI", system-ui, -apple-system, "Helvetica Neue", Arial, sans-serif'
    fontSize: "15px"
    lineHeight: 1.55
  label:
    fontFamily: '"Segoe UI", system-ui, -apple-system, "Helvetica Neue", Arial, sans-serif'
    fontSize: "13px"
  brand:
    fontFamily: '"Archivo Logo", "Segoe UI", system-ui, sans-serif'
    fontSize: "16px"
    fontWeight: 800
    lineHeight: 1.2
  code:
    fontFamily: 'Consolas, "Courier New", monospace'
    fontSize: "13px"
rounded:
  detail: "4px"
  compact: "6px"
  sm: "8px"
  card: "12px"
  pill: "999px"
spacing:
  compact: "8px"
  row: "10px"
  card: "18px"
  gap: "20px"
  section-gap: "26px"
---

# Design System: TrenerBiegowyAI

Jedyne źródło prawdy dla warstwy web.

## 1. Zasady nienaruszalne

- **Stos:** FastAPI + Jinja2 (`templates/*.html`), jeden arkusz stylów ([static/css/styles.css](static/css/styles.css)) i jeden plik lekkiego JS ([static/js/interface.js](static/js/interface.js)).
- **Zero zasobów z sieci:** brak CDN, Google Fonts i zewnętrznych bibliotek CSS/JS.
- **Bezpieczeństwo szablonów:** zero `|safe` (autoescaping Jinja2 wszędzie) i zero inline `<script>` w HTML.
- **Płaska hierarchia:** maksymalnie jeden poziom karty — w karcie nie ma zagnieżdżonych kart.
- **Znaczenie nigdy samym kolorem:** każdy stan (`ok`, `warn`, `bad`) łączy kolor z czytelnym polskim tekstem bez technicznego żargonu.
- **Równorzędne motywy Light i Dark:** każda zmiana koloru musi być wpisana jednocześnie w `:root`, `@media (prefers-color-scheme: dark)` i `:root[data-theme="dark"]`.

## 2. Kolory i policzone kontrasty WCAG 2.1 AA

Minimalny próg to **4,5:1** dla tekstu i **3,0:1** dla kontrolek, obramowań aktywnych pól/przycisków i wykresów (`--control-border`, `--fg-muted`, `--*-icon`).

| Para tokenów | Zastosowanie | Light | Dark |
|:-------------|:-------------|:------|:-----|
| `--fg` / `--surface` | Tekst główny na karcie | 17,50:1 | 12,51:1 |
| `--fg-mid` / `--surface` | Opisy i etykiety na karcie | 7,43:1 | 8,19:1 |
| `--fg-muted` / `--bg` | Podtytuły i stopki na tle strony | 4,90:1 | 6,30:1 |
| `--fg-muted` / `--surface-alt` | Tekst drugorzędny na kafelku | 4,73:1 | 4,90:1 |
| `--fg-muted` / `--sidebar-bg` | Podpis marki i etykiety w menu | 4,56:1 | 4,55:1 |
| `--accent` / `--surface` | Linki na karcie | 5,07:1 | 5,97:1 |
| `--accent-strong` / `--accent-soft` | Aktywna pozycja menu i kapsuła `info` | 6,25:1 | 6,54:1 |
| `--accent-strong` / `--danger-bg` | Link w banerze błędu | 5,48:1 | 8,82:1 |
| `--accent-strong` / `--surface-alt` | Link w odpowiedzi trenera / kafelku | 5,73:1 | 7,57:1 |
| `--on-accent` / `--accent` | Przycisk główny | 5,17:1 | 6,95:1 |
| `--on-danger` / `--danger-fg` | Przycisk usuwania (`btn-danger`) | 6,47:1 | 7,18:1 |
| `--ok-fg` / `--ok-bg` | Stan `ok` i kapsuła strefy `Z2` | 5,14:1 | 7,23:1 |
| `--warn-fg` / `--warn-bg` | Stan `warn` i baner ostrzeżenia | 5,82:1 | 7,88:1 |
| `--warn-fg` / `--surface-alt` | Nagłówek ostrzeżeń w odpowiedzi trenera | 5,47:1 | 7,84:1 |
| `--danger-fg` / `--danger-bg` | Stan `bad` i baner błędu | 5,30:1 | 5,43:1 |
| `--control-border` / `--surface` | Obramowanie przycisków wtórnych i pól wyboru (≥ 3:1) | 3,47:1 | 3,18:1 |
| `--fg-muted` / `--surface` | Obramowanie pól tekstowych (≥ 3:1) | 5,38:1 | 5,64:1 |

## 3. Typografia i układ

- **Kroje:** `"Segoe UI", system-ui, -apple-system, "Helvetica Neue", Arial, sans-serif` dla treści; lokalny `"Archivo Logo"` (podstawowy zestaw łaciński) wyłącznie dla znaku słownego oraz dużych liczb treningowych z `tabular-nums`.
- **Skala desktop:** `h1` 28 px, `h2` 19 px (nagłówek karty), tekst 15 px (`line-height: 1.55`), etykiety 13 px, odstęp między sekcjami 26 px, w kartach 18–20 px.
- **Układ desktop:** przyklejony panel boczny `248px`, treść wyśrodkowana do `1320px`. Poniżej `1024px` menu przechodzi na górę.

## 4. Komponenty i zasoby lokalne

- **Ikony i ilustracje:** kolorowe ikony PNG przy nagłówkach sekcji (`24px`) i kafelkach (`22px`) są integralną częścią charakteru aplikacji; ikony SVG (`_icons.html`) służą przyciskom i kontrolkom.
- **Plan tygodnia:** dni to płaskie kolumny tygodnia (bez zagnieżdżonych kart); akcje destrukcyjne (usunięcie treningu) znajdują się w oknie szczegółów treningu, nie obok ikony zegarka Garmin.
- **Brak danych:** zawsze myślnik `—`, nigdy `0` ani `None`.
- **Fokus i ruch:** widoczny obrys klawiatury `outline: 2px solid var(--accent); outline-offset: 2px` na `:focus-visible`; brak animacji wejścia, pulsowania i `backdrop-filter`; pełne wsparcie `prefers-reduced-motion: reduce`.
