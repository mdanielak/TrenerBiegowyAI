# System wizualny — Trener Biegowy

Dokument pełni podwójną rolę: jest instrukcją dla osoby lub agenta pracującego nad warstwą web
oraz zapisem podjętych decyzji wizualnych. Styl wywodzi się z estetyki „Minimalist Dark" —
ciemna paleta slate z ciepłym akcentem amber — przystosowanej do twardych ograniczeń tego
projektu. Wszystkie wartości kontrastu podane niżej są policzone według WCAG 2.1, nie
oszacowane, i dotyczą konkretnych par barw użytych w tym interfejsie.

## Rola

Projektujesz i utrzymujesz interfejs lokalnego asystenta treningu biegowego. Zanim napiszesz
jakikolwiek kod, zbuduj obraz obecnego stanu: przeczytaj szablon, który zmieniasz, i sprawdź,
jakie tokeny oraz klasy już istnieją. Nie wprowadzaj nowego wzorca, jeśli działający już jest.

Pamiętaj, kto korzysta z tej aplikacji. To jedna osoba nietechniczna, która o szóstej rano
sprawdza, czy ma dziś biegać. Czyta liczby dotyczące własnego zdrowia i podejmuje na ich
podstawie decyzję. Dlatego czytelność i jednoznaczność mają pierwszeństwo przed efektem
wizualnym — zawsze, bez wyjątku. Jeśli wybór estetyczny pogarsza odczyt danych, odrzuć go.

Zmiany opisuj krótko i po polsku, bez żargonu. Wyjaśniaj powód decyzji, nie tylko jej treść.

## Kontekst techniczny i granice nienaruszalne

Stos: FastAPI, szablony Jinja2, CSS wpisany w szablon. Nie ma tu Reacta, Tailwinda,
frameworka animacji ani kroku budowania. Nie dodawaj ich.

Zakazy wynikające z założeń projektu. Każdy chroni aplikację przed złożonością, która nie
opłaca się przy jednym użytkowniku na jednym komputerze:

- **Zero JavaScriptu.** Żadnych skryptów, atrybutów zdarzeń ani `<script>`.
- **Zero zasobów z sieci.** Bez CDN, bez fontów zewnętrznych, bez obrazków z adresów URL.
  Font to wyłącznie stos systemowy.
- **Brak `StaticFiles`.** Nie montujemy katalogu statycznego; CSS mieszka w szablonach.
- **Nigdy `|safe`.** Autoescaping Jinja pozostaje włączony wszędzie.
- **Jedna kolumna, maksymalnie 700 px**, wyśrodkowana. Bez układów wielokolumnowych
  i bez siatek „bento".
- **Kolor nigdy nie jest jedynym nośnikiem znaczenia.** Każdy stan ma też tekst.
- **Teksty po polsku**, bez skrótów i terminów technicznych w treści widocznej dla użytkownika.

Konsekwencja zakazu JavaScriptu: światło podążające za kursorem, paralaksa przy przewijaniu
i animacje wyzwalane widocznością elementu są niemożliwe. Nie próbuj ich obchodzić.

## Jedno źródło prawdy dla stylu

Trzy szablony — `today.html`, `week.html`, `job.html` — powielają dziś własne bloki CSS.
To się rozjedzie przy pierwszej zmianie palety. Ponieważ nie mamy katalogu statycznego,
wspólny styl trzymaj w częściowym szablonie `templates/_styles.html` i włączaj go przez
`{% include "_styles.html" %}` w sekcji `<head>`. Deklaracje specyficzne dla jednego widoku
mogą zostać w tym widoku, ale tokeny i komponenty wspólne — nigdy.

Tokeny zapisuj jako własne właściwości CSS w `:root`. Nie wklejaj wartości szesnastkowych
wprost w reguły. Dzięki temu dodanie jasnego motywu sprowadzi się później do jednego bloku
`@media (prefers-color-scheme: light)` zamiast przeglądania wszystkich szablonów.

## Tokeny

Motyw ciemny jest obecnie jedynym. Deklaruj `color-scheme: dark`.
Jasny motyw jako wybór użytkownika przyjdzie później — struktura tokenów ma to umożliwić
bez przepisywania reguł.

### Powierzchnie i tekst

Paleta opiera się na ciepłym slate, nie na czystej czerni. Każda warstwa jest nieco inna —
głębia powstaje z samej ciemności, nie z mocnych cieni.

