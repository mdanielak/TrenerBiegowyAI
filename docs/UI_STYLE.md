# System wizualny — Trener Biegowy

Dokument jest instrukcją dla osoby lub agenta pracującego nad warstwą web oraz zapisem decyzji wizualnych. Obowiązuje jasny, spokojny motyw oparty na odcieniach slate i niebieskim akcencie. Wszystkie wartości kontrastu podane niżej są policzone według WCAG 2.1, nie oszacowane, i dotyczą konkretnych par barw użytych w tym interfejsie.

## Rola

Projektujesz i utrzymujesz interfejs lokalnego asystenta treningu biegowego. Zanim napiszesz kod, przeczytaj szablon, który zmieniasz, i sprawdź, jakie tokeny oraz klasy już istnieją. Nie wprowadzaj nowego wzorca, jeśli działający już jest.

Z aplikacji korzysta jedna osoba nietechniczna, która sprawdza informacje dotyczące własnego zdrowia i podejmuje na ich podstawie decyzję. Dlatego czytelność i jednoznaczność mają pierwszeństwo przed efektem wizualnym. Zmiany opisuj krótko i po polsku, bez żargonu; wyjaśniaj powód decyzji, nie tylko jej treść.

## Kontekst techniczny i granice nienaruszalne

Stos: FastAPI, szablony Jinja2, jeden lokalny arkusz CSS. Nie ma tu Reacta, Tailwinda, frameworka animacji ani kroku budowania. Nie dodawaj ich.

- **Zero kodu wykonywanego w przeglądarce.** Żadnych skryptów, atrybutów zdarzeń ani `<script>`.
- **Zero zasobów z sieci.** Bez CDN, fontów zewnętrznych, obrazków z adresów URL i reguł dociągających zasoby zewnętrzne. Font to wyłącznie stos systemowy.
- **Pliki statyczne tylko z dysku.** `StaticFiles` serwuje wyłącznie katalog `static/` z repozytorium (arkusz CSS), a grafiki idą przez `/assets/`. Nic nie jest pobierane z sieci.
- **Nigdy `|safe`.** Autoescaping Jinja pozostaje włączony wszędzie.
- **Kolor nigdy nie jest jedynym nośnikiem znaczenia.** Każdy stan ma też tekst.
- **Teksty po polsku**, bez skrótów i terminów technicznych w treści widocznej dla użytkownika.

## Jedno źródło prawdy dla stylu

Cały styl mieszka wyłącznie w `static/css/styles.css`. Szablon `templates/_styles.html` tylko go dołącza (`<link rel="stylesheet">`) i jest włączany przez `{% include "_styles.html" %}` w sekcji `<head>`. Nie dodawaj bloków `<style>` ani nowych atrybutów `style` w szablonach; istniejące warto stopniowo przenosić do klas. Tokeny zapisuj jako własne właściwości CSS w `:root`; nie wklejaj wartości szesnastkowych wprost w reguły.

## Tokeny

Motyw jasny jest jedynym obowiązującym. Deklaruj `color-scheme: light`.

### Powierzchnie i tekst

Jasne powierzchnie rozdzielają informacje subtelną różnicą tła, obramowaniem i lekkim cieniem. Nie buduj głębi z ciemnych bloków ani z dużych efektów rozmycia.

| Token | Wartość | Zastosowanie |
|:------|:--------|:-------------|
| `--bg` | `#F8FAFC` | Główne tło aplikacji |
| `--surface` | `#FFFFFF` | Karty i główne powierzchnie |
| `--surface-alt` | `#F1F5F9` | Kafelki i wgłębienia |
| `--border` | `#E2E8F0` | Standardowe obramowanie |
| `--border-strong` | `#CBD5E1` | Mocniejsze obramowanie |
| `--fg` | `#0F172A` | Tekst główny |
| `--fg-mid` | `#475569` | Tekst średni, opisy i etykiety |
| `--fg-muted` | `#64748B` | Tekst drugorzędny |

| Tekst | Na bieli | Na tle aplikacji | Na kafelku | Dodatkowe tło |
|:------|:---------|:-----------------|:-----------|:---------------|
| `#0F172A` | 17,85:1 | 17,06:1 | 16,30:1 | 16,40:1 na `#EFF6FF`; 17,05:1 na `#F0FDF4` |
| `#475569` | 7,58:1 | 7,24:1 | 6,92:1 | — |
| `#64748B` | 4,76:1 | 4,55:1 | — | — |

**Ważne ograniczenie:** `#64748B` na kafelku `#F1F5F9` daje tylko **4,34:1**, czyli poniżej wymaganego progu 4,5:1 dla drobnego tekstu. Na kafelkach wolno używać wyłącznie `#475569` lub ciemniejszego.

### Akcent

