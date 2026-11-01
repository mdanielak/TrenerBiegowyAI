# Wygląd na telefonie — do poprawy później

Spisane z audytu wizualnego (Playwright, headless Firefox, ekran 390×844, kopia testowa ze zmyślonymi danymi, 1.11.2026).
W wydaniu z dopracowanym desktopem celowo **bez zmian pod telefon**. Kolejność: od najpoważniejszego.

## 1. Plan i Statystyki przewijają się w bok (poważne)
- Strona ma 702 px szerokości przy ekranie 390 px.
- Przyczyna: wykres w `.chart-scroll` ma na telefonie `min-width: 640px` (`static/css/styles.css`, reguła w `@media (max-width: 520px)`),
  a kontenery nad nim (`.stack`, `.card`) nie mają `min-width: 0`, więc ich minimalna szerokość rośnie do szerokości wykresu
  i rozpycha `main`. Sprawdzone: ukrycie `.chart-scroll` przywraca 390 px.
- Poprawka: `min-width: 0` (albo `grid-template-columns: minmax(0, 1fr)`) w łańcuchu `main → .stack → .card`, żeby wykres
  przewijał się tylko w swoim pudełku. Test: `document.documentElement.scrollWidth === innerWidth` na `/plan` i `/stats`.

## 2. Za dużo nad treścią
- Zanim pojawi się nagłówek strony, ok. 200 px zajmują: ramka AI, przycisk menu i trzy duże przyciski motywu (Auto / Jasny / Ciemny).
- Propozycja: przełącznik motywu zwinięty do jednej małej ikony albo przeniesiony do Ustawień; ramka AI jako kropka przy logo.

## 3. Strona główna
- Pierścień oceny zajmuje prawie cały pierwszy ekran (~300 px karty).
- Propozycja: pierścień ~96–110 px obok werdyktu w jednym rzędzie (jak na Analizie), sygnały wyżej.

## 4. Cel
- Ilustracja mety stoi jako osobny duży blok między tytułem a treścią.
- Propozycja: ukryć ilustrację poniżej ~520 px albo zmniejszyć do ikony przy tytule.

## 5. Drobne
- Kafelki podsumowania Planu po dwa w rzędzie są ciasne przy dłuższych jednostkach („w tygodniu”).
- Wykresy sygnałów w Statystykach: podpisy dat pod osią przy 390 px stykają się.

## Jak sprawdzić po poprawkach
Playwright headless, szerokość 390: `/`, `/plan`, `/stats`, `/goal`, `/settings`, `/journal`, `/analysis`;
dla każdej strony `scrollWidth === 390` i obejrzany zrzut całej strony.