| Token | Wartość | Zastosowanie |
|:------|:--------|:-------------|
| `--bg` | `#0A0A0F` | Główne tło strony |
| `--bg-alt` | `#12121A` | Delikatnie wyniesione pasy i stopka |
| `--card` | `#1A1A24` | Tło kart i wydzielonych sekcji |
| `--fg` | `#FAFAFA` | Tekst główny — 18,9:1 na tle, 16,5:1 na karcie |
| `--fg-muted` | `#A1A1AA` | Opisy, daty, etykiety — 7,7:1 na tle, 6,7:1 na karcie |
| `--border` | `rgba(255,255,255,0.08)` | Subtelne linie i krawędzie |
| `--border-hover` | `rgba(255,255,255,0.15)` | Krawędź po najechaniu |

Uwaga do pierwowzoru: „Minimalist Dark" podaje dla tekstu drugorzędnego `#71717A`, co daje
zaledwie **4,09:1** na tle i **3,57:1** na karcie, więc nie spełnia minimum dla tekstu.
Dlatego używamy `#A1A1AA`. Nie przywracaj ciemniejszej wartości.

### Akcent

| Token | Wartość | Zastosowanie |
|:------|:--------|:-------------|
| `--accent` | `#F59E0B` | Linki, tekst akcentowany, tło przycisku głównego |
| `--accent-fg` | `#0A0A0F` | Tekst **na** tle amber — wyłącznie ciemny |
| `--accent-glow` | `rgba(245,158,11,0.35)` | Poświata przycisku po najechaniu |
| `--accent-soft` | `rgba(245,158,11,0.12)` | Tło wyróżnionych plakietek |

Amber ma 9,2:1 na tle i 8,0:1 na karcie, więc nadaje się jednocześnie na tekst i na
wypełnienie przycisku — dzięki temu wystarcza jeden token akcentu.

Reguła bezwzględna: **na tle amber nigdy nie umieszczaj białego tekstu** — biel na `#F59E0B`
daje 2,15:1 i jest nieczytelna. Tekst na amber jest zawsze ciemny (`--accent-fg`, 9,2:1).

Druga reguła: amber oznacza **wyłącznie działanie** — przycisk, link, element interaktywny.
Nie używaj go dekoracyjnie ani do sygnalizowania stanu danych. Interfejs pozostaje
w zasadzie monochromatyczny; ciepły akcent ma być rzadki, bo z rzadkości bierze swoją siłę.

### Stany

Dotychczasowe kolory statusów pochodzą z jasnego motywu i na ciemnym tle są nieczytelne:
zielony `#17663E` daje 2,92:1, czerwony `#8A1C1C` zaledwie 2,20:1, pomarańczowy `#8A5A00`
tylko 3,44:1. Wszystkie trzy wymagają zamiany. Zastąp je wartościami poniżej i zaktualizuj
`job.html`, gdzie stare kolory są wpisane wprost.

| Token | Wartość | Na tle | Na karcie | Znaczenie |
|:------|:--------|:-------|:----------|:----------|
| `--ok` | `#4ADE80` | 11,3:1 | 9,9:1 | Gotowość, sukces zadania, dopasowany trening |
| `--warn` | `#FCD34D` | 13,7:1 | 12,0:1 | Dane nieaktualne, gotowość z zapasem, stan niepewny |
| `--danger` | `#F87171` | 7,1:1 | 6,2:1 | Brak gotowości, nieudana synchronizacja |

Dwie pułapki wynikające z policzonych wartości, obie wymagają dyscypliny:

Żółty ostrzegawczy i amber mają niemal tę samą jasność — wzajemny kontrast to tylko 1,49:1.
Rozróżnia je więc wyłącznie kontekst, dlatego trzymaj się podziału: amber pojawia się
na elementach interaktywnych, żółty ostrzegawczy tylko na paskach komunikatów i krawędziach
kart. Nigdy odwrotnie.

Zielony i czerwony również mają podobną jasność — 1,59:1 między sobą. Dla osoby
nierozróżniającej tych barw są praktycznie identyczne. To właśnie dlatego zasada
„kolor nigdy sam" jest nienaruszalna: stan zawsze opisuje też tekst.

Stan sygnalizuj obramowaniem lewej krawędzi karty w kolorze stanu oraz tekstową etykietą.
Tła stanów twórz jako półprzejrzystą warstwę barwy stanu nad powierzchnią, w granicach
10–15% krycia. Nie używaj jasnych wypełnień — na ciemnym motywie rażą.

### Typografia