| Token | Wartość | Zastosowanie |
|:------|:--------|:-------------|
| `--accent` | `#2563EB` | Linki, główne działania i zaznaczenie |
| `--accent-strong` | `#1D4ED8` | Tekst na jasnych tłach akcentu i mocniejszy stan |
| `--accent-soft` | `#EFF6FF` | Delikatne tło akcentu |
| `--accent-soft-2` | `#DBEAFE` | Mocniejsze jasne tło akcentu |

Niebieski `#2563EB` ma 5,17:1 na bieli, 4,94:1 na tle aplikacji i 4,75:1 na `#EFF6FF`. Biel na przycisku `#2563EB` ma 5,17:1. Mocniejszy `#1D4ED8` ma 6,70:1 na bieli oraz 5,49:1 na `#DBEAFE`.

**Ważne ograniczenie:** `#2563EB` na `#DBEAFE` daje 4,24:1, czyli za mało dla tekstu. Na tle `#DBEAFE` stosuje się `#1D4ED8`.

### Barwy znaczeń

Zasada nadrzędna: ciemny odcień służy do **tekstu**, a jasny odcień tylko do **ikon, pierścieni i wykresów**. Dla ikon, pierścieni i wykresów wymagany próg wynosi 3:1, nie 4,5:1.

| Stan | Tekst i tło | Kontrast tekstu | Ikona, pierścień lub wykres |
|:-----|:------------|:----------------|:----------------------------|
| Dobrze | `#15803D` na `#DCFCE7` | 4,57:1; 4,79:1 na `#F0FDF4`; 5,02:1 na bieli | `#16A34A` |
| Uwaga | `#B45309` na `#FEF3C7` | 4,51:1 | `#D97706` |
| Źle | `#B91C1C` na `#FEE2E2` | 5,30:1 | `#DC2626` |

Stan zawsze opisuj także tekstem. Ikona lub kolor mogą go wspierać, lecz nie mogą go zastępować.

### Kolory odrzucone ze wzoru graficznego

Barwy użyte wprost na dostarczonych obrazach projektowych nie spełniają norm czytelności dla drobnego tekstu, dlatego zastąpiono je ciemniejszymi odcieniami tekstowymi.

- `#16A34A` ma 3,30:1 na bieli oraz 3,15:1 na `#F0FDF4`; jest dopuszczony wyłącznie jako ikona lub pierścień.
- `#D97706` ma 3,19:1 na bieli oraz 3,07:1 na `#FFFBEB`; jest dopuszczony wyłącznie jako ikona.
- `#DC2626` na `#FEF2F2` ma 4,41:1, nieznacznie poniżej progu; zastępuje go para `#B91C1C` na `#FEE2E2`.
- Biel na zieleni `#16A34A` ma 3,30:1. Jest dopuszczalna wyłącznie jako znak graficzny, na przykład symbol potwierdzenia, nigdy jako tekst.

### Typografia, kształt i głębia

Stos fontów: `"Segoe UI", system-ui, -apple-system, "Helvetica Neue", Arial, sans-serif`. Bez wyjątków. Hierarchię buduj rozmiarem i grubością, nie kolorem. Promienie: pola i przyciski `8px`, karty `12px`, plakietki `999px`. Odstępy opieraj na wielokrotnościach `4px`.

Cienie są lekkie i warstwowe, aby jedynie oddzielać kartę od tła. Nie zastępują obramowania i nie mogą dominować nad treścią.

## Komponenty

**Przycisk główny.** Tło `--accent`, biały tekst, promień `8px`, bez wersalików. Po najechaniu używa `--accent-strong`; po wciśnięciu zmniejsza się do 98 procent. Stan nieaktywny zawsze ma tekst wyjaśniający powód.

**Przycisk drugorzędny.** Tło `--surface`, tekst `--fg-mid`, obramowanie `--border-strong`. Po najechaniu tło `--surface-alt` i tekst `--fg`.

**Karta i kafelek.** Karta ma tło `--surface`, obramowanie `--border` i lekki cień. Kafelek lub wgłębienie ma tło `--surface-alt`; jego drobny tekst stosuje `--fg-mid` albo ciemniejszy, nigdy `--fg-muted`.

**Pasek komunikatu.** Używa jasnego tła stanu i pełnego zdania po polsku. Stan przekazuje tekst, a kolor i ikona tylko go wzmacniają.

**Brak danych.** Pokazuj znakiem myślnika `—`, nigdy zerem ani pustym miejscem.

**Linki.** Kolor `--accent`; podkreślenie może pojawiać się po najechaniu. Link musi pozostawać rozpoznawalny jako element interaktywny.

## Zasady