Stos: `system-ui, -apple-system, "Segoe UI", sans-serif`. Bez wyjątków. Pierwowzór wskazuje
Space Grotesk i Inter, ale wymagałyby pobrania z sieci, co jest tu zakazane.

Skala pozostaje powściągliwa, bo widok jest wąski i gęsty informacyjnie: wynik gotowości
`2,6rem` o grubości 700, nagłówek strony `1,6rem`, nagłówki sekcji `1,1rem` grubości 600,
treść `1rem`, metadane `0,9rem`. Nagłówkom nadaj `letter-spacing: -0.02em` i ciasną
interlinię, treści `line-height: 1.6`. Hierarchię buduj rozmiarem i grubością, nie kolorem.

Nie stosuj gradientowych wypełnień tekstu ani wersalików.

### Promienie, odstępy, cienie

Promienie miękkie, lecz nieprzesadzone: pola i przyciski `8px`, karty `12px`,
większe sekcje `16px`, plakietki `999px`.

Odstępy opieraj na wielokrotnościach `4px`. Pierwowzór zakłada bardzo przestronne układy,
ale został zaprojektowany dla stron marketingowych — u nas widok ma być zwarty i czytelny
bez przewijania. Rozsądne wartości: wyściółka karty `18px`, przerwa między kafelkami `10px`,
odstęp nad nagłówkiem sekcji `28px`, wyściółka strony `28px 16px`.

Cienie zawsze warstwowe, nigdy jednowarstwowe. Na ciemnym tle samo rozmycie nie wystarcza,
więc pierwszą warstwą jest włosowe obramowanie:

```css
/* karta */
box-shadow: 0 0 0 1px rgba(255,255,255,0.08), 0 4px 12px rgba(0,0,0,0.35);
/* przycisk glowny po najechaniu */
box-shadow: 0 0 20px rgba(245,158,11,0.35);
```

## Efekty — zakres świadomie ograniczony

Przyjęta zasada: tylko efekty tanie w renderowaniu i spokojne w odbiorze.

Dozwolone:

- Delikatna ciepła aura u góry strony:
  `radial-gradient(ellipse at top, rgba(245,158,11,0.04) 0%, transparent 55%)`
- Warstwowe cienie i włosowe obramowania
- Poświata amber wokół przycisku po najechaniu — mały element, koszt znikomy
- Przejścia `200ms ease-out`
- Rozjaśnienie krawędzi i tła po najechaniu, przesunięcie najwyżej `2px`
- `scale(0.98)` na wciśnięciu przycisku

Zakazane, mimo obecności w pierwowzorze:

- `backdrop-filter` i półprzejrzyste karty z rozmyciem tła — kosztowne przy każdym
  renderowaniu; karty mają tło pełne (`--card`)
- Duże rozmyte kule świetlne i animowane plamy
- Nakładka szumu — przy 2% krycia niezauważalna, a dodaje złożoności
- Animacje wejścia elementów

Ostatni zakaz ma powód praktyczny, nie estetyczny. W trakcie synchronizacji widok dnia
przeładowuje się co 15 sekund przez `meta refresh`. Każda animacja wejścia odpalałaby się
od nowa przy każdym przeładowaniu, dając uporczywe migotanie dokładnie wtedy, gdy użytkownik
czeka i patrzy na ekran. Strona musi wtedy wyglądać stabilnie. Z tego samego powodu nie
animuj paska stanu synchronizacji ani niczego, co pojawia się w trakcie trwania zadania.

## Komponenty

**Przycisk główny** („Zsynchronizuj dane"). Tło `--accent`, tekst `--accent-fg`,
promień `8px`, wyściółka `11px 20px`, grubość 600, bez wersalików. Po najechaniu
`filter: brightness(1.08)` i poświata amber. Na wciśnięciu `scale(0.98)`.
Stan nieaktywny: krycie `0.5`, `cursor: not-allowed`, bez poświaty — i zawsze wraz
z tekstem paska wyjaśniającym powód, bo sam wyszarzony przycisk nie informuje,
dlaczego nie działa.

**Przycisk drugorzędny.** Tło przezroczyste, tekst `--fg`, obramowanie `--border-hover`.
Po najechaniu tło `rgba(255,255,255,0.05)` i jaśniejsza krawędź.

**Karta.** Tło `--card`, promień `12px`, wyściółka `18px`, cień warstwowy.
Karta gotowości dodatkowo z obramowaniem lewej krawędzi `5px` w kolorze stanu.

**Pasek komunikatu.** Tło w barwie stanu przy 12% krycia, lewa krawędź `4px` w pełnym
kolorze stanu, tekst `--fg`. Treść zawsze pełnym zdaniem po polsku. Jeśli istnieje strona
szczegółów, dołącz link „Szczegóły".

**Kafelki sygnałów.** Siatka dwukolumnowa, jedna kolumna poniżej `480px`. Tło `--bg-alt`,
etykieta w `--fg-muted` rozmiarem `0,85rem`, wartość `1,2rem` w `--fg`.
Brak danych pokazuj jako `—`, nigdy jako zero ani puste miejsce.

**Linki.** Kolor `--accent`, podkreślenie z `text-underline-offset: 2px`.
Nie usuwaj podkreśleń — to dla tej osoby jedyny sygnał, że coś jest klikalne.

## Dostępność

Obowiązkowo, nie opcjonalnie:

- Widoczny pierścień fokusu na każdym elemencie interaktywnym:
  `outline: 2px solid var(--accent); outline-offset: 2px`. Używaj `:focus-visible`.
  Nigdy nie zeruj `outline` bez podania zamiennika.
- Minimalny kontrast tekstu `4,5:1`; elementy sterujące i obramowania `3:1`.
  Przy nowym kolorze policz kontrast, nie zgaduj.
- Pole kliknięcia przycisku co najmniej `44px` wysokości.
- Blok `@media (prefers-reduced-motion: reduce)` wyłączający wszystkie przejścia.
- Stan nigdy wyłącznie kolorem — zawsze z towarzyszącym tekstem.
- Zachowaj `lang="pl"` oraz sensowną hierarchię nagłówków.

## Czego nie przenieśliśmy z pierwowzorów i dlaczego

Uczciwy zapis odrzuceń, by nie wracać do nich bez potrzeby. Światło podążające za kursorem,
paralaksa i animacje wyzwalane przewijaniem wymagają JavaScriptu. Fonty Space Grotesk, Inter
i JetBrains Mono wymagają pobierania z sieci. Klasy Tailwinda nie mają zastosowania wobec
braku kroku budowania. Siatki „bento" i układy wielokolumnowe przeczą zasadzie jednej wąskiej
kolumny. Szkło z `backdrop-filter`, wielkie rozmyte kule i nakładka szumu kosztują zbyt wiele
przy widoku odświeżanym co 15 sekund, a dają efekt niewspółmierny do ceny. Bardzo przestronne
odstępy z pierwowzoru pasują stronom marketingowym, nie gęstemu widokowi danych.

Z drugiego wariantu stylu — „Linear / Modern" z akcentem indygo `#5E6AD2` — zrezygnowaliśmy
świadomie: ten akcent daje jako tekst tylko 4,33:1, więc wymagałby drugiego, jaśniejszego
tokenu na linki. Amber spełnia obie role naraz.

## Anty-wzorce

Czysta czerń `#000000` i czysta biel jako tekst. Biały tekst na tle amber. Amber użyty
do oznaczania stanu danych zamiast działania. Płaskie jednowarstwowe cienie. Wyraziste
obramowania — mają być prawie niewidoczne, w granicach 8–15% krycia bieli. Duże ruchy po
najechaniu powyżej `2px`. Animacje sprężyste i odbijające. Wartości szesnastkowe wpisane
wprost zamiast tokenów. Powielony CSS w wielu szablonach. Komunikat niosący znaczenie
wyłącznie kolorem. Wersaliki i rozstrzelone napisy.

## Weryfikacja zmiany wizualnej

Po każdej zmianie w szablonach:

1. `python -m pytest -q` — testy sprawdzają teksty i strukturę odpowiedzi, więc zmiana
   treści komunikatu wymaga aktualizacji testu. Nie zmieniaj tekstów widocznych dla
   użytkownika bez potrzeby.
2. `python -m trainer privacy-check`
3. Potwierdź brak `|safe`, brak `<script>` i brak odwołań do adresów zewnętrznych
   w szablonach.
4. Sprawdź widok w przeglądarce pod `http://127.0.0.1:8000` w trzech stanach: spokoju,
   trwającej synchronizacji oraz blokady po świeżej synchronizacji. Serwer działa bez
   przeładowywania kodu, więc po zmianie wymaga restartu.
5. Zwęź szerokość okna do około 380 px i sprawdź, czy układ pozostaje czytelny.
6. Przy każdej nowej parze barw policz kontrast i dopisz wynik do tabeli w tym dokumencie.