- Znaczenie nigdy nie jest przekazywane samym kolorem; zawsze towarzyszy mu tekst.
- Brak danych pokazujemy znakiem myślnika, nigdy zerem.
- Przejścia trwają 200 milisekund z wygaszaniem. Przesunięcia nie przekraczają dwóch pikseli, a wciśnięcie przycisku zmniejsza go do 98 procent.
- Obowiązuje obsługa ustawienia ograniczonego ruchu przez `@media (prefers-reduced-motion: reduce)`.
- Obramowanie zaznaczenia klawiaturą ma dwa piksele w barwie akcentu i odstęp dwóch pikseli: `outline: 2px solid var(--accent); outline-offset: 2px`. Stosuj `:focus-visible`.
- Zakazane są rozmycia tła i duże powierzchnie rozmyte, animacje wejścia oraz pulsowanie. Widok odświeża się samoczynnie co piętnaście sekund w trakcie pobierania danych, więc efekty te powodowałyby uporczywe migotanie.
- Cały styl mieszka wyłącznie w pliku `static/css/styles.css`.
- Zakazane są czcionki z sieci, reguły dociągające zasoby zewnętrzne oraz jakikolwiek kod wykonywany w przeglądarce.

## Dostępność

Minimalny kontrast tekstu wynosi `4,5:1`, a elementów sterujących, ikon, pierścieni, wykresów i obramowań `3:1`. Przy każdej nowej parze barw policz kontrast i dopisz wynik do tego dokumentu. Pole kliknięcia przycisku ma co najmniej `44px` wysokości. Zachowaj `lang="pl"` i sensowną hierarchię nagłówków.

## Anty-wzorce

Nie używaj wartości szesnastkowych wprost zamiast tokenów, koloru jako jedynego komunikatu, `#64748B` na `#F1F5F9`, `#2563EB` jako tekstu na `#DBEAFE`, białego tekstu na zieleni `#16A34A`, dużych ruchów po najechaniu, animacji sprężystych, pulsowania, rozmycia tła ani powielonego CSS w szablonach.

## Wariant odrzucony: motyw ciemny

Wariant ciemny nie został odrzucony z przyczyn technicznych. Użytkownik ocenił go jako niezgodny z oczekiwanym wyglądem, dlatego nie jest obowiązującym motywem. Poniższy zapis zachowujemy jako historię decyzji i źródło wcześniej policzonych kontrastów.

### Dawne powierzchnie i tekst

| Token | Wartość | Zastosowanie |
|:------|:--------|:-------------|
| `--bg` | `#0A0A0F` | Główne tło strony |
| `--bg-alt` | `#12121A` | Delikatnie wyniesione pasy i stopka |
| `--card` | `#1A1A24` | Tło kart i wydzielonych sekcji |
| `--fg` | `#FAFAFA` | Tekst główny |
| `--fg-muted` | `#A1A1AA` | Opisy, daty i etykiety |
| `--accent` | `#F59E0B` | Linki, działania i tło przycisku głównego |
| `--accent-fg` | `#0A0A0F` | Tekst na tle akcentu |

`#FAFAFA` ma 18,9:1 na `#0A0A0F`, 17,9:1 na `#12121A` i 16,5:1 na `#1A1A24`. `#A1A1AA` ma odpowiednio 7,7:1, 7,3:1 i 6,7:1. Amber `#F59E0B` ma odpowiednio 9,2:1, 8,7:1 i 8,0:1. Ciemny tekst na akcencie ma 9,2:1.

Biel na akcencie `#F59E0B` ma tylko **2,15:1** i była bezwzględnie zakazana; tekst na amber zawsze musiał być ciemny.

Odrzucony tekst drugorzędny `#71717A` dawał 4,09:1 na tle i 3,57:1 na karcie, dlatego w dawnym wariancie zastąpiono go `#A1A1AA`. Odrzucony akcent indygo `#5E6AD2` dawał jako tekst tylko 4,33:1.

### Dawne stany

| Token | Wartość | Na `#0A0A0F` | Na `#12121A` | Na `#1A1A24` |
|:------|:--------|:--------------|:--------------|:--------------|
| `--ok` | `#4ADE80` | 11,3:1 | 10,7:1 | 9,9:1 |
| `--warn` | `#FCD34D` | 13,7:1 | 12,9:1 | 12,0:1 |
| `--danger` | `#F87171` | 7,1:1 | 6,7:1 | 6,2:1 |

Pozostały dwie istotne pułapki: barwa ostrzeżenia wobec akcentu miała kontrast tylko 1,49:1, a barwa pozytywna wobec negatywnej 1,59:1. Dlatego amber oznaczał wyłącznie działanie, żółty wyłącznie ostrzeżenie, a każdy stan nadal wymagał tekstu.

### Dawne efekty

W ciemnym wariancie stosowano warstwowe cienie i włosowe obramowania. Zakazane pozostawały `backdrop-filter`, półprzezroczyste karty z rozmyciem tła, duże rozmyte kule świetlne, animacje wejścia i pulsowanie — widok odświeża się co 15 sekund podczas pobierania danych.
